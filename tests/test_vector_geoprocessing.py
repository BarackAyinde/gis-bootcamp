#!/usr/bin/env python3
"""
Unit tests for vector_geoprocessing.py
"""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon, box

from gis_bootcamp.vector_geoprocessing import (
    clip_dataset,
    buffer_dataset,
    dissolve_dataset,
)


class TestVectorGeoprocessing(unittest.TestCase):
    """Test suite for vector geoprocessing operations."""

    def setUp(self):
        """Create temporary test datasets."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def _create_points_gdf(self, filename: str) -> Path:
        """Create a points GeoDataFrame."""
        data = {
            "id": [1, 2, 3, 4, 5],
            "name": ["A", "B", "C", "D", "E"],
            "category": ["X", "Y", "X", "Y", "Z"],
            "geometry": [
                Point(0, 0),
                Point(1, 1),
                Point(2, 2),
                Point(3, 3),
                Point(4, 4),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def _create_polygons_gdf(self, filename: str) -> Path:
        """Create a polygons GeoDataFrame."""
        data = {
            "id": [1, 2, 3],
            "region": ["North", "Central", "South"],
            "population": [100, 200, 150],
            "geometry": [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(1, 1), (2, 1), (2, 2), (1, 2)]),
                Polygon([(0, -1), (1, -1), (1, 0), (0, 0)]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def _create_clip_geom(self, filename: str) -> Path:
        """Create a clipping geometry."""
        data = {
            "id": [1],
            "geometry": [box(0.5, 0.5, 2.5, 2.5)],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def test_clip_operation(self):
        """Test basic clip operation."""
        input_file = self._create_points_gdf("points.gpkg")
        clip_file = self._create_clip_geom("clip.gpkg")
        output_file = self.temp_path / "clipped.gpkg"

        results = clip_dataset(str(input_file), str(clip_file), str(output_file))

        self.assertEqual(results["operation"], "clip")
        self.assertGreater(results["input_count"], 0)
        self.assertLessEqual(results["output_count"], results["input_count"])
        self.assertTrue(output_file.exists())

    def test_clip_reduces_feature_count(self):
        """Test that clip reduces feature count when appropriate."""
        input_file = self._create_points_gdf("points.gpkg")
        clip_file = self._create_clip_geom("clip.gpkg")
        output_file = self.temp_path / "clipped.gpkg"

        results = clip_dataset(str(input_file), str(clip_file), str(output_file))

        # Clipping should reduce count
        self.assertLess(results["output_count"], results["input_count"])
        self.assertGreater(results["features_clipped"], 0)

    def test_clip_preserves_attributes(self):
        """Test that clip preserves attributes."""
        input_file = self._create_points_gdf("points.gpkg")
        clip_file = self._create_clip_geom("clip.gpkg")
        output_file = self.temp_path / "clipped.gpkg"

        clip_dataset(str(input_file), str(clip_file), str(output_file))

        input_gdf = gpd.read_file(input_file)
        output_gdf = gpd.read_file(output_file)

        # Columns should match
        self.assertEqual(set(input_gdf.columns), set(output_gdf.columns))

    def test_clip_preserves_crs(self):
        """Test that clip preserves CRS."""
        input_file = self._create_points_gdf("points.gpkg")
        clip_file = self._create_clip_geom("clip.gpkg")
        output_file = self.temp_path / "clipped.gpkg"

        clip_dataset(str(input_file), str(clip_file), str(output_file))

        input_gdf = gpd.read_file(input_file)
        output_gdf = gpd.read_file(output_file)

        self.assertEqual(input_gdf.crs, output_gdf.crs)

    def test_buffer_operation(self):
        """Test basic buffer operation."""
        input_file = self._create_points_gdf("points.gpkg")
        output_file = self.temp_path / "buffered.gpkg"

        results = buffer_dataset(str(input_file), str(output_file), distance=0.5)

        self.assertEqual(results["operation"], "buffer")
        self.assertEqual(results["distance"], 0.5)
        self.assertEqual(results["output_count"], results["input_count"])
        self.assertTrue(output_file.exists())

    def test_buffer_with_dissolve(self):
        """Test buffer with dissolve flag."""
        input_file = self._create_points_gdf("points.gpkg")
        output_file = self.temp_path / "buffered.gpkg"

        results = buffer_dataset(
            str(input_file), str(output_file), distance=1.0, dissolve=True
        )

        self.assertTrue(results["dissolve"])
        self.assertEqual(results["output_count"], 1)  # All dissolved into one

    def test_buffer_without_dissolve(self):
        """Test buffer without dissolve (default)."""
        input_file = self._create_points_gdf("points.gpkg")
        output_file = self.temp_path / "buffered.gpkg"

        results = buffer_dataset(
            str(input_file), str(output_file), distance=0.5, dissolve=False
        )

        self.assertFalse(results["dissolve"])
        self.assertEqual(results["output_count"], results["input_count"])

    def test_buffer_preserves_crs(self):
        """Test that buffer preserves CRS."""
        input_file = self._create_points_gdf("points.gpkg")
        output_file = self.temp_path / "buffered.gpkg"

        buffer_dataset(str(input_file), str(output_file), distance=0.5)

        input_gdf = gpd.read_file(input_file)
        output_gdf = gpd.read_file(output_file)

        self.assertEqual(input_gdf.crs, output_gdf.crs)

    def test_dissolve_all_features(self):
        """Test dissolve without grouping (all into one)."""
        input_file = self._create_polygons_gdf("polygons.gpkg")
        output_file = self.temp_path / "dissolved.gpkg"

        results = dissolve_dataset(str(input_file), str(output_file))

        self.assertEqual(results["operation"], "dissolve")
        self.assertIsNone(results["dissolve_by"])
        self.assertEqual(results["output_count"], 1)  # All dissolved into one
        self.assertTrue(output_file.exists())

    def test_dissolve_by_attribute(self):
        """Test dissolve by an attribute."""
        input_file = self._create_polygons_gdf("polygons.gpkg")
        output_file = self.temp_path / "dissolved.gpkg"

        results = dissolve_dataset(
            str(input_file), str(output_file), dissolve_by="region"
        )

        self.assertEqual(results["dissolve_by"], "region")
        self.assertEqual(results["output_count"], 3)  # One per region
        self.assertTrue(output_file.exists())

    def test_dissolve_reduces_feature_count(self):
        """Test that dissolve reduces feature count."""
        input_file = self._create_points_gdf("points.gpkg")
        output_file = self.temp_path / "dissolved.gpkg"

        results = dissolve_dataset(
            str(input_file), str(output_file), dissolve_by="category"
        )

        self.assertLess(results["output_count"], results["input_count"])
        self.assertGreater(results["features_dissolved"], 0)

    def test_dissolve_preserves_crs(self):
        """Test that dissolve preserves CRS."""
        input_file = self._create_polygons_gdf("polygons.gpkg")
        output_file = self.temp_path / "dissolved.gpkg"

        dissolve_dataset(str(input_file), str(output_file))

        input_gdf = gpd.read_file(input_file)
        output_gdf = gpd.read_file(output_file)

        self.assertEqual(input_gdf.crs, output_gdf.crs)

    def test_dissolve_invalid_column(self):
        """Test that dissolve with invalid column raises ValueError."""
        input_file = self._create_polygons_gdf("polygons.gpkg")
        output_file = self.temp_path / "dissolved.gpkg"

        with self.assertRaises(ValueError) as context:
            dissolve_dataset(
                str(input_file), str(output_file), dissolve_by="nonexistent"
            )

        self.assertIn("not found", str(context.exception).lower())

    def test_clip_input_file_not_found(self):
        """Test FileNotFoundError for missing input file."""
        clip_file = self._create_clip_geom("clip.gpkg")
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(FileNotFoundError):
            clip_dataset("/nonexistent/input.gpkg", str(clip_file), str(output_file))

    def test_clip_clip_file_not_found(self):
        """Test FileNotFoundError for missing clip file."""
        input_file = self._create_points_gdf("points.gpkg")
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(FileNotFoundError):
            clip_dataset(str(input_file), "/nonexistent/clip.gpkg", str(output_file))

    def test_buffer_input_file_not_found(self):
        """Test FileNotFoundError for missing input file."""
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(FileNotFoundError):
            buffer_dataset("/nonexistent/input.gpkg", str(output_file), 1.0)

    def test_dissolve_input_file_not_found(self):
        """Test FileNotFoundError for missing input file."""
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(FileNotFoundError):
            dissolve_dataset("/nonexistent/input.gpkg", str(output_file))

    def test_clip_empty_input(self):
        """Test ValueError for empty input dataset."""
        empty_gdf = gpd.GeoDataFrame({"id": [], "geometry": []}, crs="EPSG:4326")
        input_file = self.temp_path / "empty.gpkg"
        empty_gdf.to_file(input_file)

        clip_file = self._create_clip_geom("clip.gpkg")
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            clip_dataset(str(input_file), str(clip_file), str(output_file))

        self.assertIn("empty", str(context.exception).lower())

    def test_buffer_empty_input(self):
        """Test ValueError for empty input dataset."""
        empty_gdf = gpd.GeoDataFrame({"id": [], "geometry": []}, crs="EPSG:4326")
        input_file = self.temp_path / "empty.gpkg"
        empty_gdf.to_file(input_file)

        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            buffer_dataset(str(input_file), str(output_file), 1.0)

        self.assertIn("empty", str(context.exception).lower())

    def test_dissolve_empty_input(self):
        """Test ValueError for empty input dataset."""
        empty_gdf = gpd.GeoDataFrame({"id": [], "geometry": []}, crs="EPSG:4326")
        input_file = self.temp_path / "empty.gpkg"
        empty_gdf.to_file(input_file)

        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            dissolve_dataset(str(input_file), str(output_file))

        self.assertIn("empty", str(context.exception).lower())

    def test_output_directory_creation(self):
        """Test that output directory is created."""
        input_file = self._create_points_gdf("points.gpkg")
        output_file = self.temp_path / "new_dir" / "output.gpkg"

        self.assertFalse(output_file.parent.exists())

        buffer_dataset(str(input_file), str(output_file), 1.0)

        self.assertTrue(output_file.exists())
        self.assertTrue(output_file.parent.exists())


if __name__ == "__main__":
    unittest.main()
