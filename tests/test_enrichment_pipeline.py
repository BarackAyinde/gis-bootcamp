"""
Tests for enrichment_pipeline.py

Uses synthetic files written to temp directories.
Geocoding is fully mocked — no real HTTP calls required.
"""

import csv
import os
import tempfile
import types
import unittest
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import geopandas as gpd
from shapely.geometry import Point, box

from gis_bootcamp.enrichment_pipeline import run_enrichment_pipeline

CRS = "EPSG:4326"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path: str, rows: list[dict]) -> str:
    """Write a list of dicts to a CSV file."""
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_points(path: str, coords: list[tuple], crs: str = CRS) -> str:
    """Write a points GeoPackage."""
    gdf = gpd.GeoDataFrame(
        {"id": range(len(coords))},
        geometry=[Point(x, y) for x, y in coords],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _write_polygons(path: str, boxes: list[tuple], labels: list[str], crs: str = CRS) -> str:
    """Write a polygon GeoPackage."""
    gdf = gpd.GeoDataFrame(
        {"region": labels},
        geometry=[box(*b) for b in boxes],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _mock_geocoder(address, timeout=10):
    """Always returns a point near (0.5, 0.5)."""
    return types.SimpleNamespace(
        latitude=0.5,
        longitude=0.5,
        address=f"Geocoded: {address}",
    )


def _make_address_csv(path: str, n: int = 5) -> str:
    rows = [{"name": f"Place {i}", "address": f"{i} Main St"} for i in range(n)]
    return _write_csv(path, rows)


class TestEnrichmentPipeline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Stage 1: Geocode
    # ------------------------------------------------------------------

    def test_geocode_stage_creates_points_file(self):
        """Geocode stage produces a points.gpkg in the output directory."""
        src = _make_address_csv(self._p("addr.csv"))
        out = self._p("out")

        result = run_enrichment_pipeline(
            src, out, geocode_column="address", _geocoder=_mock_geocoder
        )

        self.assertIn("geocode", result["stages_run"])
        self.assertTrue(Path(result["enriched_path"]).exists())

    def test_geocode_stats_populated(self):
        """geocode_stats is a dict when the geocode stage runs."""
        src = _make_address_csv(self._p("addr.csv"))
        out = self._p("out")

        result = run_enrichment_pipeline(
            src, out, geocode_column="address", _geocoder=_mock_geocoder
        )

        self.assertIsNotNone(result["geocode_stats"])
        self.assertIn("total", result["geocode_stats"])
        self.assertIn("success", result["geocode_stats"])

    def test_geocode_point_count_matches_success(self):
        """point_count equals the number of successfully geocoded rows."""
        src = _make_address_csv(self._p("addr.csv"), n=4)
        out = self._p("out")

        result = run_enrichment_pipeline(
            src, out, geocode_column="address", _geocoder=_mock_geocoder
        )

        self.assertEqual(result["point_count"], result["geocode_stats"]["success"])

    # ------------------------------------------------------------------
    # Stage 2: Nearest-feature lookup
    # ------------------------------------------------------------------

    def test_nearest_feature_stage_enriches_points(self):
        """nearest_feature stage adds reference attributes to each point."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["ZoneA"])
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, reference_path=ref)

        self.assertIn("nearest_feature", result["stages_run"])
        gdf = gpd.read_file(result["enriched_path"])
        self.assertIn("region", gdf.columns)

    def test_lookup_stats_populated(self):
        """lookup_stats is a dict when the nearest_feature stage runs."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["A"])
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, reference_path=ref)

        self.assertIsNotNone(result["lookup_stats"])
        self.assertIn("matched", result["lookup_stats"])

    # ------------------------------------------------------------------
    # Stage 3: Density analysis
    # ------------------------------------------------------------------

    def test_density_raster_stage_creates_tif(self):
        """Density raster stage writes a .tif file."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (0.6, 0.6), (0.4, 0.4)])
        out = self._p("out")

        result = run_enrichment_pipeline(
            pts, out, density_cell_size=1.0, density_output_type="raster"
        )

        self.assertIn("density", result["stages_run"])
        self.assertTrue(Path(out, "density.tif").exists())

    def test_density_vector_stage_creates_gpkg(self):
        """Density vector stage writes a .gpkg file."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (0.6, 0.6), (0.4, 0.4)])
        out = self._p("out")

        result = run_enrichment_pipeline(
            pts, out, density_cell_size=1.0, density_output_type="vector"
        )

        self.assertIn("density", result["stages_run"])
        self.assertTrue(Path(out, "density.gpkg").exists())

    def test_density_stats_populated(self):
        """density_stats is a dict when the density stage runs."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (0.6, 0.6)])
        out = self._p("out")

        result = run_enrichment_pipeline(
            pts, out, density_cell_size=1.0
        )

        self.assertIsNotNone(result["density_stats"])
        self.assertIn("hotspot_cells", result["density_stats"])

    # ------------------------------------------------------------------
    # Stage 4: Render map
    # ------------------------------------------------------------------

    def test_render_stage_creates_map_png(self):
        """Render stage writes a map.png in the output directory."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, render=True)

        self.assertIn("render", result["stages_run"])
        self.assertTrue(Path(result["map_path"]).exists())

    def test_map_path_in_result(self):
        """map_path points to an existing file when render stage runs."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, render=True)

        self.assertIsNotNone(result["map_path"])
        self.assertTrue(Path(result["map_path"]).exists())

    def test_render_with_reference_layer(self):
        """Render stage includes reference layer in map when reference_path is set."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["A"])
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, reference_path=ref, render=True)

        self.assertTrue(Path(result["map_path"]).exists())

    # ------------------------------------------------------------------
    # Multi-stage combinations
    # ------------------------------------------------------------------

    def test_geocode_then_nearest_feature(self):
        """Geocode → nearest-feature stages run in sequence."""
        src = _make_address_csv(self._p("addr.csv"), n=3)
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["RegionA"])
        out = self._p("out")

        result = run_enrichment_pipeline(
            src, out,
            geocode_column="address",
            reference_path=ref,
            _geocoder=_mock_geocoder,
        )

        self.assertIn("geocode", result["stages_run"])
        self.assertIn("nearest_feature", result["stages_run"])
        gdf = gpd.read_file(result["enriched_path"])
        self.assertIn("region", gdf.columns)

    def test_all_stages(self):
        """All four stages run and produce expected outputs."""
        src = _make_address_csv(self._p("addr.csv"), n=4)
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["Zone1"])
        out = self._p("out")

        result = run_enrichment_pipeline(
            src, out,
            geocode_column="address",
            reference_path=ref,
            density_cell_size=1.0,
            density_output_type="vector",   # avoid KDE singularity: geocoder returns identical coords
            render=True,
            map_title="Test Pipeline Map",
            _geocoder=_mock_geocoder,
        )

        self.assertEqual(result["stages_run"], ["geocode", "nearest_feature", "density", "render"])
        self.assertTrue(Path(result["enriched_path"]).exists())
        self.assertTrue(Path(out, "density.gpkg").exists())
        self.assertTrue(Path(result["map_path"]).exists())

    # ------------------------------------------------------------------
    # Result dict
    # ------------------------------------------------------------------

    def test_result_dict_structure(self):
        """Result dict has all expected keys."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, render=True)

        expected = {
            "output_dir", "stages_run", "enriched_path", "point_count",
            "geocode_stats", "lookup_stats", "density_stats", "map_path",
        }
        self.assertEqual(expected, set(result.keys()))

    def test_point_count_in_result(self):
        """point_count matches the actual feature count in the enriched output."""
        coords = [(float(i) * 0.1, float(i) * 0.1) for i in range(6)]
        pts = _write_points(self._p("pts.gpkg"), coords)
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, render=True)

        self.assertEqual(result["point_count"], 6)

    def test_stages_run_reflects_executed_stages(self):
        """stages_run lists exactly the stages that were executed."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["A"])
        out = self._p("out")

        # Use vector density to avoid KDE singularity with few points
        result = run_enrichment_pipeline(
            pts, out, reference_path=ref,
            density_cell_size=1.0, density_output_type="vector",
        )

        self.assertEqual(result["stages_run"], ["nearest_feature", "density"])

    def test_non_executed_stats_are_none(self):
        """Stats for stages that did not run are None."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        out = self._p("out")

        result = run_enrichment_pipeline(pts, out, render=True)

        self.assertIsNone(result["geocode_stats"])
        self.assertIsNone(result["lookup_stats"])
        self.assertIsNone(result["density_stats"])

    def test_output_dir_auto_created(self):
        """Nested output_dir is created automatically."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        out = self._p("sub/nested/out")

        result = run_enrichment_pipeline(pts, out, render=True)

        self.assertTrue(Path(out).is_dir())

    # ------------------------------------------------------------------
    # Error tests
    # ------------------------------------------------------------------

    def test_no_stages_raises_value_error(self):
        """ValueError raised when no pipeline stages are configured."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        with self.assertRaises(ValueError):
            run_enrichment_pipeline(pts, self._p("out"))

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised for a non-existent input file."""
        with self.assertRaises(FileNotFoundError):
            run_enrichment_pipeline("no_such.gpkg", self._p("out"), render=True)

    def test_missing_reference_raises_file_not_found(self):
        """FileNotFoundError raised for a non-existent reference file."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        with self.assertRaises(FileNotFoundError):
            run_enrichment_pipeline(pts, self._p("out"), reference_path="no_ref.gpkg")


if __name__ == "__main__":
    unittest.main()
