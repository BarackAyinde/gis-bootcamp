#!/usr/bin/env python3
"""
Raster Metadata Inspector: CLI tool to inspect raster datasets.

Reads a raster file (GeoTIFF, COG, etc.) and prints metadata without
loading full raster data into memory:
- CRS
- Resolution (pixel size)
- Bounds (geographic extent)
- Number of bands
- Data type
- Nodata value
- Raster dimensions (width, height)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import rasterio
from rasterio.crs import CRS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def inspect_raster(file_path: str) -> dict:
    """
    Inspect a raster dataset and return metadata without loading pixel data.

    Args:
        file_path: Path to raster file (GeoTIFF, COG, etc.)

    Returns:
        Dictionary containing raster metadata

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file cannot be read or is not a valid raster
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    logger.info(f"Inspecting raster: {file_path}")
    
    try:
        with rasterio.open(file_path) as src:
            metadata = {
                "file_path": str(file_path),
                "crs": str(src.crs) if src.crs else None,
                "width": src.width,
                "height": src.height,
                "bounds": {
                    "minx": src.bounds.left,
                    "miny": src.bounds.bottom,
                    "maxx": src.bounds.right,
                    "maxy": src.bounds.top,
                },
                "bounds_crs": str(src.crs) if src.crs else None,
                "num_bands": src.count,
                "band_details": [],
                "transform": {
                    "a": src.transform.a,  # pixel width
                    "b": src.transform.b,  # rotation
                    "c": src.transform.c,  # x-coordinate of upper-left corner
                    "d": src.transform.d,  # rotation
                    "e": src.transform.e,  # pixel height (negative)
                    "f": src.transform.f,  # y-coordinate of upper-left corner
                },
                "pixel_size": {
                    "x": abs(src.transform.a),
                    "y": abs(src.transform.e),
                },
                "driver": src.driver,
                "compression": src.compression,
            }
            
            # Collect per-band metadata
            for band_idx in range(1, src.count + 1):
                band = src.read_masks(band_idx)
                band_meta = {
                    "band": band_idx,
                    "dtype": str(src.dtypes[band_idx - 1]),
                    "nodata": src.nodata,
                    "colorinterp": str(src.colorinterp[band_idx - 1]) if src.colorinterp else None,
                }
                metadata["band_details"].append(band_meta)
            
            # Convert CRS object to string for JSON serialization
            logger.info(f"Successfully read raster: {src.width}x{src.height}, {src.count} band(s)")
            
    except rasterio.errors.RasterioIOError as e:
        raise ValueError(f"Failed to read raster {file_path}: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error reading raster {file_path}: {e}")
    
    return metadata


def print_inspection(metadata: dict) -> None:
    """
    Pretty-print inspection results to stdout.

    Args:
        metadata: Dictionary of raster metadata
    """
    print("\n" + "=" * 70)
    print(f"RASTER METADATA INSPECTION")
    print("=" * 70)
    
    print(f"\nFile:                  {metadata['file_path']}")
    print(f"Driver:                {metadata['driver']}")
    print(f"Compression:           {metadata['compression']}")
    
    print(f"\nDimensions:")
    print(f"  Width (columns):      {metadata['width']}")
    print(f"  Height (rows):        {metadata['height']}")
    print(f"  Total pixels:         {metadata['width'] * metadata['height']:,}")
    
    print(f"\nGeospatial:")
    print(f"  CRS:                  {metadata['crs']}")
    bounds = metadata["bounds"]
    print(f"  Bounds (minx, miny, maxx, maxy):")
    print(f"    {bounds['minx']:.6f}, {bounds['miny']:.6f}")
    print(f"    {bounds['maxx']:.6f}, {bounds['maxy']:.6f}")
    
    pixel_size = metadata["pixel_size"]
    print(f"\nPixel Size:")
    print(f"  X resolution:         {pixel_size['x']:.10f}")
    print(f"  Y resolution:         {pixel_size['y']:.10f}")
    
    print(f"\nBands:")
    print(f"  Total bands:          {metadata['num_bands']}")
    
    for band in metadata["band_details"]:
        print(f"\n  Band {band['band']}:")
        print(f"    Data type:        {band['dtype']}")
        print(f"    Nodata value:     {band['nodata']}")
        print(f"    Color interp:     {band['colorinterp']}")
    
    print("\n" + "=" * 70 + "\n")


def print_json(metadata: dict) -> None:
    """
    Print metadata as JSON.

    Args:
        metadata: Dictionary of raster metadata
    """
    print(json.dumps(metadata, indent=2, default=str))


def main() -> None:
    """Parse arguments and run raster inspection."""
    parser = argparse.ArgumentParser(
        description="Inspect raster dataset metadata (GeoTIFF, COG, etc.)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  raster_metadata_inspector input.tif
  raster_metadata_inspector input.tif --json
  raster_metadata_inspector input.tif -v
        """,
    )
    
    parser.add_argument("raster", help="Path to raster file")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metadata as JSON",
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
        metadata = inspect_raster(args.raster)
        
        if args.json:
            print_json(metadata)
        else:
            print_inspection(metadata)
        
        logger.info("Inspection completed successfully")
        sys.exit(0)
        
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
