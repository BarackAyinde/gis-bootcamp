#!/usr/bin/env python3
"""
Unit tests for raster_clipper module.

Tests:
- Clip with bounding box
- Clip with vector mask
- CRS alignment (auto-reprojection)
- Output file creation
- Error handling (missing files, invalid bbox, empty mask)
- Nodata value preservation
- Window/bounds calculations
"""

import json
import logging
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine
from shapely.geometry import box, Polygon

from gis_bootcamp.raster_clipper import clip_raster_bbox, clip_raster_mask


class TestRasterClipper(unittest.TestCase):
    """Test raster clipping functionality."""

    @classmethod
    def setUpClass(cls):
        """Create temporary test rasters and vector files."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name)

        # Create test raster (256x256, WGS84, float32)
        cls.raster_path = cls.temp_path / "test_raster.tif"
        cls._create_test_raster(
            cls.raster_path,
            width=256,
            height=256,
            crs=CRS.from_epsg(4326),
            dtype=rasterio.float32,
            nodata=-9999.0,
        )

        # Create vector mask (polygon within raster bounds)
        cls.mask_path = cls.temp_path / "mask.gpkg"
        cls._create_test_mask(cls.mask_path, crs=CRS.from_epsg(4326))

        # Create vector mask with different CRS (Web Mercator)
        cls.mask_3857_path = cls.temp_path / "mask_3857.gpkg"
        cls._create_test_mask(cls.mask_3857_path, crs=CRS.from_epsg(3857))

        # Create empty mask
        cls.empty_mask_path = cls.temp_path / "empty_mask.gpkg"
        empty_gdf = gpd.GeoDataFrame(geometry=[], crs=CRS.from_epsg(4326))
        empty_gdf.to_file(cls.empty_mask_path)

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
        nodata=None,
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
            nodata=nodata,
        ) as dst:
            data = np.arange(width * height, dtype=dtype).reshape(height, width)
            dst.write(data, 1)

    @staticmethod
    def _create_test_mask(path: Path, crs: CRS) -> None:
        """Create a test vector mask."""
        if crs == CRS.from_epsg(4326):
            # For WGS84: clip a central square (-90 to 0 lon, 0 to 45 lat)
            polygon = Polygon([(-90, 0), (-90, 45), (0, 45), (0, 0)])
        else:
            # For Web Mercator: create polygon and let GeoPandas reproject
            polygon = Polygon([(-90, 0), (-90, 45), (0, 45), (0, 0)])

        gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[polygon], crs=crs)
        gdf.to_file(path)

    def test_clip_with_bbox(self):
        """Test clipping with bounding box."""
        output = self.temp_path / "clipped_bbox.tif"
        result = clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,  # bbox
            str(output),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "bbox")
        self.assertTrue(output.exists())
        self.assertIn("output_bounds", result)

    def test_clip_with_mask(self):
        """Test clipping with vector mask."""
        output = self.temp_path / "clipped_mask.tif"
        result = clip_raster_mask(
            str(self.raster_path),
            str(self.mask_path),
            str(output),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "mask")
        self.assertTrue(output.exists())
        self.assertEqual(result["mask_features"], 1)

    def test_output_file_creation(self):
        """Test that output file is properly created."""
        output = self.temp_path / "subdir" / "clipped.tif"
        clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,
            str(output),
        )

        self.assertTrue(output.exists())
        
        # Verify output is a valid raster
        with rasterio.open(output) as src:
            self.assertGreater(src.width, 0)
            self.assertGreater(src.height, 0)

    def test_bbox_clipping_dimensions(self):
        """Test that clipped dimensions are reasonable."""
        output = self.temp_path / "clipped_dims.tif"
        result = clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,
            str(output),
        )

        # Original is 256x256, bbox is half (180 deg -> 90 deg, 90 deg -> 45 deg)
        clipped_height, clipped_width = result["output_shape"][1], result["output_shape"][2]
        self.assertLess(clipped_height, 256)
        self.assertLess(clipped_width, 256)

    def test_mask_with_crs_mismatch(self):
        """Test auto-reprojection when mask CRS != raster CRS."""
        output = self.temp_path / "clipped_crs_mismatch.tif"
        result = clip_raster_mask(
            str(self.raster_path),  # EPSG:4326
            str(self.mask_3857_path),  # EPSG:3857
            str(output),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["crs_alignment"], "auto-reprojected")
        self.assertTrue(output.exists())

    def test_nodata_preservation(self):
        """Test that nodata value is preserved in output."""
        output = self.temp_path / "clipped_nodata.tif"
        result = clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,
            str(output),
        )

        self.assertEqual(result["nodata"], -9999.0)

        # Verify in output file
        with rasterio.open(output) as src:
            self.assertEqual(src.nodata, -9999.0)

    def test_crs_preservation(self):
        """Test that CRS is preserved in output."""
        output = self.temp_path / "clipped_crs.tif"
        clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,
            str(output),
        )

        with rasterio.open(output) as src:
            self.assertIn("4326", str(src.crs))

    def test_output_bounds_validity(self):
        """Test that output bounds are valid."""
        output = self.temp_path / "clipped_bounds.tif"
        result = clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,
            str(output),
        )

        bounds = result["output_bounds"]
        self.assertLess(bounds["minx"], bounds["maxx"])
        self.assertLess(bounds["miny"], bounds["maxy"])

    def test_bbox_invalid_coordinates(self):
        """Test error handling for invalid bbox."""
        output = self.temp_path / "invalid.tif"

        with self.assertRaises(ValueError):
            clip_raster_bbox(
                str(self.raster_path),
                0, 0, -90, 45,  # minx > maxx
                str(output),
            )

    def test_bbox_no_overlap(self):
        """Test error handling when bbox doesn't overlap raster."""
        output = self.temp_path / "no_overlap.tif"

        with self.assertRaises(ValueError):
            clip_raster_bbox(
                str(self.raster_path),
                100, 100, 120, 120,  # Outside raster bounds
                str(output),
            )

    def test_raster_not_found(self):
        """Test error handling for missing raster."""
        output = self.temp_path / "output.tif"

        with self.assertRaises(FileNotFoundError):
            clip_raster_bbox(
                str(self.temp_path / "nonexistent.tif"),
                -90, 0, 0, 45,
                str(output),
            )

    def test_mask_file_not_found(self):
        """Test error handling for missing mask file."""
        output = self.temp_path / "output.tif"

        with self.assertRaises(FileNotFoundError):
            clip_raster_mask(
                str(self.raster_path),
                str(self.temp_path / "nonexistent.gpkg"),
                str(output),
            )

    def test_empty_mask(self):
        """Test error handling for empty mask."""
        output = self.temp_path / "output.tif"

        with self.assertRaises(ValueError):
            clip_raster_mask(
                str(self.raster_path),
                str(self.empty_mask_path),
                str(output),
            )

    def test_result_structure_bbox(self):
        """Test that result dict has all required keys for bbox method."""
        output = self.temp_path / "result_struct_bbox.tif"
        result = clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,
            str(output),
        )

        required_keys = [
            "success",
            "input_file",
            "output_file",
            "method",
            "bbox",
            "output_shape",
            "output_bounds",
            "crs",
            "nodata",
        ]

        for key in required_keys:
            self.assertIn(key, result, f"Missing key in result: {key}")

    def test_result_structure_mask(self):
        """Test that result dict has all required keys for mask method."""
        output = self.temp_path / "result_struct_mask.tif"
        result = clip_raster_mask(
            str(self.raster_path),
            str(self.mask_path),
            str(output),
        )

        required_keys = [
            "success",
            "input_file",
            "mask_file",
            "output_file",
            "method",
            "mask_features",
            "output_shape",
            "crs",
            "nodata",
        ]

        for key in required_keys:
            self.assertIn(key, result, f"Missing key in result: {key}")

    def test_multiple_clipping_same_file(self):
        """Test that multiple clipping operations on same file work."""
        output1 = self.temp_path / "clip1.tif"
        output2 = self.temp_path / "clip2.tif"

        result1 = clip_raster_bbox(
            str(self.raster_path),
            -180, 0, 0, 45,
            str(output1),
        )

        result2 = clip_raster_bbox(
            str(self.raster_path),
            -90, 0, 0, 45,
            str(output2),
        )

        self.assertTrue(result1["success"])
        self.assertTrue(result2["success"])
        self.assertTrue(output1.exists())
        self.assertTrue(output2.exists())


if __name__ == "__main__":
    unittest.main()
