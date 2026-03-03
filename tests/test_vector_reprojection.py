#!/usr/bin/env python3
"""
Unit tests for vector_reprojection.py
"""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon

from gis_bootcamp.vector_reprojection import reproject_dataset


class TestVectorReprojection(unittest.TestCase):
    """Test suite for vector reprojection."""

    def setUp(self):
        """Create temporary test datasets."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def _create_test_gdf(
        self, filename: str, crs: str = "EPSG:4326"
    ) -> Path:
        """Helper to create a simple point GeoDataFrame."""
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

    def _create_polygon_gdf(self, filename: str, crs: str) -> Path:
        """Helper to create a polygon GeoDataFrame."""
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

    def test_reproject_wgs84_to_web_mercator(self):
        """Test reprojection from WGS84 to Web Mercator."""
        input_file = self._create_test_gdf("points_4326.gpkg", crs="EPSG:4326")
        output_file = self.temp_path / "points_3857.gpkg"

        metadata = reproject_dataset(
            str(input_file), str(output_file), "EPSG:3857"
        )

        self.assertEqual(metadata["source_crs"], "EPSG:4326")
        self.assertEqual(metadata["target_crs"], "EPSG:3857")
        self.assertEqual(metadata["feature_count"], 3)

        # Verify output file was created
        self.assertTrue(output_file.exists())

        # Verify output has correct CRS
        output_gdf = gpd.read_file(output_file)
        self.assertEqual(str(output_gdf.crs), "EPSG:3857")
        self.assertEqual(len(output_gdf), 3)

    def test_reproject_wgs84_to_utm(self):
        """Test reprojection to UTM zone."""
        input_file = self._create_test_gdf("points_4326.gpkg", crs="EPSG:4326")
        output_file = self.temp_path / "points_utm.gpkg"

        metadata = reproject_dataset(
            str(input_file), str(output_file), "EPSG:32633"
        )

        self.assertEqual(metadata["target_crs"], "EPSG:32633")

        output_gdf = gpd.read_file(output_file)
        self.assertEqual(str(output_gdf.crs), "EPSG:32633")

    def test_reproject_preserves_attributes(self):
        """Test that all attributes are preserved during reprojection."""
        input_file = self._create_test_gdf("points_4326.gpkg", crs="EPSG:4326")
        output_file = self.temp_path / "points_3857.gpkg"

        metadata = reproject_dataset(
            str(input_file), str(output_file), "EPSG:3857"
        )

        input_gdf = gpd.read_file(input_file)
        output_gdf = gpd.read_file(output_file)

        # Check attribute columns match
        self.assertEqual(
            set(input_gdf.columns), set(output_gdf.columns)
        )

        # Check data preserved
        self.assertEqual(list(output_gdf["id"]), [1, 2, 3])
        self.assertEqual(
            list(output_gdf["name"]),
            ["Point A", "Point B", "Point C"],
        )
        self.assertEqual(list(output_gdf["value"]), [10, 20, 30])

    def test_reproject_preserves_geometry_type(self):
        """Test that geometry types are preserved."""
        input_file = self._create_polygon_gdf(
            "polygons_4326.gpkg", crs="EPSG:4326"
        )
        output_file = self.temp_path / "polygons_3857.gpkg"

        metadata = reproject_dataset(
            str(input_file), str(output_file), "EPSG:3857"
        )

        self.assertEqual(metadata["geometry_types"]["Polygon"], 2)

        output_gdf = gpd.read_file(output_file)
        self.assertEqual(len(output_gdf.geometry.type.unique()), 1)
        self.assertEqual(output_gdf.geometry.type.iloc[0], "Polygon")

    def test_reproject_feature_count_preserved(self):
        """Test that feature count is preserved."""
        input_file = self._create_test_gdf("points_4326.gpkg", crs="EPSG:4326")
        output_file = self.temp_path / "points_3857.gpkg"

        metadata = reproject_dataset(
            str(input_file), str(output_file), "EPSG:3857"
        )

        input_gdf = gpd.read_file(input_file)
        self.assertEqual(metadata["feature_count"], len(input_gdf))

    def test_invalid_epsg_format(self):
        """Test that invalid EPSG format raises ValueError."""
        input_file = self._create_test_gdf("points_4326.gpkg", crs="EPSG:4326")
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            reproject_dataset(str(input_file), str(output_file), "3857")

        self.assertIn("Invalid EPSG format", str(context.exception))

    def test_missing_crs_in_input(self):
        """Test that missing CRS raises ValueError."""
        # Create a GeoDataFrame without CRS
        data = {
            "id": [1, 2],
            "geometry": [Point(0, 0), Point(1, 1)],
        }
        gdf = gpd.GeoDataFrame(data, crs=None)
        input_file = self.temp_path / "no_crs.gpkg"
        gdf.to_file(input_file)

        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            reproject_dataset(str(input_file), str(output_file), "EPSG:3857")

        self.assertIn("no crs defined", str(context.exception).lower())

    def test_file_not_found(self):
        """Test that FileNotFoundError is raised for missing input file."""
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(FileNotFoundError):
            reproject_dataset(
                "/nonexistent/path/file.gpkg",
                str(output_file),
                "EPSG:3857",
            )

    def test_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist."""
        input_file = self._create_test_gdf("points_4326.gpkg", crs="EPSG:4326")
        output_file = self.temp_path / "new_dir" / "output.gpkg"

        self.assertFalse(output_file.parent.exists())

        reproject_dataset(str(input_file), str(output_file), "EPSG:3857")

        self.assertTrue(output_file.exists())
        self.assertTrue(output_file.parent.exists())

    def test_empty_dataset(self):
        """Test that ValueError is raised for empty dataset."""
        empty_gdf = gpd.GeoDataFrame(
            {"id": [], "geometry": []}, crs="EPSG:4326"
        )
        input_file = self.temp_path / "empty.gpkg"
        empty_gdf.to_file(input_file)

        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            reproject_dataset(str(input_file), str(output_file), "EPSG:3857")

        self.assertIn("empty", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
