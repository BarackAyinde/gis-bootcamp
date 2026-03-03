"""
Tests for spatial_qa.py

No external services required.
- Vector checks: built from synthetic GeoDataFrames using Shapely/GeoPandas.
- Raster checks: real GeoTIFF files written to a tempdir via rasterio.
- SpatialQAReport: unit tests for accumulation, summary, and raise_if_failed.
- SpatialQATestCase: subclass tests that exercise assert* wrappers.
"""

import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, Polygon
from shapely.wkt import loads as wkt_loads

from gis_bootcamp.spatial_qa import (
    CheckResult,
    SpatialQAReport,
    SpatialQATestCase,
    check_attribute_range,
    check_bbox_within,
    check_columns_present,
    check_crs,
    check_crs_consistency,
    check_feature_count,
    check_geometry_type,
    check_geometry_validity,
    check_no_duplicate_values,
    check_no_null_geometries,
    check_raster_band_count,
    check_raster_crs,
    check_raster_dimensions,
    check_raster_dtype,
    check_raster_nodata,
)

CRS_4326 = "EPSG:4326"
CRS_3857 = "EPSG:3857"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gdf(
    n: int = 5,
    crs: str = CRS_4326,
    x_start: float = 0.0,
) -> gpd.GeoDataFrame:
    """Synthetic point GeoDataFrame with id and value columns."""
    return gpd.GeoDataFrame(
        {
            "id": range(n),
            "name": [f"feat_{i}" for i in range(n)],
            "value": [float(i) for i in range(n)],
        },
        geometry=[Point(x_start + float(i), float(i)) for i in range(n)],
        crs=crs,
    )


def _make_invalid_gdf() -> gpd.GeoDataFrame:
    """GeoDataFrame containing one self-intersecting (invalid) polygon."""
    valid = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    # Bowtie polygon — self-intersecting, is_valid == False
    invalid = wkt_loads("POLYGON((0 0, 10 10, 0 10, 10 0, 0 0))")
    return gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[valid, invalid],
        crs=CRS_4326,
    )


def _make_raster(
    path: str,
    width: int = 8,
    height: int = 6,
    crs: str = CRS_4326,
    nodata: float = -9999.0,
    dtype: str = "float32",
    count: int = 1,
) -> str:
    """Write a minimal single-band GeoTIFF and return the path."""
    transform = from_origin(-10.0, 10.0, 20.0 / width, 20.0 / height)
    data = np.ones((count, height, width), dtype=dtype)
    with rasterio.open(
        path, "w",
        driver="GTiff",
        width=width, height=height, count=count,
        crs=crs, transform=transform,
        dtype=dtype, nodata=nodata,
    ) as dst:
        dst.write(data)
    return path


def _make_raster_no_nodata(path: str, width: int = 8, height: int = 6) -> str:
    """Write a GeoTIFF with no nodata value set."""
    transform = from_origin(-10.0, 10.0, 20.0 / width, 20.0 / height)
    data = np.ones((1, height, width), dtype="float32")
    with rasterio.open(
        path, "w",
        driver="GTiff",
        width=width, height=height, count=1,
        crs=CRS_4326, transform=transform,
        dtype="float32",
        # nodata deliberately omitted
    ) as dst:
        dst.write(data)
    return path


# ---------------------------------------------------------------------------
# TestVectorChecks
# ---------------------------------------------------------------------------

class TestVectorChecks(unittest.TestCase):

    def setUp(self):
        self.gdf = _make_gdf(n=5)
        self.gdf_3857 = _make_gdf(n=3, crs=CRS_3857)

    # --- check_crs ---

    def test_check_crs_passes_matching(self):
        """check_crs passes when CRS matches expected."""
        result = check_crs(self.gdf, CRS_4326)
        self.assertTrue(result.passed)

    def test_check_crs_fails_different(self):
        """check_crs fails when CRS does not match expected."""
        result = check_crs(self.gdf, CRS_3857)
        self.assertFalse(result.passed)

    def test_check_crs_fails_no_crs(self):
        """check_crs fails when dataset has no CRS."""
        no_crs = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)])
        result = check_crs(no_crs, CRS_4326)
        self.assertFalse(result.passed)
        self.assertIn("no CRS", result.message)

    def test_check_crs_result_contains_actual_and_expected(self):
        """check_crs details include 'actual' and 'expected' keys."""
        result = check_crs(self.gdf, CRS_3857)
        self.assertIn("actual", result.details)
        self.assertIn("expected", result.details)

    # --- check_crs_consistency ---

    def test_check_crs_consistency_passes_all_same(self):
        """check_crs_consistency passes when all datasets share the same CRS."""
        gdf2 = _make_gdf(n=3, crs=CRS_4326)
        result = check_crs_consistency([self.gdf, gdf2])
        self.assertTrue(result.passed)

    def test_check_crs_consistency_fails_mismatch(self):
        """check_crs_consistency fails when datasets have different CRS."""
        result = check_crs_consistency([self.gdf, self.gdf_3857])
        self.assertFalse(result.passed)
        self.assertGreater(len(result.details["mismatches"]), 0)

    def test_check_crs_consistency_single_dataset(self):
        """check_crs_consistency trivially passes for a single dataset."""
        result = check_crs_consistency([self.gdf])
        self.assertTrue(result.passed)

    # --- check_geometry_validity ---

    def test_check_geometry_validity_passes_valid(self):
        """check_geometry_validity passes when all geometries are valid."""
        result = check_geometry_validity(self.gdf)
        self.assertTrue(result.passed)

    def test_check_geometry_validity_fails_invalid(self):
        """check_geometry_validity fails when any geometry is invalid."""
        result = check_geometry_validity(_make_invalid_gdf())
        self.assertFalse(result.passed)
        self.assertEqual(result.details["invalid_count"], 1)

    def test_check_geometry_validity_passes_empty_dataset(self):
        """check_geometry_validity passes for an empty GeoDataFrame."""
        empty = gpd.GeoDataFrame({"id": []}, geometry=[], crs=CRS_4326)
        result = check_geometry_validity(empty)
        self.assertTrue(result.passed)

    def test_check_geometry_validity_detail_has_invalid_indices(self):
        """check_geometry_validity reports invalid_indices in details."""
        result = check_geometry_validity(_make_invalid_gdf())
        self.assertIn("invalid_indices", result.details)
        self.assertEqual(len(result.details["invalid_indices"]), 1)

    # --- check_no_null_geometries ---

    def test_check_no_null_geometries_passes(self):
        """check_no_null_geometries passes when all geometries are present."""
        result = check_no_null_geometries(self.gdf)
        self.assertTrue(result.passed)

    def test_check_no_null_geometries_fails_null(self):
        """check_no_null_geometries fails when a geometry is None."""
        with_null = gpd.GeoDataFrame(
            {"id": [1, 2]},
            geometry=[Point(0, 0), None],
            crs=CRS_4326,
        )
        result = check_no_null_geometries(with_null)
        self.assertFalse(result.passed)
        self.assertEqual(result.details["null_count"], 1)

    def test_check_no_null_geometries_fails_empty(self):
        """check_no_null_geometries fails when a geometry is empty."""
        with_empty = gpd.GeoDataFrame(
            {"id": [1, 2]},
            geometry=[Point(0, 0), Point()],  # Point() is empty
            crs=CRS_4326,
        )
        result = check_no_null_geometries(with_empty)
        self.assertFalse(result.passed)
        self.assertEqual(result.details["empty_count"], 1)

    # --- check_feature_count ---

    def test_check_feature_count_passes_min_only(self):
        """check_feature_count passes when count ≥ min_count."""
        result = check_feature_count(self.gdf, min_count=3)
        self.assertTrue(result.passed)

    def test_check_feature_count_fails_below_min(self):
        """check_feature_count fails when count < min_count."""
        result = check_feature_count(self.gdf, min_count=10)
        self.assertFalse(result.passed)

    def test_check_feature_count_passes_within_range(self):
        """check_feature_count passes when count is within [min, max]."""
        result = check_feature_count(self.gdf, min_count=3, max_count=7)
        self.assertTrue(result.passed)

    def test_check_feature_count_fails_above_max(self):
        """check_feature_count fails when count exceeds max_count."""
        result = check_feature_count(self.gdf, min_count=1, max_count=3)
        self.assertFalse(result.passed)

    # --- check_columns_present ---

    def test_check_columns_present_passes(self):
        """check_columns_present passes when all columns exist."""
        result = check_columns_present(self.gdf, ["id", "name", "value"])
        self.assertTrue(result.passed)

    def test_check_columns_present_fails_missing(self):
        """check_columns_present fails when a required column is absent."""
        result = check_columns_present(self.gdf, ["id", "population"])
        self.assertFalse(result.passed)
        self.assertIn("population", result.details["missing"])

    # --- check_geometry_type ---

    def test_check_geometry_type_passes_point(self):
        """check_geometry_type passes for a Point dataset."""
        result = check_geometry_type(self.gdf, "Point")
        self.assertTrue(result.passed)

    def test_check_geometry_type_fails_wrong_type(self):
        """check_geometry_type fails when type does not match."""
        result = check_geometry_type(self.gdf, "Polygon")
        self.assertFalse(result.passed)

    # --- check_bbox_within ---

    def test_check_bbox_within_passes(self):
        """check_bbox_within passes when all features are within bbox."""
        # Points are at (0,0)..(4,4); give a generous bbox
        result = check_bbox_within(self.gdf, (-1.0, -1.0, 10.0, 10.0))
        self.assertTrue(result.passed)

    def test_check_bbox_within_fails_outside(self):
        """check_bbox_within fails when features extend outside bbox."""
        result = check_bbox_within(self.gdf, (1.0, 1.0, 3.0, 3.0))
        self.assertFalse(result.passed)

    # --- check_no_duplicate_values ---

    def test_check_no_duplicate_values_passes(self):
        """check_no_duplicate_values passes when id column is unique."""
        result = check_no_duplicate_values(self.gdf, "id")
        self.assertTrue(result.passed)

    def test_check_no_duplicate_values_fails_dupes(self):
        """check_no_duplicate_values fails when duplicates exist."""
        dup = gpd.GeoDataFrame(
            {"id": [1, 1, 2]},
            geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
            crs=CRS_4326,
        )
        result = check_no_duplicate_values(dup, "id")
        self.assertFalse(result.passed)
        self.assertEqual(result.details["duplicate_count"], 1)

    def test_check_no_duplicate_values_fails_missing_column(self):
        """check_no_duplicate_values fails gracefully for a missing column."""
        result = check_no_duplicate_values(self.gdf, "nonexistent")
        self.assertFalse(result.passed)

    # --- check_attribute_range ---

    def test_check_attribute_range_passes(self):
        """check_attribute_range passes when all values are in range."""
        # value column has 0..4
        result = check_attribute_range(self.gdf, "value", 0.0, 10.0)
        self.assertTrue(result.passed)

    def test_check_attribute_range_fails_out_of_range(self):
        """check_attribute_range fails when values exceed max_val."""
        result = check_attribute_range(self.gdf, "value", 0.0, 2.0)
        self.assertFalse(result.passed)

    def test_check_attribute_range_fails_missing_column(self):
        """check_attribute_range fails gracefully for a missing column."""
        result = check_attribute_range(self.gdf, "nonexistent", 0.0, 100.0)
        self.assertFalse(result.passed)


# ---------------------------------------------------------------------------
# TestRasterChecks
# ---------------------------------------------------------------------------

class TestRasterChecks(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.raster = _make_raster(
            self._p("test.tif"), width=8, height=6,
            crs=CRS_4326, nodata=-9999.0, dtype="float32",
        )

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # --- check_raster_crs ---

    def test_check_raster_crs_passes(self):
        """check_raster_crs passes when CRS matches expected."""
        result = check_raster_crs(self.raster, CRS_4326)
        self.assertTrue(result.passed)

    def test_check_raster_crs_fails(self):
        """check_raster_crs fails when CRS does not match."""
        result = check_raster_crs(self.raster, CRS_3857)
        self.assertFalse(result.passed)

    # --- check_raster_dimensions ---

    def test_check_raster_dimensions_passes(self):
        """check_raster_dimensions passes when width and height match."""
        result = check_raster_dimensions(self.raster, width=8, height=6)
        self.assertTrue(result.passed)

    def test_check_raster_dimensions_fails_wrong_width(self):
        """check_raster_dimensions fails when width differs."""
        result = check_raster_dimensions(self.raster, width=99, height=6)
        self.assertFalse(result.passed)

    def test_check_raster_dimensions_fails_wrong_height(self):
        """check_raster_dimensions fails when height differs."""
        result = check_raster_dimensions(self.raster, width=8, height=99)
        self.assertFalse(result.passed)

    # --- check_raster_band_count ---

    def test_check_raster_band_count_passes(self):
        """check_raster_band_count passes for a single-band raster."""
        result = check_raster_band_count(self.raster, expected_bands=1)
        self.assertTrue(result.passed)

    def test_check_raster_band_count_fails(self):
        """check_raster_band_count fails when band count differs."""
        result = check_raster_band_count(self.raster, expected_bands=3)
        self.assertFalse(result.passed)

    def test_check_raster_band_count_passes_multiband(self):
        """check_raster_band_count passes for a 3-band raster."""
        multi = _make_raster(self._p("multi.tif"), count=3)
        result = check_raster_band_count(multi, expected_bands=3)
        self.assertTrue(result.passed)

    # --- check_raster_nodata ---

    def test_check_raster_nodata_passes(self):
        """check_raster_nodata passes when nodata is defined."""
        result = check_raster_nodata(self.raster)
        self.assertTrue(result.passed)
        self.assertEqual(result.details["nodata"], -9999.0)

    def test_check_raster_nodata_fails_when_not_set(self):
        """check_raster_nodata fails when nodata is not set."""
        no_nd = _make_raster_no_nodata(self._p("no_nd.tif"))
        result = check_raster_nodata(no_nd)
        self.assertFalse(result.passed)

    # --- check_raster_dtype ---

    def test_check_raster_dtype_passes(self):
        """check_raster_dtype passes when dtype matches expected."""
        result = check_raster_dtype(self.raster, "float32")
        self.assertTrue(result.passed)

    def test_check_raster_dtype_fails_wrong_dtype(self):
        """check_raster_dtype fails when dtype does not match."""
        result = check_raster_dtype(self.raster, "uint8")
        self.assertFalse(result.passed)


# ---------------------------------------------------------------------------
# TestSpatialQAReport
# ---------------------------------------------------------------------------

class TestSpatialQAReport(unittest.TestCase):

    def _pass_result(self, name: str = "check_x") -> CheckResult:
        return CheckResult(name, True, "all good", {})

    def _fail_result(self, name: str = "check_y") -> CheckResult:
        return CheckResult(name, False, "something wrong", {})

    def test_all_pass_does_not_raise(self):
        """raise_if_failed does not raise when all checks pass."""
        report = SpatialQAReport("test")
        report.add(self._pass_result("a"))
        report.add(self._pass_result("b"))
        report.raise_if_failed()  # should not raise

    def test_with_failure_raises_assertion_error(self):
        """raise_if_failed raises AssertionError when a check fails."""
        report = SpatialQAReport("test")
        report.add(self._pass_result())
        report.add(self._fail_result())
        with self.assertRaises(AssertionError):
            report.raise_if_failed()

    def test_passed_property_true_when_all_pass(self):
        """passed property is True when all checks pass."""
        report = SpatialQAReport("test")
        report.add(self._pass_result())
        self.assertTrue(report.passed)

    def test_passed_property_false_when_any_fail(self):
        """passed property is False when any check fails."""
        report = SpatialQAReport("test")
        report.add(self._pass_result())
        report.add(self._fail_result())
        self.assertFalse(report.passed)

    def test_summary_has_expected_keys(self):
        """summary() dict contains all expected top-level keys."""
        report = SpatialQAReport("test")
        report.add(self._pass_result())
        s = report.summary()
        for key in ("name", "total", "passed", "failed", "checks"):
            self.assertIn(key, s)

    def test_failed_checks_list(self):
        """failed_checks contains only the failed CheckResults."""
        report = SpatialQAReport("test")
        report.add(self._pass_result("a"))
        report.add(self._fail_result("b"))
        report.add(self._fail_result("c"))
        self.assertEqual(len(report.failed_checks), 2)
        self.assertEqual({r.name for r in report.failed_checks}, {"b", "c"})

    def test_chaining_add_returns_self(self):
        """add() returns the report for method chaining."""
        report = SpatialQAReport("test")
        result = report.add(self._pass_result())
        self.assertIs(result, report)

    def test_summary_counts_correct(self):
        """summary() total/passed/failed counts match added results."""
        report = SpatialQAReport("test")
        report.add(self._pass_result("a"))
        report.add(self._pass_result("b"))
        report.add(self._fail_result("c"))
        s = report.summary()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["passed"], 2)
        self.assertEqual(s["failed"], 1)


# ---------------------------------------------------------------------------
# TestSpatialQATestCase
# ---------------------------------------------------------------------------

class TestSpatialQATestCase(SpatialQATestCase):
    """Exercises SpatialQATestCase assert methods directly."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.gdf = _make_gdf(n=4)

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_assert_crs_passes_silently(self):
        """assertCRS does not raise when CRS matches."""
        self.assertCRS(self.gdf, CRS_4326)

    def test_assert_crs_raises_on_wrong_crs(self):
        """assertCRS raises AssertionError when CRS does not match."""
        with self.assertRaises(AssertionError):
            self.assertCRS(self.gdf, CRS_3857)

    def test_assert_geometry_validity_raises_on_invalid(self):
        """assertGeometryValidity raises AssertionError for invalid geometries."""
        with self.assertRaises(AssertionError):
            self.assertGeometryValidity(_make_invalid_gdf())

    def test_assert_feature_count_passes(self):
        """assertFeatureCount does not raise when count is in range."""
        self.assertFeatureCount(self.gdf, min_count=1, max_count=10)

    def test_assert_raster_crs_passes(self):
        """assertRasterCRS does not raise when raster CRS matches."""
        raster = _make_raster(self._p("r.tif"))
        self.assertRasterCRS(raster, CRS_4326)

    def test_assert_raster_nodata_raises_when_not_set(self):
        """assertRasterNodata raises AssertionError when nodata is missing."""
        no_nd = _make_raster_no_nodata(self._p("no_nd.tif"))
        with self.assertRaises(AssertionError):
            self.assertRasterNodata(no_nd)


if __name__ == "__main__":
    unittest.main()
