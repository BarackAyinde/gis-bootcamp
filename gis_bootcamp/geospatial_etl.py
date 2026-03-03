"""
geospatial_etl.py — Geospatial ETL Platform.

Declarative extract-transform-load pipeline for vector geospatial datasets.
Define a source, a sequence of transforms, and a sink in code or as a JSON
config file. All transforms are composable and stateless.

Sources:
  file     — any format geopandas reads (GPKG, Shapefile, GeoJSON, GeoParquet)
  postgis  — PostGIS table via sqlalchemy (requires psycopg2-binary at runtime)

Transforms (11):
  reproject         — re-project to a target CRS
  filter            — attribute filter via pandas query expression
  clip_bbox         — clip features to a bounding box [minx, miny, maxx, maxy]
  buffer            — buffer geometries by a distance (CRS units)
  dissolve          — dissolve features by an attribute column (or dissolve all)
  rename_columns    — rename one or more attribute columns
  drop_columns      — remove attribute columns by name
  select_columns    — keep only the specified attribute columns (+ geometry)
  validate_geometry — fix (make_valid) or drop geometries that fail is_valid
  deduplicate       — remove duplicate rows based on a column subset
  add_attribute     — add a new column with a constant value

Sinks:
  file     — GPKG (default), GeoJSON, Shapefile, GeoParquet
  postgis  — PostGIS table

Pipeline definition (dict or JSON file):
    {
        "name": "parcels_clean",
        "source": {"type": "file", "path": "raw/parcels.gpkg"},
        "transforms": [
            {"type": "reproject", "crs": "EPSG:4326"},
            {"type": "filter", "query": "area_m2 > 50"},
            {"type": "validate_geometry", "action": "fix"},
            {"type": "drop_columns", "columns": ["tmp_id"]}
        ],
        "sink": {"type": "file", "path": "clean/parcels.gpkg"}
    }

Example:
    from gis_bootcamp.geospatial_etl import run_pipeline
    result = run_pipeline({
        "name": "demo",
        "source": {"type": "file", "path": "parcels.gpkg"},
        "transforms": [{"type": "reproject", "crs": "EPSG:4326"}],
        "sink":   {"type": "file", "path": "output/parcels_wgs84.gpkg"},
    })
    print(f"{result['rows_in']} in → {result['rows_out']} out")
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
from shapely import make_valid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transform implementations
# ---------------------------------------------------------------------------

def _transform_reproject(gdf: gpd.GeoDataFrame, crs: str, **_) -> gpd.GeoDataFrame:
    """Re-project to a target CRS."""
    before_crs = gdf.crs.to_string() if gdf.crs else "None"
    gdf = gdf.to_crs(crs)
    logger.info("  reproject: %s → %s", before_crs, crs)
    return gdf


def _transform_filter(gdf: gpd.GeoDataFrame, query: str, **_) -> gpd.GeoDataFrame:
    """Filter rows using a pandas query expression."""
    before = len(gdf)
    gdf = gdf.query(query).copy()
    logger.info("  filter '%s': %d → %d rows", query, before, len(gdf))
    return gdf


def _transform_clip_bbox(
    gdf: gpd.GeoDataFrame,
    bbox: list[float],
    **_,
) -> gpd.GeoDataFrame:
    """Clip features to a bounding box [minx, miny, maxx, maxy]."""
    from shapely.geometry import box as shapely_box
    before = len(gdf)
    clip_geom = shapely_box(*bbox)
    gdf = gdf.clip(clip_geom).copy()
    logger.info("  clip_bbox %s: %d → %d rows", bbox, before, len(gdf))
    return gdf


def _transform_buffer(
    gdf: gpd.GeoDataFrame,
    distance: float,
    cap_style: str = "round",
    **_,
) -> gpd.GeoDataFrame:
    """Buffer all geometries by distance (in CRS units)."""
    _cap = {"round": 1, "flat": 2, "square": 3}.get(cap_style, 1)
    gdf = gdf.copy()
    gdf.geometry = gdf.geometry.buffer(distance, cap_style=_cap)
    logger.info("  buffer distance=%s cap_style=%s", distance, cap_style)
    return gdf


def _transform_dissolve(
    gdf: gpd.GeoDataFrame,
    by: Optional[str] = None,
    aggfunc: str = "first",
    **_,
) -> gpd.GeoDataFrame:
    """Dissolve features by a column (or dissolve all into one if by=None)."""
    before = len(gdf)
    dissolved = gdf.dissolve(by=by, aggfunc=aggfunc)
    gdf = dissolved.reset_index() if by is not None else dissolved.reset_index(drop=True)
    logger.info("  dissolve by=%s aggfunc=%s: %d → %d rows", by, aggfunc, before, len(gdf))
    return gdf


def _transform_rename_columns(
    gdf: gpd.GeoDataFrame,
    mapping: dict[str, str],
    **_,
) -> gpd.GeoDataFrame:
    """Rename attribute columns using a {old_name: new_name} mapping."""
    gdf = gdf.rename(columns=mapping)
    logger.info("  rename_columns: %s", mapping)
    return gdf


def _transform_drop_columns(
    gdf: gpd.GeoDataFrame,
    columns: list[str],
    **_,
) -> gpd.GeoDataFrame:
    """Drop attribute columns by name; silently ignores columns that don't exist."""
    existing = [c for c in columns if c in gdf.columns]
    gdf = gdf.drop(columns=existing)
    logger.info("  drop_columns: removed %d of %d requested (%s)", len(existing), len(columns), existing)
    return gdf


def _transform_select_columns(
    gdf: gpd.GeoDataFrame,
    columns: list[str],
    **_,
) -> gpd.GeoDataFrame:
    """Keep only the specified attribute columns (geometry is always retained)."""
    geom_col = gdf.geometry.name
    keep = list(dict.fromkeys([*columns, geom_col]))  # preserve order, deduplicate
    keep = [c for c in keep if c in gdf.columns]
    gdf = gdf[keep]
    logger.info("  select_columns → %s", keep)
    return gdf


def _transform_validate_geometry(
    gdf: gpd.GeoDataFrame,
    action: str = "fix",
    **_,
) -> gpd.GeoDataFrame:
    """Fix or drop invalid geometries.

    action="fix"  — apply shapely.make_valid to all geometries
    action="drop" — remove rows with invalid geometries
    """
    if action not in ("fix", "drop"):
        raise ValueError(f"validate_geometry: action must be 'fix' or 'drop', got '{action}'")
    before = len(gdf)
    if action == "fix":
        gdf = gdf.copy()
        gdf.geometry = gdf.geometry.apply(make_valid)
    else:
        gdf = gdf[gdf.geometry.is_valid].copy()
    logger.info("  validate_geometry action=%s: %d → %d rows", action, before, len(gdf))
    return gdf


def _transform_deduplicate(
    gdf: gpd.GeoDataFrame,
    columns: Optional[list[str]] = None,
    keep: str = "first",
    **_,
) -> gpd.GeoDataFrame:
    """Remove duplicate rows based on a column subset (or all columns if None)."""
    before = len(gdf)
    gdf = gdf.drop_duplicates(subset=columns, keep=keep).copy()
    logger.info("  deduplicate on %s: %d → %d rows", columns, before, len(gdf))
    return gdf


def _transform_add_attribute(
    gdf: gpd.GeoDataFrame,
    column: str,
    value: Any,
    **_,
) -> gpd.GeoDataFrame:
    """Add a new column with a constant value (overwrites if column already exists)."""
    gdf = gdf.copy()
    gdf[column] = value
    logger.info("  add_attribute '%s' = %r", column, value)
    return gdf


_TRANSFORMS: dict[str, Any] = {
    "reproject":         _transform_reproject,
    "filter":            _transform_filter,
    "clip_bbox":         _transform_clip_bbox,
    "buffer":            _transform_buffer,
    "dissolve":          _transform_dissolve,
    "rename_columns":    _transform_rename_columns,
    "drop_columns":      _transform_drop_columns,
    "select_columns":    _transform_select_columns,
    "validate_geometry": _transform_validate_geometry,
    "deduplicate":       _transform_deduplicate,
    "add_attribute":     _transform_add_attribute,
}


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------

def _read_source(source: dict) -> tuple[gpd.GeoDataFrame, dict]:
    src_type = source.get("type", "file")

    if src_type == "file":
        path = source.get("path")
        if not path:
            raise ValueError("File source requires a 'path' key")
        if not Path(path).exists():
            raise FileNotFoundError(f"Source file not found: {path}")
        kwargs: dict[str, Any] = {}
        if "layer" in source:
            kwargs["layer"] = source["layer"]
        gdf = gpd.read_file(path, **kwargs)
        return gdf, {
            "type": "file",
            "path": path,
            "feature_count": len(gdf),
            "crs": gdf.crs.to_string() if gdf.crs else None,
        }

    elif src_type == "postgis":
        from gis_bootcamp.postgis_client import make_engine
        dsn = source.get("dsn")
        table = source.get("table")
        if not dsn or not table:
            raise ValueError("PostGIS source requires 'dsn' and 'table' keys")
        schema = source.get("schema", "public")
        geom_col = source.get("geom_col", "geom")
        where = source.get("where")
        engine = make_engine(dsn)
        sql = f'SELECT * FROM "{schema}"."{table}"'
        if where:
            sql += f" WHERE {where}"
        gdf = gpd.read_postgis(sql, engine, geom_col=geom_col)
        return gdf, {
            "type": "postgis",
            "table": f"{schema}.{table}",
            "feature_count": len(gdf),
            "crs": gdf.crs.to_string() if gdf.crs else None,
        }

    else:
        raise ValueError(f"Unknown source type '{src_type}'. Must be 'file' or 'postgis'")


# ---------------------------------------------------------------------------
# Sink writers
# ---------------------------------------------------------------------------

def _write_sink(gdf: gpd.GeoDataFrame, sink: dict) -> dict:
    sink_type = sink.get("type", "file")

    if sink_type == "file":
        path = sink.get("path")
        if not path:
            raise ValueError("File sink requires a 'path' key")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        ext = Path(path).suffix.lower()
        if ext == ".parquet":
            gdf.to_parquet(path, engine="pyarrow", index=False)
        elif ext in (".geojson", ".json"):
            gdf.to_file(path, driver="GeoJSON")
        elif ext == ".shp":
            gdf.to_file(path, driver="ESRI Shapefile")
        else:
            gdf.to_file(path, driver="GPKG")
        return {
            "type": "file",
            "path": path,
            "feature_count": len(gdf),
            "crs": gdf.crs.to_string() if gdf.crs else None,
        }

    elif sink_type == "postgis":
        from gis_bootcamp.postgis_client import make_engine
        dsn = sink.get("dsn")
        table = sink.get("table")
        if not dsn or not table:
            raise ValueError("PostGIS sink requires 'dsn' and 'table' keys")
        schema = sink.get("schema", "public")
        if_exists = sink.get("if_exists", "replace")
        engine = make_engine(dsn)
        gdf.to_postgis(name=table, con=engine, schema=schema, if_exists=if_exists)
        return {
            "type": "postgis",
            "table": f"{schema}.{table}",
            "feature_count": len(gdf),
            "crs": gdf.crs.to_string() if gdf.crs else None,
        }

    else:
        raise ValueError(f"Unknown sink type '{sink_type}'. Must be 'file' or 'postgis'")


# ---------------------------------------------------------------------------
# Pipeline validation
# ---------------------------------------------------------------------------

def validate_pipeline(pipeline_def: dict) -> list[str]:
    """
    Validate a pipeline definition without executing it.

    Args:
        pipeline_def: Pipeline dict to validate.

    Returns:
        List of error strings (empty list means valid).
    """
    errors: list[str] = []

    if "source" not in pipeline_def:
        errors.append("Missing 'source' definition")
    else:
        src_type = pipeline_def["source"].get("type", "file")
        if src_type not in ("file", "postgis"):
            errors.append(f"Unknown source type '{src_type}'")

    if "sink" not in pipeline_def:
        errors.append("Missing 'sink' definition")
    else:
        snk_type = pipeline_def["sink"].get("type", "file")
        if snk_type not in ("file", "postgis"):
            errors.append(f"Unknown sink type '{snk_type}'")

    for i, t in enumerate(pipeline_def.get("transforms", [])):
        t_type = t.get("type")
        if not t_type:
            errors.append(f"Transform #{i}: missing 'type' key")
        elif t_type not in _TRANSFORMS:
            errors.append(
                f"Transform #{i}: unknown type '{t_type}'. "
                f"Available: {sorted(_TRANSFORMS)}"
            )

    return errors


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(pipeline_def: dict) -> dict:
    """
    Execute an ETL pipeline.

    Args:
        pipeline_def: Pipeline definition dict with keys:
            name (str, optional): Pipeline name (default "unnamed").
            source (dict): Source definition with 'type' and type-specific params.
            transforms (list[dict], optional): Ordered list of transform defs.
            sink (dict): Sink definition with 'type' and type-specific params.

    Returns:
        dict with:
            pipeline_name   — name from the definition
            source          — source metadata (type, path/table, feature_count, crs)
            transforms_applied — ordered list of transform type names run
            sink            — sink metadata (type, path/table, feature_count, crs)
            rows_in         — feature count after reading source
            rows_out        — feature count written to sink
            rows_dropped    — rows_in - rows_out
            duration_seconds — wall-clock time for the full run

    Raises:
        FileNotFoundError: Source file not found.
        ValueError: Invalid pipeline definition, unknown source/sink/transform type.
    """
    name = pipeline_def.get("name", "unnamed")

    # Validate up front so errors surface before any I/O
    errors = validate_pipeline(pipeline_def)
    if errors:
        raise ValueError(
            f"Pipeline '{name}' has {len(errors)} configuration error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    transforms = pipeline_def.get("transforms", [])
    source_def = pipeline_def["source"]
    sink_def = pipeline_def["sink"]

    t0 = time.perf_counter()
    logger.info("Pipeline '%s': starting (%d transform(s))", name, len(transforms))

    # ── Extract ──────────────────────────────────────────────────────────────
    logger.info("Extracting from source: type=%s", source_def.get("type", "file"))
    gdf, source_meta = _read_source(source_def)
    rows_in = len(gdf)
    logger.info("  %d features  CRS=%s", rows_in, source_meta.get("crs"))

    # ── Transform ────────────────────────────────────────────────────────────
    transforms_applied: list[str] = []
    for t in transforms:
        t_type = t["type"]
        params = {k: v for k, v in t.items() if k != "type"}
        logger.info("Applying transform: %s %s", t_type, params or "")
        gdf = _TRANSFORMS[t_type](gdf, **params)
        transforms_applied.append(t_type)

    # ── Load ─────────────────────────────────────────────────────────────────
    logger.info("Loading to sink: type=%s", sink_def.get("type", "file"))
    sink_meta = _write_sink(gdf, sink_def)
    rows_out = len(gdf)

    duration = time.perf_counter() - t0
    logger.info(
        "Pipeline '%s' complete: %d → %d rows (dropped %d) in %.3fs",
        name, rows_in, rows_out, rows_in - rows_out, duration,
    )

    return {
        "pipeline_name": name,
        "source": source_meta,
        "transforms_applied": transforms_applied,
        "sink": sink_meta,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "rows_dropped": rows_in - rows_out,
        "duration_seconds": round(duration, 4),
    }


def run_pipeline_from_config(config_path: str) -> dict:
    """
    Load a JSON pipeline config file and run the pipeline.

    Relative file paths in 'source' and 'sink' are resolved relative to the
    config file's directory.

    Args:
        config_path: Path to the JSON pipeline config file.

    Returns:
        Result dict from run_pipeline().

    Raises:
        FileNotFoundError: Config file or source file not found.
        ValueError: Invalid config or pipeline definition.
    """
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Pipeline config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        pipeline_def = json.load(f)

    config_dir = Path(config_path).parent
    for section in ("source", "sink"):
        if section in pipeline_def and "path" in pipeline_def[section]:
            p = pipeline_def[section]["path"]
            if not Path(p).is_absolute():
                pipeline_def[section]["path"] = str(config_dir / p)

    return run_pipeline(pipeline_def)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Geospatial ETL — run a declarative vector data pipeline"
    )
    parser.add_argument(
        "config",
        help="JSON pipeline config file",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the pipeline config without executing it",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        if not Path(args.config).exists():
            logger.error("Config file not found: %s", args.config)
            return 1

        with open(args.config, encoding="utf-8") as f:
            pipeline_def = json.load(f)

        errors = validate_pipeline(pipeline_def)
        if errors:
            logger.error("Pipeline config has %d error(s):", len(errors))
            for e in errors:
                logger.error("  - %s", e)
            return 1

        if args.validate_only:
            print(f"Pipeline '{pipeline_def.get('name', 'unnamed')}': config is valid")
            return 0

        result = run_pipeline_from_config(args.config)

        print(f"\nPipeline '{result['pipeline_name']}' complete")
        print(f"  Source     : {result['source'].get('path') or result['source'].get('table')}")
        print(f"  Transforms : {', '.join(result['transforms_applied']) or '(none)'}")
        print(f"  Sink       : {result['sink'].get('path') or result['sink'].get('table')}")
        print(f"  Rows in    : {result['rows_in']}")
        print(f"  Rows out   : {result['rows_out']}")
        print(f"  Dropped    : {result['rows_dropped']}")
        print(f"  Duration   : {result['duration_seconds']}s")

        return 0

    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
