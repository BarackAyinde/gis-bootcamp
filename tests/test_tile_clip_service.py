"""
Tests for tile_clip_service.py

FastAPI microservice for clipping vector and raster datasets to bounding boxes.

Uses FastAPI's TestClient (backed by httpx) — no real HTTP server started.
All tests use temporary files created from synthetic test data.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import rasterio
from fastapi.testclient import TestClient
from numpy import uint8 as np_uint8
from rasterio.crs import CRS as RasterioCRS
from rasterio.transform import from_bounds
from shapely.geometry import Point, box

from gis_bootcamp.tile_clip_service import (
    app,
    bbox_metadata,
    clip_raster,
    clip_vector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_points(path: str, coords: list[tuple], crs: str = "EPSG:4326") -> str:
    """Write synthetic point GeoDataFrame to GPKG."""
    gdf = gpd.GeoDataFrame(
        {"id": range(len(coords)), "value": [float(i * 10) for i in range(len(coords))]},
        geometry=[Point(x, y) for x, y in coords],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _write_polygons(path: str, boxes: list[tuple], crs: str = "EPSG:4326") -> str:
    """Write synthetic polygon GeoDataFrame to GPKG."""
    gdf = gpd.GeoDataFrame(
        {"id": range(len(boxes)), "name": [f"Zone{i}" for i in range(len(boxes))]},
        geometry=[box(*b) for b in boxes],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _write_raster(path: str, minx: float, miny: float, maxx: float, maxy: float,
                  width: int = 256, height: int = 256, crs: str = "EPSG:4326",
                  bands: int = 1, dtype: type = np_uint8) -> str:
    """Write a synthetic single-band raster (GeoTIFF)."""
    import numpy as np
    
    data = np.random.randint(0, 255, (bands, height, width), dtype=dtype)
    
    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    
    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "nodata": None,
        "width": width,
        "height": height,
        "count": bands,
        "crs": RasterioCRS.from_string(crs),
        "transform": transform,
        "compress": "lzw",
    }
    
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
    
    return path


# ---------------------------------------------------------------------------
# Test core functions
# ---------------------------------------------------------------------------

class TestBboxMetadata(unittest.TestCase):
    """Test bbox_metadata() function."""

    def test_valid_bbox_returns_dict(self):
        """bbox_metadata with valid bbox returns dict with all keys."""
        result = bbox_metadata(0, 0, 10, 10)
        self.assertIsInstance(result, dict)
        self.assertIn("bbox", result)
        self.assertIn("crs", result)
        self.assertIn("center", result)
        self.assertIn("width", result)
        self.assertIn("height", result)
        self.assertIn("area_crs_units", result)

    def test_bbox_metadata_computes_dimensions(self):
        """bbox_metadata computes correct width and height."""
        result = bbox_metadata(0, 0, 10, 20)
        self.assertEqual(result["width"], 10)
        self.assertEqual(result["height"], 20)

    def test_bbox_metadata_computes_area(self):
        """bbox_metadata computes correct area (width * height)."""
        result = bbox_metadata(0, 0, 5, 4)
        self.assertEqual(result["area_crs_units"], 20)

    def test_bbox_metadata_computes_center(self):
        """bbox_metadata computes correct center point."""
        result = bbox_metadata(0, 0, 10, 10)
        self.assertEqual(result["center"], [5, 5])

    def test_bbox_metadata_with_custom_crs(self):
        """bbox_metadata preserves custom CRS string."""
        result = bbox_metadata(0, 0, 10, 10, crs="EPSG:3857")
        self.assertEqual(result["crs"], "EPSG:3857")

    def test_bbox_metadata_invalid_minx_maxx_raises(self):
        """bbox_metadata raises ValueError when minx >= maxx."""
        with self.assertRaises(ValueError):
            bbox_metadata(10, 0, 10, 10)

    def test_bbox_metadata_invalid_miny_maxy_raises(self):
        """bbox_metadata raises ValueError when miny >= maxy."""
        with self.assertRaises(ValueError):
            bbox_metadata(0, 10, 10, 10)


class TestClipVector(unittest.TestCase):
    """Test clip_vector() function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_clip_vector_nonexistent_file_raises_filenotfound(self):
        """clip_vector raises FileNotFoundError when dataset does not exist."""
        with self.assertRaises(FileNotFoundError):
            clip_vector("/no/such/file.gpkg", [0, 0, 1, 1])

    def test_clip_vector_invalid_format_raises_valueerror(self):
        """clip_vector raises ValueError for invalid output_format."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        with self.assertRaises(ValueError):
            clip_vector(pts, [0, 0, 2, 2], output_format="invalid")

    def test_clip_vector_gpkg_without_output_path_raises(self):
        """clip_vector raises ValueError when output_format=gpkg but no output_path."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        with self.assertRaises(ValueError):
            clip_vector(pts, [0, 0, 2, 2], output_format="gpkg")

    def test_clip_vector_geojson_returns_geojson(self):
        """clip_vector with format=geojson returns inline GeoJSON."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5), (2.5, 2.5)])
        result = clip_vector(pts, [0, 0, 2, 2], output_format="geojson")
        self.assertEqual(result["output_format"], "geojson")
        self.assertIsNotNone(result["geojson"])
        self.assertIn("features", result["geojson"])

    def test_clip_vector_geojson_clips_correctly(self):
        """clip_vector correctly removes features outside the bbox."""
        # 3 points: (0.5, 0.5), (1.5, 1.5), (2.5, 2.5)
        # clip to [0, 0, 2, 2] should keep only first two
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5), (2.5, 2.5)])
        result = clip_vector(pts, [0, 0, 2, 2], output_format="geojson")
        self.assertEqual(result["feature_count"], 2)

    def test_clip_vector_gpkg_writes_file(self):
        """clip_vector with format=gpkg writes output file."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("clipped.gpkg")
        result = clip_vector(pts, [0, 0, 2, 2], output_format="gpkg", output_path=out)
        self.assertEqual(result["output_format"], "gpkg")
        self.assertEqual(result["output_path"], out)
        self.assertTrue(Path(out).exists())

    def test_clip_vector_crs_mismatch_reprojects(self):
        """clip_vector reprojects bbox when bbox_crs differs from dataset CRS."""
        # Create points in Web Mercator (EPSG:3857)
        pts = _write_points(self._p("pts_3857.gpkg"), [(0, 0), (1000000, 1000000)], crs="EPSG:3857")
        # Supply bbox in WGS84 (EPSG:4326)
        result = clip_vector(
            pts, [0, 0, 10, 10], bbox_crs="EPSG:4326",
            output_format="geojson",
        )
        # Should succeed (reprojection happened)
        self.assertIsInstance(result, dict)
        self.assertIn("feature_count", result)

    def test_clip_vector_returns_crs(self):
        """clip_vector returns the CRS of the dataset."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)], crs="EPSG:3857")
        result = clip_vector(pts, [0, 0, 2, 2], output_format="geojson")
        self.assertIn("3857", result["crs"])

    def test_clip_vector_returns_duration(self):
        """clip_vector returns duration_seconds."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        result = clip_vector(pts, [0, 0, 2, 2], output_format="geojson")
        self.assertGreater(result["duration_seconds"], 0)

    def test_clip_vector_empty_result(self):
        """clip_vector with no features in bbox returns empty result."""
        pts = _write_points(self._p("pts.gpkg"), [(10, 10), (20, 20)])
        result = clip_vector(pts, [0, 0, 1, 1], output_format="geojson")
        self.assertEqual(result["feature_count"], 0)

    def test_clip_vector_polygons(self):
        """clip_vector works with polygon data."""
        polys = _write_polygons(self._p("polys.gpkg"), [(0, 0, 10, 10), (5, 5, 15, 15)])
        result = clip_vector(polys, [0, 0, 8, 8], output_format="geojson")
        self.assertGreater(result["feature_count"], 0)


class TestClipRaster(unittest.TestCase):
    """Test clip_raster() function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_clip_raster_nonexistent_file_raises_filenotfound(self):
        """clip_raster raises FileNotFoundError when raster does not exist."""
        with self.assertRaises(FileNotFoundError):
            clip_raster("/no/such/file.tif", [0, 0, 1, 1], output_path=self._p("out.tif"))

    def test_clip_raster_no_output_path_raises(self):
        """clip_raster raises ValueError when output_path is empty."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        with self.assertRaises(ValueError):
            clip_raster(raster, [0, 0, 5, 5], output_path="")

    def test_clip_raster_no_overlap_raises(self):
        """clip_raster raises ValueError when bbox does not overlap raster extent."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        with self.assertRaises(ValueError):
            clip_raster(raster, [20, 20, 30, 30], output_path=self._p("out.tif"))

    def test_clip_raster_writes_file(self):
        """clip_raster writes output GeoTIFF file."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, width=256, height=256)
        out = self._p("clipped.tif")
        result = clip_raster(raster, [0, 0, 5, 5], output_path=out)
        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_path"], out)

    def test_clip_raster_reduces_dimensions(self):
        """clip_raster produces smaller output than input."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, width=256, height=256)
        out = self._p("clipped.tif")
        result = clip_raster(raster, [0, 0, 5, 5], output_path=out)
        # Full raster is 256x256; clipped to half area should be roughly half in each dimension
        self.assertLess(result["width"], 256)
        self.assertLess(result["height"], 256)

    def test_clip_raster_returns_metadata(self):
        """clip_raster returns complete metadata dict."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        out = self._p("clipped.tif")
        result = clip_raster(raster, [2, 2, 8, 8], output_path=out)
        self.assertIn("output_path", result)
        self.assertIn("crs", result)
        self.assertIn("bbox_used", result)
        self.assertIn("width", result)
        self.assertIn("height", result)
        self.assertIn("band_count", result)
        self.assertIn("dtype", result)
        self.assertIn("duration_seconds", result)

    def test_clip_raster_crs_mismatch_reprojects(self):
        """clip_raster reprojects bbox when bbox_crs differs from raster CRS."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, crs="EPSG:3857")
        out = self._p("clipped.tif")
        # Supply bbox in WGS84
        result = clip_raster(raster, [0, 0, 0.1, 0.1], bbox_crs="EPSG:4326", output_path=out)
        self.assertTrue(Path(out).exists())
        self.assertIn("3857", result["crs"])

    def test_clip_raster_returns_duration(self):
        """clip_raster returns duration_seconds."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        out = self._p("clipped.tif")
        result = clip_raster(raster, [0, 0, 5, 5], output_path=out)
        self.assertGreater(result["duration_seconds"], 0)

    def test_clip_raster_partial_overlap(self):
        """clip_raster handles partial overlap (bbox extends beyond raster)."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        out = self._p("clipped.tif")
        # Request bbox [5, 5, 15, 15] but raster only goes to [10, 10]
        result = clip_raster(raster, [5, 5, 15, 15], output_path=out)
        self.assertTrue(Path(out).exists())
        self.assertLess(result["width"], 256)  # Partial clip


# ---------------------------------------------------------------------------
# Test FastAPI endpoints
# ---------------------------------------------------------------------------

class TestTileClipServiceAPI(unittest.TestCase):
    """Test FastAPI endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # GET /health
    # ------------------------------------------------------------------

    def test_health_returns_200(self):
        """GET /health returns 200."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    # ------------------------------------------------------------------
    # GET /bbox/metadata
    # ------------------------------------------------------------------

    def test_bbox_metadata_endpoint_returns_200(self):
        """GET /bbox/metadata with valid params returns 200."""
        resp = self.client.get("/bbox/metadata", params={
            "minx": 0, "miny": 0, "maxx": 10, "maxy": 10,
        })
        self.assertEqual(resp.status_code, 200)

    def test_bbox_metadata_endpoint_returns_correct_structure(self):
        """GET /bbox/metadata returns BBoxMetadataResponse fields."""
        resp = self.client.get("/bbox/metadata", params={
            "minx": 0, "miny": 0, "maxx": 10, "maxy": 10,
        })
        body = resp.json()
        self.assertIn("bbox", body)
        self.assertIn("crs", body)
        self.assertIn("center", body)
        self.assertIn("width", body)
        self.assertIn("height", body)
        self.assertIn("area_crs_units", body)

    def test_bbox_metadata_endpoint_with_custom_crs(self):
        """GET /bbox/metadata with custom crs param."""
        resp = self.client.get("/bbox/metadata", params={
            "minx": 0, "miny": 0, "maxx": 10, "maxy": 10, "crs": "EPSG:3857",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["crs"], "EPSG:3857")

    def test_bbox_metadata_endpoint_invalid_bbox_returns_400(self):
        """GET /bbox/metadata with invalid bbox returns 400."""
        resp = self.client.get("/bbox/metadata", params={
            "minx": 10, "miny": 0, "maxx": 10, "maxy": 10,  # minx == maxx
        })
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # POST /clip/vector
    # ------------------------------------------------------------------

    def test_clip_vector_endpoint_geojson_returns_200(self):
        """POST /clip/vector with geojson format returns 200."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 2, 2],
            "output_format": "geojson",
        })
        self.assertEqual(resp.status_code, 200)

    def test_clip_vector_endpoint_geojson_includes_data(self):
        """POST /clip/vector geojson response includes geojson field."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 2, 2],
            "output_format": "geojson",
        })
        body = resp.json()
        self.assertIsNotNone(body["geojson"])
        self.assertIn("features", body["geojson"])

    def test_clip_vector_endpoint_gpkg_returns_200(self):
        """POST /clip/vector with gpkg format returns 200."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("clipped.gpkg")
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 2, 2],
            "output_format": "gpkg",
            "output_path": out,
        })
        self.assertEqual(resp.status_code, 200)

    def test_clip_vector_endpoint_gpkg_creates_file(self):
        """POST /clip/vector gpkg format creates output file."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("clipped.gpkg")
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 2, 2],
            "output_format": "gpkg",
            "output_path": out,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Path(out).exists())

    def test_clip_vector_endpoint_missing_file_returns_404(self):
        """POST /clip/vector with non-existent file returns 404."""
        resp = self.client.post("/clip/vector", json={
            "dataset_path": "/no/such/file.gpkg",
            "bbox": [0, 0, 2, 2],
            "output_format": "geojson",
        })
        self.assertEqual(resp.status_code, 404)

    def test_clip_vector_endpoint_invalid_format_returns_422(self):
        """POST /clip/vector with invalid format returns 422 (validation error)."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 2, 2],
            "output_format": "invalid_format",
        })
        self.assertEqual(resp.status_code, 422)

    def test_clip_vector_endpoint_gpkg_no_output_path_returns_400(self):
        """POST /clip/vector gpkg without output_path returns 400."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 2, 2],
            "output_format": "gpkg",
        })
        self.assertEqual(resp.status_code, 400)

    def test_clip_vector_endpoint_invalid_bbox_returns_422(self):
        """POST /clip/vector with invalid bbox (minx >= maxx) returns 422 (validation error)."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)])
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [10, 0, 10, 10],  # minx == maxx
            "output_format": "geojson",
        })
        self.assertEqual(resp.status_code, 422)

    def test_clip_vector_endpoint_returns_feature_count(self):
        """POST /clip/vector response includes feature_count."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 2, 2],
            "output_format": "geojson",
        })
        body = resp.json()
        self.assertIn("feature_count", body)
        self.assertGreaterEqual(body["feature_count"], 0)

    def test_clip_vector_endpoint_with_bbox_crs(self):
        """POST /clip/vector with bbox_crs param."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5)], crs="EPSG:3857")
        resp = self.client.post("/clip/vector", json={
            "dataset_path": pts,
            "bbox": [0, 0, 100000, 100000],
            "bbox_crs": "EPSG:3857",
            "output_format": "geojson",
        })
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------
    # POST /clip/raster
    # ------------------------------------------------------------------

    def test_clip_raster_endpoint_returns_200(self):
        """POST /clip/raster returns 200."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        out = self._p("clipped.tif")
        resp = self.client.post("/clip/raster", json={
            "raster_path": raster,
            "bbox": [0, 0, 5, 5],
            "output_path": out,
        })
        self.assertEqual(resp.status_code, 200)

    def test_clip_raster_endpoint_creates_file(self):
        """POST /clip/raster creates output file."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        out = self._p("clipped.tif")
        resp = self.client.post("/clip/raster", json={
            "raster_path": raster,
            "bbox": [0, 0, 5, 5],
            "output_path": out,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Path(out).exists())

    def test_clip_raster_endpoint_returns_metadata(self):
        """POST /clip/raster response includes metadata fields."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        out = self._p("clipped.tif")
        resp = self.client.post("/clip/raster", json={
            "raster_path": raster,
            "bbox": [0, 0, 5, 5],
            "output_path": out,
        })
        body = resp.json()
        self.assertIn("output_path", body)
        self.assertIn("width", body)
        self.assertIn("height", body)
        self.assertIn("band_count", body)

    def test_clip_raster_endpoint_missing_file_returns_404(self):
        """POST /clip/raster with non-existent file returns 404."""
        resp = self.client.post("/clip/raster", json={
            "raster_path": "/no/such/file.tif",
            "bbox": [0, 0, 5, 5],
            "output_path": self._p("out.tif"),
        })
        self.assertEqual(resp.status_code, 404)

    def test_clip_raster_endpoint_no_overlap_returns_400(self):
        """POST /clip/raster with non-overlapping bbox returns 400."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        resp = self.client.post("/clip/raster", json={
            "raster_path": raster,
            "bbox": [20, 20, 30, 30],  # No overlap
            "output_path": self._p("out.tif"),
        })
        self.assertEqual(resp.status_code, 400)

    def test_clip_raster_endpoint_invalid_bbox_returns_422(self):
        """POST /clip/raster with invalid bbox returns 422 (validation error)."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        resp = self.client.post("/clip/raster", json={
            "raster_path": raster,
            "bbox": [10, 0, 10, 10],  # minx == maxx
            "output_path": self._p("out.tif"),
        })
        self.assertEqual(resp.status_code, 422)

    def test_clip_raster_endpoint_with_bbox_crs(self):
        """POST /clip/raster with bbox_crs param."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, crs="EPSG:3857")
        out = self._p("clipped.tif")
        resp = self.client.post("/clip/raster", json={
            "raster_path": raster,
            "bbox": [0, 0, 1000000, 1000000],
            "bbox_crs": "EPSG:3857",
            "output_path": out,
        })
        self.assertEqual(resp.status_code, 200)

    def test_clip_raster_endpoint_returns_bbox_used(self):
        """POST /clip/raster response includes bbox_used."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10)
        out = self._p("clipped.tif")
        resp = self.client.post("/clip/raster", json={
            "raster_path": raster,
            "bbox": [2, 2, 8, 8],
            "output_path": out,
        })
        body = resp.json()
        self.assertIn("bbox_used", body)
        self.assertEqual(len(body["bbox_used"]), 4)


if __name__ == "__main__":
    unittest.main()
