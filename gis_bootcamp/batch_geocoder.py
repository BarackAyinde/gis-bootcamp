"""
batch_geocoder.py — Batch geocoding CLI tool for data pipelines.

Reads a CSV, geocodes each row via Nominatim (OpenStreetMap), handles rate
limiting and failures gracefully, and writes a geospatial point dataset with
geocoding status columns.

Nominatim terms require:
  - A unique User-Agent string identifying your application
  - Max 1 request/second (enforced by RateLimiter)
  - Non-commercial use only (use a commercial provider for production at scale)
"""

import argparse
import csv
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

logger = logging.getLogger(__name__)


def _build_geocoder(user_agent: str, min_delay: float):
    """Build a Nominatim geocoder with a RateLimiter wrapper."""
    from geopy.extra.rate_limiter import RateLimiter
    from geopy.geocoders import Nominatim

    geolocator = Nominatim(user_agent=user_agent)
    return RateLimiter(geolocator.geocode, min_delay_seconds=min_delay)


def _geocode_row(
    geocode_fn: Any,
    address: str,
    max_retries: int,
) -> tuple[Optional[float], Optional[float], Optional[str], str]:
    """
    Geocode a single address with retry logic.

    Returns:
        (latitude, longitude, matched_address, status)
        status is one of: "success", "not_found", "error"
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            location = geocode_fn(address, timeout=10)
            if location is None:
                logger.debug("Not found: %s", address)
                return None, None, None, "not_found"
            logger.debug("Success [attempt %d]: %s", attempt, address)
            return location.latitude, location.longitude, location.address, "success"
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Geocoding error [attempt %d/%d] for '%s': %s",
                attempt,
                max_retries,
                address,
                exc,
            )
            if attempt < max_retries:
                time.sleep(attempt)  # back-off between retries

    logger.error("Failed after %d attempts: '%s' — %s", max_retries, address, last_error)
    return None, None, None, "error"


def batch_geocode(
    input_path: str,
    output_path: str,
    address_column: str = "address",
    user_agent: str = "gis-bootcamp-geocoder",
    min_delay: float = 1.0,
    max_retries: int = 3,
    output_format: str = "gpkg",
    _geocoder=None,  # injectable for testing (bypasses real HTTP)
) -> dict:
    """
    Geocode all rows in a CSV and write a geospatial point dataset.

    Args:
        input_path: Path to input CSV file.
        output_path: Output path (.gpkg or .parquet).
        address_column: CSV column containing the address string.
        user_agent: User-Agent string for Nominatim (required by OSM TOS).
        min_delay: Minimum seconds between geocoding requests (default 1.0).
        max_retries: Max retry attempts per row on transient errors (default 3).
        output_format: "gpkg" (GeoPackage) or "parquet" (GeoParquet).
        _geocoder: Optional geocode callable for testing. Bypasses real HTTP.

    Returns:
        dict with: output_path, total, success, not_found, error, skipped.

    Raises:
        FileNotFoundError: Input CSV not found.
        ValueError: address_column not in CSV, or empty CSV.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    logger.info("Loading CSV: %s", input_path)
    df = pd.read_csv(input_path)

    if len(df) == 0:
        raise ValueError(f"Input CSV is empty: {input_path}")

    if address_column not in df.columns:
        raise ValueError(
            f"Column '{address_column}' not found in CSV. "
            f"Available columns: {list(df.columns)}"
        )

    logger.info("Rows to geocode: %d", len(df))
    logger.info("Address column: '%s'", address_column)

    geocode_fn = _geocoder if _geocoder is not None else _build_geocoder(user_agent, min_delay)

    lats, lons, matched, statuses = [], [], [], []
    counts = {"success": 0, "not_found": 0, "error": 0, "skipped": 0}

    for idx, row in df.iterrows():
        raw = row[address_column]

        if pd.isna(raw) or str(raw).strip() == "":
            logger.warning("Row %d: empty address — skipped", idx)
            lats.append(None)
            lons.append(None)
            matched.append(None)
            statuses.append("skipped")
            counts["skipped"] += 1
            continue

        address = str(raw).strip()
        lat, lon, addr, status = _geocode_row(geocode_fn, address, max_retries)

        lats.append(lat)
        lons.append(lon)
        matched.append(addr)
        statuses.append(status)
        counts[status] += 1

        if (idx + 1) % 10 == 0 or (idx + 1) == len(df):
            logger.info(
                "Progress: %d/%d — success=%d, not_found=%d, error=%d, skipped=%d",
                idx + 1, len(df),
                counts["success"], counts["not_found"],
                counts["error"], counts["skipped"],
            )

    # Build GeoDataFrame — only geocoded rows get a Point geometry
    df["latitude"] = lats
    df["longitude"] = lons
    df["geocode_matched_address"] = matched
    df["geocode_status"] = statuses

    geometries = [
        Point(lon, lat) if lat is not None and lon is not None else None
        for lat, lon in zip(lats, lons)
    ]
    gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "parquet":
        gdf.to_parquet(output_path, engine="pyarrow", index=False)
    else:
        gdf.to_file(output_path, driver="GPKG")

    total = len(df)
    logger.info(
        "Complete: %d total — %d success, %d not_found, %d error, %d skipped",
        total, counts["success"], counts["not_found"],
        counts["error"], counts["skipped"],
    )
    logger.info("Output written: %s", output_path)

    return {
        "output_path": output_path,
        "total": total,
        "success": counts["success"],
        "not_found": counts["not_found"],
        "error": counts["error"],
        "skipped": counts["skipped"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch geocode a CSV of addresses to a geospatial point dataset"
    )
    parser.add_argument("input", help="Input CSV file path")
    parser.add_argument("-o", "--output", required=True, help="Output file path")
    parser.add_argument(
        "-col", "--address-column", default="address",
        help="CSV column containing the address string (default: 'address')"
    )
    parser.add_argument(
        "-ua", "--user-agent", default="gis-bootcamp-geocoder",
        help="User-Agent string for Nominatim (required by OSM TOS)"
    )
    parser.add_argument(
        "-d", "--delay", type=float, default=1.0,
        help="Min seconds between geocoding requests (default 1.0)"
    )
    parser.add_argument(
        "-r", "--retries", type=int, default=3,
        help="Max retry attempts per row (default 3)"
    )
    parser.add_argument(
        "-f", "--format", choices=["gpkg", "parquet"], default="gpkg",
        dest="output_format", help="Output format (default: gpkg)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = batch_geocode(
            input_path=args.input,
            output_path=args.output,
            address_column=args.address_column,
            user_agent=args.user_agent,
            min_delay=args.delay,
            max_retries=args.retries,
            output_format=args.output_format,
        )
        print(f"\nGeocoding complete")
        print(f"  Total rows  : {result['total']}")
        print(f"  Success     : {result['success']}")
        print(f"  Not found   : {result['not_found']}")
        print(f"  Error       : {result['error']}")
        print(f"  Skipped     : {result['skipped']}")
        print(f"  Output      : {result['output_path']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
