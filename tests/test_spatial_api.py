"""
Tests for spatial_api.py

Uses FastAPI's TestClient (backed by httpx) — no real HTTP server started.
Geocoder dependency is overridden to avoid real Nominatim calls.
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
from fastapi.testclient import TestClient
from shapely.geometry import Point, box

from gis_bootcamp.spatial_api import _default_geocoder, app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_geocoder(address, timeout=10):
    return types.SimpleNamespace(
        latitude=1.0,
        longitude=1.0,
        address=f"Geocoded: {address}",
    )


def _write_csv(path: str, rows: list[dict]) -> str:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_points(path: str, coords: list[tuple], crs: str = "EPSG:4326") -> str:
    gdf = gpd.GeoDataFrame(
        {"id": range(len(coords))},
        geometry=[Point(x, y) for x, y in coords],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _write_polygons(path: str, boxes: list[tuple], labels: list[str], crs: str = "EPSG:4326") -> str:
    gdf = gpd.GeoDataFrame(
        {"region": labels},
        geometry=[box(*b) for b in boxes],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSpatialAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Override geocoder dependency for all tests in this class
        app.dependency_overrides[_default_geocoder] = lambda: _mock_geocoder
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # GET /health
    # ------------------------------------------------------------------

    def test_health_returns_200(self):
        """GET /health returns 200 with status ok."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    # ------------------------------------------------------------------
    # POST /geocode
    # ------------------------------------------------------------------

    def test_geocode_success(self):
        """POST /geocode with valid CSV returns 200 and GeocodeResponse."""
        rows = [{"address": f"{i} Main St"} for i in range(3)]
        src = _write_csv(self._p("addr.csv"), rows)
        out = self._p("geocoded.gpkg")

        resp = self.client.post("/geocode", json={
            "input_path": src,
            "output_path": out,
            "address_column": "address",
        })

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("total", body)
        self.assertIn("success", body)
        self.assertEqual(body["total"], 3)

    def test_geocode_missing_file_returns_404(self):
        """POST /geocode with non-existent input returns 404."""
        resp = self.client.post("/geocode", json={
            "input_path": "/no/such/file.csv",
            "output_path": self._p("out.gpkg"),
        })
        self.assertEqual(resp.status_code, 404)

    def test_geocode_missing_column_returns_400(self):
        """POST /geocode with wrong address_column returns 400."""
        rows = [{"name": "Place A"}]
        src = _write_csv(self._p("addr.csv"), rows)
        resp = self.client.post("/geocode", json={
            "input_path": src,
            "output_path": self._p("out.gpkg"),
            "address_column": "no_such_col",
        })
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # POST /nearest-feature
    # ------------------------------------------------------------------

    def test_nearest_feature_success(self):
        """POST /nearest-feature with valid files returns 200."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["ZoneA"])
        out = self._p("enriched.gpkg")

        resp = self.client.post("/nearest-feature", json={
            "points_path": pts,
            "reference_path": ref,
            "output_path": out,
        })

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Path(out).exists())

    def test_nearest_feature_response_schema(self):
        """POST /nearest-feature response contains all expected keys."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["A"])
        out = self._p("enriched.gpkg")

        resp = self.client.post("/nearest-feature", json={
            "points_path": pts, "reference_path": ref, "output_path": out,
        })
        body = resp.json()

        for key in ("output_path", "total_points", "matched", "unmatched", "match_rate"):
            self.assertIn(key, body)

    def test_nearest_feature_missing_file_returns_404(self):
        """POST /nearest-feature with missing points file returns 404."""
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["A"])
        resp = self.client.post("/nearest-feature", json={
            "points_path": "/no/such.gpkg",
            "reference_path": ref,
            "output_path": self._p("out.gpkg"),
        })
        self.assertEqual(resp.status_code, 404)

    def test_nearest_feature_invalid_mode_returns_400(self):
        """POST /nearest-feature with invalid mode returns 400."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        ref = _write_polygons(self._p("ref.gpkg"), [(0, 0, 2, 2)], ["A"])
        resp = self.client.post("/nearest-feature", json={
            "points_path": pts, "reference_path": ref,
            "output_path": self._p("out.gpkg"), "mode": "intersects",
        })
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # POST /density
    # ------------------------------------------------------------------

    def test_density_success(self):
        """POST /density (vector mode) with valid file returns 200."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5), (0.7, 0.7)])
        out = self._p("density.gpkg")

        resp = self.client.post("/density", json={
            "input_path": pts, "output_path": out,
            "cell_size": 1.0, "output_type": "vector",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Path(out).exists())

    def test_density_response_schema(self):
        """POST /density response contains all expected keys."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("density.gpkg")

        resp = self.client.post("/density", json={
            "input_path": pts, "output_path": out,
            "cell_size": 1.0, "output_type": "vector",
        })
        body = resp.json()

        for key in ("output_path", "output_type", "point_count", "crs",
                    "cell_size", "bandwidth", "grid_width", "grid_height",
                    "total_cells", "hotspot_cells"):
            self.assertIn(key, body)

    def test_density_missing_file_returns_404(self):
        """POST /density with non-existent input returns 404."""
        resp = self.client.post("/density", json={
            "input_path": "/no/such.gpkg",
            "output_path": self._p("out.tif"),
            "cell_size": 1.0,
        })
        self.assertEqual(resp.status_code, 404)

    def test_density_negative_cell_size_returns_400(self):
        """POST /density with cell_size <= 0 returns 400."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        resp = self.client.post("/density", json={
            "input_path": pts, "output_path": self._p("out.tif"), "cell_size": -5.0,
        })
        self.assertEqual(resp.status_code, 400)

    def test_density_invalid_output_type_returns_400(self):
        """POST /density with unsupported output_type returns 400."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        resp = self.client.post("/density", json={
            "input_path": pts, "output_path": self._p("out.tif"),
            "cell_size": 1.0, "output_type": "hexbin",
        })
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # POST /render
    # ------------------------------------------------------------------

    def test_render_success(self):
        """POST /render with valid layer returns 200 and creates PNG."""
        layer = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("map.png")

        resp = self.client.post("/render", json={
            "layers": [{"path": layer}],
            "output_path": out,
        })

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Path(out).exists())

    def test_render_response_schema(self):
        """POST /render response contains all expected keys."""
        layer = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        out = self._p("map.png")

        resp = self.client.post("/render", json={
            "layers": [{"path": layer}], "output_path": out,
        })
        body = resp.json()

        for key in ("output_path", "output_format", "layer_count",
                    "feature_count", "crs", "bbox", "figsize", "dpi"):
            self.assertIn(key, body)

    def test_render_bbox_is_list(self):
        """bbox in /render response is a JSON array of 4 floats."""
        layer = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        out = self._p("map.png")

        resp = self.client.post("/render", json={
            "layers": [{"path": layer}], "output_path": out,
        })
        bbox = resp.json()["bbox"]

        self.assertIsInstance(bbox, list)
        self.assertEqual(len(bbox), 4)

    def test_render_missing_file_returns_404(self):
        """POST /render with non-existent layer file returns 404."""
        resp = self.client.post("/render", json={
            "layers": [{"path": "/no/such.gpkg"}],
            "output_path": self._p("map.png"),
        })
        self.assertEqual(resp.status_code, 404)

    def test_render_invalid_format_returns_400(self):
        """POST /render with unsupported output format returns 400."""
        layer = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        resp = self.client.post("/render", json={
            "layers": [{"path": layer}],
            "output_path": self._p("map.xyz"),
        })
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # POST /pipeline
    # ------------------------------------------------------------------

    def test_pipeline_render_only(self):
        """POST /pipeline with render=True and existing points returns 200."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("pipeline_out")

        resp = self.client.post("/pipeline", json={
            "input_path": pts, "output_dir": out, "render": True,
        })

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("render", body["stages_run"])

    def test_pipeline_response_schema(self):
        """POST /pipeline response contains all expected keys."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        out = self._p("pipeline_out")

        resp = self.client.post("/pipeline", json={
            "input_path": pts, "output_dir": out, "render": True,
        })
        body = resp.json()

        for key in ("output_dir", "stages_run", "enriched_path", "point_count",
                    "geocode_stats", "lookup_stats", "density_stats", "map_path"):
            self.assertIn(key, body)

    def test_pipeline_no_stages_returns_400(self):
        """POST /pipeline with no stages configured returns 400."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        resp = self.client.post("/pipeline", json={
            "input_path": pts, "output_dir": self._p("out"),
        })
        self.assertEqual(resp.status_code, 400)

    def test_pipeline_missing_file_returns_404(self):
        """POST /pipeline with non-existent input returns 404."""
        resp = self.client.post("/pipeline", json={
            "input_path": "/no/such.gpkg",
            "output_dir": self._p("out"),
            "render": True,
        })
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
