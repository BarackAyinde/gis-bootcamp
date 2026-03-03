"""
Tests for gis_data_quality.py

GIS Data Quality & Validation Toolkit tests.

Covers all validation rules (vector and raster), configuration loading,
and report generation.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.crs import CRS as RasterioCRS
from rasterio.transform import from_bounds
from shapely.geometry import Point, Polygon, box as shapely_box
from shapely.wkt import loads as wkt_loads

from gis_bootcamp.gis_data_quality import (
    CheckResult,
    QualityReport,
    check_raster_band_count,
    check_raster_crs,
    check_raster_dimensions,
    check_raster_dtype,
    check_raster_nodata_defined,
    check_vector_attribute_range,
    check_vector_bbox_within,
    check_vector_columns_present,
    check_vector_crs,
    check_vector_feature_count,
    check_vector_geometry_validity,
    check_vector_no_null_geometries,
    validate_from_config,
    validate_raster,
    validate_vector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_points(path: str, coords: list[tuple], crs: str = "EPSG:4326",
                  valid: bool = True) -> str:
    """Write point GeoDataFrame to GPKG."""
    geometries = [Point(x, y) for x, y in coords]
    if not valid:
        # Add one invalid geometry (self-intersecting polygon)
        geometries.append(wkt_loads("POLYGON((0 0, 10 10, 0 10, 10 0, 0 0))"))

    gdf = gpd.GeoDataFrame(
        {"id": range(len(geometries)), "value": [float(i * 10) for i in range(len(geometries))]},
        geometry=geometries,
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _write_polygons(path: str, boxes: list[tuple], crs: str = "EPSG:4326") -> str:
    """Write polygon GeoDataFrame to GPKG."""
    gdf = gpd.GeoDataFrame(
        {"id": range(len(boxes)), "area": [float((b[2] - b[0]) * (b[3] - b[1])) for b in boxes]},
        geometry=[shapely_box(*b) for b in boxes],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _write_raster(path: str, minx: float, miny: float, maxx: float, maxy: float,
                  width: int = 256, height: int = 256, crs: str = "EPSG:4326",
                  bands: int = 1, dtype=np.uint8, nodata: bool = True) -> str:
    """Write synthetic raster (GeoTIFF)."""
    data = np.random.randint(0, 255, (bands, height, width), dtype=dtype)
    transform = from_bounds(minx, miny, maxx, maxy, width, height)

    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "nodata": 0 if nodata else None,
        "width": width,
        "height": height,
        "count": bands,
        "crs": RasterioCRS.from_string(crs),
        "transform": transform,
    }

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)

    return path


# ---------------------------------------------------------------------------
# Vector check tests
# ---------------------------------------------------------------------------

class TestVectorChecks(unittest.TestCase):
    """Test vector validation checks."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # CRS checks

    def test_check_vector_crs_matches(self):
        """check_vector_crs passes when CRS matches."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1)], crs="EPSG:4326")
        gdf = gpd.read_file(pts)
        result = check_vector_crs(gdf, "EPSG:4326")
        self.assertTrue(result.passed)

    def test_check_vector_crs_mismatch(self):
        """check_vector_crs fails when CRS does not match."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)], crs="EPSG:4326")
        gdf = gpd.read_file(pts)
        result = check_vector_crs(gdf, "EPSG:3857")
        self.assertFalse(result.passed)

    def test_check_vector_crs_none(self):
        """check_vector_crs fails when CRS is None."""
        gdf = gpd.GeoDataFrame(
            {"id": [1]},
            geometry=[Point(0, 0)],
            crs=None,
        )
        result = check_vector_crs(gdf, "EPSG:4326")
        self.assertFalse(result.passed)

    # Geometry validity checks

    def test_check_vector_geometry_validity_valid(self):
        """check_vector_geometry_validity passes for valid geometries."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1)], valid=True)
        gdf = gpd.read_file(pts)
        result = check_vector_geometry_validity(gdf)
        self.assertTrue(result.passed)

    def test_check_vector_geometry_validity_invalid(self):
        """check_vector_geometry_validity fails for invalid geometries."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)], valid=False)
        gdf = gpd.read_file(pts)
        result = check_vector_geometry_validity(gdf)
        self.assertFalse(result.passed)

    def test_check_vector_geometry_validity_empty(self):
        """check_vector_geometry_validity passes for empty dataset."""
        gdf = gpd.GeoDataFrame({"id": []}, geometry=[], crs="EPSG:4326")
        result = check_vector_geometry_validity(gdf)
        self.assertTrue(result.passed)

    # Null geometry checks

    def test_check_vector_no_null_geometries_valid(self):
        """check_vector_no_null_geometries passes when no nulls."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1)])
        gdf = gpd.read_file(pts)
        result = check_vector_no_null_geometries(gdf)
        self.assertTrue(result.passed)

    def test_check_vector_no_null_geometries_with_nulls(self):
        """check_vector_no_null_geometries fails when nulls exist."""
        gdf = gpd.GeoDataFrame(
            {"id": [1, 2, 3]},
            geometry=[Point(0, 0), None, Point(2, 2)],
            crs="EPSG:4326",
        )
        result = check_vector_no_null_geometries(gdf)
        self.assertFalse(result.passed)

    # Feature count checks

    def test_check_vector_feature_count_within_range(self):
        """check_vector_feature_count passes when count in range."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1), (2, 2)])
        gdf = gpd.read_file(pts)
        result = check_vector_feature_count(gdf, min_count=2, max_count=5)
        self.assertTrue(result.passed)

    def test_check_vector_feature_count_below_min(self):
        """check_vector_feature_count fails when count below min."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)])
        gdf = gpd.read_file(pts)
        result = check_vector_feature_count(gdf, min_count=5)
        self.assertFalse(result.passed)

    def test_check_vector_feature_count_above_max(self):
        """check_vector_feature_count fails when count above max."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1), (2, 2)])
        gdf = gpd.read_file(pts)
        result = check_vector_feature_count(gdf, max_count=2)
        self.assertFalse(result.passed)

    # Bounding box checks

    def test_check_vector_bbox_within_all_inside(self):
        """check_vector_bbox_within passes when all features inside."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        gdf = gpd.read_file(pts)
        result = check_vector_bbox_within(gdf, 0, 0, 2, 2)
        self.assertTrue(result.passed)

    def test_check_vector_bbox_within_some_outside(self):
        """check_vector_bbox_within fails when some features outside."""
        pts = _write_points(self._p("pts.gpkg"), [(0.5, 0.5), (1.5, 1.5), (3, 3)])
        gdf = gpd.read_file(pts)
        result = check_vector_bbox_within(gdf, 0, 0, 2, 2)
        self.assertFalse(result.passed)

    # Column checks

    def test_check_vector_columns_present_all_exist(self):
        """check_vector_columns_present passes when all columns exist."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)])
        gdf = gpd.read_file(pts)
        result = check_vector_columns_present(gdf, ["id", "value"])
        self.assertTrue(result.passed)

    def test_check_vector_columns_present_missing(self):
        """check_vector_columns_present fails when columns missing."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)])
        gdf = gpd.read_file(pts)
        result = check_vector_columns_present(gdf, ["id", "nonexistent"])
        self.assertFalse(result.passed)

    # Attribute range checks

    def test_check_vector_attribute_range_within(self):
        """check_vector_attribute_range passes when values in range."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1), (2, 2)])
        gdf = gpd.read_file(pts)
        result = check_vector_attribute_range(gdf, "value", min_val=0, max_val=30)
        self.assertTrue(result.passed)

    def test_check_vector_attribute_range_below_min(self):
        """check_vector_attribute_range fails when values below min."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1)])
        gdf = gpd.read_file(pts)
        result = check_vector_attribute_range(gdf, "value", min_val=20)
        self.assertFalse(result.passed)

    def test_check_vector_attribute_range_above_max(self):
        """check_vector_attribute_range fails when values above max."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1)])
        gdf = gpd.read_file(pts)
        result = check_vector_attribute_range(gdf, "value", max_val=5)
        self.assertFalse(result.passed)

    def test_check_vector_attribute_range_missing_column(self):
        """check_vector_attribute_range fails when column missing."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)])
        gdf = gpd.read_file(pts)
        result = check_vector_attribute_range(gdf, "nonexistent", min_val=0)
        self.assertFalse(result.passed)


# ---------------------------------------------------------------------------
# Raster check tests
# ---------------------------------------------------------------------------

class TestRasterChecks(unittest.TestCase):
    """Test raster validation checks."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # CRS checks

    def test_check_raster_crs_matches(self):
        """check_raster_crs passes when CRS matches."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, crs="EPSG:4326")
        result = check_raster_crs(raster, "EPSG:4326")
        self.assertTrue(result.passed)

    def test_check_raster_crs_mismatch(self):
        """check_raster_crs fails when CRS does not match."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, crs="EPSG:4326")
        result = check_raster_crs(raster, "EPSG:3857")
        self.assertFalse(result.passed)

    # Dimension checks

    def test_check_raster_dimensions_matches(self):
        """check_raster_dimensions passes when dimensions match."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, width=256, height=256)
        result = check_raster_dimensions(raster, width=256, height=256)
        self.assertTrue(result.passed)

    def test_check_raster_dimensions_width_mismatch(self):
        """check_raster_dimensions fails when width mismatch."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, width=256, height=256)
        result = check_raster_dimensions(raster, width=512, height=256)
        self.assertFalse(result.passed)

    def test_check_raster_dimensions_height_mismatch(self):
        """check_raster_dimensions fails when height mismatch."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, width=256, height=256)
        result = check_raster_dimensions(raster, width=256, height=512)
        self.assertFalse(result.passed)

    # Band count checks

    def test_check_raster_band_count_matches(self):
        """check_raster_band_count passes when band count matches."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, bands=1)
        result = check_raster_band_count(raster, expected=1)
        self.assertTrue(result.passed)

    def test_check_raster_band_count_mismatch(self):
        """check_raster_band_count fails when band count mismatch."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, bands=1)
        result = check_raster_band_count(raster, expected=3)
        self.assertFalse(result.passed)

    # No-data checks

    def test_check_raster_nodata_defined(self):
        """check_raster_nodata_defined passes when nodata is set."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, nodata=True)
        result = check_raster_nodata_defined(raster)
        self.assertTrue(result.passed)

    def test_check_raster_nodata_not_defined(self):
        """check_raster_nodata_defined fails when nodata is not set."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, nodata=False)
        result = check_raster_nodata_defined(raster)
        self.assertFalse(result.passed)

    # Data type checks

    def test_check_raster_dtype_matches(self):
        """check_raster_dtype passes when dtype matches."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, dtype=np.uint8)
        result = check_raster_dtype(raster, "uint8")
        self.assertTrue(result.passed)

    def test_check_raster_dtype_mismatch(self):
        """check_raster_dtype fails when dtype does not match."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, dtype=np.uint8)
        result = check_raster_dtype(raster, "float32")
        self.assertFalse(result.passed)


# ---------------------------------------------------------------------------
# Validation workflow tests
# ---------------------------------------------------------------------------

class TestValidationWorkflow(unittest.TestCase):
    """Test validation workflow (config loading, report generation)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_validate_vector_all_checks_pass(self):
        """validate_vector runs all checks successfully."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1), (2, 2)], crs="EPSG:4326")
        rules = [
            {"check": "crs", "params": {"expected_crs": "EPSG:4326"}},
            {"check": "geometry_validity"},
            {"check": "no_null_geometries"},
            {"check": "feature_count", "params": {"min_count": 2}},
        ]
        results = validate_vector(pts, rules)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r.passed for r in results))

    def test_validate_vector_some_checks_fail(self):
        """validate_vector reports failures correctly."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)], crs="EPSG:4326")
        rules = [
            {"check": "feature_count", "params": {"min_count": 10}},
            {"check": "crs", "params": {"expected_crs": "EPSG:3857"}},
        ]
        results = validate_vector(pts, rules)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].passed is False)
        self.assertTrue(results[1].passed is False)

    def test_validate_raster_all_checks_pass(self):
        """validate_raster runs all checks successfully."""
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, width=256, height=256, crs="EPSG:4326")
        rules = [
            {"check": "crs", "params": {"expected_crs": "EPSG:4326"}},
            {"check": "dimensions", "params": {"width": 256, "height": 256}},
            {"check": "band_count", "params": {"expected": 1}},
            {"check": "nodata_defined"},
        ]
        results = validate_raster(raster, rules)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r.passed for r in results))

    def test_quality_report_all_passed(self):
        """QualityReport.all_passed is True when no failures."""
        report = QualityReport("test")
        report.results = [
            CheckResult("file1", "check1", True, "msg"),
        ]
        self.assertTrue(report.all_passed)
        self.assertEqual(report.passed_count, 1)
        self.assertEqual(report.failed_count, 0)

    def test_quality_report_summary(self):
        """QualityReport.summary generates readable output."""
        report = QualityReport("test")
        report.results = []
        report.duration_seconds = 0.5
        summary = report.summary
        self.assertIn("Quality Report: test", summary)
        self.assertIn("0/0", summary)
        self.assertIn("0.500", summary)

    def test_validate_from_config_vector(self):
        """validate_from_config processes vector dataset correctly."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0), (1, 1)], crs="EPSG:4326")
        config = {
            "name": "test_validation",
            "rules": [
                {
                    "type": "vector",
                    "path": pts,
                    "rules": [
                        {"check": "crs", "params": {"expected_crs": "EPSG:4326"}},
                        {"check": "feature_count", "params": {"min_count": 1}},
                    ],
                }
            ]
        }
        config_path = self._p("config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        report = validate_from_config(config_path)
        self.assertEqual(report.name, "test_validation")
        self.assertEqual(len(report.results), 2)
        self.assertTrue(report.all_passed)

    def test_validate_from_config_mixed(self):
        """validate_from_config handles vector and raster datasets."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)], crs="EPSG:4326")
        raster = _write_raster(self._p("src.tif"), 0, 0, 10, 10, crs="EPSG:4326")

        config = {
            "name": "mixed_validation",
            "rules": [
                {
                    "type": "vector",
                    "path": pts,
                    "rules": [{"check": "crs", "params": {"expected_crs": "EPSG:4326"}}],
                },
                {
                    "type": "raster",
                    "path": raster,
                    "rules": [{"check": "crs", "params": {"expected_crs": "EPSG:4326"}}],
                },
            ]
        }
        config_path = self._p("config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        report = validate_from_config(config_path)
        self.assertEqual(len(report.results), 2)

    def test_validate_from_config_unknown_check(self):
        """validate_from_config handles unknown checks gracefully."""
        pts = _write_points(self._p("pts.gpkg"), [(0, 0)], crs="EPSG:4326")
        config = {
            "name": "test",
            "rules": [
                {
                    "type": "vector",
                    "path": pts,
                    "rules": [{"check": "nonexistent_check"}],
                }
            ]
        }
        config_path = self._p("config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        report = validate_from_config(config_path)
        # Unknown check is logged and skipped, so 0 results
        self.assertEqual(len(report.results), 0)

    def test_quality_report_to_json(self):
        """QualityReport.to_json writes valid JSON file."""
        report = QualityReport("test")
        report.duration_seconds = 0.5
        output_path = self._p("report.json")

        report.to_json(output_path)
        self.assertTrue(Path(output_path).exists())

        with open(output_path) as f:
            data = json.load(f)

        self.assertEqual(data["name"], "test")
        self.assertIn("all_passed", data)
        self.assertIn("results", data)


if __name__ == "__main__":
    unittest.main()
