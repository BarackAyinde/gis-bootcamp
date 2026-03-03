"""
Tests for batch_geocoder.py

All geocoding calls are mocked — no real HTTP requests are made.
"""

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd

from gis_bootcamp.batch_geocoder import batch_geocode


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_location(lat: float, lon: float, address: str = "Mocked Address"):
    loc = MagicMock()
    loc.latitude = lat
    loc.longitude = lon
    loc.address = address
    return loc


def _always_succeed(n_rows: int, lat: float = 40.7, lon: float = -74.0):
    """Return a geocode callable that always succeeds."""
    def geocode(address, timeout=10):
        return _mock_location(lat, lon, f"Matched: {address}")
    return geocode


def _always_fail():
    """Return a geocode callable that always raises."""
    def geocode(address, timeout=10):
        raise ConnectionError("Simulated network failure")
    return geocode


def _always_none():
    """Return a geocode callable that always returns None (not found)."""
    def geocode(address, timeout=10):
        return None
    return geocode


def _mixed(results: list):
    """
    Return a geocode callable that yields a sequence of results.
    Each element is either a mock location or None or an exception class.
    """
    results_iter = iter(results)

    def geocode(address, timeout=10):
        val = next(results_iter)
        if isinstance(val, type) and issubclass(val, Exception):
            raise val("Simulated error")
        return val

    return geocode


# ---------------------------------------------------------------------------
# CSV fixture helpers
# ---------------------------------------------------------------------------

def _write_csv(path: str, rows: list[dict], fieldnames: list[str] | None = None) -> str:
    if fieldnames is None and rows:
        fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames or [])
        writer.writeheader()
        writer.writerows(rows)
    return path


class TestBatchGeocoder(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_all_success_gpkg(self):
        """All rows geocoded successfully; output is a valid GPKG."""
        src = _write_csv(self._p("addrs.csv"), [
            {"address": "London, UK"},
            {"address": "Paris, France"},
            {"address": "Berlin, Germany"},
        ])
        out = self._p("out.gpkg")

        result = batch_geocode(src, out, _geocoder=_always_succeed(3))

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["success"], 3)
        self.assertEqual(result["not_found"], 0)
        self.assertEqual(result["error"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertTrue(Path(out).exists())

    def test_all_success_parquet(self):
        """GeoParquet output format works correctly."""
        src = _write_csv(self._p("addrs.csv"), [
            {"address": "New York, USA"},
            {"address": "Tokyo, Japan"},
        ])
        out = self._p("out.parquet")

        result = batch_geocode(src, out, output_format="parquet", _geocoder=_always_succeed(2))

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["success"], 2)
        gdf = gpd.read_parquet(out)
        self.assertEqual(len(gdf), 2)

    def test_point_geometries_set_for_successful_rows(self):
        """Rows that geocode successfully have Point geometry."""
        src = _write_csv(self._p("addrs.csv"), [
            {"address": "Sydney, Australia"},
        ])
        out = self._p("out.gpkg")

        batch_geocode(src, out, _geocoder=_always_succeed(1, lat=-33.8, lon=151.2))

        gdf = gpd.read_file(out)
        self.assertFalse(gdf.geometry.iloc[0].is_empty)
        self.assertAlmostEqual(gdf.geometry.iloc[0].x, 151.2, places=1)
        self.assertAlmostEqual(gdf.geometry.iloc[0].y, -33.8, places=1)

    def test_original_attributes_preserved(self):
        """Non-address columns are preserved in output."""
        src = _write_csv(self._p("addrs.csv"), [
            {"name": "HQ", "address": "London, UK", "region": "EMEA"},
        ])
        out = self._p("out.gpkg")

        batch_geocode(src, out, _geocoder=_always_succeed(1))

        gdf = gpd.read_file(out)
        self.assertIn("name", gdf.columns)
        self.assertIn("region", gdf.columns)
        self.assertEqual(gdf["name"].iloc[0], "HQ")

    def test_status_columns_added(self):
        """geocode_status and geocode_matched_address columns are in output."""
        src = _write_csv(self._p("addrs.csv"), [{"address": "Rome, Italy"}])
        out = self._p("out.gpkg")

        batch_geocode(src, out, _geocoder=_always_succeed(1))

        gdf = gpd.read_file(out)
        self.assertIn("geocode_status", gdf.columns)
        self.assertIn("geocode_matched_address", gdf.columns)
        self.assertEqual(gdf["geocode_status"].iloc[0], "success")

    def test_not_found_rows_get_null_geometry(self):
        """Rows that return None from geocoder have null geometry and not_found status."""
        src = _write_csv(self._p("addrs.csv"), [
            {"address": "Completely Made Up Address 99999"},
        ])
        out = self._p("out.gpkg")

        result = batch_geocode(src, out, _geocoder=_always_none())

        self.assertEqual(result["not_found"], 1)
        self.assertEqual(result["success"], 0)
        gdf = gpd.read_file(out)
        self.assertTrue(gdf.geometry.iloc[0] is None or gdf.geometry.iloc[0].is_empty or pd.isna(gdf.geometry.iloc[0]))
        self.assertEqual(gdf["geocode_status"].iloc[0], "not_found")

    def test_empty_address_rows_are_skipped(self):
        """Rows with empty or NaN address are counted as skipped."""
        src = _write_csv(self._p("addrs.csv"), [
            {"address": "London, UK"},
            {"address": ""},
            {"address": "Paris, France"},
        ])
        out = self._p("out.gpkg")

        result = batch_geocode(src, out, _geocoder=_always_succeed(3))

        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["success"], 2)
        self.assertEqual(result["total"], 3)

    def test_error_rows_tracked_and_do_not_crash(self):
        """Transient geocoding errors are caught, logged, and counted."""
        src = _write_csv(self._p("addrs.csv"), [
            {"address": "London, UK"},
            {"address": "Bad Address"},
        ])
        out = self._p("out.gpkg")

        # First succeeds, second always raises
        call_count = {"n": 0}
        def mixed_geocoder(address, timeout=10):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _mock_location(51.5, -0.1)
            raise ConnectionError("Network failure")

        result = batch_geocode(src, out, max_retries=2, _geocoder=mixed_geocoder)

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["error"], 1)
        self.assertTrue(Path(out).exists())

    def test_output_directory_auto_created(self):
        """Nested output directory is created automatically."""
        src = _write_csv(self._p("addrs.csv"), [{"address": "London"}])
        out = self._p("sub/nested/out.gpkg")

        batch_geocode(src, out, _geocoder=_always_succeed(1))

        self.assertTrue(Path(out).exists())

    def test_result_dict_structure(self):
        """Result dict has all expected keys."""
        src = _write_csv(self._p("addrs.csv"), [{"address": "London"}])
        out = self._p("out.gpkg")

        result = batch_geocode(src, out, _geocoder=_always_succeed(1))

        expected = {"output_path", "total", "success", "not_found", "error", "skipped"}
        self.assertEqual(expected, set(result.keys()))

    def test_custom_address_column(self):
        """Custom address_column name is read correctly."""
        src = _write_csv(self._p("addrs.csv"), [
            {"location": "Madrid, Spain"},
            {"location": "Rome, Italy"},
        ])
        out = self._p("out.gpkg")

        result = batch_geocode(
            src, out, address_column="location", _geocoder=_always_succeed(2)
        )

        self.assertEqual(result["success"], 2)

    def test_crs_is_epsg4326(self):
        """Output dataset CRS is EPSG:4326."""
        src = _write_csv(self._p("addrs.csv"), [{"address": "London"}])
        out = self._p("out.gpkg")

        batch_geocode(src, out, _geocoder=_always_succeed(1))

        gdf = gpd.read_file(out)
        self.assertEqual(gdf.crs.to_epsg(), 4326)

    def test_mixed_success_not_found_error(self):
        """Mix of success, not_found, and error rows all counted correctly."""
        src = _write_csv(self._p("addrs.csv"), [
            {"address": "London"},   # success
            {"address": "Nowhere"},  # not_found
            {"address": "Bad"},      # error
        ])
        out = self._p("out.gpkg")

        seq = [
            _mock_location(51.5, -0.1),  # success
            None,                          # not_found
            ConnectionError,               # error
        ]
        result = batch_geocode(src, out, max_retries=1, _geocoder=_mixed(seq))

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["not_found"], 1)
        self.assertEqual(result["error"], 1)
        self.assertEqual(result["total"], 3)

    # ------------------------------------------------------------------
    # Error tests
    # ------------------------------------------------------------------

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised for non-existent CSV."""
        with self.assertRaises(FileNotFoundError):
            batch_geocode("no_such.csv", self._p("out.gpkg"), _geocoder=_always_succeed(0))

    def test_empty_csv_raises_value_error(self):
        """ValueError raised for empty CSV (header only)."""
        src = self._p("empty.csv")
        with open(src, "w") as f:
            f.write("address\n")  # header only, no data rows

        with self.assertRaises(ValueError):
            batch_geocode(src, self._p("out.gpkg"), _geocoder=_always_succeed(0))

    def test_missing_address_column_raises_value_error(self):
        """ValueError raised when address_column not in CSV."""
        src = _write_csv(self._p("addrs.csv"), [{"location": "London"}])

        with self.assertRaises(ValueError):
            batch_geocode(
                src, self._p("out.gpkg"),
                address_column="address",  # column doesn't exist
                _geocoder=_always_succeed(1),
            )


if __name__ == "__main__":
    unittest.main()
