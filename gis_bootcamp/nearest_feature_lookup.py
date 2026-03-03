"""
nearest_feature_lookup.py — Reverse geocoder / nearest-feature lookup CLI.

Loads a point dataset and a reference dataset, then enriches each point with
attributes from the spatially matching or nearest reference feature.

Modes:
  nearest  — assigns the closest reference feature to every point (always matches)
  within   — assigns the containing reference polygon (left join; may be unmatched)
  contains — assigns the reference feature that the point contains (left join)

Uses GeoPandas STRtree spatial indexing internally for all three modes.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Literal

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)

_VALID_MODES = ("nearest", "within", "contains")


def nearest_feature_lookup(
    points_path: str,
    reference_path: str,
    output_path: str,
    mode: str = "nearest",
) -> dict:
    """
    Enrich a point dataset with attributes from a reference spatial dataset.

    Args:
        points_path: Path to the point dataset (GPKG, Shapefile, GeoJSON).
        reference_path: Path to the reference dataset.
        output_path: Output path for the enriched dataset (GPKG).
        mode: Join mode — "nearest", "within", or "contains".

    Returns:
        dict with: output_path, total_points, matched, unmatched, match_rate.

    Raises:
        FileNotFoundError: Either input file not found.
        ValueError: Invalid mode, empty points dataset, or missing CRS.
    """
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}'. Valid modes: {', '.join(_VALID_MODES)}"
        )

    for path, label in [(points_path, "points"), (reference_path, "reference")]:
        if not Path(path).exists():
            raise FileNotFoundError(f"{label.capitalize()} file not found: {path}")

    logger.info("Loading points: %s", points_path)
    points = gpd.read_file(points_path)

    logger.info("Loading reference: %s", reference_path)
    reference = gpd.read_file(reference_path)

    if len(points) == 0:
        raise ValueError(f"Points dataset is empty: {points_path}")

    if points.crs is None:
        raise ValueError(f"Points dataset has no CRS: {points_path}")

    if reference.crs is None:
        raise ValueError(f"Reference dataset has no CRS: {reference_path}")

    logger.info("Points   : %d features, CRS=%s", len(points), points.crs.to_string())
    logger.info("Reference: %d features, CRS=%s", len(reference), reference.crs.to_string())

    # CRS alignment: reproject reference to match points
    if points.crs != reference.crs:
        logger.info(
            "CRS mismatch — reprojecting reference from %s to %s",
            reference.crs.to_string(),
            points.crs.to_string(),
        )
        reference = reference.to_crs(points.crs)

    # Reset indexes for predictable join behaviour
    points = points.reset_index(drop=True)
    reference = reference.reset_index(drop=True)

    logger.info("Running spatial join: mode='%s'", mode)

    if mode == "nearest":
        result = gpd.sjoin_nearest(
            points,
            reference,
            how="left",
            distance_col="match_distance",
        )
        # sjoin_nearest always produces a match
        result["match_status"] = "matched"
        result = result[~result.index.duplicated(keep="first")]
        matched = len(result)
        unmatched = 0

    else:  # within or contains
        result = gpd.sjoin(points, reference, how="left", predicate=mode)
        # Deduplicate: if a point matches multiple reference features, keep first
        result = result[~result.index.duplicated(keep="first")]
        unmatched_mask = result["index_right"].isna()
        result["match_status"] = result.apply(
            lambda r: "matched" if pd.notna(r.get("index_right")) else "unmatched",
            axis=1,
        )
        matched = int((~unmatched_mask).sum())
        unmatched = int(unmatched_mask.sum())

    # Drop internal join bookkeeping columns
    result = result.drop(columns=["index_right"], errors="ignore")

    # Drop geometry_right if present (from right GDF)
    right_geom_col = f"{reference.geometry.name}_right"
    result = result.drop(columns=[right_geom_col], errors="ignore")

    total = len(result)
    match_rate = round(matched / total * 100, 2) if total > 0 else 0.0

    logger.info(
        "Results: %d total, %d matched (%.1f%%), %d unmatched",
        total, matched, match_rate, unmatched,
    )

    # Write output
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(output_path, driver="GPKG")
    logger.info("Output written: %s", output_path)

    return {
        "output_path": output_path,
        "total_points": total,
        "matched": matched,
        "unmatched": unmatched,
        "match_rate": match_rate,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich a point dataset with attributes from a reference spatial dataset"
    )
    parser.add_argument("points", help="Input point dataset path")
    parser.add_argument("reference", help="Reference dataset path")
    parser.add_argument("-o", "--output", required=True, help="Output dataset path")
    parser.add_argument(
        "-m", "--mode",
        choices=list(_VALID_MODES),
        default="nearest",
        help="Join mode: nearest (default), within, or contains",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = nearest_feature_lookup(
            points_path=args.points,
            reference_path=args.reference,
            output_path=args.output,
            mode=args.mode,
        )
        print(f"\nLookup complete")
        print(f"  Mode         : {args.mode}")
        print(f"  Total points : {result['total_points']}")
        print(f"  Matched      : {result['matched']} ({result['match_rate']}%)")
        print(f"  Unmatched    : {result['unmatched']}")
        print(f"  Output       : {result['output_path']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
