#!/usr/bin/env python3
"""
Geometry Validation & Repair: CLI tool to detect and fix invalid geometries.

Loads a vector dataset, validates all geometries, attempts to repair invalid
ones using Shapely techniques, and writes a cleaned dataset to disk with
detailed logs of all fixes and failures.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape
from shapely.validation import make_valid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def validate_and_repair_dataset(
    input_path: str,
    output_path: str,
    drop_unfixable: bool = False,
) -> dict:
    """
    Validate and repair geometries in a vector dataset.

    Args:
        input_path: Path to input vector file
        output_path: Path for cleaned output file
        drop_unfixable: If True, drop rows with unfixable geometries.
                       If False, keep them as-is.

    Returns:
        Dictionary with validation/repair metadata

    Raises:
        FileNotFoundError: If input file does not exist
        ValueError: If dataset is empty or has no geometry column
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

    if "geometry" not in gdf.columns:
        raise ValueError("Dataset has no geometry column")

    initial_count = len(gdf)
    logger.info(f"Loaded {initial_count} features")

    # Analyze geometries before repair
    validation_results = {
        "initial_count": initial_count,
        "null_geometries": int(gdf.geometry.isnull().sum()),
        "invalid_geometries": 0,
        "empty_geometries": 0,
        "fixed_count": 0,
        "unfixable_count": 0,
        "dropped_count": 0,
        "issues_by_row": {},
    }

    # Check each geometry
    for idx, geom in enumerate(gdf.geometry):
        if geom is None:
            validation_results["issues_by_row"][idx] = "null_geometry"
        elif geom.is_empty:
            validation_results["empty_geometries"] += 1
            validation_results["issues_by_row"][idx] = "empty_geometry"
        elif not geom.is_valid:
            validation_results["invalid_geometries"] += 1
            validation_results["issues_by_row"][idx] = f"invalid: {geom.geom_type}"

    # Attempt repairs
    repaired_geometries = []
    rows_to_keep = []

    for idx, geom in enumerate(gdf.geometry):
        if geom is None:
            # Keep null as-is
            repaired_geometries.append(None)
            rows_to_keep.append(idx)
        elif geom.is_empty:
            # Try to recreate from scratch (not possible, keep as-is)
            repaired_geometries.append(geom)
            rows_to_keep.append(idx)
        elif not geom.is_valid:
            # Try to repair using make_valid
            try:
                fixed_geom = make_valid(geom)
                if fixed_geom.is_valid and not fixed_geom.is_empty:
                    repaired_geometries.append(fixed_geom)
                    validation_results["fixed_count"] += 1
                    logger.debug(f"Row {idx}: Fixed invalid {geom.geom_type}")
                    rows_to_keep.append(idx)
                else:
                    # Repair unsuccessful
                    validation_results["unfixable_count"] += 1
                    if drop_unfixable:
                        logger.debug(f"Row {idx}: Dropped unfixable geometry")
                    else:
                        repaired_geometries.append(geom)
                        rows_to_keep.append(idx)
            except Exception as e:
                validation_results["unfixable_count"] += 1
                logger.debug(f"Row {idx}: Repair failed ({e})")
                if not drop_unfixable:
                    repaired_geometries.append(geom)
                    rows_to_keep.append(idx)
        else:
            # Valid geometry, keep as-is
            repaired_geometries.append(geom)
            rows_to_keep.append(idx)

    # Create repaired GeoDataFrame
    gdf_repaired = gdf.iloc[rows_to_keep].copy()
    gdf_repaired["geometry"] = [repaired_geometries[i] for i in rows_to_keep]

    validation_results["dropped_count"] = initial_count - len(gdf_repaired)
    validation_results["final_count"] = len(gdf_repaired)

    logger.info(f"Validation complete:")
    logger.info(f"  - Invalid geometries: {validation_results['invalid_geometries']}")
    logger.info(f"  - Empty geometries: {validation_results['empty_geometries']}")
    logger.info(f"  - Null geometries: {validation_results['null_geometries']}")
    logger.info(f"  - Fixed: {validation_results['fixed_count']}")
    logger.info(f"  - Unfixable: {validation_results['unfixable_count']}")
    logger.info(f"  - Dropped: {validation_results['dropped_count']}")
    logger.info(f"  - Final count: {validation_results['final_count']}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    try:
        gdf_repaired.to_file(output_path)
    except Exception as e:
        raise ValueError(f"Failed to write output file {output_path}: {e}")

    logger.info(f"Output written to: {output_path}")

    return validation_results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate and repair geometries in a vector GIS dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Repair techniques:
  - make_valid(): Fixes self-intersecting polygons, invalid rings, etc.
  - Null geometries: Logged but kept
  - Empty geometries: Logged but kept (cannot be repaired)
  - All fixes are logged row-by-row for auditing

Examples:
  Repair and keep unfixable geometries:
    python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg

  Repair and drop unfixable geometries:
    python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg --drop

  Verbose output with detailed logs:
    python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg -v
        """,
    )

    parser.add_argument(
        "input",
        help="Path to input vector file (GeoPackage, Shapefile, or GeoJSON)",
    )

    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path for output cleaned file",
    )

    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop rows with unfixable geometries (default: keep them)",
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
        results = validate_and_repair_dataset(
            args.input,
            args.output,
            drop_unfixable=args.drop,
        )

        print("\n" + "=" * 70)
        print("GEOMETRY VALIDATION & REPAIR COMPLETE")
        print("=" * 70)
        print(f"\nInput:  {args.input}")
        print(f"Output: {args.output}")
        print(f"\nGeometry Issues Found:")
        print(f"  Invalid geometries:  {results['invalid_geometries']}")
        print(f"  Empty geometries:    {results['empty_geometries']}")
        print(f"  Null geometries:     {results['null_geometries']}")
        print(f"\nRepair Results:")
        print(f"  Fixed:     {results['fixed_count']}")
        print(f"  Unfixable: {results['unfixable_count']}")
        print(f"  Dropped:   {results['dropped_count']}")
        print(f"\nFeature Counts:")
        print(f"  Initial: {results['initial_count']}")
        print(f"  Final:   {results['final_count']}")
        print("=" * 70 + "\n")

        logger.info("Validation and repair completed successfully")
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
