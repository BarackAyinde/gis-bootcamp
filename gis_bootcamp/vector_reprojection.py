#!/usr/bin/env python3
"""
Vector Reprojection: CLI tool to reproject vector datasets.

Loads a vector file, validates CRS, reprojects to target EPSG,
and writes the result to disk with all attributes preserved.
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


def reproject_dataset(
    input_path: str, output_path: str, target_epsg: str
) -> dict:
    """
    Reproject a vector dataset to target EPSG and write to disk.

    Args:
        input_path: Path to input vector file
        output_path: Path for output reprojected file
        target_epsg: Target EPSG code (e.g., 'EPSG:3857')

    Returns:
        Dictionary with reprojection metadata

    Raises:
        FileNotFoundError: If input file does not exist
        ValueError: If CRS is missing, invalid EPSG, or reprojection fails
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info(f"Loading dataset: {input_path}")
    try:
        gdf = gpd.read_file(input_path)
    except Exception as e:
        raise ValueError(f"Failed to read input file {input_path}: {e}")

    if gdf.empty:
        raise ValueError("Dataset is empty (no features)")

    # Validate CRS exists
    if gdf.crs is None:
        raise ValueError(
            "Dataset has no CRS defined. Cannot reproject without source CRS. "
            "Set CRS first or specify source EPSG."
        )

    source_crs = str(gdf.crs)
    logger.info(f"Source CRS: {source_crs}")
    logger.info(f"Target CRS: {target_epsg}")

    # Validate target EPSG format
    if not target_epsg.startswith("EPSG:"):
        raise ValueError(
            f"Invalid EPSG format: {target_epsg}. Must be 'EPSG:XXXX' (e.g., 'EPSG:3857')"
        )

    # Perform reprojection
    try:
        gdf_reprojected = gdf.to_crs(target_epsg)
    except Exception as e:
        raise ValueError(f"Reprojection failed: {e}")

    logger.info(
        f"Reprojected {len(gdf_reprojected)} features from {source_crs} to {target_epsg}"
    )

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    try:
        gdf_reprojected.to_file(output_path)
    except Exception as e:
        raise ValueError(f"Failed to write output file {output_path}: {e}")

    logger.info(f"Output written to: {output_path}")

    # Collect metadata
    metadata = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_crs": source_crs,
        "target_crs": target_epsg,
        "feature_count": len(gdf_reprojected),
        "attributes": list(gdf_reprojected.columns),
        "geometry_types": gdf_reprojected.geometry.type.value_counts().to_dict(),
    }

    return metadata


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Reproject a vector GIS dataset to a target EPSG code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Reproject to Web Mercator (EPSG:3857):
    python -m gis_bootcamp.vector_reprojection data/roads.gpkg -t EPSG:3857 -o output/roads_3857.gpkg

  Reproject to UTM Zone 33N (EPSG:32633):
    python -m gis_bootcamp.vector_reprojection data/points.shp -t EPSG:32633 -o output/points_utm.shp

  Reproject to NAD83 (EPSG:4269):
    python -m gis_bootcamp.vector_reprojection data/parcels.geojson -t EPSG:4269 -o output/parcels_nad83.geojson
        """,
    )

    parser.add_argument(
        "input",
        help="Path to input vector file (GeoPackage, Shapefile, or GeoJSON)",
    )

    parser.add_argument(
        "-t",
        "--target",
        required=True,
        help="Target EPSG code (e.g., EPSG:3857, EPSG:4269)",
    )

    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path for output reprojected file",
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
        metadata = reproject_dataset(args.input, args.output, args.target)
        print("\n" + "=" * 70)
        print("REPROJECTION COMPLETE")
        print("=" * 70)
        print(f"\nInput:  {metadata['input_path']}")
        print(f"Output: {metadata['output_path']}")
        print(f"\nSource CRS: {metadata['source_crs']}")
        print(f"Target CRS: {metadata['target_crs']}")
        print(f"Features:   {metadata['feature_count']}")
        print(f"\nGeometry Types: {metadata['geometry_types']}")
        print(f"Attributes:     {len(metadata['attributes'])} columns")
        print("=" * 70 + "\n")
        logger.info("Reprojection completed successfully")
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
