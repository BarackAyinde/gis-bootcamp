"""
raster_mosaic.py — CLI tool to mosaic multiple rasters into a single output raster.

Handles CRS alignment via WarpedVRT (no temp files), nodata propagation,
and multi-band inputs. Logs input count, dimensions, and CRS at each step.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT

logger = logging.getLogger(__name__)


def mosaic_rasters(
    input_paths: list[str],
    output_path: str,
    target_crs: Optional[str] = None,
) -> dict:
    """
    Mosaic multiple raster datasets into a single output raster.

    Args:
        input_paths: List of input raster file paths (must be non-empty).
        output_path: Output raster path (directories are created if needed).
        target_crs: Optional CRS string (e.g. 'EPSG:4326'). Defaults to the
                    CRS of the first input raster.

    Returns:
        dict with keys: output_path, input_count, crs, width, height, bands,
                        nodata, transform.

    Raises:
        ValueError: Empty input list, or a raster has no CRS.
        FileNotFoundError: Any input path does not exist.
        rasterio.errors.RasterioIOError: Any input cannot be opened.
    """
    if not input_paths:
        raise ValueError("At least one input raster path is required")

    for path in input_paths:
        if not Path(path).exists():
            raise FileNotFoundError(f"Input raster not found: {path}")

    logger.info("Opening %d raster(s)", len(input_paths))

    datasets = []
    try:
        for path in input_paths:
            ds = rasterio.open(path)
            datasets.append(ds)

        # Resolve target CRS
        if target_crs:
            crs = CRS.from_string(target_crs)
            logger.info("Target CRS (user-specified): %s", crs.to_string())
        else:
            crs = datasets[0].crs
            if crs is None:
                raise ValueError(
                    f"First raster has no CRS and no target_crs was specified: {input_paths[0]}"
                )
            logger.info("Target CRS (from first raster): %s", crs.to_string())

        # Log mixed-dtype warning
        dtypes = [ds.dtypes[0] for ds in datasets]
        if len(set(dtypes)) > 1:
            logger.warning(
                "Mixed dtypes across inputs: %s. Output dtype follows first raster.",
                dtypes,
            )

        # Wrap mismatched-CRS rasters in WarpedVRT for on-the-fly reprojection
        sources: list = []
        vrts: list = []
        for i, ds in enumerate(datasets):
            if ds.crs is None:
                raise ValueError(
                    f"Raster has no CRS and cannot be aligned: {input_paths[i]}"
                )
            if ds.crs != crs:
                logger.info(
                    "Reprojecting %s from %s to %s",
                    input_paths[i],
                    ds.crs.to_string(),
                    crs.to_string(),
                )
                vrt = WarpedVRT(ds, crs=crs)
                vrts.append(vrt)
                sources.append(vrt)
            else:
                sources.append(ds)

        # Nodata from first dataset
        nodata = datasets[0].nodata

        logger.info("Merging %d source(s)...", len(sources))
        mosaic, transform = merge(sources, nodata=nodata)

        out_bands, out_height, out_width = mosaic.shape
        logger.info(
            "Mosaic dimensions: %d x %d px, %d band(s)", out_width, out_height, out_bands
        )

        # Build output profile from first dataset
        out_meta = datasets[0].meta.copy()
        out_meta.update(
            {
                "driver": "GTiff",
                "height": out_height,
                "width": out_width,
                "transform": transform,
                "crs": crs,
            }
        )
        if nodata is not None:
            out_meta["nodata"] = nodata

        # Write output
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(output_path, "w", **out_meta) as dst:
            dst.write(mosaic)

        logger.info("Output written: %s", output_path)

        return {
            "output_path": output_path,
            "input_count": len(input_paths),
            "crs": crs.to_string(),
            "width": out_width,
            "height": out_height,
            "bands": out_bands,
            "nodata": nodata,
            "transform": transform,
        }

    finally:
        for vrt in vrts if "vrts" in dir() else []:
            vrt.close()
        for ds in datasets:
            ds.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mosaic multiple raster datasets into a single output raster"
    )
    parser.add_argument("inputs", nargs="+", help="Input raster file paths")
    parser.add_argument("-o", "--output", required=True, help="Output raster path")
    parser.add_argument(
        "-crs",
        "--crs",
        default=None,
        help="Target CRS (e.g. EPSG:4326). Defaults to first input raster CRS.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = mosaic_rasters(
            input_paths=args.inputs,
            output_path=args.output,
            target_crs=args.crs,
        )
        print(f"\nMosaic complete")
        print(f"  Input rasters : {result['input_count']}")
        print(f"  Output        : {result['output_path']}")
        print(f"  Dimensions    : {result['width']} x {result['height']} px")
        print(f"  Bands         : {result['bands']}")
        print(f"  CRS           : {result['crs']}")
        if result["nodata"] is not None:
            print(f"  Nodata        : {result['nodata']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
