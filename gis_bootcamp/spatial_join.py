#!/usr/bin/env python3
"""
Spatial Join: CLI tool to perform spatial joins on vector datasets.

Loads two vector datasets, ensures they share a common CRS (reprojecting
if needed), performs a spatial join with a specified predicate, and writes
the joined dataset to disk.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Literal

import geopandas as gpd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Supported predicates for spatial joins
PREDICATES = {"intersects", "within", "contains"}


def spatial_join(
    left_path: str,
    right_path: str,
    output_path: str,
    predicate: str = "intersects",
    how: str = "left",
) -> dict:
    """
    Perform a spatial join on two vector datasets.

    Args:
        left_path: Path to left (base) vector file
        right_path: Path to right (join) vector file
        output_path: Path for output joined file
        predicate: Spatial predicate (intersects, within, contains)
        how: Join type (left, right, inner, outer)

    Returns:
        Dictionary with join metadata

    Raises:
        FileNotFoundError: If input files do not exist
        ValueError: If datasets are empty, have no CRS, or invalid predicate
    """
    left_path = Path(left_path)
    right_path = Path(right_path)
    output_path = Path(output_path)

    # Validate files exist
    if not left_path.exists():
        raise FileNotFoundError(f"Left file not found: {left_path}")
    if not right_path.exists():
        raise FileNotFoundError(f"Right file not found: {right_path}")

    # Validate predicate
    if predicate not in PREDICATES:
        raise ValueError(
            f"Invalid predicate: {predicate}. "
            f"Must be one of: {', '.join(PREDICATES)}"
        )

    # Load datasets
    logger.info(f"Loading left dataset: {left_path}")
    try:
        gdf_left = gpd.read_file(left_path)
    except Exception as e:
        raise ValueError(f"Failed to read left file {left_path}: {e}")

    logger.info(f"Loading right dataset: {right_path}")
    try:
        gdf_right = gpd.read_file(right_path)
    except Exception as e:
        raise ValueError(f"Failed to read right file {right_path}: {e}")

    # Validate non-empty
    if gdf_left.empty:
        raise ValueError("Left dataset is empty")
    if gdf_right.empty:
        raise ValueError("Right dataset is empty")

    # Validate CRS exists
    if gdf_left.crs is None:
        raise ValueError("Left dataset has no CRS defined")
    if gdf_right.crs is None:
        raise ValueError("Right dataset has no CRS defined")

    left_crs = str(gdf_left.crs)
    right_crs = str(gdf_right.crs)

    logger.info(f"Left CRS:  {left_crs}")
    logger.info(f"Right CRS: {right_crs}")

    # Handle CRS mismatch by reprojecting right to left
    if left_crs != right_crs:
        logger.info(f"CRS mismatch. Reprojecting right dataset to {left_crs}")
        try:
            gdf_right = gdf_right.to_crs(left_crs)
        except Exception as e:
            raise ValueError(f"Failed to reproject right dataset: {e}")

    # Log pre-join counts
    logger.info(
        f"Pre-join: {len(gdf_left)} left features, {len(gdf_right)} right features"
    )

    # Perform spatial join
    try:
        gdf_joined = gpd.sjoin(
            gdf_left,
            gdf_right,
            how=how,
            predicate=predicate,
        )
    except Exception as e:
        raise ValueError(f"Spatial join failed: {e}")

    # Log post-join count
    logger.info(f"Post-join: {len(gdf_joined)} features (how={how}, predicate={predicate})")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    try:
        gdf_joined.to_file(output_path)
    except Exception as e:
        raise ValueError(f"Failed to write output file {output_path}: {e}")

    logger.info(f"Output written to: {output_path}")

    # Collect metadata
    metadata = {
        "left_path": str(left_path),
        "right_path": str(right_path),
        "output_path": str(output_path),
        "left_crs": left_crs,
        "right_crs": right_crs,
        "predicate": predicate,
        "how": how,
        "left_count": len(gdf_left),
        "right_count": len(gdf_right),
        "joined_count": len(gdf_joined),
        "left_attributes": list(gdf_left.columns),
        "right_attributes": list(gdf_right.columns),
        "joined_attributes": list(gdf_joined.columns),
    }

    return metadata


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Perform a spatial join on two vector GIS datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Predicates:
  intersects  - geometries intersect (default)
  within      - left geometries are within right geometries
  contains    - left geometries contain right geometries

Join types:
  left        - keep all left features (default)
  right       - keep all right features
  inner       - keep features where both sides match
  outer       - keep all features from both sides

Examples:
  Point-in-polygon (cities within countries):
    python -m gis_bootcamp.spatial_join \\
      data/cities.gpkg data/countries.gpkg \\
      -o output/cities_in_countries.gpkg -p within

  Find intersecting features (roads crossing streams):
    python -m gis_bootcamp.spatial_join \\
      data/roads.shp data/streams.shp \\
      -o output/road_stream_intersections.gpkg

  Find containing features (districts containing points):
    python -m gis_bootcamp.spatial_join \\
      data/districts.gpkg data/points.geojson \\
      -o output/points_by_district.gpkg -p contains
        """,
    )

    parser.add_argument(
        "left",
        help="Path to left (base) vector file",
    )

    parser.add_argument(
        "right",
        help="Path to right (join) vector file",
    )

    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path for output joined file",
    )

    parser.add_argument(
        "-p",
        "--predicate",
        default="intersects",
        choices=list(PREDICATES),
        help="Spatial predicate (default: intersects)",
    )

    parser.add_argument(
        "-how",
        "--how",
        default="left",
        choices=["left", "right", "inner", "outer"],
        help="Join type (default: left)",
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
        metadata = spatial_join(
            args.left,
            args.right,
            args.output,
            predicate=args.predicate,
            how=args.how,
        )

        print("\n" + "=" * 70)
        print("SPATIAL JOIN COMPLETE")
        print("=" * 70)
        print(f"\nLeft:  {metadata['left_path']}")
        print(f"Right: {metadata['right_path']}")
        print(f"Output: {metadata['output_path']}")
        print(f"\nPredicate: {metadata['predicate']}")
        print(f"Join type: {metadata['how']}")
        print(f"\nCRS: {metadata['left_crs']}")
        if metadata['left_crs'] != metadata['right_crs']:
            print(f"  (Right dataset reprojected from {metadata['right_crs']})")
        print(f"\nFeature counts:")
        print(f"  Left:   {metadata['left_count']}")
        print(f"  Right:  {metadata['right_count']}")
        print(f"  Result: {metadata['joined_count']}")
        print(f"\nAttributes:")
        print(f"  Left:   {len(metadata['left_attributes'])} columns")
        print(f"  Right:  {len(metadata['right_attributes'])} columns")
        print(f"  Result: {len(metadata['joined_attributes'])} columns")
        print("=" * 70 + "\n")

        logger.info("Spatial join completed successfully")
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
