"""
spatial_api.py — FastAPI Spatial Service.

Exposes GIS bootcamp tools as HTTP endpoints.
All endpoints accept and return JSON; file paths reference server-side files.

Endpoints:
  GET  /health              — liveness check
  POST /geocode             — batch geocode a CSV (Nominatim; injectable for tests)
  POST /nearest-feature     — spatial attribute lookup
  POST /density             — KDE raster or fishnet count density
  POST /render              — render vector layers to a static map image
  POST /pipeline            — run the full enrichment pipeline

Run with:
  python -m gis_bootcamp.spatial_api
  python -m gis_bootcamp.spatial_api --port 9000 --reload
"""

import argparse
import logging
import sys
from typing import Any, Callable, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gis_bootcamp.batch_geocoder import batch_geocode
from gis_bootcamp.density_analysis import analyze_density
from gis_bootcamp.enrichment_pipeline import run_enrichment_pipeline
from gis_bootcamp.map_renderer import render_map
from gis_bootcamp.nearest_feature_lookup import nearest_feature_lookup

logger = logging.getLogger(__name__)

app = FastAPI(
    title="GIS Spatial API",
    version="1.0.0",
    description="HTTP API for GIS data processing tools",
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Dependency: geocoder (injectable for testing)
# ---------------------------------------------------------------------------

def _default_geocoder() -> Optional[Callable]:
    """Returns None, causing batch_geocode to use real Nominatim. Override in tests."""
    return None


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GeocodeRequest(BaseModel):
    input_path: str
    output_path: str
    address_column: str = "address"


class GeocodeResponse(BaseModel):
    output_path: str
    total: int
    success: int
    not_found: int
    error: int
    skipped: int


class NearestFeatureRequest(BaseModel):
    points_path: str
    reference_path: str
    output_path: str
    mode: str = "nearest"


class NearestFeatureResponse(BaseModel):
    output_path: str
    total_points: int
    matched: int
    unmatched: int
    match_rate: float


class DensityRequest(BaseModel):
    input_path: str
    output_path: str
    cell_size: float
    bandwidth: Optional[float] = None
    output_type: str = "raster"


class DensityResponse(BaseModel):
    output_path: str
    output_type: str
    point_count: int
    crs: str
    cell_size: float
    bandwidth: Optional[float]
    grid_width: int
    grid_height: int
    total_cells: int
    hotspot_cells: int


class RenderRequest(BaseModel):
    layers: list[dict[str, Any]]
    output_path: str
    title: str = ""
    figsize: list[float] = [10.0, 10.0]
    dpi: int = 150
    target_crs: Optional[str] = None


class RenderResponse(BaseModel):
    output_path: str
    output_format: str
    layer_count: int
    feature_count: int
    crs: str
    bbox: list[float]
    figsize: list[float]
    dpi: int


class PipelineRequest(BaseModel):
    input_path: str
    output_dir: str
    geocode_column: Optional[str] = None
    reference_path: Optional[str] = None
    lookup_mode: str = "nearest"
    density_cell_size: Optional[float] = None
    density_output_type: str = "raster"
    density_bandwidth: Optional[float] = None
    render: bool = False
    map_title: str = ""


class PipelineResponse(BaseModel):
    output_dir: str
    stages_run: list[str]
    enriched_path: str
    point_count: int
    geocode_stats: Optional[dict[str, Any]] = None
    lookup_stats: Optional[dict[str, Any]] = None
    density_stats: Optional[dict[str, Any]] = None
    map_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@app.post("/geocode", response_model=GeocodeResponse)
def geocode(
    req: GeocodeRequest,
    geocoder: Optional[Callable] = Depends(_default_geocoder),
) -> dict:
    """Geocode addresses in a CSV file."""
    return batch_geocode(
        input_path=req.input_path,
        output_path=req.output_path,
        address_column=req.address_column,
        _geocoder=geocoder,
    )


@app.post("/nearest-feature", response_model=NearestFeatureResponse)
def nearest_feature(req: NearestFeatureRequest) -> dict:
    """Enrich a point dataset with attributes from a reference spatial dataset."""
    return nearest_feature_lookup(
        points_path=req.points_path,
        reference_path=req.reference_path,
        output_path=req.output_path,
        mode=req.mode,
    )


@app.post("/density", response_model=DensityResponse)
def density(req: DensityRequest) -> dict:
    """Compute KDE raster or fishnet count density from a point dataset."""
    return analyze_density(
        input_path=req.input_path,
        output_path=req.output_path,
        cell_size=req.cell_size,
        bandwidth=req.bandwidth,
        output_type=req.output_type,
    )


@app.post("/render", response_model=RenderResponse)
def render(req: RenderRequest) -> dict:
    """Render one or more vector layers to a static map image."""
    result = render_map(
        layers=req.layers,
        output_path=req.output_path,
        title=req.title,
        figsize=tuple(req.figsize),
        dpi=req.dpi,
        target_crs=req.target_crs,
    )
    # Convert tuples to lists for JSON serialisation
    result["bbox"] = list(result["bbox"])
    result["figsize"] = list(result["figsize"])
    return result


@app.post("/pipeline", response_model=PipelineResponse)
def pipeline(req: PipelineRequest) -> dict:
    """Run the spatial data enrichment pipeline."""
    return run_enrichment_pipeline(
        input_path=req.input_path,
        output_dir=req.output_dir,
        geocode_column=req.geocode_column,
        reference_path=req.reference_path,
        lookup_mode=req.lookup_mode,
        density_cell_size=req.density_cell_size,
        density_output_type=req.density_output_type,
        density_bandwidth=req.density_bandwidth,
        render=req.render,
        map_title=req.map_title,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Start the GIS Spatial API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    uvicorn.run(
        "gis_bootcamp.spatial_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
