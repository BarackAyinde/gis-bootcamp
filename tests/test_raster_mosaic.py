"""
Tests for raster_mosaic.py
"""

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from gis_bootcamp.raster_mosaic import mosaic_rasters


def _make_raster(
    path: str,
    bounds=(-180.0, -90.0, 0.0, 90.0),
    width: int = 64,
    height: int = 64,
    crs: str = "EPSG:4326",
    nodata=None,
    dtype: str = "float32",
    bands: int = 1,
    fill_value: float = 1.0,
) -> str:
    """Write a synthetic GeoTIFF for testing."""
    transform = from_bounds(*bounds, width=width, height=height)
    data = np.full((bands, height, width), fill_value, dtype=dtype)
    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "width": width,
        "height": height,
        "count": bands,
        "crs": CRS.from_string(crs),
        "transform": transform,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
    return path


class TestRasterMosaic(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_two_adjacent_tiles_wider_output(self):
        """Two horizontally adjacent tiles produce a wider mosaic."""
        left = _make_raster(self._p("left.tif"), bounds=(-180, -90, 0, 90))
        right = _make_raster(self._p("right.tif"), bounds=(0, -90, 180, 90))
        out = self._p("mosaic.tif")

        result = mosaic_rasters([left, right], out)

        self.assertEqual(result["input_count"], 2)
        self.assertTrue(Path(out).exists())
        # Mosaic of two 64-wide tiles should be wider than a single tile
        self.assertGreater(result["width"], 64)

    def test_single_raster_passthrough(self):
        """Single input passes through with correct dimensions."""
        r = _make_raster(self._p("single.tif"))
        out = self._p("out.tif")

        result = mosaic_rasters([r], out)

        self.assertEqual(result["input_count"], 1)
        self.assertTrue(Path(out).exists())
        self.assertEqual(result["width"], 64)
        self.assertEqual(result["height"], 64)
        self.assertEqual(result["bands"], 1)

    def test_crs_of_output_matches_first_raster(self):
        """Output CRS defaults to first raster's CRS."""
        r1 = _make_raster(self._p("r1.tif"), crs="EPSG:4326", bounds=(-180, -90, 0, 90))
        r2 = _make_raster(self._p("r2.tif"), crs="EPSG:4326", bounds=(0, -90, 180, 90))
        out = self._p("out.tif")

        result = mosaic_rasters([r1, r2], out)

        self.assertEqual(result["crs"], CRS.from_epsg(4326).to_string())
        with rasterio.open(out) as ds:
            self.assertEqual(ds.crs, CRS.from_epsg(4326))

    def test_mismatched_crs_auto_reprojected(self):
        """Second raster with different CRS is reprojected to first raster's CRS."""
        r1 = _make_raster(self._p("r1.tif"), crs="EPSG:4326", bounds=(-180, -90, 0, 90))
        # Web Mercator equivalent of the eastern hemisphere (approximate)
        r2 = _make_raster(
            self._p("r2_3857.tif"),
            crs="EPSG:3857",
            bounds=(0, -20037508, 20037508, 20037508),
        )
        out = self._p("mosaic_reprojected.tif")

        result = mosaic_rasters([r1, r2], out)

        self.assertTrue(Path(out).exists())
        # Output CRS should be EPSG:4326 (from first raster)
        self.assertEqual(result["crs"], CRS.from_epsg(4326).to_string())

    def test_user_specified_target_crs(self):
        """User-specified target_crs overrides first raster's CRS."""
        r1 = _make_raster(self._p("a.tif"), crs="EPSG:4326", bounds=(-180, -90, 0, 90))
        r2 = _make_raster(self._p("b.tif"), crs="EPSG:4326", bounds=(0, -90, 180, 90))
        out = self._p("out_3857.tif")

        result = mosaic_rasters([r1, r2], out, target_crs="EPSG:3857")

        self.assertEqual(result["crs"], CRS.from_epsg(3857).to_string())
        self.assertTrue(Path(out).exists())

    def test_output_directory_auto_created(self):
        """Nested output directory is created automatically."""
        r = _make_raster(self._p("r.tif"))
        out = self._p("sub/nested/out.tif")

        result = mosaic_rasters([r], out)

        self.assertTrue(Path(out).exists())

    def test_nodata_preserved_in_output(self):
        """Nodata value from first raster is carried into output file."""
        r1 = _make_raster(self._p("nd1.tif"), nodata=-9999.0, bounds=(-180, -90, 0, 90))
        r2 = _make_raster(self._p("nd2.tif"), nodata=-9999.0, bounds=(0, -90, 180, 90))
        out = self._p("nd_out.tif")

        result = mosaic_rasters([r1, r2], out)

        self.assertEqual(result["nodata"], -9999.0)
        with rasterio.open(out) as ds:
            self.assertEqual(ds.nodata, -9999.0)

    def test_multiband_rasters(self):
        """Multi-band rasters are mosaicked with band count preserved."""
        r1 = _make_raster(self._p("mb1.tif"), bands=3, bounds=(-180, -90, 0, 90))
        r2 = _make_raster(self._p("mb2.tif"), bands=3, bounds=(0, -90, 180, 90))
        out = self._p("mb_out.tif")

        result = mosaic_rasters([r1, r2], out)

        self.assertEqual(result["bands"], 3)
        with rasterio.open(out) as ds:
            self.assertEqual(ds.count, 3)

    def test_overlapping_rasters_merged_without_error(self):
        """Overlapping extents produce a valid output (first-wins merge strategy)."""
        r1 = _make_raster(self._p("ov1.tif"), bounds=(-180, -90, 90, 90), fill_value=1.0)
        r2 = _make_raster(self._p("ov2.tif"), bounds=(0, -90, 180, 90), fill_value=2.0)
        out = self._p("ov_out.tif")

        result = mosaic_rasters([r1, r2], out)

        self.assertTrue(Path(out).exists())
        self.assertGreater(result["width"], 0)
        self.assertGreater(result["height"], 0)

    def test_result_dict_has_expected_keys(self):
        """Result dict contains all documented keys."""
        r = _make_raster(self._p("r.tif"))
        out = self._p("out.tif")

        result = mosaic_rasters([r], out)

        expected_keys = {
            "output_path", "input_count", "crs", "width", "height",
            "bands", "nodata", "transform",
        }
        self.assertEqual(expected_keys, set(result.keys()))

    def test_three_tiles_full_globe(self):
        """Three tiles spanning the globe produce a valid mosaic."""
        t1 = _make_raster(self._p("t1.tif"), bounds=(-180, -90, -60, 90))
        t2 = _make_raster(self._p("t2.tif"), bounds=(-60, -90, 60, 90))
        t3 = _make_raster(self._p("t3.tif"), bounds=(60, -90, 180, 90))
        out = self._p("globe.tif")

        result = mosaic_rasters([t1, t2, t3], out)

        self.assertEqual(result["input_count"], 3)
        self.assertTrue(Path(out).exists())
        self.assertGreater(result["width"], 64)

    # ------------------------------------------------------------------
    # Error / edge-case tests
    # ------------------------------------------------------------------

    def test_empty_input_list_raises_value_error(self):
        """Empty input list raises ValueError."""
        with self.assertRaises(ValueError):
            mosaic_rasters([], self._p("out.tif"))

    def test_missing_input_file_raises_file_not_found(self):
        """Non-existent input path raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            mosaic_rasters(["does_not_exist.tif"], self._p("out.tif"))

    def test_raster_without_crs_raises_value_error(self):
        """Raster with no CRS raises ValueError (cannot determine target CRS)."""
        path = self._p("no_crs.tif")
        transform = from_bounds(-180, -90, 0, 90, 64, 64)
        with rasterio.open(
            path, "w", driver="GTiff", dtype="float32",
            width=64, height=64, count=1, transform=transform,
        ) as dst:
            dst.write(np.ones((1, 64, 64), dtype="float32"))

        with self.assertRaises(ValueError):
            mosaic_rasters([path], self._p("out.tif"))


if __name__ == "__main__":
    unittest.main()
