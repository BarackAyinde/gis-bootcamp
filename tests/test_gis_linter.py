"""
Tests for gis_linter.py

No external services required.
- Vector linting: synthetic GeoDataFrames written to tempdir as GPKG files.
- Raster linting: minimal GeoTIFFs written to tempdir via rasterio.
- Config loading: JSON config files written to tempdir.
"""

import json
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

from gis_bootcamp.gis_linter import (
    LintFinding,
    format_report,
    lint,
    lint_from_config,
)

CRS_4326 = "EPSG:4326"
CRS_3857 = "EPSG:3857"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gpkg(path: str, n: int = 5, crs: str = CRS_4326) -> str:
    """Write a synthetic point GPKG and return the path."""
    gdf = gpd.GeoDataFrame(
        {
            "id": range(n),
            "name": [f"feat_{i}" for i in range(n)],
            "value": [float(i) for i in range(n)],
        },
        geometry=[Point(float(i), float(i)) for i in range(n)],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _make_invalid_gpkg(path: str) -> str:
    """Write a GPKG with one self-intersecting polygon."""
    valid = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    invalid = wkt_loads("POLYGON((0 0, 10 10, 0 10, 10 0, 0 0))")
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[valid, invalid],
        crs=CRS_4326,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _make_raster(
    path: str,
    width: int = 8,
    height: int = 6,
    crs: str = CRS_4326,
    nodata: float = -9999.0,
    dtype: str = "float32",
    count: int = 1,
) -> str:
    """Write a minimal GeoTIFF and return the path."""
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


def _make_raster_no_nodata(path: str) -> str:
    """Write a GeoTIFF with no nodata value."""
    transform = from_origin(-10.0, 10.0, 2.5, 2.5)
    data = np.ones((1, 6, 8), dtype="float32")
    with rasterio.open(
        path, "w",
        driver="GTiff",
        width=8, height=6, count=1,
        crs=CRS_4326, transform=transform, dtype="float32",
    ) as dst:
        dst.write(data)
    return path


def _write_config(tmpdir: str, dataset_path: str, rules: list) -> str:
    """Write a JSON lint config to tmpdir and return the config path."""
    config = {"dataset": dataset_path, "rules": rules}
    config_path = os.path.join(tmpdir, "lint.json")
    with open(config_path, "w") as f:
        json.dump(config, f)
    return config_path


# ---------------------------------------------------------------------------
# TestLintVectorRules
# ---------------------------------------------------------------------------

class TestLintVectorRules(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.gpkg = _make_gpkg(self._p("pts.gpkg"))

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_all_pass_status_is_pass(self):
        """lint() returns status='pass' when all rules pass."""
        rules = [
            {"check": "crs", "expected_crs": CRS_4326, "severity": "error"},
            {"check": "geometry_validity", "severity": "error"},
        ]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")

    def test_failing_error_rule_sets_status_fail(self):
        """lint() returns status='fail' when an error-severity rule fails."""
        rules = [{"check": "crs", "expected_crs": CRS_3857, "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["errors"], 1)

    def test_failing_warning_rule_does_not_fail_status(self):
        """lint() keeps status='pass' when only warning-severity rules fail."""
        rules = [
            {"check": "crs", "expected_crs": CRS_3857, "severity": "warning"},
        ]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["warnings"], 1)

    def test_result_dict_structure(self):
        """lint() result contains all expected top-level keys."""
        rules = [{"check": "geometry_validity", "severity": "error"}]
        result = lint(self.gpkg, rules)
        for key in ("input_path", "total", "passed", "errors", "warnings", "status", "findings"):
            self.assertIn(key, result)

    def test_findings_count_matches_rules(self):
        """findings list length equals the number of rules applied."""
        rules = [
            {"check": "crs", "expected_crs": CRS_4326, "severity": "error"},
            {"check": "geometry_validity", "severity": "error"},
            {"check": "no_null_geometries", "severity": "warning"},
        ]
        result = lint(self.gpkg, rules)
        self.assertEqual(len(result["findings"]), 3)

    def test_feature_count_rule_passes(self):
        """feature_count rule passes when file has enough features."""
        rules = [{"check": "feature_count", "min_count": 3, "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")

    def test_feature_count_rule_fails(self):
        """feature_count rule fails when min_count exceeds feature count."""
        rules = [{"check": "feature_count", "min_count": 100, "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "fail")

    def test_columns_present_rule_passes(self):
        """columns_present rule passes when all required columns exist."""
        rules = [{"check": "columns_present", "required_columns": ["id", "name", "value"], "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")

    def test_columns_present_rule_fails_missing(self):
        """columns_present rule fails when a required column is absent."""
        rules = [{"check": "columns_present", "required_columns": ["id", "nonexistent"], "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "fail")

    def test_geometry_type_rule_passes(self):
        """geometry_type rule passes for a Point dataset."""
        rules = [{"check": "geometry_type", "expected_type": "Point", "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")

    def test_geometry_type_rule_fails(self):
        """geometry_type rule fails when expected type differs."""
        rules = [{"check": "geometry_type", "expected_type": "Polygon", "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "fail")

    def test_no_duplicate_values_rule_passes(self):
        """no_duplicate_values passes when id column is unique."""
        rules = [{"check": "no_duplicate_values", "column": "id", "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")

    def test_attribute_range_rule_passes(self):
        """attribute_range passes when values are within bounds."""
        # value column has 0..4
        rules = [{"check": "attribute_range", "column": "value",
                  "min_val": 0.0, "max_val": 10.0, "severity": "warning"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")

    def test_attribute_range_rule_fails(self):
        """attribute_range fails when values exceed max_val."""
        rules = [{"check": "attribute_range", "column": "value",
                  "min_val": 0.0, "max_val": 2.0, "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "fail")

    def test_geometry_validity_rule_fails_invalid(self):
        """geometry_validity rule fails for a file with invalid geometries."""
        invalid_gpkg = _make_invalid_gpkg(self._p("invalid.gpkg"))
        rules = [{"check": "geometry_validity", "severity": "error"}]
        result = lint(invalid_gpkg, rules)
        self.assertEqual(result["status"], "fail")

    def test_bbox_within_rule_passes(self):
        """bbox_within passes when all points are within the given bbox."""
        rules = [{"check": "bbox_within", "bbox": [-1.0, -1.0, 10.0, 10.0], "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["status"], "pass")

    def test_input_path_in_result(self):
        """input_path in result matches the provided file path."""
        rules = [{"check": "geometry_validity", "severity": "error"}]
        result = lint(self.gpkg, rules)
        self.assertEqual(result["input_path"], self.gpkg)

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised when input file does not exist."""
        with self.assertRaises(FileNotFoundError):
            lint("/no/such/file.gpkg", [{"check": "geometry_validity", "severity": "error"}])

    def test_unknown_check_raises_value_error(self):
        """ValueError raised for an unknown check name."""
        with self.assertRaises(ValueError):
            lint(self.gpkg, [{"check": "nonexistent_check", "severity": "error"}])

    def test_invalid_severity_raises_value_error(self):
        """ValueError raised for an invalid severity value."""
        with self.assertRaises(ValueError):
            lint(self.gpkg, [{"check": "geometry_validity", "severity": "critical"}])


# ---------------------------------------------------------------------------
# TestLintRasterRules
# ---------------------------------------------------------------------------

class TestLintRasterRules(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.raster = _make_raster(
            self._p("test.tif"), width=8, height=6, crs=CRS_4326,
            nodata=-9999.0, dtype="float32",
        )

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_raster_crs_rule_passes(self):
        """raster_crs rule passes when CRS matches."""
        rules = [{"check": "raster_crs", "expected_crs": CRS_4326, "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "pass")

    def test_raster_crs_rule_fails(self):
        """raster_crs rule fails when CRS does not match."""
        rules = [{"check": "raster_crs", "expected_crs": CRS_3857, "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "fail")

    def test_raster_dimensions_rule_passes(self):
        """raster_dimensions rule passes when dimensions match."""
        rules = [{"check": "raster_dimensions", "width": 8, "height": 6, "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "pass")

    def test_raster_dimensions_rule_fails(self):
        """raster_dimensions rule fails when dimensions differ."""
        rules = [{"check": "raster_dimensions", "width": 100, "height": 100, "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "fail")

    def test_raster_band_count_rule_passes(self):
        """raster_band_count rule passes for a single-band raster."""
        rules = [{"check": "raster_band_count", "expected_bands": 1, "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "pass")

    def test_raster_nodata_rule_passes(self):
        """raster_nodata passes when nodata is defined."""
        rules = [{"check": "raster_nodata", "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "pass")

    def test_raster_nodata_rule_fails(self):
        """raster_nodata fails when nodata is not defined."""
        no_nd = _make_raster_no_nodata(self._p("no_nd.tif"))
        rules = [{"check": "raster_nodata", "severity": "error"}]
        result = lint(no_nd, rules)
        self.assertEqual(result["status"], "fail")

    def test_raster_dtype_rule_passes(self):
        """raster_dtype passes when dtype matches."""
        rules = [{"check": "raster_dtype", "expected_dtype": "float32", "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "pass")

    def test_raster_dtype_rule_fails(self):
        """raster_dtype fails when dtype differs."""
        rules = [{"check": "raster_dtype", "expected_dtype": "uint8", "severity": "error"}]
        result = lint(self.raster, rules)
        self.assertEqual(result["status"], "fail")


# ---------------------------------------------------------------------------
# TestLintFromConfig
# ---------------------------------------------------------------------------

class TestLintFromConfig(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.gpkg = _make_gpkg(self._p("pts.gpkg"))

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_all_pass_from_config(self):
        """lint_from_config passes when all rules in config pass."""
        rules = [
            {"check": "crs", "expected_crs": CRS_4326, "severity": "error"},
            {"check": "geometry_validity", "severity": "error"},
        ]
        config_path = _write_config(self.tmpdir, self.gpkg, rules)
        result = lint_from_config(config_path)
        self.assertEqual(result["status"], "pass")

    def test_failing_rule_from_config(self):
        """lint_from_config returns fail when a rule fails."""
        rules = [{"check": "feature_count", "min_count": 100, "severity": "error"}]
        config_path = _write_config(self.tmpdir, self.gpkg, rules)
        result = lint_from_config(config_path)
        self.assertEqual(result["status"], "fail")

    def test_missing_config_raises_file_not_found(self):
        """FileNotFoundError raised when config file does not exist."""
        with self.assertRaises(FileNotFoundError):
            lint_from_config("/no/such/config.json")

    def test_config_without_dataset_raises_value_error(self):
        """ValueError raised when config has no 'dataset' key."""
        bad_config = {"rules": [{"check": "geometry_validity", "severity": "error"}]}
        config_path = self._p("bad.json")
        with open(config_path, "w") as f:
            json.dump(bad_config, f)
        with self.assertRaises(ValueError):
            lint_from_config(config_path)

    def test_config_without_rules_raises_value_error(self):
        """ValueError raised when config has no 'rules' key."""
        bad_config = {"dataset": self.gpkg}
        config_path = self._p("bad2.json")
        with open(config_path, "w") as f:
            json.dump(bad_config, f)
        with self.assertRaises(ValueError):
            lint_from_config(config_path)

    def test_relative_dataset_path_resolved_from_config_dir(self):
        """Relative dataset path in config is resolved relative to config dir."""
        # Write config to tmpdir with a relative dataset path
        rules = [{"check": "geometry_validity", "severity": "error"}]
        config = {"dataset": "pts.gpkg", "rules": rules}  # relative
        config_path = self._p("lint.json")
        with open(config_path, "w") as f:
            json.dump(config, f)
        result = lint_from_config(config_path)
        self.assertEqual(result["status"], "pass")

    def test_output_report_written_when_path_given(self):
        """lint_from_config writes a report file when output_path is provided."""
        rules = [{"check": "geometry_validity", "severity": "error"}]
        config_path = _write_config(self.tmpdir, self.gpkg, rules)
        out = self._p("report.json")
        lint_from_config(config_path, output_path=out, output_format="json")
        self.assertTrue(Path(out).exists())
        with open(out) as f:
            report = json.load(f)
        self.assertIn("status", report)


# ---------------------------------------------------------------------------
# TestFormatReport
# ---------------------------------------------------------------------------

class TestFormatReport(unittest.TestCase):

    def _make_result(self, status: str = "pass", errors: int = 0, warnings: int = 0) -> dict:
        findings = []
        if errors:
            findings.append({
                "check": "geometry_validity", "severity": "error",
                "passed": False, "message": "2 invalid geometries", "details": {},
            })
        if warnings:
            findings.append({
                "check": "feature_count", "severity": "warning",
                "passed": False, "message": "10 < minimum 100", "details": {},
            })
        # Add a passing check
        findings.append({
            "check": "crs", "severity": "error",
            "passed": True, "message": "CRS matches EPSG:4326", "details": {},
        })
        return {
            "input_path": "/data/parcels.gpkg",
            "total": len(findings),
            "passed": sum(1 for f in findings if f["passed"]),
            "errors": errors,
            "warnings": warnings,
            "status": status,
            "findings": findings,
        }

    def test_json_format_is_valid_json(self):
        """format_report('json') produces valid JSON."""
        result = self._make_result()
        report_str = format_report(result, "json")
        parsed = json.loads(report_str)
        self.assertIn("status", parsed)

    def test_json_format_contains_findings(self):
        """JSON report includes the findings list."""
        result = self._make_result()
        report_str = format_report(result, "json")
        parsed = json.loads(report_str)
        self.assertIsInstance(parsed["findings"], list)

    def test_text_format_contains_header(self):
        """Text report contains a 'GIS Linter Report' header."""
        result = self._make_result()
        report_str = format_report(result, "text")
        self.assertIn("GIS Linter Report", report_str)

    def test_text_format_shows_fail_status(self):
        """Text report shows FAIL status when errors exist."""
        result = self._make_result(status="fail", errors=1)
        report_str = format_report(result, "text")
        self.assertIn("FAIL", report_str)

    def test_text_format_shows_pass_status(self):
        """Text report shows PASS status when no errors."""
        result = self._make_result(status="pass")
        report_str = format_report(result, "text")
        self.assertIn("PASS", report_str)

    def test_text_format_lists_all_findings(self):
        """Text report lists every finding by check name."""
        result = self._make_result(errors=1)
        report_str = format_report(result, "text")
        self.assertIn("geometry_validity", report_str)
        self.assertIn("crs", report_str)

    def test_summary_counts_in_text(self):
        """Text report includes rule counts."""
        result = self._make_result(errors=1)
        report_str = format_report(result, "text")
        self.assertIn("Errors", report_str)
        self.assertIn("Warnings", report_str)


if __name__ == "__main__":
    unittest.main()
