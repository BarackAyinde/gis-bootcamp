#!/usr/bin/env python3
"""
Raster Clipper: CLI tool to clip raster datasets.

Clips a raster using either:
- A bounding box (minx, miny, maxx, maxy), OR
- A vector mask (polygon geometry)

Outputs clipped raster with proper CRS alignment and nodata preservation.
"""

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.windows import from_bounds
from shapely.geometry import box

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def clip_raster_bbox(
    raster_path: str,
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    output_path: str,
) -> dict:
    """
    Clip a raster to a bounding box.

    Args:
        raster_path: Path to input raster
        minx, miny, maxx, maxy: Bounding box coordinates
        output_path: Path to output clipped raster

    Returns:
        Dictionary with clipping results

    Raises:
        FileNotFoundError: If raster file not found
        ValueError: If bbox is invalid or raster cannot be read
    """
    raster_path = Path(raster_path)
    output_path = Path(output_path)

    if not raster_path.exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}")

    if minx >= maxx or miny >= maxy:
        raise ValueError(f"Invalid bounding box: ({minx}, {miny}, {maxx}, {maxy})")

    logger.info(f"Clipping raster: {raster_path}")
    logger.info(f"Bounding box: ({minx}, {miny}, {maxx}, {maxy})")

    try:
        with rasterio.open(raster_path) as src:
            # Get window from bbox
            window = from_bounds(minx, miny, maxx, maxy, src.transform)
            
            # Validate window overlap
            if window.row_off >= src.height or window.col_off >= src.width:
                raise ValueError("Bounding box does not overlap with raster")

            # Read clipped data
            clipped_data = src.read(window=window)
            
            # Create new transform for output
            clipped_transform = rasterio.windows.transform(window, src.transform)

            # Determine output bounds (returns tuple: left, bottom, right, top)
            output_bounds_tuple = rasterio.windows.bounds(window, src.transform)

            logger.info(
                f"Window: rows {window.row_off}-{window.row_off + window.height}, "
                f"cols {window.col_off}-{window.col_off + window.width}"
            )
            logger.info(f"Output dimensions: {clipped_data.shape[1]}x{clipped_data.shape[2]}")

            # Create output directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write clipped raster
            with rasterio.open(
                output_path,
                "w",
                driver=src.driver,
                height=clipped_data.shape[1],
                width=clipped_data.shape[2],
                count=src.count,
                dtype=src.dtypes[0],
                crs=src.crs,
                transform=clipped_transform,
                nodata=src.nodata,
                compression=src.compression,
            ) as dst:
                dst.write(clipped_data)

            logger.info(f"Clipped raster written to: {output_path}")

            return {
                "success": True,
                "input_file": str(raster_path),
                "output_file": str(output_path),
                "method": "bbox",
                "bbox": {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
                "output_shape": clipped_data.shape,
                "output_bounds": {
                    "minx": output_bounds_tuple[0],
                    "miny": output_bounds_tuple[1],
                    "maxx": output_bounds_tuple[2],
                    "maxy": output_bounds_tuple[3],
                },
                "crs": str(src.crs),
                "nodata": src.nodata,
            }

    except rasterio.errors.RasterioIOError as e:
        raise ValueError(f"Failed to read raster: {e}")
    except Exception as e:
        raise ValueError(f"Clipping failed: {e}")


def clip_raster_mask(
    raster_path: str,
    mask_path: str,
    output_path: str,
) -> dict:
    """
    Clip a raster using a vector mask (polygon).

    Args:
        raster_path: Path to input raster
        mask_path: Path to vector file (GeoPackage, Shapefile, GeoJSON)
        output_path: Path to output clipped raster

    Returns:
        Dictionary with clipping results

    Raises:
        FileNotFoundError: If files not found
        ValueError: If files cannot be read or CRS mismatch
    """
    raster_path = Path(raster_path)
    mask_path = Path(mask_path)
    output_path = Path(output_path)

    if not raster_path.exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}")

    if not mask_path.exists():
        raise FileNotFoundError(f"Mask file not found: {mask_path}")

    logger.info(f"Clipping raster: {raster_path}")
    logger.info(f"Using mask: {mask_path}")

    try:
        # Load mask geometries
        mask_gdf = gpd.read_file(mask_path)

        if mask_gdf.empty:
            raise ValueError("Mask file has no features")

        logger.info(f"Loaded {len(mask_gdf)} features from mask")

        with rasterio.open(raster_path) as src:
            # Check CRS compatibility
            raster_crs = src.crs
            mask_crs = mask_gdf.crs

            if raster_crs != mask_crs:
                logger.info(f"CRS mismatch: raster {raster_crs}, mask {mask_crs}")
                logger.info("Reprojecting mask to raster CRS")
                mask_gdf = mask_gdf.to_crs(raster_crs)

            # Extract geometries
            geometries = mask_gdf.geometry.tolist()

            # Clip raster with mask
            clipped_data, clipped_transform = mask(
                src, geometries, crop=True, nodata=src.nodata
            )

            logger.info(f"Output dimensions: {clipped_data.shape[1]}x{clipped_data.shape[2]}")

            # Create output directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write clipped raster
            with rasterio.open(
                output_path,
                "w",
                driver=src.driver,
                height=clipped_data.shape[1],
                width=clipped_data.shape[2],
                count=src.count,
                dtype=src.dtypes[0],
                crs=src.crs,
                transform=clipped_transform,
                nodata=src.nodata,
                compression=src.compression,
            ) as dst:
                dst.write(clipped_data)

            logger.info(f"Clipped raster written to: {output_path}")

            return {
                "success": True,
                "input_file": str(raster_path),
                "mask_file": str(mask_path),
                "output_file": str(output_path),
                "method": "mask",
                "mask_features": len(mask_gdf),
                "output_shape": clipped_data.shape,
                "crs": str(src.crs),
                "nodata": src.nodata,
                "crs_alignment": "auto-reprojected" if raster_crs != mask_crs else "aligned",
            }

    except (rasterio.errors.RasterioIOError, ValueError) as e:
        raise ValueError(f"Failed during masking: {e}")
    except Exception as e:
        raise ValueError(f"Clipping failed: {e}")


def main() -> None:
    """Parse arguments and run raster clipping."""
    parser = argparse.ArgumentParser(
        description="Clip a raster using a bounding box or vector mask",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Clip with bounding box
  raster_clipper input.tif -bbox -180 -90 0 0 -o output.tif
  
  # Clip with vector mask
  raster_clipper input.tif -mask polygon.gpkg -o output.tif
  
  # Clip with bbox and verbose output
  raster_clipper input.tif -bbox -10 -10 10 10 -o output.tif -v
        """,
    )

    parser.add_argument("raster", help="Path to input raster")

    # Bounding box arguments
    parser.add_argument(
        "-bbox",
        nargs=4,
        type=float,
        metavar=("MINX", "MINY", "MAXX", "MAXY"),
        help="Bounding box coordinates (minx, miny, maxx, maxy)",
    )

    # Mask arguments
    parser.add_argument(
        "-mask",
        type=str,
        help="Path to vector mask file (GeoPackage, Shapefile, GeoJSON)",
    )

    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path to output clipped raster",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate that exactly one clipping method is provided
    if args.bbox and args.mask:
        logger.error("Provide either -bbox OR -mask, not both")
        sys.exit(1)

    if not args.bbox and not args.mask:
        logger.error("Provide either -bbox or -mask")
        sys.exit(1)

    try:
        if args.bbox:
            minx, miny, maxx, maxy = args.bbox
            result = clip_raster_bbox(args.raster, minx, miny, maxx, maxy, args.output)
            logger.info("Bounding box clipping completed successfully")

        else:
            result = clip_raster_mask(args.raster, args.mask, args.output)
            logger.info("Mask clipping completed successfully")

        sys.exit(0)

    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
