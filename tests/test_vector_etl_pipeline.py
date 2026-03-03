"""
Unit tests for Vector ETL Pipeline

Tests cover:
- Basic ETL pipeline execution (no geoprocessing)
- ETL with clip operation
- ETL with buffer operation
- ETL with dissolve operation
- CRS transformation
- Geometry validation and repair
- Error handling (missing files, invalid parameters)
"""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon

from gis_bootcamp.vector_etl_pipeline import run_etl_pipeline


class TestVectorETLPipeline(unittest.TestCase):
    """Test suite for Vector ETL Pipeline"""

    @classmethod
    def setUpClass(cls):
        """Create test datasets used across all tests."""
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.test_dir = cls.tmpdir.name

        # Create simple point dataset in EPSG:4326
        cls.points_path = f"{cls.test_dir}/points.gpkg"
        points_gdf = gpd.GeoDataFrame(
            {
                "id": [1, 2, 3, 4, 5],
                "category": ["A", "B", "A", "C", "B"],
                "value": [10, 20, 30, 40, 50],
            },
            geometry=[
                Point(0, 0),
                Point(1, 1),
                Point(2, 2),
                Point(3, 3),
                Point(4, 4),
            ],
            crs="EPSG:4326",
        )
        points_gdf.to_file(cls.points_path, driver="GPKG")

        # Create polygon dataset in EPSG:4326
        cls.polygons_path = f"{cls.test_dir}/polygons.gpkg"
        polygons_gdf = gpd.GeoDataFrame(
            {
                "id": [1, 2, 3],
                "region": ["North", "Central", "South"],
            },
            geometry=[
                Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]),
                Polygon([(2, 0), (4, 0), (4, 2), (2, 2), (2, 0)]),
                Polygon([(1, -2), (3, -2), (3, 0), (1, 0), (1, -2)]),
            ],
            crs="EPSG:4326",
        )
        polygons_gdf.to_file(cls.polygons_path, driver="GPKG")

        # Create clipping geometry (small box)
        cls.clip_path = f"{cls.test_dir}/clip.gpkg"
        clip_gdf = gpd.GeoDataFrame(
            {"id": [1]},
            geometry=[Polygon([(0.5, 0.5), (2.5, 0.5), (2.5, 2.5), (0.5, 2.5), (0.5, 0.5)])],
            crs="EPSG:4326",
        )
        clip_gdf.to_file(cls.clip_path, driver="GPKG")

    @classmethod
    def tearDownClass(cls):
        """Clean up test directory."""
        cls.tmpdir.cleanup()

    def test_etl_reproject_only(self):
        """Test basic ETL: load, validate, reproject, output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
                operation=None,
            )

            self.assertTrue(summary["success"])
            self.assertEqual(summary["target_epsg"], 3857)
            self.assertIsNone(summary["operation"])

            # Verify output
            output_gdf = gpd.read_file(output_path)
            self.assertEqual(len(output_gdf), 5)
            self.assertEqual(str(output_gdf.crs), "EPSG:3857")

    def test_etl_with_clip(self):
        """Test ETL with clip operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/clipped.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
                operation="clip",
                clip_path=self.clip_path,
            )

            self.assertTrue(summary["success"])
            self.assertEqual(summary["operation"], "clip")

            # Verify output
            output_gdf = gpd.read_file(output_path)
            self.assertLess(len(output_gdf), 5)  # Clipping should reduce features
            self.assertEqual(str(output_gdf.crs), "EPSG:3857")

    def test_etl_with_buffer(self):
        """Test ETL with buffer operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/buffered.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
                operation="buffer",
                operation_params={"distance": 1000, "dissolve": False},
            )

            self.assertTrue(summary["success"])
            self.assertEqual(summary["operation"], "buffer")

            # Verify output
            output_gdf = gpd.read_file(output_path)
            self.assertEqual(len(output_gdf), 5)  # Buffer without dissolve keeps count
            self.assertEqual(str(output_gdf.crs), "EPSG:3857")

    def test_etl_with_buffer_dissolve(self):
        """Test ETL with buffer + dissolve operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/buffered.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
                operation="buffer",
                operation_params={"distance": 1000, "dissolve": True},
            )

            self.assertTrue(summary["success"])
            self.assertEqual(summary["operation"], "buffer")

            # Verify output
            output_gdf = gpd.read_file(output_path)
            self.assertEqual(len(output_gdf), 1)  # Buffer with dissolve merges all
            self.assertEqual(str(output_gdf.crs), "EPSG:3857")

    def test_etl_with_dissolve_all(self):
        """Test ETL with dissolve all-to-one operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/dissolved.gpkg"

            summary = run_etl_pipeline(
                input_path=self.polygons_path,
                output_path=output_path,
                target_epsg=3857,
                operation="dissolve",
                operation_params={},
            )

            self.assertTrue(summary["success"])
            self.assertEqual(summary["operation"], "dissolve")

            # Verify output
            output_gdf = gpd.read_file(output_path)
            self.assertEqual(len(output_gdf), 1)  # All dissolved to one
            self.assertEqual(str(output_gdf.crs), "EPSG:3857")

    def test_etl_with_dissolve_by_attribute(self):
        """Test ETL with dissolve by attribute operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/dissolved.gpkg"

            summary = run_etl_pipeline(
                input_path=self.polygons_path,
                output_path=output_path,
                target_epsg=3857,
                operation="dissolve",
                operation_params={"dissolve_by": "region"},
            )

            self.assertTrue(summary["success"])
            self.assertEqual(summary["operation"], "dissolve")

            # Verify output
            output_gdf = gpd.read_file(output_path)
            self.assertEqual(len(output_gdf), 3)  # Three regions
            self.assertIn("region", output_gdf.columns)
            self.assertEqual(str(output_gdf.crs), "EPSG:3857")

    def test_etl_crs_transformation(self):
        """Test that CRS is correctly transformed through pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            # Input: EPSG:4326, Target: EPSG:32633 (UTM zone 33N)
            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=32633,
            )

            self.assertTrue(summary["success"])

            # Check intermediate stages
            self.assertEqual(
                summary["stages"]["03_reprojection"]["target_crs"],
                "EPSG:32633",
            )

            # Check final output
            output_gdf = gpd.read_file(output_path)
            self.assertEqual(str(output_gdf.crs), "EPSG:32633")

    def test_etl_attribute_preservation(self):
        """Test that attributes are preserved through ETL pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
            )

            self.assertTrue(summary["success"])

            # Check output has all original attributes
            output_gdf = gpd.read_file(output_path)
            self.assertIn("id", output_gdf.columns)
            self.assertIn("category", output_gdf.columns)
            self.assertIn("value", output_gdf.columns)
            self.assertEqual(len(output_gdf), 5)

    def test_etl_output_directory_creation(self):
        """Test that output directories are created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/deep/nested/path/output.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
            )

            self.assertTrue(summary["success"])
            self.assertTrue(Path(output_path).exists())

    def test_etl_missing_input_file(self):
        """Test error handling for missing input file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            with self.assertRaises(FileNotFoundError):
                run_etl_pipeline(
                    input_path="/nonexistent/file.shp",
                    output_path=output_path,
                    target_epsg=3857,
                )

    def test_etl_clip_missing_clip_path(self):
        """Test error handling for clip operation without clip path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            with self.assertRaises(ValueError):
                run_etl_pipeline(
                    input_path=self.points_path,
                    output_path=output_path,
                    target_epsg=3857,
                    operation="clip",
                    clip_path=None,
                )

    def test_etl_buffer_missing_distance(self):
        """Test error handling for buffer operation without distance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            with self.assertRaises(ValueError):
                run_etl_pipeline(
                    input_path=self.points_path,
                    output_path=output_path,
                    target_epsg=3857,
                    operation="buffer",
                    operation_params={},
                )

    def test_etl_invalid_operation(self):
        """Test error handling for invalid operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            with self.assertRaises(ValueError):
                run_etl_pipeline(
                    input_path=self.points_path,
                    output_path=output_path,
                    target_epsg=3857,
                    operation="invalid_op",
                )

    def test_etl_summary_structure(self):
        """Test that ETL summary has correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
            )

            # Verify summary structure
            self.assertIn("success", summary)
            self.assertIn("input_path", summary)
            self.assertIn("output_path", summary)
            self.assertIn("target_epsg", summary)
            self.assertIn("stages", summary)

            # Verify stage results
            stages = summary["stages"]
            self.assertIn("01_raw_inspection", stages)
            self.assertIn("02_geometry_validation", stages)
            self.assertIn("03_reprojection", stages)
            self.assertIn("04_geoprocessing", stages)
            self.assertIn("05_final_output", stages)

    def test_etl_feature_count_tracking(self):
        """Test that feature counts are accurately tracked through stages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
            )

            # Check raw inspection count
            self.assertEqual(
                summary["stages"]["01_raw_inspection"]["feature_count"], 5
            )

            # Check final output count
            self.assertEqual(
                summary["stages"]["05_final_output"]["feature_count"], 5
            )

    def test_etl_clip_reduces_features(self):
        """Test that clip operation reduces feature count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/clipped.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
                operation="clip",
                clip_path=self.clip_path,
            )

            # Raw had 5 features, clipped should have fewer
            raw_count = summary["stages"]["01_raw_inspection"]["feature_count"]
            clipped_count = summary["stages"]["04_geoprocessing"]["output_count"]

            self.assertEqual(raw_count, 5)
            self.assertLess(clipped_count, raw_count)

    def test_etl_dissolve_reduces_features(self):
        """Test that dissolve all-to-one reduces to single feature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/dissolved.gpkg"

            summary = run_etl_pipeline(
                input_path=self.polygons_path,
                output_path=output_path,
                target_epsg=3857,
                operation="dissolve",
                operation_params={},
            )

            # Should reduce from 3 to 1 feature
            self.assertEqual(
                summary["stages"]["04_geoprocessing"]["output_count"], 1
            )

    def test_etl_drop_unfixable_geometries(self):
        """Test drop_unfixable flag during validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/output.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
                drop_unfixable=True,
            )

            self.assertTrue(summary["success"])
            # Points dataset has no invalid geometries, so count should be same
            self.assertEqual(
                summary["stages"]["02_geometry_validation"]["features_dropped"], 0
            )

    def test_etl_complex_workflow(self):
        """Test complex multi-stage ETL: validate → reproject → clip → output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/complex_output.gpkg"

            summary = run_etl_pipeline(
                input_path=self.points_path,
                output_path=output_path,
                target_epsg=3857,
                operation="clip",
                clip_path=self.clip_path,
            )

            self.assertTrue(summary["success"])

            # Verify all stages executed
            stages = summary["stages"]
            self.assertEqual(stages["01_raw_inspection"]["feature_count"], 5)
            self.assertEqual(stages["03_reprojection"]["new_crs"], "EPSG:3857")
            self.assertLess(
                stages["04_geoprocessing"]["output_count"],
                stages["01_raw_inspection"]["feature_count"],
            )

            # Verify final output
            output_gdf = gpd.read_file(output_path)
            self.assertEqual(str(output_gdf.crs), "EPSG:3857")


if __name__ == "__main__":
    unittest.main()
