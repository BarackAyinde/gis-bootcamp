#!/usr/bin/env python3
"""
Unit tests for spatial_join.py
"""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, Polygon

from gis_bootcamp.spatial_join import spatial_join


class TestSpatialJoin(unittest.TestCase):
    """Test suite for spatial joins."""

    def setUp(self):
        """Create temporary test datasets."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def _create_points_gdf(self, filename: str, crs: str = "EPSG:4326") -> Path:
        """Create a points GeoDataFrame."""
        data = {
            "id": [1, 2, 3, 4],
            "name": ["Point A", "Point B", "Point C", "Point D"],
            "geometry": [
                Point(0.5, 0.5),    # Inside first polygon
                Point(1.5, 1.5),    # Inside second polygon
                Point(2.5, 2.5),    # Outside all polygons
                Point(0.1, 0.1),    # Inside first polygon
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs=crs)
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def _create_polygons_gdf(self, filename: str, crs: str = "EPSG:4326") -> Path:
        """Create a polygons GeoDataFrame."""
        data = {
            "id": [1, 2],
            "name": ["Polygon A", "Polygon B"],
            "value": [100, 200],
            "geometry": [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(1.5, 1.5), (2.5, 1.5), (2.5, 2.5), (1.5, 2.5)]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs=crs)
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def test_spatial_join_intersects_left(self):
        """Test left join with intersects predicate."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        metadata = spatial_join(
            str(points), str(polygons), str(output),
            predicate="intersects", how="left"
        )

        self.assertEqual(metadata["predicate"], "intersects")
        self.assertEqual(metadata["how"], "left")
        self.assertEqual(metadata["left_count"], 4)
        self.assertEqual(metadata["right_count"], 2)
        self.assertGreater(metadata["joined_count"], 0)

        # Verify output file was created
        self.assertTrue(output.exists())

    def test_spatial_join_within(self):
        """Test join with within predicate (point-in-polygon)."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        metadata = spatial_join(
            str(points), str(polygons), str(output),
            predicate="within", how="left"
        )

        self.assertEqual(metadata["predicate"], "within")
        self.assertEqual(metadata["left_count"], 4)

        # Verify output
        result = gpd.read_file(output)
        self.assertEqual(len(result), 4)  # Left join keeps all left features

    def test_spatial_join_contains(self):
        """Test join with contains predicate."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        metadata = spatial_join(
            str(points), str(polygons), str(output),
            predicate="contains", how="left"
        )

        self.assertEqual(metadata["predicate"], "contains")

        result = gpd.read_file(output)
        self.assertTrue(len(result) > 0)

    def test_spatial_join_inner(self):
        """Test inner join (only matching features)."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        metadata = spatial_join(
            str(points), str(polygons), str(output),
            predicate="within", how="inner"
        )

        self.assertEqual(metadata["how"], "inner")
        # Inner join should have fewer features than left
        self.assertLessEqual(
            metadata["joined_count"], metadata["left_count"]
        )

    def test_spatial_join_right(self):
        """Test right join (keep all right features)."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        metadata = spatial_join(
            str(points), str(polygons), str(output),
            predicate="within", how="right"
        )

        self.assertEqual(metadata["how"], "right")
        # Right join should have at least as many features as right
        self.assertGreaterEqual(
            metadata["joined_count"], metadata["right_count"]
        )

    def test_spatial_join_crs_mismatch(self):
        """Test that CRS mismatch is handled by reprojection."""
        points = self._create_points_gdf("points_4326.gpkg", crs="EPSG:4326")
        polygons = self._create_polygons_gdf("polygons_3857.gpkg", crs="EPSG:3857")
        output = self.temp_path / "joined.gpkg"

        metadata = spatial_join(
            str(points), str(polygons), str(output),
            predicate="within"
        )

        self.assertEqual(metadata["left_crs"], "EPSG:4326")
        self.assertEqual(metadata["right_crs"], "EPSG:3857")

        # Verify output was created despite CRS mismatch
        self.assertTrue(output.exists())

        result = gpd.read_file(output)
        self.assertEqual(str(result.crs), "EPSG:4326")

    def test_spatial_join_preserves_attributes(self):
        """Test that attributes from both datasets are preserved."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        metadata = spatial_join(
            str(points), str(polygons), str(output),
            predicate="within"
        )

        # Check attribute counts
        self.assertGreater(len(metadata["left_attributes"]), 0)
        self.assertGreater(len(metadata["right_attributes"]), 0)
        self.assertGreater(len(metadata["joined_attributes"]), 0)

        # Verify output has attributes from both
        result = gpd.read_file(output)
        self.assertIn("id_left", result.columns)  # From left dataset
        self.assertIn("id_right", result.columns)  # From right dataset

    def test_spatial_join_left_file_not_found(self):
        """Test FileNotFoundError for missing left file."""
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        with self.assertRaises(FileNotFoundError):
            spatial_join(
                "/nonexistent/left.gpkg",
                str(polygons),
                str(output)
            )

    def test_spatial_join_right_file_not_found(self):
        """Test FileNotFoundError for missing right file."""
        points = self._create_points_gdf("points.gpkg")
        output = self.temp_path / "joined.gpkg"

        with self.assertRaises(FileNotFoundError):
            spatial_join(
                str(points),
                "/nonexistent/right.gpkg",
                str(output)
            )

    def test_spatial_join_invalid_predicate(self):
        """Test ValueError for invalid predicate."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        with self.assertRaises(ValueError) as context:
            spatial_join(
                str(points),
                str(polygons),
                str(output),
                predicate="invalid_predicate"
            )

        self.assertIn("Invalid predicate", str(context.exception))

    def test_spatial_join_empty_left(self):
        """Test ValueError for empty left dataset."""
        empty_left = gpd.GeoDataFrame(
            {"id": [], "geometry": []}, crs="EPSG:4326"
        )
        left_file = self.temp_path / "empty_left.gpkg"
        empty_left.to_file(left_file)

        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        with self.assertRaises(ValueError) as context:
            spatial_join(str(left_file), str(polygons), str(output))

        self.assertIn("empty", str(context.exception).lower())

    def test_spatial_join_empty_right(self):
        """Test ValueError for empty right dataset."""
        points = self._create_points_gdf("points.gpkg")

        empty_right = gpd.GeoDataFrame(
            {"id": [], "geometry": []}, crs="EPSG:4326"
        )
        right_file = self.temp_path / "empty_right.gpkg"
        empty_right.to_file(right_file)

        output = self.temp_path / "joined.gpkg"

        with self.assertRaises(ValueError) as context:
            spatial_join(str(points), str(right_file), str(output))

        self.assertIn("empty", str(context.exception).lower())

    def test_spatial_join_left_no_crs(self):
        """Test ValueError for left dataset without CRS."""
        data = {
            "id": [1, 2],
            "geometry": [Point(0, 0), Point(1, 1)],
        }
        gdf_no_crs = gpd.GeoDataFrame(data, crs=None)
        left_file = self.temp_path / "no_crs_left.gpkg"
        gdf_no_crs.to_file(left_file)

        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "joined.gpkg"

        with self.assertRaises(ValueError) as context:
            spatial_join(str(left_file), str(polygons), str(output))

        self.assertIn("no crs", str(context.exception).lower())

    def test_spatial_join_right_no_crs(self):
        """Test ValueError for right dataset without CRS."""
        points = self._create_points_gdf("points.gpkg")

        data = {
            "id": [1, 2],
            "geometry": [
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
            ],
        }
        gdf_no_crs = gpd.GeoDataFrame(data, crs=None)
        right_file = self.temp_path / "no_crs_right.gpkg"
        gdf_no_crs.to_file(right_file)

        output = self.temp_path / "joined.gpkg"

        with self.assertRaises(ValueError) as context:
            spatial_join(str(points), str(right_file), str(output))

        self.assertIn("no crs", str(context.exception).lower())

    def test_spatial_join_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist."""
        points = self._create_points_gdf("points.gpkg")
        polygons = self._create_polygons_gdf("polygons.gpkg")
        output = self.temp_path / "new_dir" / "joined.gpkg"

        self.assertFalse(output.parent.exists())

        spatial_join(str(points), str(polygons), str(output))

        self.assertTrue(output.exists())
        self.assertTrue(output.parent.exists())


if __name__ == "__main__":
    unittest.main()
