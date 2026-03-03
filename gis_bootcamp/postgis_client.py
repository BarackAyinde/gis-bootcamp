"""
postgis_client.py — PostGIS Integration Client.

Provides three core operations against a PostGIS spatial database:

  postgis_read(table_name, con, ...)   — read a table into a GeoDataFrame
                                         and optionally write to a local file
  postgis_write(input_path, table_name, con, ...) — write a local vector file
                                         to a PostGIS table
  postgis_query(sql, con, ...)         — execute arbitrary spatial SQL and
                                         optionally write the result to a file

Connections are provided by the caller (SQLAlchemy engine or psycopg2 connection).
Use make_engine(dsn) to build a SQLAlchemy engine from a DSN string.

Table/schema identifiers are validated to prevent injection via identifier names.
The WHERE clause and raw SQL in postgis_query are the caller's responsibility.

Example:
    engine = make_engine("postgresql://user:pass@localhost:5432/mydb")
    result = postgis_read("parcels", engine, output_path="parcels.gpkg")
    result = postgis_write("parcels.gpkg", "parcels_new", engine)
    result = postgis_query(
        "SELECT * FROM parcels WHERE ST_Area(geom) > 1000",
        engine, output_path="large_parcels.gpkg",
    )
"""

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd

logger = logging.getLogger(__name__)

_VALID_IF_EXISTS = ("replace", "append", "fail")

# Only allow plain SQL identifiers (letters, digits, underscore, dollar sign).
# Quoted identifiers with special chars must be handled by the caller.
_SAFE_ID = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_$]*$")


def _check_identifier(name: str, label: str) -> None:
    if not _SAFE_ID.match(name):
        raise ValueError(
            f"Unsafe {label} identifier '{name}'. "
            "Use only letters, digits, underscores, and dollar signs."
        )


def _write_gdf(gdf: gpd.GeoDataFrame, output_path: str) -> None:
    """Write a GeoDataFrame to a local file, format inferred from extension."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    ext = Path(output_path).suffix.lower()
    if ext == ".parquet":
        gdf.to_parquet(output_path, engine="pyarrow", index=False)
    elif ext in (".geojson", ".json"):
        gdf.to_file(output_path, driver="GeoJSON")
    elif ext == ".shp":
        gdf.to_file(output_path, driver="ESRI Shapefile")
    else:
        gdf.to_file(output_path, driver="GPKG")


def make_engine(dsn: str):
    """
    Build a SQLAlchemy engine from a DSN connection string.

    Args:
        dsn: PostgreSQL DSN, e.g.
             "postgresql://user:pass@localhost:5432/mydb"

    Returns:
        sqlalchemy.Engine

    Raises:
        ImportError: sqlalchemy not installed.
    """
    try:
        from sqlalchemy import create_engine
    except ImportError:
        raise ImportError(
            "sqlalchemy is required for PostGIS connections. "
            "Install it with: pip install sqlalchemy psycopg2-binary"
        )
    return create_engine(dsn)


def postgis_read(
    table_name: str,
    con,
    output_path: Optional[str] = None,
    schema: str = "public",
    where: Optional[str] = None,
    geom_col: str = "geom",
    crs: Optional[str] = None,
) -> dict:
    """
    Read a PostGIS table into a GeoDataFrame and optionally write it to a file.

    Args:
        table_name: Name of the PostGIS table.
        con: SQLAlchemy engine/connection or psycopg2 connection.
        output_path: Optional local output path (.gpkg, .parquet, .geojson, .shp).
        schema: Database schema (default: "public").
        where: Optional SQL WHERE clause (e.g. "population > 1000").
        geom_col: Name of the geometry column (default: "geom").
        crs: Override CRS for the output GeoDataFrame (e.g. "EPSG:4326").

    Returns:
        dict with: output_path, feature_count, crs, columns, geometry_types.

    Raises:
        ValueError: Table returns no rows.
    """
    _check_identifier(table_name, "table name")
    _check_identifier(schema, "schema name")

    sql = f'SELECT * FROM "{schema}"."{table_name}"'
    if where:
        sql += f" WHERE {where}"

    logger.info("Reading PostGIS table: %s.%s", schema, table_name)
    if where:
        logger.info("  WHERE: %s", where)

    gdf = gpd.read_postgis(sql, con, geom_col=geom_col, crs=crs)

    if len(gdf) == 0:
        raise ValueError(f"Table '{schema}.{table_name}' returned no rows")

    crs_str = gdf.crs.to_string() if gdf.crs else None
    geom_types = sorted(set(gdf.geom_type.dropna().tolist()))
    attr_cols = [c for c in gdf.columns if c != gdf.geometry.name]

    logger.info(
        "Read %d features, CRS=%s, geometry_types=%s",
        len(gdf), crs_str, geom_types,
    )

    if output_path:
        _write_gdf(gdf, output_path)
        logger.info("Written to: %s", output_path)

    return {
        "output_path": output_path,
        "feature_count": len(gdf),
        "crs": crs_str,
        "columns": attr_cols,
        "geometry_types": geom_types,
    }


def postgis_write(
    input_path: str,
    table_name: str,
    con,
    schema: str = "public",
    if_exists: str = "replace",
    chunksize: Optional[int] = None,
) -> dict:
    """
    Write a local vector file to a PostGIS table.

    Args:
        input_path: Path to the input vector file (GPKG, Shapefile, GeoJSON).
        table_name: Target PostGIS table name.
        con: SQLAlchemy engine/connection.
        schema: Target schema (default: "public").
        if_exists: "replace" (default), "append", or "fail".
        chunksize: Rows per batch insert (None = all at once).

    Returns:
        dict with: table_name, schema, feature_count, crs, if_exists.

    Raises:
        FileNotFoundError: input_path does not exist.
        ValueError: Empty dataset, missing CRS, or invalid if_exists.
    """
    _check_identifier(table_name, "table name")
    _check_identifier(schema, "schema name")

    if if_exists not in _VALID_IF_EXISTS:
        raise ValueError(
            f"if_exists must be one of {_VALID_IF_EXISTS}, got '{if_exists}'"
        )

    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info("Loading input: %s", input_path)
    gdf = gpd.read_file(input_path)

    if len(gdf) == 0:
        raise ValueError(f"Input dataset is empty: {input_path}")

    if gdf.crs is None:
        raise ValueError(f"Input dataset has no CRS: {input_path}")

    crs_str = gdf.crs.to_string()
    logger.info(
        "Writing %d features to %s.%s (if_exists=%s)",
        len(gdf), schema, table_name, if_exists,
    )

    gdf.to_postgis(
        name=table_name,
        con=con,
        schema=schema,
        if_exists=if_exists,
        chunksize=chunksize,
    )

    logger.info("Write complete: %s.%s", schema, table_name)

    return {
        "table_name": table_name,
        "schema": schema,
        "feature_count": len(gdf),
        "crs": crs_str,
        "if_exists": if_exists,
    }


def postgis_query(
    sql: str,
    con,
    params: Optional[tuple | dict] = None,
    output_path: Optional[str] = None,
    geom_col: str = "geom",
    crs: Optional[str] = None,
) -> dict:
    """
    Execute a spatial SQL query and optionally write the result to a local file.

    Args:
        sql: Spatial SQL query (caller is responsible for safety).
        con: SQLAlchemy engine/connection or psycopg2 connection.
        params: Query parameters (passed to geopandas.read_postgis).
        output_path: Optional local output path (.gpkg, .parquet, .geojson, .shp).
        geom_col: Name of the geometry column in the result (default: "geom").
        crs: Override CRS (e.g. "EPSG:4326").

    Returns:
        dict with: output_path, feature_count, crs, columns, geometry_types.

    Raises:
        ValueError: Empty SQL or query returns no rows.
    """
    if not sql or not sql.strip():
        raise ValueError("sql must be a non-empty string")

    logger.info("Executing spatial query (%d chars)", len(sql))

    gdf = gpd.read_postgis(sql, con, geom_col=geom_col, crs=crs, params=params)

    if len(gdf) == 0:
        raise ValueError("Spatial query returned no rows")

    crs_str = gdf.crs.to_string() if gdf.crs else None
    geom_types = sorted(set(gdf.geom_type.dropna().tolist()))
    attr_cols = [c for c in gdf.columns if c != gdf.geometry.name]

    logger.info(
        "Query returned %d features, CRS=%s, geometry_types=%s",
        len(gdf), crs_str, geom_types,
    )

    if output_path:
        _write_gdf(gdf, output_path)
        logger.info("Written to: %s", output_path)

    return {
        "output_path": output_path,
        "feature_count": len(gdf),
        "crs": crs_str,
        "columns": attr_cols,
        "geometry_types": geom_types,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PostGIS client — read, write, or query a PostGIS spatial table"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # read sub-command
    p_read = subparsers.add_parser("read", help="Read a PostGIS table to a local file")
    p_read.add_argument("table", help="Table name")
    p_read.add_argument("--dsn", required=True, help="PostgreSQL DSN")
    p_read.add_argument("-o", "--output", required=True, help="Output file path")
    p_read.add_argument("--schema", default="public")
    p_read.add_argument("--where", default=None, help="SQL WHERE clause")
    p_read.add_argument("--geom-col", default="geom")

    # write sub-command
    p_write = subparsers.add_parser("write", help="Write a local file to PostGIS")
    p_write.add_argument("input", help="Input vector file path")
    p_write.add_argument("table", help="Target table name")
    p_write.add_argument("--dsn", required=True, help="PostgreSQL DSN")
    p_write.add_argument("--schema", default="public")
    p_write.add_argument(
        "--if-exists", choices=list(_VALID_IF_EXISTS), default="replace"
    )
    p_write.add_argument("--chunksize", type=int, default=None)

    # query sub-command
    p_query = subparsers.add_parser("query", help="Execute spatial SQL and write result")
    p_query.add_argument("sql", help="Spatial SQL query")
    p_query.add_argument("--dsn", required=True, help="PostgreSQL DSN")
    p_query.add_argument("-o", "--output", required=True, help="Output file path")
    p_query.add_argument("--geom-col", default="geom")

    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        engine = make_engine(args.dsn)

        if args.command == "read":
            result = postgis_read(
                table_name=args.table,
                con=engine,
                output_path=args.output,
                schema=args.schema,
                where=args.where,
                geom_col=args.geom_col,
            )
            print(f"\nRead complete")
            print(f"  Features : {result['feature_count']}")
            print(f"  CRS      : {result['crs']}")
            print(f"  Output   : {result['output_path']}")

        elif args.command == "write":
            result = postgis_write(
                input_path=args.input,
                table_name=args.table,
                con=engine,
                schema=args.schema,
                if_exists=args.if_exists,
                chunksize=args.chunksize,
            )
            print(f"\nWrite complete")
            print(f"  Table    : {result['schema']}.{result['table_name']}")
            print(f"  Features : {result['feature_count']}")

        elif args.command == "query":
            result = postgis_query(
                sql=args.sql,
                con=engine,
                output_path=args.output,
                geom_col=args.geom_col,
            )
            print(f"\nQuery complete")
            print(f"  Features : {result['feature_count']}")
            print(f"  Output   : {result['output_path']}")

        return 0

    except (FileNotFoundError, ValueError, ImportError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
