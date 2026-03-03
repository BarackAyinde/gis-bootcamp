"""
vector_to_geoparquet.py — CLI tool to convert vector datasets to GeoParquet format.

Validates CRS and geometry presence before writing. Preserves all attributes
and spatial metadata. Uses GeoPandas + pyarrow as the Parquet engine.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd

logger = logging.getLogger(__name__)


def convert_to_geoparquet(
    input_path: str,
    output_path: str,
    layer: Optional[str] = None,
) -> dict:
    """
    Convert a vector dataset to GeoParquet format.

    Args:
        input_path: Path to input vector file (GPKG, Shapefile, GeoJSON, etc.).
        output_path: Output path for the .parquet file.
        layer: Optional layer name for multi-layer sources (e.g. GeoPackage).

    Returns:
        dict with keys: output_path, feature_count, crs, geometry_types,
                        columns, file_size_bytes.

    Raises:
        FileNotFoundError: Input file does not exist.
        ValueError: Dataset is empty, has no CRS, or has no geometry column.
        Exception: Any read/write failure propagated as-is.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info("Loading: %s", input_path)

    read_kwargs = {}
    if layer:
        read_kwargs["layer"] = layer

    gdf = gpd.read_file(input_path, **read_kwargs)

    # Validate dataset
    if len(gdf) == 0:
        raise ValueError(f"Dataset is empty: {input_path}")

    if gdf.geometry is None or gdf.geometry.name not in gdf.columns:
        raise ValueError(f"No geometry column found in: {input_path}")

    if gdf.crs is None:
        raise ValueError(
            f"Dataset has no CRS. GeoParquet requires a defined CRS: {input_path}"
        )

    # Log summary
    feature_count = len(gdf)
    geom_types = gdf.geometry.geom_type.value_counts().to_dict()
    crs_str = gdf.crs.to_string()

    logger.info("Feature count  : %d", feature_count)
    logger.info("CRS            : %s", crs_str)
    logger.info("Geometry types : %s", geom_types)
    logger.info(
        "Columns        : %s",
        [c for c in gdf.columns if c != gdf.geometry.name],
    )

    # Write output
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Writing GeoParquet: %s", output_path)
    gdf.to_parquet(output_path, engine="pyarrow", index=False)

    file_size = out_path.stat().st_size
    logger.info("Done. File size: %d bytes", file_size)

    return {
        "output_path": output_path,
        "feature_count": feature_count,
        "crs": crs_str,
        "geometry_types": geom_types,
        "columns": list(gdf.columns),
        "file_size_bytes": file_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a vector dataset to GeoParquet format"
    )
    parser.add_argument("input", help="Input vector file path")
    parser.add_argument("-o", "--output", required=True, help="Output .parquet path")
    parser.add_argument(
        "-l", "--layer", default=None, help="Layer name (for multi-layer sources)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = convert_to_geoparquet(
            input_path=args.input,
            output_path=args.output,
            layer=args.layer,
        )
        print(f"\nConversion complete")
        print(f"  Input          : {args.input}")
        print(f"  Output         : {result['output_path']}")
        print(f"  Features       : {result['feature_count']}")
        print(f"  CRS            : {result['crs']}")
        print(f"  Geometry types : {result['geometry_types']}")
        print(f"  File size      : {result['file_size_bytes']:,} bytes")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
