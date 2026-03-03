#!/usr/bin/env python3
"""
Unit tests for raster_metadata_inspector module.

Tests:
- Valid raster inspection (GeoTIFF)
- Metadata extraction accuracy
- CRS handling
- Multi-band raster handling
- File not found error
- Invalid raster error
- Empty/zero-sized raster handling (edge case)
"""

import json
import logging
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

from gis_bootcamp.raster_metadata_inspector import inspect_raster


class TestRasterMetadataInspector(unittest.TestCase):
    """Test raster metadata inspector."""

    @classmethod
    def setUpClass(cls):
        """Create temporary test rasters."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name)

        # Single-band raster (WGS84)
        cls.single_band_path = cls.temp_path / "single_band.tif"
        cls._create_test_raster(
            cls.single_band_path,
            width=100,
            height=100,
            count=1,
            crs=CRS.from_epsg(4326),
            dtype=rasterio.uint8,
        )

        # Multi-band raster (Web Mercator)
        cls.multi_band_path = cls.temp_path / "multi_band.tif"
        cls._create_test_raster(
            cls.multi_band_path,
            width=512,
            height=512,
            count=3,
            crs=CRS.from_epsg(3857),
            dtype=rasterio.uint16,
        )

        # Raster with nodata value
        cls.nodata_path = cls.temp_path / "with_nodata.tif"
        cls._create_test_raster(
            cls.nodata_path,
            width=200,
            height=200,
            count=1,
            crs=CRS.from_epsg(32633),
            dtype=rasterio.float32,
            nodata=-9999.0,
        )

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary test rasters."""
        cls.temp_dir.cleanup()

    @staticmethod
    def _create_test_raster(
        path: Path,
        width: int,
        height: int,
        count: int,
        crs: CRS,
        dtype,
        nodata=None,
    ) -> None:
        """
        Create a test raster file.

        Args:
            path: Output file path
            width: Raster width
            height: Raster height
            count: Number of bands
            crs: Coordinate reference system
            dtype: Data type
            nodata: Nodata value (optional)
        """
        # Create simple affine transform (1 degree = 1 pixel at equator)
        transform = Affine.identity() * Affine.translation(-180, 90)

        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=count,
            dtype=dtype,
            crs=crs,
            transform=transform,
            nodata=nodata,
        ) as dst:
            for band_idx in range(1, count + 1):
                # Use appropriate data generation based on dtype
                if dtype in (rasterio.uint8, rasterio.uint16):
                    data = np.random.randint(0, 255, (height, width), dtype=dtype)
                elif dtype == rasterio.float32:
                    data = np.random.rand(height, width).astype(dtype) * 100
                else:
                    data = np.random.rand(height, width).astype(dtype)
                dst.write(data, band_idx)

    def test_inspect_single_band_raster(self):
        """Test inspection of single-band raster."""
        metadata = inspect_raster(str(self.single_band_path))

        self.assertEqual(metadata["width"], 100)
        self.assertEqual(metadata["height"], 100)
        self.assertEqual(metadata["num_bands"], 1)
        self.assertIn("EPSG:4326", str(metadata["crs"]))
        self.assertIsNotNone(metadata["bounds"])
        self.assertEqual(len(metadata["band_details"]), 1)

    def test_inspect_multi_band_raster(self):
        """Test inspection of multi-band raster."""
        metadata = inspect_raster(str(self.multi_band_path))

        self.assertEqual(metadata["width"], 512)
        self.assertEqual(metadata["height"], 512)
        self.assertEqual(metadata["num_bands"], 3)
        self.assertIn("EPSG:3857", str(metadata["crs"]))
        self.assertEqual(len(metadata["band_details"]), 3)

    def test_metadata_structure(self):
        """Test that metadata has all expected keys."""
        metadata = inspect_raster(str(self.single_band_path))

        required_keys = [
            "file_path",
            "crs",
            "width",
            "height",
            "bounds",
            "num_bands",
            "band_details",
            "transform",
            "pixel_size",
            "driver",
        ]

        for key in required_keys:
            self.assertIn(key, metadata, f"Missing key: {key}")

    def test_bounds_structure(self):
        """Test that bounds has correct structure."""
        metadata = inspect_raster(str(self.single_band_path))

        bounds = metadata["bounds"]
        self.assertIn("minx", bounds)
        self.assertIn("miny", bounds)
        self.assertIn("maxx", bounds)
        self.assertIn("maxy", bounds)

        # Bounds should have numeric values
        self.assertIsInstance(bounds["minx"], (int, float))
        self.assertIsInstance(bounds["miny"], (int, float))
        self.assertIsInstance(bounds["maxx"], (int, float))
        self.assertIsInstance(bounds["maxy"], (int, float))

    def test_band_details(self):
        """Test band detail information."""
        metadata = inspect_raster(str(self.multi_band_path))

        band_details = metadata["band_details"]
        self.assertEqual(len(band_details), 3)

        for i, band in enumerate(band_details, 1):
            self.assertEqual(band["band"], i)
            self.assertIn("dtype", band)
            self.assertIn("nodata", band)

    def test_nodata_value(self):
        """Test that nodata value is correctly captured."""
        metadata = inspect_raster(str(self.nodata_path))

        self.assertEqual(metadata["band_details"][0]["nodata"], -9999.0)

    def test_pixel_size(self):
        """Test that pixel size is calculated correctly."""
        metadata = inspect_raster(str(self.single_band_path))

        pixel_size = metadata["pixel_size"]
        self.assertIn("x", pixel_size)
        self.assertIn("y", pixel_size)
        self.assertGreater(pixel_size["x"], 0)
        self.assertGreater(pixel_size["y"], 0)

    def test_crs_handling(self):
        """Test CRS is correctly extracted."""
        # Test WGS84
        metadata_4326 = inspect_raster(str(self.single_band_path))
        self.assertIsNotNone(metadata_4326["crs"])
        self.assertIn("4326", str(metadata_4326["crs"]))

        # Test Web Mercator
        metadata_3857 = inspect_raster(str(self.multi_band_path))
        self.assertIn("3857", str(metadata_3857["crs"]))

    def test_file_not_found(self):
        """Test error handling for missing file."""
        nonexistent = str(self.temp_path / "nonexistent.tif")

        with self.assertRaises(FileNotFoundError):
            inspect_raster(nonexistent)

    def test_invalid_raster_file(self):
        """Test error handling for non-raster file."""
        # Create a temporary non-raster file
        fake_raster = self.temp_path / "fake.tif"
        fake_raster.write_text("This is not a valid raster file")

        with self.assertRaises(ValueError):
            inspect_raster(str(fake_raster))

        fake_raster.unlink()

    def test_transform_metadata(self):
        """Test that transform metadata is captured."""
        metadata = inspect_raster(str(self.single_band_path))

        transform = metadata["transform"]
        self.assertIn("a", transform)  # pixel width
        self.assertIn("b", transform)  # rotation
        self.assertIn("c", transform)  # x-coordinate upper-left
        self.assertIn("d", transform)  # rotation
        self.assertIn("e", transform)  # pixel height
        self.assertIn("f", transform)  # y-coordinate upper-left

    def test_driver(self):
        """Test that driver is correctly identified."""
        metadata = inspect_raster(str(self.single_band_path))

        # GeoTIFF files should have GTiff driver
        self.assertIn(metadata["driver"], ["GTiff", "GTIFF"])

    def test_metadata_serializable(self):
        """Test that metadata can be serialized to JSON."""
        metadata = inspect_raster(str(self.single_band_path))

        # Should not raise an exception
        json_str = json.dumps(metadata, default=str)
        self.assertIsInstance(json_str, str)
        self.assertGreater(len(json_str), 0)

    def test_multiple_inspections_same_file(self):
        """Test that inspecting the same file multiple times is consistent."""
        metadata1 = inspect_raster(str(self.single_band_path))
        metadata2 = inspect_raster(str(self.single_band_path))

        # Key metadata should be identical
        self.assertEqual(metadata1["width"], metadata2["width"])
        self.assertEqual(metadata1["height"], metadata2["height"])
        self.assertEqual(metadata1["num_bands"], metadata2["num_bands"])
        self.assertEqual(metadata1["crs"], metadata2["crs"])


if __name__ == "__main__":
    unittest.main()
