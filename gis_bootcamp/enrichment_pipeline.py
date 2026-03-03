"""
enrichment_pipeline.py — Spatial Data Enrichment Pipeline.

Composes Week 3 tools into a single configurable pipeline:

  Stage 1 (geocode)        — batch_geocoder: CSV addresses → point dataset
  Stage 2 (nearest_feature) — nearest_feature_lookup: enrich points with
                              attributes from a reference spatial dataset
  Stage 3 (density)        — density_analysis: KDE raster or fishnet count grid
  Stage 4 (render)         — map_renderer: static PNG map of the enriched points

All stages are optional; at least one must be configured.
Stages run in order and share an output directory for all artefacts.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd

from gis_bootcamp.batch_geocoder import batch_geocode
from gis_bootcamp.density_analysis import analyze_density
from gis_bootcamp.map_renderer import render_map
from gis_bootcamp.nearest_feature_lookup import nearest_feature_lookup

logger = logging.getLogger(__name__)


def run_enrichment_pipeline(
    input_path: str,
    output_dir: str,
    # Stage 1
    geocode_column: Optional[str] = None,
    # Stage 2
    reference_path: Optional[str] = None,
    lookup_mode: str = "nearest",
    # Stage 3
    density_cell_size: Optional[float] = None,
    density_output_type: str = "raster",
    density_bandwidth: Optional[float] = None,
    # Stage 4
    render: bool = False,
    map_title: str = "",
    # Testability
    _geocoder=None,
) -> dict:
    """
    Run a spatial data enrichment pipeline over a point dataset.

    Stages executed depend on which parameters are provided:
      - geocode_column set  → Stage 1: geocode addresses in the CSV
      - reference_path set  → Stage 2: nearest-feature attribute lookup
      - density_cell_size set → Stage 3: density analysis
      - render=True         → Stage 4: render a static map

    At least one stage must be configured.

    Args:
        input_path: Path to input file. CSV for Stage 1; vector file
                    (GPKG/SHP/GeoJSON) for Stages 2–4 without geocoding.
        output_dir: Directory for all pipeline outputs.
        geocode_column: CSV column containing addresses to geocode (Stage 1).
        reference_path: Reference spatial dataset for attribute lookup (Stage 2).
        lookup_mode: Spatial join mode — "nearest", "within", "contains".
        density_cell_size: Grid cell size in CRS units (Stage 3).
        density_output_type: "raster" (KDE GeoTIFF) or "vector" (count grid).
        density_bandwidth: KDE bandwidth (raster mode only; None = Scott's rule).
        render: If True, render a static PNG map (Stage 4).
        map_title: Title for the rendered map.
        _geocoder: Injectable geocode callable for testing (bypasses Nominatim).

    Returns:
        dict with:
          output_dir, stages_run, enriched_path, point_count,
          geocode_stats, lookup_stats, density_stats, map_path.

    Raises:
        ValueError: No stages configured, invalid options, or zero points
                    remain after geocoding.
        FileNotFoundError: input_path or reference_path does not exist.
    """
    stages_configured = bool(
        geocode_column or reference_path or density_cell_size is not None or render
    )
    if not stages_configured:
        raise ValueError(
            "No pipeline stages configured. Provide at least one of: "
            "geocode_column, reference_path, density_cell_size, render=True."
        )

    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if reference_path and not Path(reference_path).exists():
        raise FileNotFoundError(f"Reference file not found: {reference_path}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    stages_run: list[str] = []
    result: dict = {
        "output_dir": output_dir,
        "stages_run": stages_run,
        "enriched_path": None,
        "point_count": None,
        "geocode_stats": None,
        "lookup_stats": None,
        "density_stats": None,
        "map_path": None,
    }

    working_path = input_path

    # ------------------------------------------------------------------
    # Stage 1: Geocode
    # ------------------------------------------------------------------
    if geocode_column:
        logger.info("Stage 1: Geocoding '%s' column from %s", geocode_column, input_path)
        geocoded_path = str(out / "geocoded.gpkg")
        geo_stats = batch_geocode(
            input_path=input_path,
            output_path=geocoded_path,
            address_column=geocode_column,
            _geocoder=_geocoder,
        )
        result["geocode_stats"] = geo_stats

        # Keep only rows with a valid geocoded point
        gdf = gpd.read_file(geocoded_path)
        gdf = gdf[gdf["geocode_status"] == "success"].copy()

        if len(gdf) == 0:
            raise ValueError("No rows were successfully geocoded — pipeline cannot continue.")

        points_path = str(out / "points.gpkg")
        gdf.to_file(points_path, driver="GPKG")
        working_path = points_path

        stages_run.append("geocode")
        logger.info("Stage 1 complete: %d/%d rows geocoded", len(gdf), geo_stats["total"])

    # ------------------------------------------------------------------
    # Stage 2: Nearest-feature lookup
    # ------------------------------------------------------------------
    if reference_path:
        logger.info("Stage 2: Nearest-feature lookup (%s mode)", lookup_mode)
        enriched_path = str(out / "enriched.gpkg")
        lookup_stats = nearest_feature_lookup(
            points_path=working_path,
            reference_path=reference_path,
            output_path=enriched_path,
            mode=lookup_mode,
        )
        working_path = enriched_path
        result["lookup_stats"] = lookup_stats
        stages_run.append("nearest_feature")
        logger.info(
            "Stage 2 complete: %d/%d points matched",
            lookup_stats["matched"], lookup_stats["total_points"],
        )

    # ------------------------------------------------------------------
    # Stage 3: Density analysis
    # ------------------------------------------------------------------
    if density_cell_size is not None:
        logger.info(
            "Stage 3: Density analysis (%s, cell_size=%s)", density_output_type, density_cell_size
        )
        density_ext = ".tif" if density_output_type == "raster" else ".gpkg"
        density_path = str(out / f"density{density_ext}")
        density_stats = analyze_density(
            input_path=working_path,
            output_path=density_path,
            cell_size=density_cell_size,
            bandwidth=density_bandwidth,
            output_type=density_output_type,
        )
        result["density_stats"] = density_stats
        stages_run.append("density")
        logger.info(
            "Stage 3 complete: %d hotspot cells out of %d",
            density_stats["hotspot_cells"], density_stats["total_cells"],
        )

    # ------------------------------------------------------------------
    # Stage 4: Render map
    # ------------------------------------------------------------------
    if render:
        logger.info("Stage 4: Rendering map")
        map_path = str(out / "map.png")
        layers = []
        if reference_path:
            layers.append({
                "path": reference_path,
                "label": "Reference",
                "color": "#4e79a7",
                "alpha": 0.35,
                "zorder": 1,
            })
        layers.append({
            "path": working_path,
            "label": "Points",
            "color": "#e15759",
            "markersize": 6.0,
            "zorder": 2,
        })
        render_map(layers, map_path, title=map_title)
        result["map_path"] = map_path
        stages_run.append("render")
        logger.info("Stage 4 complete: %s", map_path)

    # ------------------------------------------------------------------
    # Finalise result
    # ------------------------------------------------------------------
    result["enriched_path"] = working_path
    result["point_count"] = len(gpd.read_file(working_path))

    logger.info(
        "Pipeline complete — stages: %s, points: %d, output_dir: %s",
        stages_run, result["point_count"], output_dir,
    )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Spatial Data Enrichment Pipeline"
    )
    parser.add_argument("input", help="Input file path (CSV for geocoding; GPKG/SHP/GeoJSON otherwise)")
    parser.add_argument("-o", "--output-dir", required=True, help="Output directory for all artefacts")
    parser.add_argument(
        "--geocode-col", default=None,
        help="CSV column with addresses to geocode (Stage 1)",
    )
    parser.add_argument(
        "--reference", default=None,
        help="Reference spatial dataset for attribute lookup (Stage 2)",
    )
    parser.add_argument(
        "--lookup-mode", choices=["nearest", "within", "contains"], default="nearest",
        help="Spatial join mode for Stage 2 (default: nearest)",
    )
    parser.add_argument(
        "--density-cell-size", type=float, default=None,
        help="Cell size for density analysis in CRS units (Stage 3)",
    )
    parser.add_argument(
        "--density-type", choices=["raster", "vector"], default="raster",
        help="Density output type: raster (KDE) or vector (count grid) (default: raster)",
    )
    parser.add_argument(
        "--density-bandwidth", type=float, default=None,
        help="KDE bandwidth in CRS units (Stage 3 raster mode; default: Scott's rule)",
    )
    parser.add_argument("--render", action="store_true", help="Render a static PNG map (Stage 4)")
    parser.add_argument("--map-title", default="", help="Title for the rendered map")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = run_enrichment_pipeline(
            input_path=args.input,
            output_dir=args.output_dir,
            geocode_column=args.geocode_col,
            reference_path=args.reference,
            lookup_mode=args.lookup_mode,
            density_cell_size=args.density_cell_size,
            density_output_type=args.density_type,
            density_bandwidth=args.density_bandwidth,
            render=args.render,
            map_title=args.map_title,
        )
        print(f"\nEnrichment pipeline complete")
        print(f"  Stages run    : {', '.join(result['stages_run'])}")
        print(f"  Points        : {result['point_count']}")
        print(f"  Enriched file : {result['enriched_path']}")
        if result["map_path"]:
            print(f"  Map           : {result['map_path']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
