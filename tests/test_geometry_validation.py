#!/usr/bin/env python3
"""
Unit tests for geometry_validation.py
"""

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, LinearRing

from gis_bootcamp.geometry_validation import validate_and_repair_dataset


class TestGeometryValidation(unittest.TestCase):
    """Test suite for geometry validation and repair."""

    def setUp(self):
        """Create temporary test datasets."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def _create_valid_gdf(self, filename: str) -> Path:
        """Create a valid GeoDataFrame."""
        data = {
            "id": [1, 2, 3],
            "name": ["A", "B", "C"],
            "geometry": [
                Point(0, 0),
                Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                Point(2, 2),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def _create_invalid_gdf(self, filename: str) -> Path:
        """Create a GeoDataFrame with invalid geometries."""
        # Self-intersecting polygon (figure-eight/bowtie)
        invalid_poly = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
        
        data = {
            "id": [1, 2, 3, 4],
            "name": ["Valid Point", "Invalid Poly", "Null Geom", "Valid Poly"],
            "geometry": [
                Point(0, 0),
                invalid_poly,
                None,
                Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def _create_empty_geom_gdf(self, filename: str) -> Path:
        """Create a GeoDataFrame with empty geometries."""
        data = {
            "id": [1, 2],
            "geometry": [
                Point(0, 0),
                Polygon(),  # Empty polygon
            ],
        }
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        output_path = self.temp_path / filename
        gdf.to_file(output_path)
        return output_path

    def test_validate_valid_dataset(self):
        """Test validation of a dataset with all valid geometries."""
        input_file = self._create_valid_gdf("valid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        results = validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertEqual(results["initial_count"], 3)
        self.assertEqual(results["invalid_geometries"], 0)
        self.assertEqual(results["null_geometries"], 0)
        self.assertEqual(results["empty_geometries"], 0)
        self.assertEqual(results["fixed_count"], 0)
        self.assertEqual(results["final_count"], 3)

    def test_validate_dataset_with_invalid_geometry(self):
        """Test detection of invalid geometries."""
        input_file = self._create_invalid_gdf("invalid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        results = validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertEqual(results["initial_count"], 4)
        self.assertGreater(results["invalid_geometries"], 0)
        self.assertEqual(results["null_geometries"], 1)
        # Should keep all rows by default
        self.assertEqual(results["final_count"], 4)
        self.assertEqual(results["dropped_count"], 0)

    def test_repair_invalid_geometry(self):
        """Test that invalid geometries are repaired."""
        input_file = self._create_invalid_gdf("invalid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        results = validate_and_repair_dataset(str(input_file), str(output_file))

        # Should have attempted repairs
        self.assertGreater(results["fixed_count"] + results["unfixable_count"], 0)

        # Verify output file created
        self.assertTrue(output_file.exists())

    def test_drop_unfixable_geometries(self):
        """Test that unfixable geometries are dropped when flag is set."""
        input_file = self._create_invalid_gdf("invalid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        results = validate_and_repair_dataset(
            str(input_file), str(output_file), drop_unfixable=True
        )

        # If there are unfixable geometries, they should be dropped
        if results["unfixable_count"] > 0:
            self.assertLess(results["final_count"], results["initial_count"])
            self.assertGreater(results["dropped_count"], 0)
        # Otherwise, final count should equal initial count
        self.assertLessEqual(results["final_count"], results["initial_count"])

    def test_keep_unfixable_geometries_default(self):
        """Test that unfixable geometries are kept by default."""
        input_file = self._create_invalid_gdf("invalid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        results = validate_and_repair_dataset(
            str(input_file), str(output_file), drop_unfixable=False
        )

        # All rows should be kept when drop_unfixable=False
        self.assertEqual(results["final_count"], results["initial_count"])
        self.assertEqual(results["dropped_count"], 0)

    def test_detect_null_geometries(self):
        """Test detection of null geometries."""
        input_file = self._create_invalid_gdf("invalid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        results = validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertEqual(results["null_geometries"], 1)

    def test_detect_empty_geometries(self):
        """Test detection of empty geometries."""
        input_file = self._create_empty_geom_gdf("empty.gpkg")
        output_file = self.temp_path / "output.gpkg"

        results = validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertGreaterEqual(results["empty_geometries"], 1)

    def test_output_file_created(self):
        """Test that output file is created."""
        input_file = self._create_valid_gdf("valid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        self.assertFalse(output_file.exists())

        validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertTrue(output_file.exists())

    def test_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist."""
        input_file = self._create_valid_gdf("valid.gpkg")
        output_file = self.temp_path / "new_dir" / "output.gpkg"

        self.assertFalse(output_file.parent.exists())

        validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertTrue(output_file.exists())
        self.assertTrue(output_file.parent.exists())

    def test_attributes_preserved(self):
        """Test that attributes are preserved after repair."""
        input_file = self._create_invalid_gdf("invalid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        validate_and_repair_dataset(str(input_file), str(output_file))

        input_gdf = gpd.read_file(input_file)
        output_gdf = gpd.read_file(output_file)

        # Same columns should exist
        self.assertEqual(set(input_gdf.columns), set(output_gdf.columns))

    def test_crs_preserved(self):
        """Test that CRS is preserved after repair."""
        input_file = self._create_valid_gdf("valid.gpkg")
        output_file = self.temp_path / "output.gpkg"

        validate_and_repair_dataset(str(input_file), str(output_file))

        input_gdf = gpd.read_file(input_file)
        output_gdf = gpd.read_file(output_file)

        self.assertEqual(input_gdf.crs, output_gdf.crs)

    def test_file_not_found(self):
        """Test FileNotFoundError for missing input file."""
        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(FileNotFoundError):
            validate_and_repair_dataset(
                "/nonexistent/path/file.gpkg",
                str(output_file)
            )

    def test_empty_dataset(self):
        """Test ValueError for empty dataset."""
        empty_gdf = gpd.GeoDataFrame(
            {"id": [], "geometry": []}, crs="EPSG:4326"
        )
        input_file = self.temp_path / "empty.gpkg"
        empty_gdf.to_file(input_file)

        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertIn("empty", str(context.exception).lower())

    def test_no_geometry_column(self):
        """Test ValueError if geometry column is missing."""
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        input_file = self.temp_path / "no_geometry.csv"
        df.to_csv(input_file, index=False)

        output_file = self.temp_path / "output.gpkg"

        with self.assertRaises(ValueError) as context:
            validate_and_repair_dataset(str(input_file), str(output_file))

        self.assertIn("geometry", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
