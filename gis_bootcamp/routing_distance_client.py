"""
routing_distance_client.py — Routing distance client for OSRM.

Reads a CSV of origin/destination coordinate pairs, queries the OSRM Route API
for each pair, and writes a structured output with distance and duration.

OSRM Route API:
  GET {endpoint}/route/v1/driving/{lon},{lat};{lon},{lat}?overview=false

Default public endpoint: http://router.project-osrm.org
  (rate-limited; use a self-hosted instance for bulk workloads)

Output columns added to each input row:
  distance_m    — route distance in metres
  distance_km   — route distance in kilometres (3 d.p.)
  duration_s    — route duration in seconds
  duration_min  — route duration in minutes (2 d.p.)
  routing_status — "success" | "no_route" | "error" | "skipped"
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "http://router.project-osrm.org"


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "gis-bootcamp-routing-client/1.0"
    return session


def _query_route(
    session: Any,
    endpoint: str,
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
    timeout: int,
) -> tuple[Optional[float], Optional[float], str]:
    """
    Query OSRM for a single origin→destination route.

    Returns:
        (distance_m, duration_s, status)
        status: "success" | "no_route" | "error"
    """
    url = (
        f"{endpoint.rstrip('/')}/route/v1/driving/"
        f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        f"?overview=false"
    )
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            logger.debug("No route found: %s → %s", (origin_lat, origin_lon), (dest_lat, dest_lon))
            return None, None, "no_route"

        route = data["routes"][0]
        return float(route["distance"]), float(route["duration"]), "success"

    except requests.exceptions.Timeout:
        logger.warning("Timeout querying route: %s → %s", (origin_lat, origin_lon), (dest_lat, dest_lon))
        return None, None, "error"
    except requests.exceptions.RequestException as exc:
        logger.warning("Request error: %s", exc)
        return None, None, "error"
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Unexpected response format: %s", exc)
        return None, None, "error"


def route_distances(
    input_path: str,
    output_path: str,
    endpoint: str = _DEFAULT_ENDPOINT,
    origin_lat_col: str = "origin_lat",
    origin_lon_col: str = "origin_lon",
    dest_lat_col: str = "dest_lat",
    dest_lon_col: str = "dest_lon",
    timeout: int = 10,
    request_delay: float = 0.0,
    output_format: str = "csv",
    _session: Any = None,
) -> dict:
    """
    Compute route distances for all origin/destination pairs in a CSV.

    Args:
        input_path: CSV with origin and destination coordinate columns.
        output_path: Output path (.csv or .json).
        endpoint: OSRM-compatible routing API base URL.
        origin_lat_col: Column name for origin latitude.
        origin_lon_col: Column name for origin longitude.
        dest_lat_col: Column name for destination latitude.
        dest_lon_col: Column name for destination longitude.
        timeout: HTTP request timeout in seconds.
        request_delay: Seconds to wait between requests (for rate limiting).
        output_format: "csv" or "json".
        _session: Injectable requests.Session for testing.

    Returns:
        dict with: output_path, total, success, no_route, error, skipped.

    Raises:
        FileNotFoundError: Input CSV not found.
        ValueError: CSV is empty or required coordinate columns are missing.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    df = pd.read_csv(input_path)

    if len(df) == 0:
        raise ValueError(f"Input CSV is empty: {input_path}")

    required_cols = [origin_lat_col, origin_lon_col, dest_lat_col, dest_lon_col]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required column(s): {missing}. "
            f"Available: {list(df.columns)}"
        )

    logger.info("Routing %d pairs via %s", len(df), endpoint)

    session = _session if _session is not None else _build_session()
    counts = {"success": 0, "no_route": 0, "error": 0, "skipped": 0}

    distances_m, distances_km = [], []
    durations_s, durations_min = [], []
    statuses = []

    for idx, row in df.iterrows():
        coords = [row[c] for c in required_cols]

        if any(pd.isna(c) for c in coords):
            logger.warning("Row %d: missing coordinate(s) — skipped", idx)
            distances_m.append(None)
            distances_km.append(None)
            durations_s.append(None)
            durations_min.append(None)
            statuses.append("skipped")
            counts["skipped"] += 1
            continue

        dist_m, dur_s, status = _query_route(
            session=session,
            endpoint=endpoint,
            origin_lon=float(row[origin_lon_col]),
            origin_lat=float(row[origin_lat_col]),
            dest_lon=float(row[dest_lon_col]),
            dest_lat=float(row[dest_lat_col]),
            timeout=timeout,
        )

        distances_m.append(dist_m)
        distances_km.append(round(dist_m / 1000, 3) if dist_m is not None else None)
        durations_s.append(dur_s)
        durations_min.append(round(dur_s / 60, 2) if dur_s is not None else None)
        statuses.append(status)
        counts[status] += 1

        if (idx + 1) % 10 == 0 or (idx + 1) == len(df):
            logger.info(
                "Progress: %d/%d — success=%d, no_route=%d, error=%d, skipped=%d",
                idx + 1, len(df),
                counts["success"], counts["no_route"],
                counts["error"], counts["skipped"],
            )

        if request_delay > 0:
            time.sleep(request_delay)

    df["distance_m"] = distances_m
    df["distance_km"] = distances_km
    df["duration_s"] = durations_s
    df["duration_min"] = durations_min
    df["routing_status"] = statuses

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        df.to_json(output_path, orient="records", indent=2)
    else:
        df.to_csv(output_path, index=False)

    total = len(df)
    logger.info(
        "Complete: %d total — %d success, %d no_route, %d error, %d skipped",
        total, counts["success"], counts["no_route"],
        counts["error"], counts["skipped"],
    )
    logger.info("Output written: %s", output_path)

    return {
        "output_path": output_path,
        "total": total,
        "success": counts["success"],
        "no_route": counts["no_route"],
        "error": counts["error"],
        "skipped": counts["skipped"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute route distances for origin/destination pairs via OSRM"
    )
    parser.add_argument("input", help="Input CSV with origin/destination coordinates")
    parser.add_argument("-o", "--output", required=True, help="Output file path")
    parser.add_argument(
        "-e", "--endpoint", default=_DEFAULT_ENDPOINT,
        help=f"OSRM API base URL (default: {_DEFAULT_ENDPOINT})",
    )
    parser.add_argument("--origin-lat", default="origin_lat", dest="origin_lat_col")
    parser.add_argument("--origin-lon", default="origin_lon", dest="origin_lon_col")
    parser.add_argument("--dest-lat", default="dest_lat", dest="dest_lat_col")
    parser.add_argument("--dest-lon", default="dest_lon", dest="dest_lon_col")
    parser.add_argument("-t", "--timeout", type=int, default=10, help="Request timeout (s)")
    parser.add_argument("-d", "--delay", type=float, default=0.0, help="Delay between requests (s)")
    parser.add_argument(
        "-f", "--format", choices=["csv", "json"], default="csv",
        dest="output_format", help="Output format (default: csv)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = route_distances(
            input_path=args.input,
            output_path=args.output,
            endpoint=args.endpoint,
            origin_lat_col=args.origin_lat_col,
            origin_lon_col=args.origin_lon_col,
            dest_lat_col=args.dest_lat_col,
            dest_lon_col=args.dest_lon_col,
            timeout=args.timeout,
            request_delay=args.delay,
            output_format=args.output_format,
        )
        print(f"\nRouting complete")
        print(f"  Total   : {result['total']}")
        print(f"  Success : {result['success']}")
        print(f"  No route: {result['no_route']}")
        print(f"  Error   : {result['error']}")
        print(f"  Skipped : {result['skipped']}")
        print(f"  Output  : {result['output_path']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
