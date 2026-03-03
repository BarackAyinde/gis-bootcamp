"""
Tests for raster_pipeline.py

Uses 1024x1024 rasters for tests where COG validity matters (overviews require
a raster > 512px in at least one dimension). Uses 256x256 for structural/error tests.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from shapely.geometry import box

from gis_bootcamp.raster_pipeline import run_pipeline


def _make_raster(
    path: str,
    bounds=(-180.0, -90.0, 0.0, 90.0),
    width: int = 1024,
    height: int = 1024,
    crs: str = "EPSG:4326",
    nodata: float = -9999.0,
    fill_value: float = 1.0,
) -> str:
    transform = from_bounds(*bounds, width=width, height=height)
    data = np.full((1, height, width), fill_value, dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", dtype="float32",
        width=width, height=height, count=1,
        crs=CRS.from_string(crs), transform=transform, nodata=nodata,
    ) as dst:
        dst.write(data)
    return path


def _make_mask(path: str, bounds=(-170.0, 5.0, -10.0, 85.0), crs: str = "EPSG:4326") -> str:
    """Write a simple polygon GeoPackage as a clip mask."""
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[box(*bounds)],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


class TestRasterPipeline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_full_pipeline_single_input_no_clip(self):
        """Single raster, no AOI: mosaic(passthrough) → COG → metadata JSON."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir)

        self.assertTrue(Path(result["output_cog"]).exists())
        self.assertTrue(Path(result["output_metadata_json"]).exists())
        self.assertEqual(result["input_count"], 1)

    def test_full_pipeline_two_inputs_no_clip(self):
        """Two rasters mosaicked then converted to COG."""
        r1 = _make_raster(self._p("r1.tif"), bounds=(-180, -90, -90, 90))
        r2 = _make_raster(self._p("r2.tif"), bounds=(-90, -90, 0, 90))
        out_dir = self._p("out")

        result = run_pipeline([r1, r2], out_dir)

        self.assertTrue(Path(result["output_cog"]).exists())
        self.assertEqual(result["input_count"], 2)
        self.assertTrue(Path(out_dir) / "mosaic.tif")

    def test_full_pipeline_bbox_clip(self):
        """Pipeline with bbox clip: mosaic → clip → COG."""
        r = _make_raster(self._p("r.tif"), bounds=(-180, 0, 0, 90))
        out_dir = self._p("out_bbox")

        result = run_pipeline(
            [r], out_dir, bbox=(-170.0, 5.0, -10.0, 85.0)
        )

        self.assertTrue(Path(result["output_cog"]).exists())
        self.assertTrue(Path(out_dir) / "clipped.tif")
        self.assertEqual(result["stages"]["clip"]["method"], "bbox")

    def test_full_pipeline_mask_clip(self):
        """Pipeline with vector mask clip."""
        r = _make_raster(self._p("r.tif"), bounds=(-180, 0, 0, 90))
        mask = _make_mask(self._p("mask.gpkg"), bounds=(-170, 5, -10, 85))
        out_dir = self._p("out_mask")

        result = run_pipeline([r], out_dir, mask_path=mask)

        self.assertTrue(Path(result["output_cog"]).exists())
        self.assertEqual(result["stages"]["clip"]["method"], "mask")

    def test_cog_file_exists_in_output_dir(self):
        """output.cog.tif is written to the output directory."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir)

        self.assertEqual(result["output_cog"], str(Path(out_dir) / "output.cog.tif"))
        self.assertTrue(Path(result["output_cog"]).exists())

    def test_metadata_json_exists_in_output_dir(self):
        """metadata.json is written to the output directory."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir)

        self.assertEqual(
            result["output_metadata_json"],
            str(Path(out_dir) / "metadata.json"),
        )
        self.assertTrue(Path(result["output_metadata_json"]).exists())

    def test_metadata_json_structure(self):
        """metadata.json contains all required top-level fields."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir)

        with open(result["output_metadata_json"]) as f:
            meta = json.load(f)

        required_keys = {
            "pipeline", "started_at", "finished_at", "input_count",
            "input_paths", "output_dir", "output_cog", "cog_valid",
            "crs", "final_dimensions", "stages",
        }
        self.assertEqual(required_keys, set(meta.keys()))

    def test_metadata_json_stages_structure(self):
        """metadata.json stages section has inspect/mosaic/clip/cog keys."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir)

        with open(result["output_metadata_json"]) as f:
            meta = json.load(f)

        self.assertIn("inspect", meta["stages"])
        self.assertIn("mosaic", meta["stages"])
        self.assertIn("clip", meta["stages"])
        self.assertIn("cog", meta["stages"])

    def test_clip_stage_skipped_when_no_aoi(self):
        """Clip stage is marked skipped in metadata when no AOI provided."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir)

        with open(result["output_metadata_json"]) as f:
            meta = json.load(f)

        self.assertEqual(meta["stages"]["clip"]["status"], "skipped")
        self.assertIsNone(meta["stages"]["clip"]["method"])

    def test_clip_stage_completed_with_bbox(self):
        """Clip stage is marked completed and method=bbox when bbox provided."""
        r = _make_raster(self._p("r.tif"), bounds=(-180, 0, 0, 90))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir, bbox=(-170, 5, -10, 85))

        with open(result["output_metadata_json"]) as f:
            meta = json.load(f)

        self.assertEqual(meta["stages"]["clip"]["status"], "completed")
        self.assertEqual(meta["stages"]["clip"]["method"], "bbox")

    def test_cog_valid_for_large_raster(self):
        """1024x1024 raster produces a COG-valid output."""
        r = _make_raster(self._p("large.tif"), width=1024, height=1024)
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir, block_size=256)

        self.assertTrue(result["cog_valid"])

    def test_result_dict_structure(self):
        """run_pipeline result has all expected keys."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        result = run_pipeline([r], out_dir)

        expected = {"output_cog", "output_metadata_json", "stages", "input_count", "cog_valid"}
        self.assertEqual(expected, set(result.keys()))

    def test_output_dir_auto_created(self):
        """Nested output directory is created automatically."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("sub/nested/pipeline_out")

        result = run_pipeline([r], out_dir)

        self.assertTrue(Path(out_dir).exists())
        self.assertTrue(Path(result["output_cog"]).exists())

    def test_mosaic_intermediate_file_created(self):
        """mosaic.tif intermediate file is present in the output directory."""
        r = _make_raster(self._p("r.tif"))
        out_dir = self._p("out")

        run_pipeline([r], out_dir)

        self.assertTrue((Path(out_dir) / "mosaic.tif").exists())

    def test_input_count_in_result(self):
        """input_count in result matches number of inputs."""
        r1 = _make_raster(self._p("r1.tif"), bounds=(-180, -90, -90, 90))
        r2 = _make_raster(self._p("r2.tif"), bounds=(-90, -90, 0, 90))
        out_dir = self._p("out")

        result = run_pipeline([r1, r2], out_dir)

        self.assertEqual(result["input_count"], 2)
        with open(result["output_metadata_json"]) as f:
            meta = json.load(f)
        self.assertEqual(meta["input_count"], 2)

    # ------------------------------------------------------------------
    # Error / edge-case tests
    # ------------------------------------------------------------------

    def test_empty_input_list_raises_value_error(self):
        """ValueError raised for empty input list."""
        with self.assertRaises(ValueError):
            run_pipeline([], self._p("out"))

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised for non-existent input."""
        with self.assertRaises(FileNotFoundError):
            run_pipeline(["nonexistent.tif"], self._p("out"))

    def test_both_bbox_and_mask_raises_value_error(self):
        """ValueError raised when both bbox and mask_path are provided."""
        r = _make_raster(self._p("r.tif"))
        mask = _make_mask(self._p("mask.gpkg"))
        with self.assertRaises(ValueError):
            run_pipeline(
                [r], self._p("out"),
                bbox=(-10, -10, 10, 10),
                mask_path=mask,
            )


if __name__ == "__main__":
    unittest.main()
