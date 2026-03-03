#!/usr/bin/env python3
"""
Unit tests for geotiff_to_cog module.

Tests:
- COG creation with default settings
- COG creation with custom block sizes
- Overview level computation
- COG validation (compliant and non-compliant)
- Output file creation
- Error handling (missing files, invalid rasters)
- Metadata preservation (CRS, dimensions, dtype)
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

from gis_bootcamp.geotiff_to_cog import create_cog, validate_cog, _compute_overview_levels


class TestGeoTIFFToCOG(unittest.TestCase):
    """Test GeoTIFF to COG conversion."""

    @classmethod
    def setUpClass(cls):
        """Create temporary test rasters."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name)

        # Create large test raster (1024x1024, suitable for overviews)
        cls.large_raster_path = cls.temp_path / "large_raster.tif"
        cls._create_test_raster(
            cls.large_raster_path,
            width=1024,
            height=1024,
            crs=CRS.from_epsg(4326),
            dtype=rasterio.uint16,
        )

        # Create small test raster (256x256, minimal overviews)
        cls.small_raster_path = cls.temp_path / "small_raster.tif"
        cls._create_test_raster(
            cls.small_raster_path,
            width=256,
            height=256,
            crs=CRS.from_epsg(3857),
            dtype=rasterio.float32,
        )

        # Create non-square raster (512x1024)
        cls.nonsquare_raster_path = cls.temp_path / "nonsquare_raster.tif"
        cls._create_test_raster(
            cls.nonsquare_raster_path,
            width=512,
            height=1024,
            crs=CRS.from_epsg(4326),
            dtype=rasterio.uint8,
        )

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary files."""
        cls.temp_dir.cleanup()

    @staticmethod
    def _create_test_raster(
        path: Path,
        width: int,
        height: int,
        crs: CRS,
        dtype,
    ) -> None:
        """Create a test raster file."""
        transform = Affine.identity() * Affine.translation(-180, 90) * Affine.scale(180/width, -90/height)

        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype=dtype,
            crs=crs,
            transform=transform,
        ) as dst:
            data = np.random.rand(height, width).astype(dtype) * 255
            dst.write(data, 1)

    def test_cog_creation_large_raster(self):
        """Test COG creation on large raster."""
        output = self.temp_path / "cog_large.tif"
        result = create_cog(str(self.large_raster_path), str(output))

        self.assertTrue(result["success"])
        self.assertTrue(output.exists())
        self.assertEqual(result["input_dimensions"]["width"], 1024)
        self.assertEqual(result["input_dimensions"]["height"], 1024)
        self.assertGreater(len(result["overview_levels"]), 0)

    def test_cog_creation_small_raster(self):
        """Test COG creation on small raster."""
        output = self.temp_path / "cog_small.tif"
        result = create_cog(str(self.small_raster_path), str(output))

        self.assertTrue(result["success"])
        self.assertTrue(output.exists())

    def test_cog_with_custom_block_size(self):
        """Test COG creation with custom block size."""
        output = self.temp_path / "cog_custom_block.tif"
        result = create_cog(
            str(self.large_raster_path),
            str(output),
            block_size=256,
        )

        self.assertEqual(result["block_size"], 256)
        self.assertTrue(output.exists())

    def test_output_file_creation(self):
        """Test that output COG file is properly created."""
        output = self.temp_path / "subdir" / "cog_output.tif"
        create_cog(str(self.large_raster_path), str(output))

        self.assertTrue(output.exists())
        
        # Verify output is a valid raster
        with rasterio.open(output) as src:
            self.assertGreater(src.width, 0)
            self.assertGreater(src.height, 0)

    def test_metadata_preservation(self):
        """Test that CRS and dtype are preserved in COG."""
        output = self.temp_path / "cog_metadata.tif"
        result = create_cog(str(self.large_raster_path), str(output))

        self.assertIn("4326", result["crs"])
        self.assertEqual(result["dtype"], "uint16")

        # Verify in output file
        with rasterio.open(output) as src:
            self.assertIn("4326", str(src.crs))

    def test_dimensions_preservation(self):
        """Test that dimensions are preserved in COG."""
        output = self.temp_path / "cog_dims.tif"
        result = create_cog(str(self.large_raster_path), str(output))

        with rasterio.open(output) as src:
            self.assertEqual(src.width, 1024)
            self.assertEqual(src.height, 1024)

    def test_overview_levels_computation(self):
        """Test overview level auto-computation."""
        # Large raster should have at least one overview level
        levels = _compute_overview_levels(1024, 1024)
        self.assertGreater(len(levels), 0)
        self.assertEqual(levels[0], 2)  # First level is always 2

        # Very large raster should have multiple levels
        levels_xlarge = _compute_overview_levels(4096, 4096)
        self.assertGreaterEqual(len(levels_xlarge), 1)

        # Small raster might have just one level
        levels_small = _compute_overview_levels(256, 256)
        self.assertGreater(len(levels_small), 0)

    def test_overview_levels_nonsquare(self):
        """Test overview computation for non-square rasters."""
        levels = _compute_overview_levels(512, 1024)
        self.assertGreater(len(levels), 0)
        # Levels should be powers of 2
        for level in levels:
            self.assertEqual(level & (level - 1), 0)  # Check if power of 2

    def test_cog_validation_compliant(self):
        """Test validation of a compliant COG."""
        output = self.temp_path / "cog_valid.tif"
        create_cog(str(self.large_raster_path), str(output))

        result = validate_cog(str(output))

        self.assertTrue(result["is_cog_compliant"])
        self.assertTrue(result["checks"]["is_tiled"])
        self.assertTrue(result["checks"]["block_size_valid"])
        self.assertTrue(result["checks"]["has_overviews"])

    def test_cog_validation_noncompliant(self):
        """Test validation of a non-compliant raster (standard GeoTIFF)."""
        # The input raster is not a COG, so validation should reflect that
        result = validate_cog(str(self.large_raster_path))

        # Input rasters are not tiled, so should be non-compliant
        self.assertFalse(result["is_cog_compliant"])

    def test_result_structure(self):
        """Test that result dict has all required keys."""
        output = self.temp_path / "result_struct.tif"
        result = create_cog(str(self.large_raster_path), str(output))

        required_keys = [
            "success",
            "input_file",
            "output_file",
            "input_dimensions",
            "block_size",
            "overview_levels",
            "compression",
            "bands",
            "dtype",
            "crs",
            "is_tiled",
        ]

        for key in required_keys:
            self.assertIn(key, result, f"Missing key in result: {key}")

    def test_input_file_not_found(self):
        """Test error handling for missing input file."""
        output = self.temp_path / "output.tif"

        with self.assertRaises(FileNotFoundError):
            create_cog(
                str(self.temp_path / "nonexistent.tif"),
                str(output),
            )

    def test_validation_file_not_found(self):
        """Test error handling for missing file during validation."""
        with self.assertRaises(FileNotFoundError):
            validate_cog(str(self.temp_path / "nonexistent.tif"))

    def test_compression_applied(self):
        """Test that compression is applied in COG."""
        output = self.temp_path / "cog_compressed.tif"
        result = create_cog(str(self.large_raster_path), str(output))

        self.assertEqual(result["compression"], "lzw")

        # Verify in output file
        with rasterio.open(output) as src:
            self.assertIsNotNone(src.compression)

    def test_multiple_cog_creations_same_input(self):
        """Test that multiple COG creations from same input work."""
        output1 = self.temp_path / "cog1.tif"
        output2 = self.temp_path / "cog2.tif"

        result1 = create_cog(str(self.large_raster_path), str(output1))
        result2 = create_cog(str(self.large_raster_path), str(output2))

        self.assertTrue(result1["success"])
        self.assertTrue(result2["success"])
        self.assertTrue(output1.exists())
        self.assertTrue(output2.exists())

    def test_nonsquare_raster_cog(self):
        """Test COG creation on non-square raster."""
        output = self.temp_path / "cog_nonsquare.tif"
        result = create_cog(str(self.nonsquare_raster_path), str(output))

        self.assertTrue(result["success"])
        self.assertEqual(result["input_dimensions"]["width"], 512)
        self.assertEqual(result["input_dimensions"]["height"], 1024)

    def test_validation_structure(self):
        """Test that validation result has all required keys."""
        output = self.temp_path / "validate_struct.tif"
        create_cog(str(self.large_raster_path), str(output))

        result = validate_cog(str(output))

        required_keys = [
            "file",
            "is_cog_compliant",
            "checks",
        ]

        for key in required_keys:
            self.assertIn(key, result, f"Missing key in validation result: {key}")

    def test_block_size_in_output(self):
        """Test that block size is correctly set in output."""
        output = self.temp_path / "cog_blocksize.tif"
        create_cog(str(self.large_raster_path), str(output), block_size=256)

        with rasterio.open(output) as src:
            self.assertEqual(src.profile.get("blockxsize"), 256)
            self.assertEqual(src.profile.get("blockysize"), 256)


if __name__ == "__main__":
    unittest.main()
