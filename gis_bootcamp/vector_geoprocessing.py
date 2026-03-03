#!/usr/bin/env python3
"""
Vector Geoprocessing: CLI tool for clip, buffer, and dissolve operations.

Performs explicit, deterministic geoprocessing operations on vector datasets:
- Clip: Clip features to a bounding geometry
- Buffer: Create a buffer zone around geometries
- Dissolve: Dissolve features based on an attribute and aggregate boundaries
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Literal, Optional

import geopandas as gpd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Supported operations
OPERATIONS = {"clip", "buffer", "dissolve"}


def clip_dataset(
    input_path: str,
    clip_path: str,
    output_path: str,
) -> dict:
    """
    Clip a dataset to a clipping geometry.

    Args:
        input_path: Path to input vector file
        clip_path: Path to clipping geometry file
        output_path: Path for output clipped file

    Returns:
        Dictionary with operation metadata

    Raises:
        FileNotFoundError: If input or clip file not found
        ValueError: If datasets empty, no CRS, or clip fails
    """
    input_path = Path(input_path)
    clip_path = Path(clip_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not clip_path.exists():
        raise FileNotFoundError(f"Clip file not found: {clip_path}")

    logger.info(f"Loading input dataset: {input_path}")
    try:
        gdf = gpd.read_file(input_path)
    except Exception as e:
        raise ValueError(f"Failed to read input file {input_path}: {e}")

    logger.info(f"Loading clip geometry: {clip_path}")
    try:
        gdf_clip = gpd.read_file(clip_path)
    except Exception as e:
        raise ValueError(f"Failed to read clip file {clip_path}: {e}")

    if gdf.empty:
        raise ValueError("Input dataset is empty")
    if gdf_clip.empty:
        raise ValueError("Clip dataset is empty")

    if gdf.crs is None or gdf_clip.crs is None:
        raise ValueError("Input or clip dataset has no CRS defined")

    # Ensure same CRS
    if str(gdf.crs) != str(gdf_clip.crs):
        logger.info(f"Reprojecting clip to {gdf.crs}")
        gdf_clip = gdf_clip.to_crs(gdf.crs)

    pre_count = len(gdf)
    logger.info(f"Input features: {pre_count}")
    logger.info(f"Clip geometry count: {len(gdf_clip)}")

    # Perform clip (using unary union of all clip geometries)
    try:
        clip_geom = gdf_clip.unary_union
        gdf_clipped = gpd.clip(gdf, clip_geom)
    except Exception as e:
        raise ValueError(f"Clip operation failed: {e}")

    post_count = len(gdf_clipped)
    logger.info(f"Clipped features: {post_count}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    try:
        gdf_clipped.to_file(output_path)
    except Exception as e:
        raise ValueError(f"Failed to write output file {output_path}: {e}")

    logger.info(f"Output written to: {output_path}")

    return {
        "operation": "clip",
        "input_path": str(input_path),
        "clip_path": str(clip_path),
        "output_path": str(output_path),
        "crs": str(gdf.crs),
        "input_count": pre_count,
        "output_count": post_count,
        "features_clipped": pre_count - post_count,
    }


def buffer_dataset(
    input_path: str,
    output_path: str,
    distance: float,
    dissolve: bool = False,
) -> dict:
    """
    Create a buffer around geometries.

    Args:
        input_path: Path to input vector file
        output_path: Path for output buffer file
        distance: Buffer distance in units of CRS (meters for projected, degrees for geographic)
        dissolve: If True, dissolve all buffers into single polygon

    Returns:
        Dictionary with operation metadata

    Raises:
        FileNotFoundError: If input file not found
        ValueError: If dataset empty, no CRS, or buffer fails
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info(f"Loading input dataset: {input_path}")
    try:
        gdf = gpd.read_file(input_path)
    except Exception as e:
        raise ValueError(f"Failed to read input file {input_path}: {e}")

    if gdf.empty:
        raise ValueError("Input dataset is empty")
    if gdf.crs is None:
        raise ValueError("Input dataset has no CRS defined")

    pre_count = len(gdf)
    logger.info(f"Input features: {pre_count}")
    logger.info(f"Buffer distance: {distance} (CRS units)")

    # Perform buffer
    try:
        gdf_buffered = gdf.copy()
        gdf_buffered["geometry"] = gdf.geometry.buffer(distance)
    except Exception as e:
        raise ValueError(f"Buffer operation failed: {e}")

    # Optionally dissolve
    if dissolve:
        logger.info("Dissolving all buffers into single polygon")
        try:
            gdf_buffered = gdf_buffered.dissolve()
            post_count = 1
        except Exception as e:
            raise ValueError(f"Dissolve operation failed: {e}")
    else:
        post_count = len(gdf_buffered)

    logger.info(f"Output features: {post_count}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    try:
        gdf_buffered.to_file(output_path)
    except Exception as e:
        raise ValueError(f"Failed to write output file {output_path}: {e}")

    logger.info(f"Output written to: {output_path}")

    return {
        "operation": "buffer",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "crs": str(gdf.crs),
        "distance": distance,
        "dissolve": dissolve,
        "input_count": pre_count,
        "output_count": post_count,
    }


def dissolve_dataset(
    input_path: str,
    output_path: str,
    dissolve_by: Optional[str] = None,
    aggregation: Optional[str] = None,
) -> dict:
    """
    Dissolve features based on an attribute.

    Args:
        input_path: Path to input vector file
        output_path: Path for output dissolved file
        dissolve_by: Attribute to dissolve by (if None, dissolve all into one)
        aggregation: Aggregation function for other columns (first, last, sum, mean, count)

    Returns:
        Dictionary with operation metadata

    Raises:
        FileNotFoundError: If input file not found
        ValueError: If dataset empty, no CRS, or dissolve fails
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info(f"Loading input dataset: {input_path}")
    try:
        gdf = gpd.read_file(input_path)
    except Exception as e:
        raise ValueError(f"Failed to read input file {input_path}: {e}")

    if gdf.empty:
        raise ValueError("Input dataset is empty")
    if gdf.crs is None:
        raise ValueError("Input dataset has no CRS defined")

    pre_count = len(gdf)
    logger.info(f"Input features: {pre_count}")

    if dissolve_by:
        logger.info(f"Dissolving by: {dissolve_by}")
        if dissolve_by not in gdf.columns:
            raise ValueError(f"Column '{dissolve_by}' not found in dataset")

    # Perform dissolve
    try:
        if dissolve_by:
            gdf_dissolved = gdf.dissolve(by=dissolve_by, aggfunc="first")
        else:
            logger.info("Dissolving all features into single polygon")
            gdf_dissolved = gdf.dissolve(aggfunc="first")
    except Exception as e:
        raise ValueError(f"Dissolve operation failed: {e}")

    post_count = len(gdf_dissolved)
    logger.info(f"Output features: {post_count}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    try:
        gdf_dissolved.to_file(output_path)
    except Exception as e:
        raise ValueError(f"Failed to write output file {output_path}: {e}")

    logger.info(f"Output written to: {output_path}")

    return {
        "operation": "dissolve",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "crs": str(gdf.crs),
        "dissolve_by": dissolve_by,
        "input_count": pre_count,
        "output_count": post_count,
        "features_dissolved": pre_count - post_count,
    }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Perform vector geoprocessing operations: clip, buffer, dissolve.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Operations:

CLIP:
  Clip input features to a clipping geometry.
  python -m gis_bootcamp.vector_geoprocessing clip input.gpkg clip.gpkg -o output.gpkg

BUFFER:
  Create a buffer zone around geometries.
  python -m gis_bootcamp.vector_geoprocessing buffer input.gpkg -d 1000 -o output.gpkg
  (use -ds to dissolve all buffers into single polygon)

DISSOLVE:
  Dissolve features by an attribute or all into one.
  python -m gis_bootcamp.vector_geoprocessing dissolve input.gpkg -o output.gpkg
  (all features become one)

  python -m gis_bootcamp.vector_geoprocessing dissolve input.gpkg -by country -o output.gpkg
  (dissolve by country attribute)

Examples:
  Clip countries to a region:
    python -m gis_bootcamp.vector_geoprocessing clip \\
      data/countries.gpkg data/region.gpkg -o output/clipped.gpkg

  Create 10km buffer around roads (projected CRS):
    python -m gis_bootcamp.vector_geoprocessing buffer \\
      data/roads.shp -d 10000 -o output/buffered.gpkg

  Create and dissolve buffer:
    python -m gis_bootcamp.vector_geoprocessing buffer \\
      data/points.gpkg -d 500 -ds -o output/merged_buffer.gpkg

  Dissolve countries by continent:
    python -m gis_bootcamp.vector_geoprocessing dissolve \\
      data/countries.gpkg -by continent -o output/continents.gpkg
        """,
    )

    subparsers = parser.add_subparsers(dest="operation", help="Operation to perform")

    # CLIP subparser
    clip_parser = subparsers.add_parser("clip", help="Clip to geometry")
    clip_parser.add_argument("input", help="Input vector file")
    clip_parser.add_argument("clip", help="Clipping geometry file")
    clip_parser.add_argument("-o", "--output", required=True, help="Output file")
    clip_parser.add_argument("-v", "--verbose", action="store_true")

    # BUFFER subparser
    buffer_parser = subparsers.add_parser("buffer", help="Create buffer")
    buffer_parser.add_argument("input", help="Input vector file")
    buffer_parser.add_argument(
        "-d", "--distance", type=float, required=True,
        help="Buffer distance (in CRS units)"
    )
    buffer_parser.add_argument("-o", "--output", required=True, help="Output file")
    buffer_parser.add_argument(
        "-ds", "--dissolve", action="store_true",
        help="Dissolve all buffers into single polygon"
    )
    buffer_parser.add_argument("-v", "--verbose", action="store_true")

    # DISSOLVE subparser
    dissolve_parser = subparsers.add_parser("dissolve", help="Dissolve features")
    dissolve_parser.add_argument("input", help="Input vector file")
    dissolve_parser.add_argument("-o", "--output", required=True, help="Output file")
    dissolve_parser.add_argument(
        "-by", "--dissolve-by", dest="dissolve_by",
        help="Dissolve by attribute (if omitted, dissolve all into one)"
    )
    dissolve_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if not args.operation:
        parser.print_help()
        return 1

    verbose = getattr(args, "verbose", False)
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.operation == "clip":
            results = clip_dataset(args.input, args.clip, args.output)
        elif args.operation == "buffer":
            results = buffer_dataset(
                args.input, args.output, args.distance, args.dissolve
            )
        elif args.operation == "dissolve":
            results = dissolve_dataset(
                args.input, args.output, args.dissolve_by
            )
        else:
            raise ValueError(f"Unknown operation: {args.operation}")

        print("\n" + "=" * 70)
        print(f"GEOPROCESSING COMPLETE: {results['operation'].upper()}")
        print("=" * 70)
        print(f"\nInput:  {results['input_path']}")
        print(f"Output: {results['output_path']}")
        print(f"CRS:    {results['crs']}")
        print(f"\nFeature Counts:")
        print(f"  Input:  {results['input_count']}")
        print(f"  Output: {results['output_count']}")

        if "features_clipped" in results:
            print(f"  Clipped: {results['features_clipped']}")
        if "distance" in results:
            print(f"\nBuffer Distance: {results['distance']} (CRS units)")
            if results.get("dissolve"):
                print("  Dissolved: Yes (all buffers merged)")
        if "features_dissolved" in results:
            print(f"  Dissolved: {results['features_dissolved']}")

        print("=" * 70 + "\n")

        logger.info(f"{results['operation'].capitalize()} completed successfully")
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
