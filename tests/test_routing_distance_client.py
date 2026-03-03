"""
Tests for routing_distance_client.py

All HTTP calls are mocked — no real routing service is contacted.
"""

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import requests

from gis_bootcamp.routing_distance_client import route_distances


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_session(responses: list) -> MagicMock:
    """
    Build a mock requests.Session whose get() returns items from `responses`
    in sequence. Each element is either:
      - a dict  → success response with that OSRM payload
      - None    → no-route (code != Ok)
      - an Exception subclass → raises on get()
    """
    session = MagicMock()
    call_iter = iter(responses)

    def _get(url, timeout=10):
        val = next(call_iter)
        if isinstance(val, type) and issubclass(val, Exception):
            raise val("Simulated error")
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if val is None:
            resp.json.return_value = {"code": "NoRoute", "routes": []}
        else:
            resp.json.return_value = val
        return resp

    session.get.side_effect = _get
    return session


def _osrm_ok(distance_m: float = 12500.0, duration_s: float = 600.0) -> dict:
    return {
        "code": "Ok",
        "routes": [{"distance": distance_m, "duration": duration_s}],
    }


def _write_csv(path: str, rows: list[dict]) -> str:
    if not rows:
        return path
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _od_row(olat=51.5, olon=-0.1, dlat=48.8, dlon=2.3, **extra):
    return {"origin_lat": olat, "origin_lon": olon, "dest_lat": dlat, "dest_lon": dlon, **extra}


class TestRoutingDistanceClient(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_all_success_csv_output(self):
        """All rows succeed; output CSV is created with correct counts."""
        src = _write_csv(self._p("od.csv"), [_od_row(), _od_row()])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok(), _osrm_ok()])

        result = route_distances(src, out, _session=session)

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["success"], 2)
        self.assertEqual(result["no_route"], 0)
        self.assertEqual(result["error"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertTrue(Path(out).exists())

    def test_distance_and_duration_columns_correct(self):
        """distance_m, distance_km, duration_s, duration_min computed correctly."""
        src = _write_csv(self._p("od.csv"), [_od_row()])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok(distance_m=10000.0, duration_s=720.0)])

        route_distances(src, out, _session=session)

        df = pd.read_csv(out)
        self.assertAlmostEqual(df["distance_m"].iloc[0], 10000.0)
        self.assertAlmostEqual(df["distance_km"].iloc[0], 10.0)
        self.assertAlmostEqual(df["duration_s"].iloc[0], 720.0)
        self.assertAlmostEqual(df["duration_min"].iloc[0], 12.0)

    def test_routing_status_success(self):
        """routing_status is 'success' for successful rows."""
        src = _write_csv(self._p("od.csv"), [_od_row()])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok()])

        route_distances(src, out, _session=session)

        df = pd.read_csv(out)
        self.assertEqual(df["routing_status"].iloc[0], "success")

    def test_no_route_rows_counted_and_status_set(self):
        """Rows with no route get None distances and 'no_route' status."""
        src = _write_csv(self._p("od.csv"), [_od_row(), _od_row()])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok(), None])

        result = route_distances(src, out, _session=session)

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["no_route"], 1)
        df = pd.read_csv(out)
        self.assertEqual(df["routing_status"].iloc[1], "no_route")
        self.assertTrue(pd.isna(df["distance_m"].iloc[1]))

    def test_timeout_counted_as_error(self):
        """Timeout exceptions are caught and counted as 'error'."""
        src = _write_csv(self._p("od.csv"), [_od_row()])
        out = self._p("out.csv")
        session = _mock_session([requests.exceptions.Timeout])

        result = route_distances(src, out, _session=session)

        self.assertEqual(result["error"], 1)
        self.assertEqual(result["success"], 0)
        df = pd.read_csv(out)
        self.assertEqual(df["routing_status"].iloc[0], "error")

    def test_connection_error_counted_as_error(self):
        """ConnectionError is caught and counted as 'error'."""
        src = _write_csv(self._p("od.csv"), [_od_row()])
        out = self._p("out.csv")
        session = _mock_session([requests.exceptions.ConnectionError])

        result = route_distances(src, out, _session=session)

        self.assertEqual(result["error"], 1)

    def test_missing_coordinates_skipped(self):
        """Rows with NaN coordinates are counted as 'skipped'."""
        src = _write_csv(self._p("od.csv"), [
            _od_row(),
            {"origin_lat": None, "origin_lon": -0.1, "dest_lat": 48.8, "dest_lon": 2.3},
        ])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok()])

        result = route_distances(src, out, _session=session)

        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["success"], 1)

    def test_original_columns_preserved(self):
        """Extra CSV columns (e.g. 'trip_id') are preserved in output."""
        src = _write_csv(self._p("od.csv"), [_od_row(trip_id="T001")])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok()])

        route_distances(src, out, _session=session)

        df = pd.read_csv(out)
        self.assertIn("trip_id", df.columns)
        self.assertEqual(df["trip_id"].iloc[0], "T001")

    def test_json_output_format(self):
        """JSON output format produces a parseable file with expected fields."""
        src = _write_csv(self._p("od.csv"), [_od_row()])
        out = self._p("out.json")
        session = _mock_session([_osrm_ok()])

        route_distances(src, out, output_format="json", _session=session)

        self.assertTrue(Path(out).exists())
        with open(out) as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertIn("distance_m", data[0])
        self.assertIn("routing_status", data[0])

    def test_output_directory_auto_created(self):
        """Nested output directory is created automatically."""
        src = _write_csv(self._p("od.csv"), [_od_row()])
        out = self._p("sub/nested/out.csv")
        session = _mock_session([_osrm_ok()])

        route_distances(src, out, _session=session)

        self.assertTrue(Path(out).exists())

    def test_result_dict_structure(self):
        """Result dict has all expected keys."""
        src = _write_csv(self._p("od.csv"), [_od_row()])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok()])

        result = route_distances(src, out, _session=session)

        expected = {"output_path", "total", "success", "no_route", "error", "skipped"}
        self.assertEqual(expected, set(result.keys()))

    def test_custom_column_names(self):
        """Custom origin/destination column names are respected."""
        src = _write_csv(self._p("od.csv"), [
            {"from_lat": 51.5, "from_lon": -0.1, "to_lat": 48.8, "to_lon": 2.3},
        ])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok()])

        result = route_distances(
            src, out,
            origin_lat_col="from_lat", origin_lon_col="from_lon",
            dest_lat_col="to_lat", dest_lon_col="to_lon",
            _session=session,
        )

        self.assertEqual(result["success"], 1)

    def test_mixed_statuses_all_counted(self):
        """Mix of success, no_route, error, and skipped all counted correctly."""
        src = _write_csv(self._p("od.csv"), [
            _od_row(),                                                                 # success
            _od_row(),                                                                 # no_route
            _od_row(),                                                                 # error
            {"origin_lat": None, "origin_lon": -0.1, "dest_lat": 48.8, "dest_lon": 2.3},  # skipped
        ])
        out = self._p("out.csv")
        session = _mock_session([
            _osrm_ok(),
            None,
            requests.exceptions.Timeout,
        ])

        result = route_distances(src, out, _session=session)

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["no_route"], 1)
        self.assertEqual(result["error"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["total"], 4)

    def test_feature_count_in_output_matches_input(self):
        """Output CSV has the same number of rows as input."""
        n = 5
        src = _write_csv(self._p("od.csv"), [_od_row() for _ in range(n)])
        out = self._p("out.csv")
        session = _mock_session([_osrm_ok() for _ in range(n)])

        result = route_distances(src, out, _session=session)

        self.assertEqual(result["total"], n)
        df = pd.read_csv(out)
        self.assertEqual(len(df), n)

    # ------------------------------------------------------------------
    # Error tests
    # ------------------------------------------------------------------

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised for non-existent input CSV."""
        with self.assertRaises(FileNotFoundError):
            route_distances("no_such.csv", self._p("out.csv"))

    def test_empty_csv_raises_value_error(self):
        """ValueError raised for empty CSV (header only)."""
        src = self._p("empty.csv")
        with open(src, "w") as f:
            f.write("origin_lat,origin_lon,dest_lat,dest_lon\n")
        with self.assertRaises(ValueError):
            route_distances(src, self._p("out.csv"))

    def test_missing_column_raises_value_error(self):
        """ValueError raised when required coordinate columns are missing."""
        src = _write_csv(self._p("od.csv"), [{"origin_lat": 51.5, "origin_lon": -0.1}])
        with self.assertRaises(ValueError):
            route_distances(src, self._p("out.csv"))


if __name__ == "__main__":
    unittest.main()
