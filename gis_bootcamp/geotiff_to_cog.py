#!/usr/bin/env python3
"""
GeoTIFF to Cloud Optimized GeoTIFF (COG) Converter.

Converts standard GeoTIFF to Cloud Optimized GeoTIFF format with:
- Internal overviews (for multi-scale access)
- Proper tiling and block size
- COG compliance validation
"""

import argparse
import logging
import sys
from pathlib import Path

import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.shutil import copy
from rasterio.vrt import WarpedVRT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_cog(
    input_path: str,
    output_path: str,
    block_size: int = 512,
    overview_levels: list = None,
    resampling: str = "nearest",
) -> dict:
    """
    Convert a GeoTIFF to Cloud Optimized GeoTIFF (COG).

    A COG is a GeoTIFF with:
    - Internal overviews (for coarse-to-fine access)
    - Optimal tiling (typically 512x512 or 256x256 blocks)
    - Proper metadata for cloud-efficient access

    Args:
        input_path: Path to input GeoTIFF
        output_path: Path to output COG
        block_size: Block size for tiling (default 512)
        overview_levels: List of overview levels (default: auto-computed)
        resampling: Resampling method for overviews (default: nearest)

    Returns:
        Dictionary with COG creation results

    Raises:
        FileNotFoundError: If input file not found
        ValueError: If input is not a valid raster
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input raster not found: {input_path}")

    logger.info(f"Converting to COG: {input_path}")
    logger.info(f"Block size: {block_size}")

    try:
        with rasterio.open(input_path) as src:
            meta = src.meta.copy()
            width = src.width
            height = src.height
            dtype = src.dtypes[0]
            
            logger.info(f"Input dimensions: {width}x{height}, dtype: {dtype}")

            # Auto-compute overview levels if not provided
            if overview_levels is None:
                overview_levels = _compute_overview_levels(width, height)
            
            logger.info(f"Overview levels: {overview_levels}")

            # Update metadata for COG
            meta.update({
                "driver": "GTiff",
                "tiled": True,
                "blockxsize": block_size,
                "blockysize": block_size,
                "compress": "lzw",  # LZW compression is COG-friendly
            })

            # Create output directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write COG with overviews
            logger.info(f"Writing COG to: {output_path}")
            
            with rasterio.open(output_path, "w", **meta) as dst:
                # Copy data
                for band_idx in range(1, src.count + 1):
                    data = src.read(band_idx)
                    dst.write(data, band_idx)

                # Build overviews
                dst.build_overviews(overview_levels, Resampling.nearest)
                logger.info(f"Built overviews for {src.count} band(s)")

            logger.info("COG creation completed")

            return {
                "success": True,
                "input_file": str(input_path),
                "output_file": str(output_path),
                "input_dimensions": {"width": width, "height": height},
                "block_size": block_size,
                "overview_levels": overview_levels,
                "compression": "lzw",
                "bands": src.count,
                "dtype": dtype,
                "crs": str(src.crs) if src.crs else None,
                "is_tiled": True,
            }

    except rasterio.errors.RasterioIOError as e:
        raise ValueError(f"Failed to read input raster: {e}")
    except Exception as e:
        raise ValueError(f"COG creation failed: {e}")


def validate_cog(raster_path: str) -> dict:
    """
    Validate that a raster is COG-compliant.

    A valid COG should have:
    - Tiling enabled
    - Block size >= 256
    - Internal overviews
    - Compression (optional but recommended)

    Args:
        raster_path: Path to raster file to validate

    Returns:
        Dictionary with validation results

    Raises:
        FileNotFoundError: If file not found
        ValueError: If file cannot be read
    """
    raster_path = Path(raster_path)

    if not raster_path.exists():
        raise FileNotFoundError(f"File not found: {raster_path}")

    logger.info(f"Validating COG: {raster_path}")

    try:
        with rasterio.open(raster_path) as src:
            is_tiled = src.profile.get("tiled", False)
            block_size_x = src.profile.get("blockxsize", src.width)
            block_size_y = src.profile.get("blockysize", src.height)
            compression = src.profile.get("compress", None)
            
            # Check for overviews
            overviews = src.overviews(1) if src.count > 0 else []

            # Validation criteria
            checks = {
                "is_tiled": is_tiled,
                "block_size_valid": block_size_x >= 256 and block_size_y >= 256,
                "has_overviews": len(overviews) > 0,
                "has_compression": compression is not None,
                "block_size": (block_size_x, block_size_y),
                "overview_count": len(overviews),
                "overview_levels": overviews,
                "compression": compression,
            }

            # Overall COG compliance (not all checks are required)
            is_cog_compliant = (
                checks["is_tiled"] 
                and checks["block_size_valid"]
                and checks["has_overviews"]
            )

            logger.info(f"Tiled: {is_tiled}")
            logger.info(f"Block size: {block_size_x}x{block_size_y}")
            logger.info(f"Overviews: {len(overviews)}")
            logger.info(f"Compression: {compression}")
            logger.info(f"COG compliant: {is_cog_compliant}")

            return {
                "file": str(raster_path),
                "is_cog_compliant": is_cog_compliant,
                "checks": checks,
            }

    except rasterio.errors.RasterioIOError as e:
        raise ValueError(f"Failed to read raster: {e}")
    except Exception as e:
        raise ValueError(f"Validation failed: {e}")


def _compute_overview_levels(width: int, height: int, min_size: int = 512) -> list:
    """
    Auto-compute appropriate overview levels for a raster.

    Args:
        width: Raster width
        height: Raster height
        min_size: Minimum dimension for smallest overview (default: 512)

    Returns:
        List of overview levels (e.g., [2, 4, 8, 16])
    """
    levels = []
    max_dim = max(width, height)
    level = 2

    while max_dim // level >= min_size:
        levels.append(level)
        level *= 2

    # If no levels computed (small raster), add at least level 2
    return levels if levels else [2]


def main() -> None:
    """Parse arguments and run COG conversion."""
    parser = argparse.ArgumentParser(
        description="Convert GeoTIFF to Cloud Optimized GeoTIFF (COG)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic COG creation
  geotiff_to_cog input.tif -o output_cog.tif
  
  # With custom block size and validation
  geotiff_to_cog input.tif -o output_cog.tif -b 256
  
  # Validate existing raster for COG compliance
  geotiff_to_cog --validate input.tif
  
  # Create and validate
  geotiff_to_cog input.tif -o output_cog.tif --validate-output
        """,
    )

    parser.add_argument("input", help="Path to input GeoTIFF")
    
    parser.add_argument(
        "-o", "--output",
        help="Path to output COG (required unless --validate)",
    )

    parser.add_argument(
        "-b", "--block-size",
        type=int,
        default=512,
        help="Block size for COG tiling (default: 512)",
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate input raster for COG compliance (no output file created)",
    )

    parser.add_argument(
        "--validate-output",
        action="store_true",
        help="Validate output COG after creation",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Validate-only mode
        if args.validate:
            result = validate_cog(args.input)
            if result["is_cog_compliant"]:
                print(f"✓ {args.input} is COG-compliant")
            else:
                print(f"✗ {args.input} is NOT COG-compliant")
                print(f"  Issues: {result['checks']}")
            sys.exit(0)

        # Create COG mode
        if not args.output:
            logger.error("--output required for COG creation (or use --validate for validation-only)")
            sys.exit(1)

        result = create_cog(args.input, args.output, block_size=args.block_size)
        logger.info("COG creation completed successfully")

        # Validate output if requested
        if args.validate_output:
            logger.info("Validating output COG...")
            validation = validate_cog(args.output)
            if validation["is_cog_compliant"]:
                logger.info("✓ Output is COG-compliant")
            else:
                logger.warning("⚠ Output may not be fully COG-compliant")
                logger.warning(f"Checks: {validation['checks']}")

        sys.exit(0)

    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
