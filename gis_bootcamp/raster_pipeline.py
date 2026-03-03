"""
raster_pipeline.py — End-of-week raster processing pipeline.

Chains Week 2 tools in sequence:
  1. Inspect  — metadata extraction for each input raster
  2. Mosaic   — merge all inputs into a single raster
  3. Clip     — clip to AOI (bbox or vector mask; optional)
  4. COG      — convert to Cloud Optimized GeoTIFF
  5. Metadata — write JSON pipeline summary

Outputs written to a single output directory:
  mosaic.tif       — intermediate mosaic (or passthrough for single input)
  clipped.tif      — clipped raster (present only if AOI provided)
  output.cog.tif   — final Cloud Optimized GeoTIFF
  metadata.json    — structured pipeline run summary
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from gis_bootcamp.geotiff_to_cog import create_cog, validate_cog
from gis_bootcamp.raster_clipper import clip_raster_bbox, clip_raster_mask
from gis_bootcamp.raster_metadata_inspector import inspect_raster
from gis_bootcamp.raster_mosaic import mosaic_rasters

logger = logging.getLogger(__name__)


def run_pipeline(
    input_paths: list[str],
    output_dir: str,
    bbox: Optional[tuple[float, float, float, float]] = None,
    mask_path: Optional[str] = None,
    target_crs: Optional[str] = None,
    block_size: int = 512,
) -> dict:
    """
    Run the full raster processing pipeline.

    Stages:
        1. Inspect — collect metadata for each input raster
        2. Mosaic  — merge all inputs into one raster
        3. Clip    — clip to AOI (optional; skipped if neither bbox nor mask_path)
        4. COG     — convert to Cloud Optimized GeoTIFF
        5. Metadata JSON — write structured pipeline summary

    Args:
        input_paths: List of input raster file paths (minimum 1).
        output_dir: Directory for all output files.
        bbox: Optional (minx, miny, maxx, maxy) bounding box for clipping.
        mask_path: Optional vector file path for mask-based clipping.
        target_crs: Optional CRS string for the mosaic step (e.g. 'EPSG:4326').
        block_size: COG tile block size (default 512).

    Returns:
        dict with keys: output_cog, output_metadata_json, stages,
                        input_count, cog_valid.

    Raises:
        ValueError: Empty input list, or both bbox and mask_path provided.
        FileNotFoundError: Any input raster or mask_path not found.
    """
    if not input_paths:
        raise ValueError("At least one input raster is required")
    if bbox is not None and mask_path is not None:
        raise ValueError("Provide either bbox or mask_path, not both")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    stages = {}

    # --- Stage 1: Inspect ---
    logger.info("=== Stage 1: Inspect ===")
    inspections = []
    for path in input_paths:
        meta = inspect_raster(path)
        inspections.append({"path": path, "metadata": meta})
        logger.info(
            "  %s — %dx%d px, CRS=%s, %d band(s)",
            path,
            meta["width"],
            meta["height"],
            meta.get("crs", "none"),
            meta["num_bands"],
        )
    stages["inspect"] = {"inputs": input_paths, "results": inspections}

    # --- Stage 2: Mosaic ---
    logger.info("=== Stage 2: Mosaic (%d raster(s)) ===", len(input_paths))
    mosaic_path = str(out_dir / "mosaic.tif")
    mosaic_result = mosaic_rasters(
        input_paths=input_paths,
        output_path=mosaic_path,
        target_crs=target_crs,
    )
    logger.info(
        "  Mosaic complete: %dx%d px, CRS=%s",
        mosaic_result["width"],
        mosaic_result["height"],
        mosaic_result["crs"],
    )
    stages["mosaic"] = mosaic_result

    # --- Stage 3: Clip (optional) ---
    to_cog_path = mosaic_path

    if bbox is not None:
        logger.info("=== Stage 3: Clip (bbox) ===")
        clipped_path = str(out_dir / "clipped.tif")
        clip_result = clip_raster_bbox(
            raster_path=mosaic_path,
            minx=bbox[0],
            miny=bbox[1],
            maxx=bbox[2],
            maxy=bbox[3],
            output_path=clipped_path,
        )
        out_h, out_w = clip_result["output_shape"][1], clip_result["output_shape"][2]
        logger.info("  Clipped: %dx%d px", out_w, out_h)
        stages["clip"] = {"method": "bbox", "bbox": bbox, "result": clip_result}
        to_cog_path = clipped_path

    elif mask_path is not None:
        logger.info("=== Stage 3: Clip (mask) ===")
        clipped_path = str(out_dir / "clipped.tif")
        clip_result = clip_raster_mask(
            raster_path=mosaic_path,
            mask_path=mask_path,
            output_path=clipped_path,
        )
        out_h, out_w = clip_result["output_shape"][1], clip_result["output_shape"][2]
        logger.info("  Clipped: %dx%d px", out_w, out_h)
        stages["clip"] = {
            "method": "mask",
            "mask_path": mask_path,
            "result": clip_result,
        }
        to_cog_path = clipped_path

    else:
        logger.info("=== Stage 3: Clip — skipped (no AOI provided) ===")
        stages["clip"] = {"method": None, "result": None}

    # --- Stage 4: COG ---
    logger.info("=== Stage 4: COG (block_size=%d) ===", block_size)
    cog_path = str(out_dir / "output.cog.tif")
    cog_result = create_cog(
        input_path=to_cog_path,
        output_path=cog_path,
        block_size=block_size,
    )
    validation = validate_cog(cog_path)
    cog_w = cog_result["input_dimensions"]["width"]
    cog_h = cog_result["input_dimensions"]["height"]
    logger.info(
        "  COG complete: %dx%d px, valid=%s",
        cog_w,
        cog_h,
        validation["is_cog_compliant"],
    )
    stages["cog"] = {**cog_result, "validation": validation}

    # --- Stage 5: Metadata JSON ---
    logger.info("=== Stage 5: Metadata JSON ===")
    finished_at = datetime.now(timezone.utc).isoformat()

    metadata = {
        "pipeline": "raster_processing_pipeline",
        "started_at": started_at,
        "finished_at": finished_at,
        "input_count": len(input_paths),
        "input_paths": input_paths,
        "output_dir": output_dir,
        "output_cog": cog_path,
        "cog_valid": validation["is_cog_compliant"],
        "crs": mosaic_result["crs"],
        "final_dimensions": {
            "width": cog_w,
            "height": cog_h,
            "bands": cog_result["bands"],
        },
        "stages": {
            "inspect": {
                "status": "completed",
                "input_count": len(input_paths),
            },
            "mosaic": {
                "status": "completed",
                "width": mosaic_result["width"],
                "height": mosaic_result["height"],
            },
            "clip": {
                "status": "skipped" if stages["clip"]["method"] is None else "completed",
                "method": stages["clip"]["method"],
            },
            "cog": {
                "status": "completed",
                "block_size": cog_result["block_size"],
                "overview_levels": cog_result["overview_levels"],
                "compression": cog_result["compression"],
            },
        },
    }

    metadata_path = str(out_dir / "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    logger.info("  Metadata written: %s", metadata_path)

    return {
        "output_cog": cog_path,
        "output_metadata_json": metadata_path,
        "stages": stages,
        "input_count": len(input_paths),
        "cog_valid": validation["is_cog_compliant"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Raster processing pipeline: inspect → mosaic → clip (optional) → COG → metadata JSON"
        )
    )
    parser.add_argument("inputs", nargs="+", help="Input raster file paths")
    parser.add_argument("-o", "--output-dir", required=True, help="Output directory")

    aoi_group = parser.add_mutually_exclusive_group()
    aoi_group.add_argument(
        "-bbox",
        nargs=4,
        type=float,
        metavar=("MINX", "MINY", "MAXX", "MAXY"),
        help="Bounding box for clipping",
    )
    aoi_group.add_argument(
        "-mask", "--mask", default=None, help="Vector mask file for clipping"
    )

    parser.add_argument(
        "-crs", "--crs", default=None, help="Target CRS for mosaic (e.g. EPSG:4326)"
    )
    parser.add_argument(
        "-b", "--block-size", type=int, default=512, help="COG tile block size (default 512)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    bbox = tuple(args.bbox) if args.bbox else None

    try:
        result = run_pipeline(
            input_paths=args.inputs,
            output_dir=args.output_dir,
            bbox=bbox,
            mask_path=args.mask,
            target_crs=args.crs,
            block_size=args.block_size,
        )
        print(f"\nPipeline complete")
        print(f"  Inputs         : {result['input_count']}")
        print(f"  Output COG     : {result['output_cog']}")
        print(f"  Metadata JSON  : {result['output_metadata_json']}")
        print(f"  COG valid      : {result['cog_valid']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
