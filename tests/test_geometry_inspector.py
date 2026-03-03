#!/usr/bin/env python3
"""
Unit tests for geometry_inspector.py
"""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon

from gis_bootcamp.geometry_inspector import inspect_dataset


class TestGeometryInspector(unittest.TestCase):
    """Test suite for geometry inspection."""

    def setUp(self):
        """Create temporary test datasets."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def _create_point_gdf(self, filename: str, crs: str = None) -> Path:
        """Helper to create a point GeoDataFrame and save it."""
        data = {
            "id": [1, 2, 3],
            "name": ["Point A", "Point B", "Point C"],
            "value": [10, 20, 30],
            "geometry": [Point(0, 0), Point(1, 1), Point(2, 2)],
        }
        gdf = gpd.GeoDataFrame(data, crs=crs)
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def _create_polygon_gdf(self, filename: str, crs: str = None) -> Path:
        """Helper to create a polygon GeoDataFrame and save it."""
        data = {
            "id": [1, 2],
            "name": ["Polygon A", "Polygon B"],
            "geometry": [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs=crs)
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def _create_mixed_gdf(self, filename: str) -> Path:
        """Helper to create a mixed geometry GeoDataFrame."""
        data = {
            "id": [1, 2],
            "geometry": [Point(0, 0), Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def test_inspect_points_with_crs(self):
        """Test inspection of point dataset with CRS."""
        file_path = self._create_point_gdf("points.gpkg", crs="EPSG:4326")
        metadata = inspect_dataset(str(file_path))

        self.assertEqual(metadata["feature_count"], 3)
        self.assertEqual(metadata["crs"], "EPSG:4326")
        self.assertEqual(metadata["geometry_types"]["Point"], 3)
        self.assertEqual(metadata["has_null_geometries"], 0)
        self.assertIn("id", metadata["attributes"])
        self.assertIn("name", metadata["attributes"])
        self.assertIn("value", metadata["attributes"])
        self.assertIn("geometry", metadata["attributes"])

    def test_inspect_points_without_crs(self):
        """Test inspection of point dataset without CRS."""
        file_path = self._create_point_gdf("points_no_crs.gpkg", crs=None)
        metadata = inspect_dataset(str(file_path))

        self.assertEqual(metadata["feature_count"], 3)
        self.assertIsNone(metadata["crs"])
        self.assertEqual(metadata["geometry_types"]["Point"], 3)

    def test_inspect_polygons(self):
        """Test inspection of polygon dataset."""
        file_path = self._create_polygon_gdf("polygons.gpkg", crs="EPSG:3857")
        metadata = inspect_dataset(str(file_path))

        self.assertEqual(metadata["feature_count"], 2)
        self.assertEqual(metadata["crs"], "EPSG:3857")
        self.assertEqual(metadata["geometry_types"]["Polygon"], 2)

    def test_inspect_mixed_geometries(self):
        """Test inspection of mixed geometry dataset."""
        file_path = self._create_mixed_gdf("mixed.gpkg")
        metadata = inspect_dataset(str(file_path))

        self.assertEqual(metadata["feature_count"], 2)
        self.assertEqual(metadata["geometry_types"]["Point"], 1)
        self.assertEqual(metadata["geometry_types"]["Polygon"], 1)

    def test_bounding_box(self):
        """Test that bounding box is correctly computed."""
        file_path = self._create_point_gdf("points.gpkg", crs="EPSG:4326")
        metadata = inspect_dataset(str(file_path))

        bounds = metadata["bounds"]
        self.assertEqual(bounds[0], 0.0)  # minx
        self.assertEqual(bounds[1], 0.0)  # miny
        self.assertEqual(bounds[2], 2.0)  # maxx
        self.assertEqual(bounds[3], 2.0)  # maxy

    def test_file_not_found(self):
        """Test that FileNotFoundError is raised for missing file."""
        with self.assertRaises(FileNotFoundError):
            inspect_dataset("/nonexistent/path/file.gpkg")

    def test_empty_dataset(self):
        """Test that ValueError is raised for empty dataset."""
        empty_gdf = gpd.GeoDataFrame(
            {"id": [], "geometry": []}, crs="EPSG:4326"
        )
        file_path = self.temp_path / "empty.gpkg"
        empty_gdf.to_file(file_path)

        with self.assertRaises(ValueError) as context:
            inspect_dataset(str(file_path))
        self.assertIn("empty", str(context.exception).lower())

    def test_no_geometry_column(self):
        """Test that ValueError is raised if geometry column is missing."""
        # Create a DataFrame without geometry
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        file_path = self.temp_path / "no_geometry.csv"
        df.to_csv(file_path, index=False)

        with self.assertRaises(ValueError) as context:
            inspect_dataset(str(file_path))

    def test_attributes_list(self):
        """Test that all attributes are captured."""
        file_path = self._create_point_gdf("points.gpkg", crs="EPSG:4326")
        metadata = inspect_dataset(str(file_path))

        expected_attrs = {"id", "name", "value", "geometry"}
        actual_attrs = set(metadata["attributes"])
        self.assertEqual(actual_attrs, expected_attrs)


if __name__ == "__main__":
    unittest.main()
