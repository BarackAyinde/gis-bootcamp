"""
Vector ETL Pipeline

A production-grade end-of-week project that composes all Week 1 tools into a single ETL workflow.

Pipeline stages:
1. Load raw vector dataset
2. Inspect dataset (metadata, CRS, geometry types)
3. Validate and repair geometries
4. Reproject to target CRS
5. Perform geoprocessing operation (clip, buffer, dissolve)
6. Write cleaned, production-ready output

Each stage includes error handling, logging, and rollback capability.
"""

import argparse
import logging
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import geopandas as gpd
from shapely.validation import make_valid

from gis_bootcamp.geometry_inspector import inspect_dataset
from gis_bootcamp.geometry_validation import validate_and_repair_dataset
from gis_bootcamp.vector_reprojection import reproject_dataset
from gis_bootcamp.vector_geoprocessing import (
    clip_dataset,
    buffer_dataset,
    dissolve_dataset,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_etl_pipeline(
    input_path,
    output_path,
    target_epsg,
    operation=None,
    operation_params=None,
    clip_path=None,
    drop_unfixable=False,
    verbose=False,
):
    """
    Execute complete vector ETL pipeline.

    Args:
        input_path (str): Input vector dataset path
        output_path (str): Output vector dataset path
        target_epsg (int): Target EPSG code for reprojection
        operation (str): Geoprocessing operation (clip, buffer, dissolve)
        operation_params (dict): Operation-specific parameters
            - clip: requires clip_path in this dict
            - buffer: requires distance, optionally dissolve
            - dissolve: optionally requires dissolve_by
        clip_path (str): Path to clipping geometry (for clip operation)
        drop_unfixable (bool): Drop unfixable geometries during validation
        verbose (bool): Print verbose output

    Returns:
        dict: Pipeline execution summary with stage results
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    summary = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "target_epsg": target_epsg,
        "operation": operation,
        "stages": {},
        "success": False,
    }

    try:
        # ===== STAGE 1: Load and Inspect Raw Data =====
        logger.info("=" * 70)
        logger.info("STAGE 1: Load and Inspect Raw Vector Dataset")
        logger.info("=" * 70)
        logger.info(f"Input file: {input_path}")

        if not Path(input_path).exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        raw_gdf = gpd.read_file(input_path)
        logger.info(f"✓ Loaded {len(raw_gdf)} features from {input_path}")

        # Inspect raw dataset
        raw_metadata = inspect_dataset(input_path)
        summary["stages"]["01_raw_inspection"] = {
            "feature_count": raw_metadata["feature_count"],
            "crs": str(raw_metadata["crs"]),
            "geometry_types": raw_metadata["geometry_types"],
            "null_count": raw_metadata["has_null_geometries"],
            "bounds": raw_metadata["bounds"],
        }
        logger.info(
            f"  Features: {raw_metadata['feature_count']} | "
            f"CRS: {raw_metadata['crs']} | "
            f"Geometry types: {raw_metadata['geometry_types']}"
        )

        # ===== STAGE 2: Validate and Repair Geometries =====
        logger.info("=" * 70)
        logger.info("STAGE 2: Validate and Repair Geometries")
        logger.info("=" * 70)

        with TemporaryDirectory() as tmpdir:
            repaired_path = f"{tmpdir}/repaired.gpkg"
            validate_and_repair_dataset(
                input_path, repaired_path, drop_unfixable=drop_unfixable
            )

            repaired_gdf = gpd.read_file(repaired_path)
            summary["stages"]["02_geometry_validation"] = {
                "input_count": len(raw_gdf),
                "output_count": len(repaired_gdf),
                "features_dropped": len(raw_gdf) - len(repaired_gdf),
                "null_count": repaired_gdf.geometry.isnull().sum(),
            }
            logger.info(
                f"✓ Geometry validation complete: "
                f"{len(raw_gdf)} → {len(repaired_gdf)} features"
            )

            # ===== STAGE 3: Reproject to Target CRS =====
            logger.info("=" * 70)
            logger.info("STAGE 3: Reproject to Target CRS")
            logger.info("=" * 70)
            logger.info(f"Target CRS: EPSG:{target_epsg}")

            reprojected_path = f"{tmpdir}/reprojected.gpkg"
            # Convert integer EPSG to "EPSG:XXXX" format for reprojection function
            target_epsg_str = f"EPSG:{target_epsg}"
            reproject_dataset(repaired_path, reprojected_path, target_epsg_str)

            reprojected_gdf = gpd.read_file(reprojected_path)
            original_crs = repaired_gdf.crs
            new_crs = reprojected_gdf.crs
            summary["stages"]["03_reprojection"] = {
                "original_crs": str(original_crs),
                "target_crs": f"EPSG:{target_epsg}",
                "new_crs": str(new_crs),
                "feature_count": len(reprojected_gdf),
            }
            logger.info(
                f"✓ Reprojection complete: "
                f"{original_crs} → {new_crs}"
            )

            # ===== STAGE 4: Geoprocessing (Optional) =====
            if operation:
                logger.info("=" * 70)
                logger.info(f"STAGE 4: Geoprocessing Operation - {operation.upper()}")
                logger.info("=" * 70)

                processed_path = f"{tmpdir}/processed.gpkg"

                if operation.lower() == "clip":
                    if not clip_path or not Path(clip_path).exists():
                        raise ValueError(
                            f"Clip operation requires valid clip_path. "
                            f"Got: {clip_path}"
                        )
                    logger.info(f"Clipping to geometry: {clip_path}")
                    clip_dataset(reprojected_path, clip_path, processed_path)
                    processed_gdf = gpd.read_file(processed_path)
                    summary["stages"]["04_geoprocessing"] = {
                        "operation": "clip",
                        "input_count": len(reprojected_gdf),
                        "output_count": len(processed_gdf),
                        "clip_path": str(clip_path),
                    }

                elif operation.lower() == "buffer":
                    if not operation_params or "distance" not in operation_params:
                        raise ValueError(
                            "Buffer operation requires distance parameter"
                        )
                    distance = operation_params["distance"]
                    dissolve_flag = operation_params.get("dissolve", False)
                    logger.info(
                        f"Buffering with distance: {distance} "
                        f"(dissolve={dissolve_flag})"
                    )
                    buffer_dataset(
                        reprojected_path, processed_path, distance, dissolve_flag
                    )
                    processed_gdf = gpd.read_file(processed_path)
                    summary["stages"]["04_geoprocessing"] = {
                        "operation": "buffer",
                        "distance": distance,
                        "dissolve": dissolve_flag,
                        "input_count": len(reprojected_gdf),
                        "output_count": len(processed_gdf),
                    }

                elif operation.lower() == "dissolve":
                    dissolve_by = operation_params.get("dissolve_by", None) if operation_params else None
                    logger.info(
                        f"Dissolving {'by ' + dissolve_by if dissolve_by else 'all to one'}"
                    )
                    dissolve_dataset(reprojected_path, processed_path, dissolve_by)
                    processed_gdf = gpd.read_file(processed_path)
                    summary["stages"]["04_geoprocessing"] = {
                        "operation": "dissolve",
                        "dissolve_by": dissolve_by,
                        "input_count": len(reprojected_gdf),
                        "output_count": len(processed_gdf),
                    }

                else:
                    raise ValueError(
                        f"Unknown operation: {operation}. "
                        f"Must be one of: clip, buffer, dissolve"
                    )

                logger.info(
                    f"✓ {operation.upper()} complete: "
                    f"{len(reprojected_gdf)} → {len(processed_gdf)} features"
                )
                final_gdf = processed_gdf
                final_path = processed_path
            else:
                logger.info("=" * 70)
                logger.info("STAGE 4: Geoprocessing - Skipped (no operation specified)")
                logger.info("=" * 70)
                final_gdf = reprojected_gdf
                final_path = reprojected_path
                summary["stages"]["04_geoprocessing"] = {
                    "operation": "none",
                    "feature_count": len(reprojected_gdf),
                }

            # ===== STAGE 5: Write Final Output =====
            logger.info("=" * 70)
            logger.info("STAGE 5: Write Final Output Dataset")
            logger.info("=" * 70)

            # Ensure output directory exists
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Write final dataset
            final_gdf.to_file(output_path, driver="GPKG")
            logger.info(f"✓ Output written to: {output_path}")

            # Final inspection
            final_metadata = inspect_dataset(output_path)
            summary["stages"]["05_final_output"] = {
                "feature_count": final_metadata["feature_count"],
                "crs": str(final_metadata["crs"]),
                "geometry_types": final_metadata["geometry_types"],
                "null_count": final_metadata["has_null_geometries"],
                "output_path": str(output_path),
            }

            # ===== PIPELINE COMPLETE =====
            logger.info("=" * 70)
            logger.info("VECTOR ETL PIPELINE COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Raw features: {raw_metadata['feature_count']}")
            logger.info(
                f"Final features: {final_metadata['feature_count']} "
                f"({final_metadata['crs']})"
            )
            logger.info(f"Output: {output_path}")

            summary["success"] = True
            return summary

    except Exception as e:
        logger.error(f"✗ ETL Pipeline failed at stage: {e}", exc_info=True)
        summary["success"] = False
        summary["error"] = str(e)
        raise


def main():
    """CLI entry point for vector ETL pipeline."""
    parser = argparse.ArgumentParser(
        description="Vector ETL Pipeline: Load, validate, reproject, process, output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reproject and validate only
  python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 -o output.gpkg

  # Reproject, validate, then clip
  python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 \\
    -op clip -cp clip.gpkg -o output.gpkg

  # Reproject, validate, then buffer
  python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 \\
    -op buffer -dist 1000 -o output.gpkg

  # Reproject, validate, then dissolve by attribute
  python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 \\
    -op dissolve -dby region -o output.gpkg

  # Verbose output
  python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 -o output.gpkg -v
        """,
    )

    parser.add_argument(
        "input",
        help="Input vector dataset (GeoPackage, Shapefile, GeoJSON)",
    )
    parser.add_argument(
        "-e",
        "--epsg",
        type=int,
        required=True,
        help="Target EPSG code for reprojection",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output GeoPackage path",
    )
    parser.add_argument(
        "-op",
        "--operation",
        choices=["clip", "buffer", "dissolve"],
        help="Geoprocessing operation (optional)",
    )
    parser.add_argument(
        "-cp",
        "--clip-path",
        help="Path to clipping geometry (for clip operation)",
    )
    parser.add_argument(
        "-dist",
        "--distance",
        type=float,
        help="Buffer distance in CRS units (for buffer operation)",
    )
    parser.add_argument(
        "-dby",
        "--dissolve-by",
        help="Attribute column to dissolve by (for dissolve operation)",
    )
    parser.add_argument(
        "-ds",
        "--dissolve-buffers",
        action="store_true",
        help="Dissolve buffers into single polygon (for buffer operation)",
    )
    parser.add_argument(
        "--drop-unfixable",
        action="store_true",
        help="Drop unfixable geometries during validation",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Validate operation-specific parameters
    operation_params = {}
    if args.operation == "clip":
        if not args.clip_path:
            parser.error("--clip-path required for clip operation")
    elif args.operation == "buffer":
        if args.distance is None:
            parser.error("--distance required for buffer operation")
        operation_params["distance"] = args.distance
        operation_params["dissolve"] = args.dissolve_buffers
    elif args.operation == "dissolve":
        if args.dissolve_by:
            operation_params["dissolve_by"] = args.dissolve_by

    try:
        summary = run_etl_pipeline(
            input_path=args.input,
            output_path=args.output,
            target_epsg=args.epsg,
            operation=args.operation,
            operation_params=operation_params,
            clip_path=args.clip_path,
            drop_unfixable=args.drop_unfixable,
            verbose=args.verbose,
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
