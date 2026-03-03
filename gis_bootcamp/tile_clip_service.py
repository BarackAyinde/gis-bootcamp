"""
tile_clip_service.py — Tile/Clip Service.

FastAPI microservice that dynamically clips vector and raster spatial datasets
to user-supplied bounding boxes. Designed for spatial data delivery backends.

Endpoints:
  GET  /health           — liveness check
  GET  /bbox/metadata    — metadata about a bounding box (area, center, CRS)
  POST /clip/vector      — clip a vector dataset to a bbox (GeoJSON or GPKG)
  POST /clip/raster      — clip a raster using windowed reads → GeoTIFF

Design notes:
  - Vector clip: spatial pre-filter via gdf.cx[] (STRtree-backed), then precise
    shapely clip. Handles CRS mismatch between bbox and dataset.
  - Raster clip: uses rasterio.mask.mask with crop=True for windowed reads —
    only the pixels intersecting the bbox are loaded from disk.
  - All inputs validated strictly; all requests timed and logged.
  - No full raster is loaded into memory when clipping.

Configuration (environment variables):
  TCS_DATA_DIR    — base directory datasets are served from (optional; for logging)
  TCS_OUTPUT_DIR  — base directory for written output files (default: ./output)

Run:
  python -m gis_bootcamp.tile_clip_service
  python -m gis_bootcamp.tile_clip_service --port 9000
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
import rasterio
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from rasterio.crs import CRS as RasterioCRS
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_bounds
from shapely.geometry import box as shapely_box, mapping

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("TCS_DATA_DIR", "./data")
_OUTPUT_DIR = os.environ.get("TCS_OUTPUT_DIR", "./output")

app = FastAPI(
    title="Tile/Clip Service",
    version="1.0.0",
    description="Dynamically clip vector and raster datasets to bounding boxes",
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(FileNotFoundError)
async def _file_not_found(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BBoxMetadataResponse(BaseModel):
    bbox: list[float]
    crs: str
    center: list[float]
    width: float
    height: float
    area_crs_units: float


class ClipVectorRequest(BaseModel):
    dataset_path: str
    bbox: list[float]           # [minx, miny, maxx, maxy]
    bbox_crs: str = "EPSG:4326"
    output_format: str = "geojson"   # "geojson" or "gpkg"
    output_path: Optional[str] = None  # required when output_format="gpkg"

    @field_validator("output_format")
    @classmethod
    def _check_format(cls, v: str) -> str:
        if v not in ("geojson", "gpkg"):
            raise ValueError(f"output_format must be 'geojson' or 'gpkg', got '{v}'")
        return v

    @field_validator("bbox")
    @classmethod
    def _check_bbox(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("bbox must have exactly 4 elements: [minx, miny, maxx, maxy]")
        if v[0] >= v[2] or v[1] >= v[3]:
            raise ValueError("Invalid bbox: minx must be < maxx and miny must be < maxy")
        return v


class ClipVectorResponse(BaseModel):
    feature_count: int
    crs: Optional[str]
    bbox: list[float]
    bbox_crs: str
    output_format: str
    output_path: Optional[str] = None
    geojson: Optional[dict[str, Any]] = None
    duration_seconds: float


class ClipRasterRequest(BaseModel):
    raster_path: str
    bbox: list[float]           # [minx, miny, maxx, maxy]
    bbox_crs: str = "EPSG:4326"
    output_path: str

    @field_validator("bbox")
    @classmethod
    def _check_bbox(cls, v: list[float]) -> list[float]:
        if len(v) != 4:
            raise ValueError("bbox must have exactly 4 elements: [minx, miny, maxx, maxy]")
        if v[0] >= v[2] or v[1] >= v[3]:
            raise ValueError("Invalid bbox: minx must be < maxx and miny must be < maxy")
        return v


class ClipRasterResponse(BaseModel):
    output_path: str
    crs: Optional[str]
    bbox_used: list[float]
    width: int
    height: int
    band_count: int
    dtype: str
    nodata: Optional[float]
    duration_seconds: float


# ---------------------------------------------------------------------------
# Core logic (importable independently of FastAPI)
# ---------------------------------------------------------------------------

def bbox_metadata(
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    crs: str = "EPSG:4326",
) -> dict:
    """Compute metadata for a bounding box.

    Args:
        minx, miny, maxx, maxy: Bounding box coordinates.
        crs: CRS string (default EPSG:4326).

    Returns:
        dict with bbox, crs, center, width, height, area_crs_units.

    Raises:
        ValueError: Invalid bounding box (minx >= maxx or miny >= maxy).
    """
    if minx >= maxx or miny >= maxy:
        raise ValueError(
            f"Invalid bbox: minx ({minx}) must be < maxx ({maxx}) "
            f"and miny ({miny}) must be < maxy ({maxy})"
        )
    width = maxx - minx
    height = maxy - miny
    return {
        "bbox": [minx, miny, maxx, maxy],
        "crs": crs,
        "center": [(minx + maxx) / 2, (miny + maxy) / 2],
        "width": width,
        "height": height,
        "area_crs_units": width * height,
    }


def clip_vector(
    dataset_path: str,
    bbox: list[float],
    bbox_crs: str = "EPSG:4326",
    output_format: str = "geojson",
    output_path: Optional[str] = None,
) -> dict:
    """Clip a vector dataset to a bounding box.

    Uses a spatial index pre-filter (gdf.cx[]) followed by a precise Shapely
    clip. If the bbox CRS differs from the dataset CRS, the bbox is reprojected
    to the dataset CRS before clipping.

    Args:
        dataset_path: Path to the input vector file.
        bbox: [minx, miny, maxx, maxy] in bbox_crs coordinates.
        bbox_crs: CRS of the supplied bbox (default EPSG:4326).
        output_format: "geojson" (inline) or "gpkg" (writes to output_path).
        output_path: Output file path (required when output_format="gpkg").

    Returns:
        dict with feature_count, crs, bbox, bbox_crs, output_format,
        output_path, geojson (when format=geojson), duration_seconds.

    Raises:
        FileNotFoundError: dataset_path does not exist.
        ValueError: Invalid output_format or output_path not provided for gpkg.
    """
    t0 = time.perf_counter()

    if not Path(dataset_path).exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    if output_format not in ("geojson", "gpkg"):
        raise ValueError(f"output_format must be 'geojson' or 'gpkg', got '{output_format}'")
    if output_format == "gpkg" and not output_path:
        raise ValueError("output_path is required when output_format='gpkg'")

    logger.info("clip_vector: loading %s", dataset_path)
    gdf = gpd.read_file(dataset_path)

    minx, miny, maxx, maxy = bbox

    # Build clip geometry in dataset CRS
    clip_geom = shapely_box(minx, miny, maxx, maxy)
    if gdf.crs and bbox_crs != gdf.crs.to_string():
        logger.info("  reprojecting bbox from %s to %s", bbox_crs, gdf.crs.to_string())
        bbox_gdf = gpd.GeoDataFrame(geometry=[clip_geom], crs=bbox_crs)
        bbox_gdf = bbox_gdf.to_crs(gdf.crs)
        clip_geom = bbox_gdf.geometry.iloc[0]

    # Spatial pre-filter using STRtree-backed coordinate indexer
    b = clip_geom.bounds
    candidates = gdf.cx[b[0]:b[2], b[1]:b[3]]
    logger.info("  spatial index pre-filter: %d → %d candidates", len(gdf), len(candidates))

    # Precise clip
    clipped = candidates.clip(clip_geom) if len(candidates) > 0 else candidates.copy()
    clipped = clipped[~clipped.geometry.is_empty & ~clipped.geometry.isna()].copy()
    logger.info("  clipped result: %d features", len(clipped))

    crs_str = clipped.crs.to_string() if clipped.crs else None
    result: dict[str, Any] = {
        "feature_count": len(clipped),
        "crs": crs_str,
        "bbox": bbox,
        "bbox_crs": bbox_crs,
        "output_format": output_format,
        "output_path": None,
        "geojson": None,
        "duration_seconds": 0.0,
    }

    if output_format == "geojson":
        result["geojson"] = clipped.__geo_interface__
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        clipped.to_file(output_path, driver="GPKG")
        result["output_path"] = output_path
        logger.info("  written to: %s", output_path)

    result["duration_seconds"] = round(time.perf_counter() - t0, 4)
    logger.info(
        "clip_vector complete: %d features in %.3fs",
        len(clipped), result["duration_seconds"],
    )
    return result


def clip_raster(
    raster_path: str,
    bbox: list[float],
    bbox_crs: str = "EPSG:4326",
    output_path: str = "",
) -> dict:
    """Clip a raster dataset to a bounding box using windowed reads.

    Uses rasterio.mask.mask with crop=True so only the pixels within the
    bounding box are read from disk — the full raster is never loaded.
    If the bbox CRS differs from the raster CRS, the bbox is reprojected.

    Args:
        raster_path: Path to the input raster (GeoTIFF or COG).
        bbox: [minx, miny, maxx, maxy] in bbox_crs coordinates.
        bbox_crs: CRS of the supplied bbox (default EPSG:4326).
        output_path: Path to write the clipped GeoTIFF.

    Returns:
        dict with output_path, crs, bbox_used, width, height, band_count,
        dtype, nodata, duration_seconds.

    Raises:
        FileNotFoundError: raster_path does not exist.
        ValueError: Bounding box does not intersect the raster, or output_path missing.
    """
    t0 = time.perf_counter()

    if not Path(raster_path).exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}")
    if not output_path:
        raise ValueError("output_path is required for clip_raster")

    logger.info("clip_raster: %s  bbox=%s  bbox_crs=%s", raster_path, bbox, bbox_crs)

    with rasterio.open(raster_path) as src:
        raster_crs = src.crs

        # Reproject bbox to raster CRS if needed
        if raster_crs and bbox_crs != raster_crs.to_string():
            logger.info("  reprojecting bbox from %s to %s", bbox_crs, raster_crs.to_string())
            reprojected = transform_bounds(bbox_crs, raster_crs, *bbox)
            bbox_used = list(reprojected)
        else:
            bbox_used = list(bbox)

        # Check overlap with raster extent
        rb = src.bounds
        if (bbox_used[2] <= rb.left or bbox_used[0] >= rb.right
                or bbox_used[3] <= rb.bottom or bbox_used[1] >= rb.top):
            raise ValueError(
                f"Bounding box {bbox_used} does not intersect raster extent "
                f"[{rb.left}, {rb.bottom}, {rb.right}, {rb.top}]"
            )

        # Clip using windowed read via rasterio.mask.mask(crop=True)
        clip_geom = mapping(shapely_box(*bbox_used))
        try:
            out_image, out_transform = rio_mask(src, [clip_geom], crop=True)
        except ValueError as exc:
            raise ValueError(f"Raster clip failed: {exc}") from exc

        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
        })

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", **out_meta) as dst:
            dst.write(out_image)

        logger.info(
            "  clipped raster: %d×%d px  bands=%d  written to %s",
            out_meta["width"], out_meta["height"], src.count, output_path,
        )

    duration = round(time.perf_counter() - t0, 4)
    logger.info("clip_raster complete in %.3fs", duration)

    return {
        "output_path": output_path,
        "crs": raster_crs.to_string() if raster_crs else None,
        "bbox_used": bbox_used,
        "width": out_meta["width"],
        "height": out_meta["height"],
        "band_count": out_meta["count"],
        "dtype": out_meta["dtype"],
        "nodata": out_meta.get("nodata"),
        "duration_seconds": duration,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@app.get("/bbox/metadata", response_model=BBoxMetadataResponse)
def get_bbox_metadata(
    minx: float = Query(..., description="Minimum X (left)"),
    miny: float = Query(..., description="Minimum Y (bottom)"),
    maxx: float = Query(..., description="Maximum X (right)"),
    maxy: float = Query(..., description="Maximum Y (top)"),
    crs: str = Query("EPSG:4326", description="CRS of the bounding box"),
) -> dict:
    """Return metadata about a bounding box: area, center, dimensions."""
    return bbox_metadata(minx, miny, maxx, maxy, crs)


@app.post("/clip/vector", response_model=ClipVectorResponse)
def clip_vector_endpoint(req: ClipVectorRequest) -> dict:
    """Clip a vector dataset to a bounding box.

    Returns inline GeoJSON when output_format='geojson'.
    Writes a GPKG and returns the output path when output_format='gpkg'.
    """
    t = time.perf_counter()
    logger.info(
        "POST /clip/vector  dataset=%s  bbox=%s  format=%s",
        req.dataset_path, req.bbox, req.output_format,
    )
    result = clip_vector(
        dataset_path=req.dataset_path,
        bbox=req.bbox,
        bbox_crs=req.bbox_crs,
        output_format=req.output_format,
        output_path=req.output_path,
    )
    logger.info("  → %d features  %.3fs", result["feature_count"], time.perf_counter() - t)
    return result


@app.post("/clip/raster", response_model=ClipRasterResponse)
def clip_raster_endpoint(req: ClipRasterRequest) -> dict:
    """Clip a raster dataset to a bounding box using windowed reads.

    Only the pixels within the bounding box are read from disk.
    Writes a GeoTIFF to output_path and returns metadata.
    """
    t = time.perf_counter()
    logger.info(
        "POST /clip/raster  raster=%s  bbox=%s",
        req.raster_path, req.bbox,
    )
    result = clip_raster(
        raster_path=req.raster_path,
        bbox=req.bbox,
        bbox_crs=req.bbox_crs,
        output_path=req.output_path,
    )
    logger.info("  → %dx%d px  %.3fs", result["width"], result["height"], time.perf_counter() - t)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Start the Tile/Clip Service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    uvicorn.run(
        "gis_bootcamp.tile_clip_service:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
