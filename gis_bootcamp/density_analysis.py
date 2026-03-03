"""
density_analysis.py — Hotspot / density analysis CLI tool.

Two output modes:

  raster  — Kernel Density Estimation (KDE) surface written as GeoTIFF.
            Uses scipy.stats.gaussian_kde with configurable bandwidth.
            Grid cell values represent density (probability mass per unit area).

  vector  — Regular grid (fishnet) of square cells, each annotated with
            the count of input points it contains. Written as GeoPackage.

Parameters:
  cell_size   — grid resolution in CRS units (metres for projected, degrees otherwise)
  bandwidth   — KDE bandwidth in CRS units (raster mode only).
                None = Scott's rule (automatic from point distribution).
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

logger = logging.getLogger(__name__)

_VALID_TYPES = ("raster", "vector")


def _kde_raster(
    xs: np.ndarray,
    ys: np.ndarray,
    cell_size: float,
    bandwidth: Optional[float],
    crs,
    output_path: str,
) -> tuple[int, int, float, int]:
    """
    Compute a KDE raster over the point cloud and write it as a GeoTIFF.

    Returns:
        (grid_width, grid_height, actual_bandwidth, hotspot_cells)
    """
    from scipy.stats import gaussian_kde

    pad = cell_size * 2
    xmin, xmax = xs.min() - pad, xs.max() + pad
    ymin, ymax = ys.min() - pad, ys.max() + pad

    # Grid coordinates: x left→right, y top→bottom (rasterio convention)
    xi = np.arange(xmin, xmax, cell_size)
    yi = np.arange(ymax, ymin, -cell_size)   # decreasing = north-to-south
    grid_width, grid_height = len(xi), len(yi)

    xx, yy = np.meshgrid(xi, yi)
    positions = np.vstack([xx.ravel(), yy.ravel()])

    # Fit KDE; bandwidth=None uses Scott's rule
    bw_method = bandwidth / np.std(xs) if bandwidth is not None else "scott"
    kernel = gaussian_kde(np.vstack([xs, ys]), bw_method=bw_method)
    actual_bw = float(kernel.factor * np.std(xs))

    logger.info("KDE bandwidth: %.6f (CRS units)", actual_bw)

    density = kernel(positions).reshape(grid_height, grid_width).astype("float32")
    hotspot_cells = int((density > 0).sum())

    transform = from_origin(west=xmin, north=ymax, xsize=cell_size, ysize=cell_size)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=grid_height,
        width=grid_width,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=0.0,
    ) as dst:
        dst.write(density, 1)

    logger.info(
        "KDE raster: %d x %d px, max_density=%.6e, hotspot_cells=%d",
        grid_width, grid_height, float(density.max()), hotspot_cells,
    )

    return grid_width, grid_height, actual_bw, hotspot_cells


def _count_vector(
    points_gdf: gpd.GeoDataFrame,
    cell_size: float,
    output_path: str,
) -> tuple[int, int, int, int]:
    """
    Build a fishnet grid and count points per cell. Write as GeoPackage.

    Returns:
        (grid_width, grid_height, total_cells, hotspot_cells)
    """
    xmin, ymin, xmax, ymax = points_gdf.total_bounds
    pad = cell_size

    xs = np.arange(xmin - pad, xmax + pad, cell_size)
    ys = np.arange(ymin - pad, ymax + pad, cell_size)
    grid_width, grid_height = len(xs), len(ys)

    cells = [
        box(x, y, x + cell_size, y + cell_size)
        for x in xs
        for y in ys
    ]
    grid = gpd.GeoDataFrame({"cell_id": range(len(cells))}, geometry=cells, crs=points_gdf.crs)

    # Count points per cell via numpy floor-division (avoids sjoin boundary issues)
    pt_xs = np.array([geom.x for geom in points_gdf.geometry])
    pt_ys = np.array([geom.y for geom in points_gdf.geometry])

    x_origin = xs[0]
    y_origin = ys[0]
    col_idx = np.clip(np.floor((pt_xs - x_origin) / cell_size).astype(int), 0, len(xs) - 1)
    row_idx = np.clip(np.floor((pt_ys - y_origin) / cell_size).astype(int), 0, len(ys) - 1)
    cell_ids = col_idx * len(ys) + row_idx

    from collections import Counter
    count_map = Counter(cell_ids.tolist())

    grid = grid.copy()
    grid["point_count"] = grid["cell_id"].map(count_map).fillna(0).astype(int)

    total_cells = len(grid)
    hotspot_cells = int((grid["point_count"] > 0).sum())

    logger.info(
        "Vector grid: %d x %d (%d cells), %d non-empty",
        grid_width, grid_height, total_cells, hotspot_cells,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    grid.to_file(output_path, driver="GPKG")

    return grid_width, grid_height, total_cells, hotspot_cells


def analyze_density(
    input_path: str,
    output_path: str,
    cell_size: float,
    bandwidth: Optional[float] = None,
    output_type: str = "raster",
) -> dict:
    """
    Perform kernel density estimation or grid count density analysis on a point dataset.

    Args:
        input_path: Path to input point dataset (GPKG, Shapefile, GeoJSON).
        output_path: Output path (.tif for raster, .gpkg for vector).
        cell_size: Grid cell size in CRS units.
        bandwidth: KDE bandwidth in CRS units (raster mode only).
                   None uses Scott's rule.
        output_type: "raster" (KDE GeoTIFF) or "vector" (count grid GeoPackage).

    Returns:
        dict with: output_path, output_type, point_count, crs, cell_size,
                   bandwidth, grid_width, grid_height, total_cells, hotspot_cells.

    Raises:
        FileNotFoundError: Input file not found.
        ValueError: Empty dataset, missing CRS, invalid output_type,
                    or cell_size <= 0.
    """
    if output_type not in _VALID_TYPES:
        raise ValueError(
            f"Invalid output_type '{output_type}'. Choose: {', '.join(_VALID_TYPES)}"
        )

    if cell_size <= 0:
        raise ValueError(f"cell_size must be > 0, got {cell_size}")

    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info("Loading points: %s", input_path)
    gdf = gpd.read_file(input_path)

    if len(gdf) == 0:
        raise ValueError(f"Point dataset is empty: {input_path}")

    if gdf.crs is None:
        raise ValueError(f"Point dataset has no CRS: {input_path}")

    # Drop rows with null geometry
    n_before = len(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if len(gdf) < n_before:
        logger.warning("Dropped %d null/empty geometries", n_before - len(gdf))

    if len(gdf) == 0:
        raise ValueError("No valid geometries remain after filtering nulls")

    crs_str = gdf.crs.to_string()
    logger.info(
        "Points: %d, CRS=%s, cell_size=%s, output_type=%s",
        len(gdf), crs_str, cell_size, output_type,
    )

    xs = np.array([geom.x for geom in gdf.geometry])
    ys = np.array([geom.y for geom in gdf.geometry])

    if output_type == "raster":
        grid_width, grid_height, actual_bw, hotspot_cells = _kde_raster(
            xs, ys, cell_size, bandwidth, gdf.crs, output_path
        )
        total_cells = grid_width * grid_height
    else:
        grid_width, grid_height, total_cells, hotspot_cells = _count_vector(
            gdf, cell_size, output_path
        )
        actual_bw = None

    logger.info("Output written: %s", output_path)

    return {
        "output_path": output_path,
        "output_type": output_type,
        "point_count": len(gdf),
        "crs": crs_str,
        "cell_size": cell_size,
        "bandwidth": actual_bw,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "total_cells": total_cells,
        "hotspot_cells": hotspot_cells,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute KDE raster or grid count density from a point dataset"
    )
    parser.add_argument("input", help="Input point dataset path")
    parser.add_argument("-o", "--output", required=True, help="Output path")
    parser.add_argument(
        "-c", "--cell-size", type=float, required=True,
        help="Grid cell size in CRS units",
    )
    parser.add_argument(
        "-bw", "--bandwidth", type=float, default=None,
        help="KDE bandwidth in CRS units (raster mode; default: Scott's rule)",
    )
    parser.add_argument(
        "-t", "--type", choices=list(_VALID_TYPES), default="raster",
        dest="output_type", help="Output type: raster (KDE) or vector (count grid)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = analyze_density(
            input_path=args.input,
            output_path=args.output,
            cell_size=args.cell_size,
            bandwidth=args.bandwidth,
            output_type=args.output_type,
        )
        print(f"\nDensity analysis complete")
        print(f"  Type          : {result['output_type']}")
        print(f"  Points        : {result['point_count']}")
        print(f"  Cell size     : {result['cell_size']}")
        print(f"  Grid          : {result['grid_width']} x {result['grid_height']}")
        print(f"  Hotspot cells : {result['hotspot_cells']} / {result['total_cells']}")
        if result["bandwidth"] is not None:
            print(f"  Bandwidth     : {result['bandwidth']:.6f}")
        print(f"  Output        : {result['output_path']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
