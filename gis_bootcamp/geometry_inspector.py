#!/usr/bin/env python3
"""
Geometry Inspector: CLI tool to inspect vector datasets.

Reads a vector file (GeoPackage, Shapefile, or GeoJSON) and prints:
- Geometry types and counts
- Feature count
- CRS
- Bounding box
- Attribute columns
"""

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def inspect_dataset(file_path: str) -> dict:
    """
    Inspect a vector dataset and return metadata.

    Args:
        file_path: Path to vector file (GeoPackage, Shapefile, GeoJSON)

    Returns:
        Dictionary containing dataset metadata

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file cannot be read or has no geometry
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    logger.info(f"Loading dataset: {file_path}")
    
    try:
        gdf = gpd.read_file(file_path)
    except Exception as e:
        raise ValueError(f"Failed to read file {file_path}: {e}")
    
    if gdf.empty:
        raise ValueError("Dataset is empty (no features)")
    
    if "geometry" not in gdf.columns:
        raise ValueError("Dataset has no geometry column")
    
    logger.info(f"Successfully loaded {len(gdf)} features")
    
    # Collect metadata
    metadata = {
        "file_path": str(file_path),
        "feature_count": len(gdf),
        "crs": gdf.crs,
        "bounds": gdf.total_bounds.tolist() if len(gdf) > 0 else None,
        "geometry_types": gdf.geometry.type.value_counts().to_dict(),
        "attributes": list(gdf.columns),
        "has_null_geometries": gdf.geometry.isnull().sum(),
    }
    
    return metadata


def print_inspection(metadata: dict) -> None:
    """
    Pretty-print inspection results to stdout.

    Args:
        metadata: Dictionary from inspect_dataset()
    """
    print("\n" + "=" * 70)
    print(f"GEOMETRY INSPECTION: {metadata['file_path']}")
    print("=" * 70)
    
    print(f"\nFeature Count: {metadata['feature_count']}")
    
    print(f"\nCRS: {metadata['crs'] if metadata['crs'] else 'None (no CRS defined)'}")
    
    if metadata['bounds']:
        minx, miny, maxx, maxy = metadata['bounds']
        print(f"\nBounding Box:")
        print(f"  Min X: {minx}")
        print(f"  Min Y: {miny}")
        print(f"  Max X: {maxx}")
        print(f"  Max Y: {maxy}")
    
    print(f"\nGeometry Types:")
    for geom_type, count in metadata['geometry_types'].items():
        print(f"  {geom_type}: {count}")
    
    print(f"\nNull Geometries: {metadata['has_null_geometries']}")
    
    print(f"\nAttribute Columns ({len(metadata['attributes'])}):")
    for attr in metadata['attributes']:
        print(f"  - {attr}")
    
    print("\n" + "=" * 70 + "\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Inspect a vector GIS dataset and print metadata.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  geometry_inspector data/roads.gpkg
  geometry_inspector data/parcels.shp
  geometry_inspector data/points.geojson
        """,
    )
    
    parser.add_argument(
        "input",
        help="Path to vector file (GeoPackage, Shapefile, or GeoJSON)",
    )
    
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        metadata = inspect_dataset(args.input)
        print_inspection(metadata)
        logger.info("Inspection completed successfully")
        return 0
    except FileNotFoundError as e:
        logger.error(f"File error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
