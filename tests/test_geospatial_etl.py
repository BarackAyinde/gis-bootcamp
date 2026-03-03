"""
Tests for geospatial_etl.py

No external services required.
All tests use synthetic GeoDataFrames written to a tempdir as GPKG files.
PostGIS sources and sinks are not tested here (covered by test_postgis_client.py).
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon
from shapely.wkt import loads as wkt_loads

from gis_bootcamp.geospatial_etl import (
    run_pipeline,
    run_pipeline_from_config,
    validate_pipeline,
)

CRS_4326 = "EPSG:4326"
CRS_3857 = "EPSG:3857"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gpkg(path: str, n: int = 6, crs: str = CRS_4326) -> str:
    """Write a synthetic point GPKG and return the path."""
    gdf = gpd.GeoDataFrame(
        {
            "id": range(n),
            "region": ["A" if i < n // 2 else "B" for i in range(n)],
            "value": [float(i * 10) for i in range(n)],
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
        {"id": [1, 2], "value": [1.0, 2.0]},
        geometry=[valid, invalid],
        crs=CRS_4326,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _pipeline(src: str, sink: str, transforms: list = None) -> dict:
    """Build a minimal file-to-file pipeline dict."""
    return {
        "name": "test_pipeline",
        "source": {"type": "file", "path": src},
        "transforms": transforms or [],
        "sink": {"type": "file", "path": sink},
    }


# ---------------------------------------------------------------------------
# TestTransforms — each transform in isolation via a full pipeline run
# ---------------------------------------------------------------------------

class TestTransforms(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = _make_gpkg(self._p("src.gpkg"), n=6)

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_reproject_changes_crs(self):
        """reproject transform changes the CRS of the output dataset."""
        out = self._p("out.gpkg")
        run_pipeline(_pipeline(self.src, out, [{"type": "reproject", "crs": CRS_3857}]))
        gdf_out = gpd.read_file(out)
        self.assertIn("3857", gdf_out.crs.to_string())

    def test_reproject_preserves_feature_count(self):
        """reproject does not add or remove features."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out, [{"type": "reproject", "crs": CRS_3857}]))
        self.assertEqual(result["rows_in"], result["rows_out"])

    def test_filter_reduces_rows(self):
        """filter drops rows that do not match the query expression."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out, [{"type": "filter", "query": "value > 20"}]))
        # value column: 0, 10, 20, 30, 40, 50 — 3 rows > 20
        self.assertEqual(result["rows_out"], 3)
        self.assertEqual(result["rows_dropped"], 3)

    def test_filter_keeps_all_when_all_match(self):
        """filter keeps all rows when the query matches everything."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out, [{"type": "filter", "query": "value >= 0"}]))
        self.assertEqual(result["rows_out"], 6)

    def test_clip_bbox_removes_outside_points(self):
        """clip_bbox removes features outside the bounding box."""
        out = self._p("out.gpkg")
        # Points at (0,0)..(5,5); clip to [-0.5,-0.5,2.5,2.5] keeps (0,0),(1,1),(2,2)
        result = run_pipeline(_pipeline(
            self.src, out,
            [{"type": "clip_bbox", "bbox": [-0.5, -0.5, 2.5, 2.5]}],
        ))
        self.assertEqual(result["rows_out"], 3)

    def test_buffer_changes_geometry_type_to_polygon(self):
        """buffer on point data produces Polygon geometries."""
        out = self._p("out_buf.gpkg")
        run_pipeline(_pipeline(self.src, out, [{"type": "buffer", "distance": 1.0}]))
        gdf_out = gpd.read_file(out)
        geom_types = gdf_out.geom_type.unique().tolist()
        self.assertIn("Polygon", geom_types)

    def test_dissolve_by_column_reduces_rows(self):
        """dissolve by 'region' collapses 6 rows (3A+3B) into 2."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out, [{"type": "dissolve", "by": "region"}]))
        self.assertEqual(result["rows_out"], 2)

    def test_dissolve_all_produces_one_row(self):
        """dissolve without 'by' collapses all features into one."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out, [{"type": "dissolve"}]))
        self.assertEqual(result["rows_out"], 1)

    def test_rename_columns_renames_attribute(self):
        """rename_columns renames the specified attribute column."""
        out = self._p("out.gpkg")
        run_pipeline(_pipeline(
            self.src, out,
            [{"type": "rename_columns", "mapping": {"region": "zone"}}],
        ))
        gdf_out = gpd.read_file(out)
        self.assertIn("zone", gdf_out.columns)
        self.assertNotIn("region", gdf_out.columns)

    def test_drop_columns_removes_attribute(self):
        """drop_columns removes the specified attribute column."""
        out = self._p("out.gpkg")
        run_pipeline(_pipeline(
            self.src, out,
            [{"type": "drop_columns", "columns": ["region", "value"]}],
        ))
        gdf_out = gpd.read_file(out)
        self.assertNotIn("region", gdf_out.columns)
        self.assertNotIn("value", gdf_out.columns)

    def test_drop_columns_ignores_nonexistent(self):
        """drop_columns silently ignores columns that do not exist."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(
            self.src, out,
            [{"type": "drop_columns", "columns": ["nonexistent"]}],
        ))
        self.assertEqual(result["rows_out"], 6)

    def test_select_columns_keeps_only_specified_and_geometry(self):
        """select_columns keeps only listed columns plus geometry."""
        out = self._p("out.gpkg")
        run_pipeline(_pipeline(
            self.src, out,
            [{"type": "select_columns", "columns": ["id"]}],
        ))
        gdf_out = gpd.read_file(out)
        self.assertIn("id", gdf_out.columns)
        self.assertNotIn("region", gdf_out.columns)
        self.assertNotIn("value", gdf_out.columns)
        self.assertIsNotNone(gdf_out.geometry)

    def test_validate_geometry_fix_repairs_invalid(self):
        """validate_geometry action='fix' repairs self-intersecting geometries."""
        invalid_src = _make_invalid_gpkg(self._p("inv.gpkg"))
        out = self._p("out.gpkg")
        run_pipeline(_pipeline(
            invalid_src, out,
            [{"type": "validate_geometry", "action": "fix"}],
        ))
        gdf_out = gpd.read_file(out)
        # After make_valid, all geometries should be valid
        self.assertTrue(gdf_out.geometry.is_valid.all())

    def test_validate_geometry_drop_removes_invalid(self):
        """validate_geometry action='drop' removes invalid rows."""
        invalid_src = _make_invalid_gpkg(self._p("inv.gpkg"))
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(
            invalid_src, out,
            [{"type": "validate_geometry", "action": "drop"}],
        ))
        # 1 valid + 1 invalid → 1 kept after drop
        self.assertEqual(result["rows_out"], 1)

    def test_validate_geometry_bad_action_raises(self):
        """validate_geometry raises ValueError for an invalid action."""
        out = self._p("out.gpkg")
        with self.assertRaises(Exception):
            run_pipeline(_pipeline(
                self.src, out,
                [{"type": "validate_geometry", "action": "ignore"}],
            ))

    def test_deduplicate_removes_duplicate_rows(self):
        """deduplicate removes rows with duplicate values in the specified column."""
        dup_src = self._p("dup.gpkg")
        gdf = gpd.GeoDataFrame(
            {"id": [1, 1, 2], "value": [10.0, 10.0, 20.0]},
            geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
            crs=CRS_4326,
        )
        gdf.to_file(dup_src, driver="GPKG")
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(
            dup_src, out,
            [{"type": "deduplicate", "columns": ["id"]}],
        ))
        self.assertEqual(result["rows_out"], 2)

    def test_add_attribute_adds_column_with_constant_value(self):
        """add_attribute adds a new column with the specified constant value."""
        out = self._p("out.gpkg")
        run_pipeline(_pipeline(
            self.src, out,
            [{"type": "add_attribute", "column": "source", "value": "etl_pipeline"}],
        ))
        gdf_out = gpd.read_file(out)
        self.assertIn("source", gdf_out.columns)
        self.assertTrue((gdf_out["source"] == "etl_pipeline").all())


# ---------------------------------------------------------------------------
# TestPipeline — full pipeline behaviour
# ---------------------------------------------------------------------------

class TestPipeline(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = _make_gpkg(self._p("src.gpkg"), n=6)

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_result_dict_has_expected_keys(self):
        """run_pipeline result contains all expected top-level keys."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out))
        for key in ("pipeline_name", "source", "transforms_applied", "sink",
                    "rows_in", "rows_out", "rows_dropped", "duration_seconds"):
            self.assertIn(key, result)

    def test_output_file_created(self):
        """run_pipeline writes the output file to the sink path."""
        out = self._p("out.gpkg")
        run_pipeline(_pipeline(self.src, out))
        self.assertTrue(Path(out).exists())

    def test_rows_in_out_counts_correct(self):
        """rows_in and rows_out correctly reflect feature counts."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out))
        self.assertEqual(result["rows_in"], 6)
        self.assertEqual(result["rows_out"], 6)
        self.assertEqual(result["rows_dropped"], 0)

    def test_rows_dropped_correct_after_filter(self):
        """rows_dropped equals rows_in - rows_out after a filter."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(
            self.src, out,
            [{"type": "filter", "query": "value > 20"}],
        ))
        self.assertEqual(result["rows_dropped"], result["rows_in"] - result["rows_out"])

    def test_pipeline_name_in_result(self):
        """pipeline_name in result matches the 'name' key in the definition."""
        out = self._p("out.gpkg")
        pdef = _pipeline(self.src, out)
        pdef["name"] = "my_pipeline"
        result = run_pipeline(pdef)
        self.assertEqual(result["pipeline_name"], "my_pipeline")

    def test_transforms_applied_list_correct(self):
        """transforms_applied lists every transform type in order."""
        out = self._p("out.gpkg")
        transforms = [
            {"type": "reproject", "crs": CRS_3857},
            {"type": "add_attribute", "column": "tag", "value": "x"},
        ]
        result = run_pipeline(_pipeline(self.src, out, transforms))
        self.assertEqual(result["transforms_applied"], ["reproject", "add_attribute"])

    def test_no_transforms_runs_passthrough(self):
        """A pipeline with no transforms passes data through unchanged."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out, transforms=[]))
        self.assertEqual(result["rows_in"], result["rows_out"])
        self.assertEqual(result["transforms_applied"], [])

    def test_multiple_transforms_chained(self):
        """Multiple transforms are applied in sequence."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(
            self.src, out, [
                {"type": "reproject", "crs": CRS_3857},
                {"type": "filter", "query": "value >= 20"},
                {"type": "add_attribute", "column": "processed", "value": True},
            ],
        ))
        gdf_out = gpd.read_file(out)
        self.assertIn("3857", gdf_out.crs.to_string())
        self.assertIn("processed", gdf_out.columns)
        self.assertLess(result["rows_out"], result["rows_in"])

    def test_sink_crs_matches_output_crs(self):
        """CRS in the sink metadata matches the CRS of the written file."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(
            self.src, out,
            [{"type": "reproject", "crs": CRS_3857}],
        ))
        gdf_out = gpd.read_file(out)
        self.assertIn("3857", result["sink"]["crs"])
        self.assertIn("3857", gdf_out.crs.to_string())

    def test_geojson_sink_creates_file(self):
        """Pipeline can write to a GeoJSON sink."""
        out = self._p("out.geojson")
        run_pipeline(_pipeline(self.src, out))
        self.assertTrue(Path(out).exists())

    def test_sink_creates_parent_directories(self):
        """Pipeline creates parent directories for the sink if they don't exist."""
        out = self._p("nested/deep/out.gpkg")
        run_pipeline(_pipeline(self.src, out))
        self.assertTrue(Path(out).exists())

    def test_duration_seconds_is_positive(self):
        """duration_seconds in result is a positive number."""
        out = self._p("out.gpkg")
        result = run_pipeline(_pipeline(self.src, out))
        self.assertGreater(result["duration_seconds"], 0)


# ---------------------------------------------------------------------------
# TestPipelineErrors
# ---------------------------------------------------------------------------

class TestPipelineErrors(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = _make_gpkg(self._p("src.gpkg"))

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_missing_source_raises_value_error(self):
        """ValueError raised when 'source' key is absent."""
        with self.assertRaises(ValueError):
            run_pipeline({"name": "x", "sink": {"type": "file", "path": self._p("out.gpkg")}})

    def test_missing_sink_raises_value_error(self):
        """ValueError raised when 'sink' key is absent."""
        with self.assertRaises(ValueError):
            run_pipeline({"name": "x", "source": {"type": "file", "path": self.src}})

    def test_source_file_not_found_raises(self):
        """FileNotFoundError raised when source file does not exist."""
        with self.assertRaises(FileNotFoundError):
            run_pipeline(_pipeline("/no/such/file.gpkg", self._p("out.gpkg")))

    def test_unknown_transform_raises_value_error(self):
        """ValueError raised for an unrecognised transform type."""
        with self.assertRaises(ValueError):
            run_pipeline(_pipeline(
                self.src, self._p("out.gpkg"),
                [{"type": "magic_transform"}],
            ))

    def test_unknown_source_type_raises_value_error(self):
        """ValueError raised for an unrecognised source type."""
        with self.assertRaises(ValueError):
            run_pipeline({
                "name": "x",
                "source": {"type": "s3"},
                "sink": {"type": "file", "path": self._p("out.gpkg")},
            })

    def test_unknown_sink_type_raises_value_error(self):
        """ValueError raised for an unrecognised sink type."""
        with self.assertRaises(ValueError):
            run_pipeline({
                "name": "x",
                "source": {"type": "file", "path": self.src},
                "sink": {"type": "s3"},
            })


# ---------------------------------------------------------------------------
# TestValidatePipeline
# ---------------------------------------------------------------------------

class TestValidatePipeline(unittest.TestCase):

    def test_valid_pipeline_returns_no_errors(self):
        """validate_pipeline returns an empty list for a valid definition."""
        pdef = {
            "source": {"type": "file", "path": "data.gpkg"},
            "transforms": [{"type": "reproject", "crs": "EPSG:4326"}],
            "sink": {"type": "file", "path": "out.gpkg"},
        }
        self.assertEqual(validate_pipeline(pdef), [])

    def test_missing_source_returns_error(self):
        """validate_pipeline returns an error when source is missing."""
        pdef = {"sink": {"type": "file", "path": "out.gpkg"}}
        errors = validate_pipeline(pdef)
        self.assertTrue(any("source" in e.lower() for e in errors))

    def test_unknown_transform_returns_error(self):
        """validate_pipeline returns an error for an unknown transform type."""
        pdef = {
            "source": {"type": "file", "path": "data.gpkg"},
            "transforms": [{"type": "nonexistent"}],
            "sink": {"type": "file", "path": "out.gpkg"},
        }
        errors = validate_pipeline(pdef)
        self.assertGreater(len(errors), 0)

    def test_empty_transforms_is_valid(self):
        """validate_pipeline accepts a pipeline with no transforms."""
        pdef = {
            "source": {"type": "file", "path": "data.gpkg"},
            "transforms": [],
            "sink": {"type": "file", "path": "out.gpkg"},
        }
        self.assertEqual(validate_pipeline(pdef), [])


# ---------------------------------------------------------------------------
# TestRunFromConfig
# ---------------------------------------------------------------------------

class TestRunFromConfig(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = _make_gpkg(self._p("src.gpkg"), n=4)

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def _write_config(self, name: str, pipeline_def: dict) -> str:
        path = self._p(name)
        with open(path, "w") as f:
            json.dump(pipeline_def, f)
        return path

    def test_config_pipeline_runs_and_returns_result(self):
        """run_pipeline_from_config executes a pipeline and returns a result dict."""
        out = self._p("out.gpkg")
        config = self._write_config("pipe.json", {
            "name": "cfg_test",
            "source": {"type": "file", "path": self.src},
            "transforms": [],
            "sink": {"type": "file", "path": out},
        })
        result = run_pipeline_from_config(config)
        self.assertEqual(result["pipeline_name"], "cfg_test")
        self.assertEqual(result["rows_in"], 4)

    def test_relative_paths_resolved_from_config_dir(self):
        """Relative source/sink paths are resolved relative to the config file."""
        out = self._p("out.gpkg")
        config = self._write_config("pipe.json", {
            "name": "rel_test",
            "source": {"type": "file", "path": "src.gpkg"},  # relative
            "transforms": [],
            "sink": {"type": "file", "path": out},
        })
        result = run_pipeline_from_config(config)
        self.assertEqual(result["rows_in"], 4)

    def test_missing_config_raises_file_not_found(self):
        """FileNotFoundError raised when config file does not exist."""
        with self.assertRaises(FileNotFoundError):
            run_pipeline_from_config("/no/such/config.json")


if __name__ == "__main__":
    unittest.main()
