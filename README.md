# GIS Bootcamp: Geospatial Data Engineering Platform

A production-ready geospatial toolkit with **24+ Python modules** across 4 weeks of curriculum, plus 3 capstone projects. Built for real-world GIS workflows with **626+ tests**, FastAPI microservices, and CLI tools.

**Status**: ✅ Complete — All 4 weeks + 3 capstone projects fully implemented and tested

---

## Quick Start

### Installation

```bash
cd gis-bootcamp
pip install -e .
pip install pytest pytest-cov
```

### Run Tests

```bash
# All tests (626 total)
pytest tests/ -v

# Specific weeks
pytest tests/ -k "test_geometry" -v    # Week 1: Vector GIS
pytest tests/ -k "test_raster" -v      # Week 2: Raster GIS  
pytest tests/ -k "test_batch" -v       # Week 3: Spatial Analysis
pytest tests/ -k "spatial_api" -v      # Week 4: Production Engineering

# With coverage
pytest tests/ --cov=gis_bootcamp --cov-report=html
```

---

## Module Overview

### **Week 1: Vector GIS Fundamentals** (6 modules, 98 tests)

Core vector operations: inspection, validation, reprojection, spatial joins, geoprocessing.

| Module | Purpose | Key Command |
|--------|---------|-------------|
| Geometry Inspector | Analyze vector dataset properties | `python -m gis_bootcamp.geometry_inspector data.gpkg` |
| Vector Reprojection | Reproject between coordinate systems | `python -m gis_bootcamp.vector_reprojection data.gpkg -e 3857 -o output.gpkg` |
| Spatial Join | Join datasets by spatial relationships | `python -m gis_bootcamp.spatial_join left.gpkg right.gpkg -p within -o output.gpkg` |
| Geometry Validation | Detect and repair invalid geometries | `python -m gis_bootcamp.geometry_validation data.gpkg -o output.gpkg` |
| Vector Geoprocessing | Clip, buffer, dissolve operations | `python -m gis_bootcamp.vector_geoprocessing clip input.gpkg clip.gpkg -o output.gpkg` |
| Vector ETL Pipeline | Composable 5-stage pipeline | `python -m gis_bootcamp.vector_etl_pipeline data.shp -e 3857 -o output.gpkg` |

---

### **Week 2: Raster GIS & Data Transformation** (6 modules, 90+ tests)

Raster processing, metadata extraction, format conversion, mosaicking.

| Module | Purpose | Key Command |
|--------|---------|-------------|
| Raster Metadata Inspector | Extract raster dataset metadata | `python -m gis_bootcamp.raster_metadata_inspector data.tif` |
| Raster Clipper | Clip raster to bbox or vector | `python -m gis_bootcamp.raster_clipper data.tif -b 10 20 15 25 -o output.tif` |
| GeoTIFF to COG | Convert to Cloud-Optimized GeoTIFF | `python -m gis_bootcamp.geotiff_to_cog data.tif -o output_cog.tif` |
| Raster Mosaic | Combine multiple raster tiles | `python -m gis_bootcamp.raster_mosaic data/tiles/ -o output.tif` |
| Vector to GeoParquet | Convert vector to columnar format | `python -m gis_bootcamp.vector_to_geoparquet data.gpkg -o output.parquet` |
| Raster Processing Pipeline | Multi-stage raster workflow | `python -m gis_bootcamp.raster_pipeline data.tif --clip aoi.gpkg --reproject 3857 -o output.tif` |

---

### **Week 3: Spatial Analysis & Enrichment** (6 modules, 90+ tests)

Advanced analytics, geocoding, routing, density analysis, map rendering.

| Module | Purpose | Key Command |
|--------|---------|-------------|
| Batch Geocoder | Convert addresses to coordinates | `python -m gis_bootcamp.batch_geocoder data/addresses.csv -o output.geojson` |
| Reverse Geocoder | Convert coordinates to addresses | `python -m gis_bootcamp.reverse_geocoder data/coords.geojson -o output.csv` |
| Routing Distance Client | Calculate routing distances | `python -m gis_bootcamp.routing_distance_client --origin "40.71,-74" --destination "40.75,-73.98"` |
| Hotspot Analysis | Identify spatial clustering (KDE) | `python -m gis_bootcamp.density_analysis data/crimes.geojson -o output.tif` |
| Map Renderer | Create interactive map visualizations | `python -m gis_bootcamp.map_renderer data.gpkg -o output.html` |
| Enrichment Pipeline | Data enrichment via spatial joins | `python -m gis_bootcamp.enrichment_pipeline data.gpkg --enrich-with regions.gpkg -o output.gpkg` |

---

### **Week 4: Production Engineering & REST APIs** (6 modules, 127 tests)

REST APIs, database integration, quality assurance, containerization.

| Module | Purpose | Key Command |
|--------|---------|-------------|
| Spatial API | FastAPI microservice for geospatial ops | `python -m gis_bootcamp.spatial_api` → http://localhost:8000 |
| PostGIS Client | PostgreSQL/PostGIS integration | Programmatic: `PostGISClient("postgresql://...")` |
| Spatial QA Framework | Data quality validation | `python -m gis_bootcamp.spatial_qa data.gpkg --output-format json` |
| GIS Linter | Check files for common issues | `python -m gis_bootcamp.gis_linter data/` |
| Nearest Feature Lookup | Efficient nearest-neighbor queries | Programmatic: `NearestFeatureLookup("data.gpkg")` |

---

## Capstone Projects (3 options, 131 tests)

Advanced integration projects combining multiple tools into production systems.

### **Option A: Geospatial ETL Platform** (42 tests ✓)

Declarative pipeline engine with 11 composable transforms.

```bash
python -m gis_bootcamp.geospatial_etl --config pipeline.json --output output.gpkg
```

**Transforms**: load, validate, reproject, clip, buffer, dissolve, join, enrich, export, simplify, aggregate

---

### **Option B: Tile/Clip Service** (50 tests ✓)

FastAPI microservice for dynamic raster/vector clipping with bounding box metadata.

```bash
python -m gis_bootcamp.tile_clip_service
# Available at http://localhost:8000
# Endpoints: /health, /bbox/metadata, /clip/vector, /clip/raster
```

---

### **Option C: GIS Data Quality & Validation Toolkit** (39 tests ✓)

Configurable validation system with 12 reusable checks (7 vector + 5 raster).

```bash
python -m gis_bootcamp.gis_data_quality validate --config validation.json --output report.json
```

**Vector Checks**: crs, geometry_validity, no_null_geometries, feature_count, bbox_within, columns_present, attribute_range  
**Raster Checks**: crs, dimensions, band_count, nodata_defined, dtype

---

## Architecture & Design Patterns

The bootcamp demonstrates production GIS engineering patterns:

- **CLI Entry Points** — All modules have command-line interfaces via `argparse`
- **Python Library API** — All modules are importable for programmatic use
- **Registry Pattern** — Extensible transform/check registries (add custom rules without code changes)
- **Pydantic Validation** — Strict input validation at REST API boundaries
- **Windowed I/O** — Memory-efficient raster processing in blocks
- **Spatial Indexing** — STRtree for O(log n) nearest-neighbor queries
- **CRS Handling** — Automatic validation and reprojection
- **Structured Reporting** — Dataclass-based results with JSON export

See `IMPLEMENT.md` for detailed examples and usage patterns for each module.

---

## Project Structure

```
gis-bootcamp/
├── gis_bootcamp/              # 24+ modules
│   ├── geometry_inspector.py          # Week 1
│   ├── vector_reprojection.py
│   ├── spatial_join.py
│   ├── geometry_validation.py
│   ├── vector_geoprocessing.py
│   ├── vector_etl_pipeline.py
│   ├── raster_metadata_inspector.py   # Week 2
│   ├── raster_clipper.py
│   ├── geotiff_to_cog.py
│   ├── raster_mosaic.py
│   ├── vector_to_geoparquet.py
│   ├── raster_pipeline.py
│   ├── batch_geocoder.py              # Week 3
│   ├── reverse_geocoder.py
│   ├── routing_distance_client.py
│   ├── density_analysis.py
│   ├── map_renderer.py
│   ├── enrichment_pipeline.py
│   ├── spatial_api.py                 # Week 4
│   ├── postgis_client.py
│   ├── spatial_qa.py
│   ├── gis_linter.py
│   ├── nearest_feature_lookup.py
│   ├── geospatial_etl.py              # Capstone A
│   ├── tile_clip_service.py           # Capstone B
│   └── gis_data_quality.py            # Capstone C
├── tests/                     # 626+ tests
├── data/                      # Sample datasets
├── output/                    # Generated outputs
├── README.md                  # This file (overview)
├── IMPLEMENT.md               # Detailed implementation guide
├── PROGRESS.md                # Week-by-week progress notes
├── CAPSTONE_SUMMARY.md        # Capstone project details
└── pyproject.toml             # Project metadata
```

---

## Testing

**Test Coverage**: 626 tests across all modules

- **Week 1**: 98 tests (vector operations)
- **Week 2**: 90+ tests (raster operations)
- **Week 3**: 90+ tests (spatial analysis)
- **Week 4**: 127 tests (production engineering)
- **Capstone**: 131 tests (42 + 50 + 39)

**Run tests by category**:
```bash
pytest tests/ -v                              # All tests
pytest tests/ -k "Week1" -v                   # Week 1
pytest tests/test_geospatial_etl.py -v        # Capstone A
pytest tests/test_tile_clip_service.py -v     # Capstone B
pytest tests/test_gis_data_quality.py -v      # Capstone C
```

---

## Dependencies

**Core**: geopandas, rasterio, shapely, pyproj, fastapi, pydantic, pytest

**Optional**: folium (maps), sqlalchemy (ORM), psycopg2 (PostGIS), pyarrow (GeoParquet)

Install all:
```bash
pip install -e ".[dev,test]"
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Inspect vector data | `python -m gis_bootcamp.geometry_inspector data.gpkg` |
| Reproject vectors | `python -m gis_bootcamp.vector_reprojection data.gpkg -e 3857 -o output.gpkg` |
| Spatial join | `python -m gis_bootcamp.spatial_join left.gpkg right.gpkg -p within -o out.gpkg` |
| Validate geometries | `python -m gis_bootcamp.geometry_validation data.gpkg -o output.gpkg` |
| Clip/buffer/dissolve | `python -m gis_bootcamp.vector_geoprocessing buffer input.gpkg -d 1000 -o output.gpkg` |
| Get raster metadata | `python -m gis_bootcamp.raster_metadata_inspector data.tif` |
| Clip raster | `python -m gis_bootcamp.raster_clipper data.tif -b 10 20 15 25 -o output.tif` |
| Run ETL pipeline | `python -m gis_bootcamp.geospatial_etl --config pipeline.json` |
| Validate data quality | `python -m gis_bootcamp.gis_data_quality validate --config validation.json` |
| Start REST API | `python -m gis_bootcamp.spatial_api` |
| Run all tests | `pytest tests/ -v` |

---

## Documentation

- **`README.md`** — This file, high-level overview
- **`IMPLEMENT.md`** — Detailed implementation guide with examples for each module
- **`PROGRESS.md`** — Week-by-week progress tracking and implementation notes
- **`CAPSTONE_SUMMARY.md`** — Detailed capstone project documentation

For API documentation:
```bash
python -m gis_bootcamp.spatial_api
# Visit http://localhost:8000/docs for interactive Swagger UI
```

---

## License

GIS Bootcamp — Educational platform for geospatial engineering

**Created**: Rackstack Educational Initiative  
**Maintained by**: Barack Ayinde, Principal Data Engineer

---

**Status**: ✅ Complete — 24+ modules, 626+ tests, 3 capstone projects, full documentation
