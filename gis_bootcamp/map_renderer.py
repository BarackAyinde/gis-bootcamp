"""
map_renderer.py — Static Cartographic Map Renderer.

Renders one or more vector layers to a static image (PNG, SVG, PDF, JPG).
Each layer is independently styled (color, alpha, linewidth, markersize, label).
All layers are reprojected to a common CRS before rendering.
Output format is inferred from the file extension.

Layer dict keys:
  path        (required) — path to the vector file
  color       — face/line/marker color (default: auto-cycled)
  edge_color  — polygon/marker edge color (default: same as color)
  alpha       — opacity 0–1 (default: 0.7)
  linewidth   — edge line width (default: 0.5)
  markersize  — point marker size in points (default: 5.0)
  label       — legend entry text (omit = no legend entry)
  zorder      — draw order (default: layer index + 1)
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")           # non-interactive; must precede pyplot import
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

logger = logging.getLogger(__name__)

_VALID_FORMATS = {"png", "svg", "pdf", "jpg", "jpeg"}

_DEFAULT_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
]


def render_map(
    layers: list[dict],
    output_path: str,
    title: str = "",
    figsize: tuple[float, float] = (10.0, 10.0),
    dpi: int = 150,
    target_crs: Optional[str] = None,
) -> dict:
    """
    Render one or more vector layers to a static map image.

    Args:
        layers: List of layer dicts. Required key: "path". Optional keys:
                "color", "edge_color", "alpha", "linewidth", "markersize",
                "label" (legend entry), "zorder".
        output_path: Output file path (.png, .svg, .pdf, .jpg).
        title: Map title (empty string = no title).
        figsize: Figure size as (width, height) in inches.
        dpi: Output resolution (ignored for SVG).
        target_crs: Reproject all layers to this CRS.
                    Defaults to the first layer's CRS.

    Returns:
        dict with: output_path, output_format, layer_count, feature_count,
                   crs, bbox, figsize, dpi.

    Raises:
        ValueError: Empty layers, invalid figsize/dpi, unsupported format,
                    missing "path" key, or layer has no CRS.
        FileNotFoundError: A layer file does not exist.
    """
    if not layers:
        raise ValueError("layers must be a non-empty list")

    if dpi <= 0:
        raise ValueError(f"dpi must be > 0, got {dpi}")

    if len(figsize) != 2 or figsize[0] <= 0 or figsize[1] <= 0:
        raise ValueError(
            f"figsize must be (width, height) with positive values, got {figsize}"
        )

    ext = Path(output_path).suffix.lstrip(".").lower()
    if not ext:
        raise ValueError("output_path must have a file extension (.png, .svg, .pdf, .jpg)")
    if ext not in _VALID_FORMATS:
        raise ValueError(
            f"Unsupported output format '{ext}'. Choose: {', '.join(sorted(_VALID_FORMATS))}"
        )
    output_format = "jpeg" if ext == "jpg" else ext

    # Load and validate layers
    gdfs = []
    for i, layer in enumerate(layers):
        if "path" not in layer:
            raise ValueError(f"Layer {i} missing required 'path' key")
        path = layer["path"]
        if not Path(path).exists():
            raise FileNotFoundError(f"Layer file not found: {path}")
        logger.info("Loading layer %d: %s", i, path)
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            raise ValueError(f"Layer has no CRS: {path}")
        gdfs.append(gdf)
        logger.info("  %d features, CRS=%s", len(gdf), gdf.crs.to_string())

    # CRS alignment: reproject all layers to a common CRS
    from pyproj import CRS as ProjCRS
    crs = ProjCRS.from_user_input(target_crs) if target_crs else gdfs[0].crs
    crs_str = crs.to_string()
    aligned = []
    for gdf in gdfs:
        if gdf.crs != crs:
            logger.info(
                "Reprojecting layer from %s to %s", gdf.crs.to_string(), crs_str
            )
            gdf = gdf.to_crs(crs)
        aligned.append(gdf)

    # Combined extent across all layers
    all_bounds = [gdf.total_bounds for gdf in aligned]   # [minx, miny, maxx, maxy]
    xmin = min(b[0] for b in all_bounds)
    ymin = min(b[1] for b in all_bounds)
    xmax = max(b[2] for b in all_bounds)
    ymax = max(b[3] for b in all_bounds)

    logger.info(
        "Rendering %d layer(s), extent=[%.6f, %.6f, %.6f, %.6f]",
        len(aligned), xmin, ymin, xmax, ymax,
    )

    fig, ax = plt.subplots(1, 1, figsize=figsize)
    legend_handles = []
    total_features = 0

    for i, (layer, gdf) in enumerate(zip(layers, aligned)):
        color = layer.get("color", _DEFAULT_COLORS[i % len(_DEFAULT_COLORS)])
        edge_color = layer.get("edge_color", color)
        alpha = layer.get("alpha", 0.7)
        linewidth = layer.get("linewidth", 0.5)
        markersize = layer.get("markersize", 5.0)
        label = layer.get("label")
        zorder = layer.get("zorder", i + 1)

        gdf.plot(
            ax=ax,
            color=color,
            edgecolor=edge_color,
            alpha=alpha,
            linewidth=linewidth,
            markersize=markersize,
            zorder=zorder,
        )
        total_features += len(gdf)

        if label:
            legend_handles.append(
                mpatches.Patch(color=color, alpha=alpha, label=label)
            )

        logger.info("  Layer %d: %d features plotted", i, len(gdf))

    if title:
        ax.set_title(title, fontsize=14, pad=10)

    if legend_handles:
        ax.legend(handles=legend_handles, loc="best", fontsize=9)

    ax.set_axis_off()

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", format=output_format)
    plt.close(fig)

    file_size = out_path.stat().st_size
    logger.info("Output written: %s (%d bytes)", output_path, file_size)

    return {
        "output_path": output_path,
        "output_format": output_format,
        "layer_count": len(layers),
        "feature_count": total_features,
        "crs": crs_str,
        "bbox": (xmin, ymin, xmax, ymax),
        "figsize": figsize,
        "dpi": dpi,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render vector layers to a static map image"
    )
    parser.add_argument(
        "layers",
        nargs="+",
        help="Layer paths (GPKG, Shapefile, GeoJSON)",
    )
    parser.add_argument(
        "-o", "--output", required=True,
        help="Output image path (.png, .svg, .pdf, .jpg)",
    )
    parser.add_argument("--title", default="", help="Map title")
    parser.add_argument("--dpi", type=int, default=150, help="Output DPI (default: 150)")
    parser.add_argument(
        "--figsize",
        type=float, nargs=2, default=[10.0, 10.0],
        metavar=("WIDTH", "HEIGHT"),
        help="Figure size in inches (default: 10 10)",
    )
    parser.add_argument(
        "--crs", default=None,
        help="Target CRS for all layers (default: first layer's CRS)",
    )
    parser.add_argument(
        "--styles", default=None,
        help=(
            "Path to a JSON file containing a list of layer style dicts "
            "(same order as positional layer args). "
            "Each dict supports: color, edge_color, alpha, linewidth, markersize, label."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    styles = []
    if args.styles:
        styles_path = Path(args.styles)
        if not styles_path.exists():
            logger.error("Styles file not found: %s", args.styles)
            return 1
        with open(styles_path) as f:
            styles = json.load(f)

    layer_dicts = []
    for i, path in enumerate(args.layers):
        d = {"path": path}
        if i < len(styles):
            d.update(styles[i])
        layer_dicts.append(d)

    try:
        result = render_map(
            layers=layer_dicts,
            output_path=args.output,
            title=args.title,
            figsize=tuple(args.figsize),
            dpi=args.dpi,
            target_crs=args.crs,
        )
        print(f"\nMap rendered")
        print(f"  Layers        : {result['layer_count']}")
        print(f"  Features      : {result['feature_count']}")
        print(f"  Format        : {result['output_format'].upper()}")
        print(f"  CRS           : {result['crs']}")
        print(f"  Output        : {result['output_path']}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
