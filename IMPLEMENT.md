# GIS Bootcamp: Implementation Guide

Detailed step-by-step guide for using each module. This document provides granular examples, parameters, and use cases.

---

## Week 1: Vector GIS Fundamentals

### 1. Geometry Inspector

Analyze vector dataset properties and geometry characteristics.

**Basic Usage**:
```bash
python -m gis_bootcamp.geometry_inspector data/countries.gpkg
```

**Output includes**:
- Feature count and geometry types
- Bounding box (min/max coordinates)
- CRS information
- Attribute schema
- Null geometry count
- Geometry complexity statistics

**Python API**:
```python
from gis_bootcamp.geometry_inspector import inspect_geometry

metadata = inspect_geometry("data/countries.gpkg")
print(f"Features: {metadata['feature_count']}")
print(f"CRS: {metadata['crs']}")
print(f"Geometry types: {metadata['geometry_types']}")
```

**Use cases**: Data reconnaissance, metadata extraction, quality checks

---

### 2. Vector Reprojection

Reproject vector datasets between coordinate systems with validation.

**Basic Usage**:
```bash
# WGS84 to Web Mercator
python -m gis_bootcamp.vector_reprojection data/input.gpkg -e 3857 -o output.gpkg

# WGS84 to UTM Zone 33N
python -m gis_bootcamp.vector_reprojection data/input.gpkg -e 32633 -o output.gpkg

# With verbose logging
python -m gis_bootcamp.vector_reprojection data/input.gpkg -e 3857 -o output.gpkg -v
```

**Python API**:
```python
from gis_bootcamp.vector_reprojection import reproject_vector

reproject_vector(
    input_path="data/countries.gpkg",
    output_epsg="EPSG:3857",
    output_path="output/countries_3857.gpkg"
)
```

**Supported EPSG codes**:
- `4326` — WGS84 (lat/lon)
- `3857` — Web Mercator
- `32633` — UTM Zone 33N
- `4269` — NAD83
- Any valid EPSG code

**Features**:
- Safe CRS validation before transformation
- Automatic intermediate transformations
- Preserves all attributes and data types
- Detailed transformation logging

**Use cases**: Data standardization, multi-region data integration, web mapping

---

### 3. Spatial Join

Join vector datasets based on spatial relationships.

**Basic Usage**:
```bash
# Point-in-polygon: cities within countries
python -m gis_bootcamp.spatial_join data/cities.gpkg data/countries.gpkg \
  -p within -o output/cities_in_countries.gpkg

# Intersection: find overlapping features
python -m gis_bootcamp.spatial_join data/roads.gpkg data/parks.gpkg \
  -p intersects -o output/intersections.gpkg

# Nearest-neighbor with distance filter
python -m gis_bootcamp.spatial_join data/stores.gpkg data/customers.gpkg \
  -p nearest -d 5000 -o output/nearby_stores.gpkg

# Right join (keep all right features)
python -m gis_bootcamp.spatial_join data/left.gpkg data/right.gpkg \
  -p within -how right -o output/result.gpkg
```

**Python API**:
```python
from gis_bootcamp.spatial_join import spatial_join

result = spatial_join(
    left_path="data/cities.gpkg",
    right_path="data/countries.gpkg",
    predicate="within",
    how="left",
    output_path="output/result.gpkg"
)
```

**Spatial predicates**:
- `intersects` — Geometries overlap or touch
- `within` — Left geometry inside right geometry
- `contains` — Left geometry contains right geometry
- `touches` — Geometries share boundary but don't overlap
- `nearest` — Find nearest feature (requires `-d` distance parameter)

**Join types**:
- `left` — Keep all left features, match where possible
- `right` — Keep all right features
- `inner` — Keep only matched features
- `outer` — Keep all features from both

**Features**:
- Automatic CRS alignment (right reprojected to left if needed)
- Efficient STRtree spatial indexing (O(log n) complexity)
- Preserves all attributes from both datasets
- Distance-based filtering for nearest-neighbor

**Use cases**: Data enrichment, geographic matching, proximity analysis, overlay analysis

---

### 4. Geometry Validation

Detect and repair invalid, null, or empty geometries.

**Basic Usage**:
```bash
# Repair geometries, keep unfixable ones (default)
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg

# Repair and drop unfixable geometries
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg --drop

# Verbose mode with detailed row-by-row logs
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg -v
```

**Python API**:
```python
from gis_bootcamp.geometry_validation import validate_geometries

result = validate_geometries(
    input_path="data/messy.gpkg",
    output_path="output/cleaned.gpkg",
    drop_unfixable=False,
    verbose=True
)

print(f"Invalid geometries found: {result['invalid_count']}")
print(f"Repaired: {result['repaired_count']}")
print(f"Dropped: {result['dropped_count']}")
```

**Detection capabilities**:
- Invalid polygons (self-intersecting, invalid rings)
- Empty geometries
- Null geometries
- Geometry type mismatches

**Repair method**: Shapely's `make_valid()` algorithm

**Output includes**:
- Repaired GeoPackage/Shapefile
- Detailed log of all issues by row
- Statistics on repairs/drops

**Use cases**: Data cleaning, quality assurance, preparation for analysis

---

### 5. Vector Geoprocessing

Perform clip, buffer, and dissolve operations on vector datasets.

**Clip Operation**:
```bash
# Clip to clipping geometry
python -m gis_bootcamp.vector_geoprocessing clip \
  input.gpkg clip_geometry.gpkg -o output/clipped.gpkg

# Example: Clip countries to specific region
python -m gis_bootcamp.vector_geoprocessing clip \
  data/countries.gpkg data/europe_bbox.gpkg -o output/europe_countries.gpkg
```

**Python API**:
```python
from gis_bootcamp.vector_geoprocessing import clip_features

clip_features(
    input_path="data/countries.gpkg",
    clip_path="data/aoi.gpkg",
    output_path="output/clipped.gpkg"
)
```

**Buffer Operation**:
```bash
# Buffer with 1000m distance
python -m gis_bootcamp.vector_geoprocessing buffer \
  input.gpkg -d 1000 -o output/buffered.gpkg

# Buffer with dissolve (merge overlapping buffers)
python -m gis_bootcamp.vector_geoprocessing buffer \
  input.gpkg -d 5000 -ds -o output/merged_buffer.gpkg

# Example: Create 10km buffer around roads
python -m gis_bootcamp.vector_geoprocessing buffer \
  data/roads.shp -d 10000 -o output/road_corridors.gpkg
```

**Python API**:
```python
from gis_bootcamp.vector_geoprocessing import buffer_features

buffer_features(
    input_path="data/roads.shp",
    distance=10000,  # meters
    dissolve=True,   # merge overlapping buffers
    output_path="output/buffered.gpkg"
)
```

**Dissolve Operation**:
```bash
# Dissolve all into single polygon
python -m gis_bootcamp.vector_geoprocessing dissolve \
  input.gpkg -o output/dissolved.gpkg

# Dissolve by attribute
python -m gis_bootcamp.vector_geoprocessing dissolve \
  input.gpkg -by region -o output/by_region.gpkg

# Example: Dissolve countries by continent
python -m gis_bootcamp.vector_geoprocessing dissolve \
  data/countries.gpkg -by continent -o output/continents.gpkg
```

**Python API**:
```python
from gis_bootcamp.vector_geoprocessing import dissolve_features

# Dissolve by attribute
dissolve_features(
    input_path="data/countries.gpkg",
    dissolve_by="continent",
    output_path="output/continents.gpkg"
)

# Dissolve all into one
dissolve_features(
    input_path="data/countries.gpkg",
    dissolve_by=None,
    output_path="output/world.gpkg"
)
```

**Features**:
- CRS and attribute preservation
- Deterministic operations with detailed logging
- Automatic output directory creation

**Use cases**: Feature selection, buffer analysis, feature aggregation, simplification

---

### 6. Vector ETL Pipeline

Composable 5-stage pipeline orchestrating Week 1 tools.

**Basic Usage**:
```bash
# Validate and reproject only
python -m gis_bootcamp.vector_etl_pipeline data/countries.shp -e 3857 -o output.gpkg

# Validate → Reproject → Clip to AOI
python -m gis_bootcamp.vector_etl_pipeline data/countries.shp -e 3857 \
  -op clip -cp clip_geometry.gpkg -o output.gpkg

# Validate → Reproject → Dissolve by attribute
python -m gis_bootcamp.vector_etl_pipeline data/countries.shp -e 3857 \
  -op dissolve -dby continent -o output.gpkg

# Full pipeline: Validate → Reproject → Buffer with dissolve
python -m gis_bootcamp.vector_etl_pipeline data/cities.shp -e 3857 \
  -op buffer -dist 10000 -ds -o output.gpkg

# Verbose output with all stage logs
python -m gis_bootcamp.vector_etl_pipeline data/roads.shp -e 3857 \
  -op buffer -dist 5000 -o output.gpkg -v
```

**Pipeline Stages**:
1. **Load** — Read input vector file
2. **Validate** — Check and repair geometries
3. **Reproject** — Transform to target CRS
4. **Geoprocess** — Apply optional clip/buffer/dissolve
5. **Write** — Save cleaned output

**Python API**:
```python
from gis_bootcamp.vector_etl_pipeline import run_etl_pipeline

result = run_etl_pipeline(
    input_path="data/countries.shp",
    target_epsg="EPSG:3857",
    geoprocess_op="dissolve",
    geoprocess_params={"by": "continent"},
    output_path="output.gpkg",
    verbose=True
)
```

**Real-world examples** (on 258 Natural Earth countries):
- Validate → Reproject (4326→3857) → Dissolve by continent: 258 → 8 features ✓
- Validate → Reproject → Clip to Europe: 258 → 61 countries ✓
- Validate → Reproject (4326→32633 UTM): 258 → 258 countries ✓

**Use cases**: Complete ETL workflows, data standardization, production pipelines

---

## Week 2: Raster GIS & Data Transformation

### 7. Raster Metadata Inspector

Extract and display comprehensive raster dataset metadata.

**Basic Usage**:
```bash
python -m gis_bootcamp.raster_metadata_inspector data/dem.tif
```

**Output includes**:
- CRS and projection information
- EPSG code
- Raster dimensions (width × height)
- Pixel resolution (x, y)
- Band count and data type
- NoData value
- Geotransform and bounding box
- Statistics per band

**Python API**:
```python
from gis_bootcamp.raster_metadata_inspector import inspect_raster

metadata = inspect_raster("data/dem.tif")
print(f"CRS: {metadata['crs']}")
print(f"Dimensions: {metadata['width']} × {metadata['height']}")
print(f"Resolution: {metadata['resolution']}")
print(f"Bands: {metadata['band_count']}")
print(f"Data type: {metadata['dtype']}")
```

**Use cases**: Data reconnaissance, metadata extraction, format validation

---

### 8. Raster Clipper

Clip raster datasets to vector geometries or bounding boxes with windowed I/O.

**Clip to Bounding Box**:
```bash
# Clip to coordinates (minx, miny, maxx, maxy)
python -m gis_bootcamp.raster_clipper data/dem.tif -b 10 20 15 25 -o output/clipped.tif

# Clip to UTM zone
python -m gis_bootcamp.raster_clipper data/dem.tif -b 500000 4000000 600000 4100000 -o output/clipped.tif
```

**Clip to Vector Geometry**:
```bash
# Clip to AOI polygon
python -m gis_bootcamp.raster_clipper data/dem.tif -v aoi.gpkg -o output/clipped.tif

# Clip with CRS conversion (if raster and vector have different CRS)
python -m gis_bootcamp.raster_clipper data/dem.tif -v aoi.gpkg -o output/clipped.tif
```

**Python API**:
```python
from gis_bootcamp.raster_clipper import clip_raster_to_bbox, clip_raster_to_vector

# Clip to bounding box
clip_raster_to_bbox(
    raster_path="data/dem.tif",
    bbox=(10, 20, 15, 25),  # minx, miny, maxx, maxy
    output_path="output/clipped.tif"
)

# Clip to vector geometry
clip_raster_to_vector(
    raster_path="data/dem.tif",
    vector_path="aoi.gpkg",
    output_path="output/clipped.tif"
)
```

**Features**:
- Windowed I/O for memory efficiency on large rasters
- CRS validation and automatic reprojection
- NoData preservation
- Metadata preservation

**Use cases**: Area-of-interest extraction, data subsetting, preprocessing

---

### 9. GeoTIFF to COG Converter

Convert GeoTIFF files to Cloud-Optimized GeoTIFF (COG) format for efficient cloud access.

**Basic Usage**:
```bash
# Default (DEFLATE compression)
python -m gis_bootcamp.geotiff_to_cog data/dem.tif -o output/dem_cog.tif

# With LZW compression
python -m gis_bootcamp.geotiff_to_cog data/dem.tif -o output/dem_cog.tif -c lzw

# With ZSTD compression
python -m gis_bootcamp.geotiff_to_cog data/dem.tif -o output/dem_cog.tif -c zstd
```

**Python API**:
```python
from gis_bootcamp.geotiff_to_cog import convert_to_cog

convert_to_cog(
    input_path="data/dem.tif",
    output_path="output/dem_cog.tif",
    compression="lzw"
)
```

**Compression options**: deflate (default), lzw, zstd

**Features**:
- COG structure with internal overviews
- Optional compression
- Cloud-friendly format for remote access (HTTP range requests)
- Preservation of metadata and CRS

**Use cases**: Cloud storage optimization, web-accessible rasters, CDN deployment

---

### 10. Raster Mosaic

Combine multiple raster tiles into a single seamless dataset.

**Basic Usage**:
```bash
# Mosaic all tiles in directory
python -m gis_bootcamp.raster_mosaic data/tiles/ -o output/mosaic.tif

# Mosaic with CRS conversion
python -m gis_bootcamp.raster_mosaic data/tiles/ -o output/mosaic.tif -e 3857

# Mosaic with verbose logging
python -m gis_bootcamp.raster_mosaic data/tiles/ -o output/mosaic.tif -v
```

**Python API**:
```python
from gis_bootcamp.raster_mosaic import mosaic_rasters

mosaic_rasters(
    tiles_directory="data/tiles/",
    output_path="output/mosaic.tif",
    target_epsg="EPSG:3857",
    verbose=True
)
```

**Features**:
- Seamless tile merging
- Automatic CRS alignment
- NoData value handling
- Efficient memory usage

**Use cases**: Multi-tile DEM assembly, satellite imagery stitching, global dataset creation

---

### 11. Vector to GeoParquet

Convert vector datasets to GeoParquet format for efficient columnar storage.

**Basic Usage**:
```bash
# Simple conversion
python -m gis_bootcamp.vector_to_geoparquet data/countries.gpkg -o output/countries.parquet

# Partition by attribute (Hive-style partitioning)
python -m gis_bootcamp.vector_to_geoparquet data/countries.gpkg -o output/countries/ \
  --partition-by continent

# With verbose output
python -m gis_bootcamp.vector_to_geoparquet data/countries.gpkg -o output/countries.parquet -v
```

**Python API**:
```python
from gis_bootcamp.vector_to_geoparquet import convert_to_geoparquet

convert_to_geoparquet(
    input_path="data/countries.gpkg",
    output_path="output/countries.parquet",
    partition_by="continent"
)
```

**Features**:
- Columnar format for fast analytics
- Geometry encoding and compression
- Partitioning support for large datasets
- Apache Arrow-based efficient I/O

**Use cases**: Large-scale analytics, cloud storage, data warehouse ingestion

---

### 12. Raster Processing Pipeline

Multi-stage pipeline for complex raster workflows.

**Basic Usage**:
```bash
# Clip, reproject, and output
python -m gis_bootcamp.raster_pipeline data/dem.tif \
  --clip aoi.gpkg --reproject 3857 --output output/processed.tif

# Mosaic tiles, then clip
python -m gis_bootcamp.raster_pipeline data/tiles/ \
  --mosaic --clip aoi.gpkg --output output/mosaic_clipped.tif
```

**Python API**:
```python
from gis_bootcamp.raster_pipeline import run_raster_pipeline

run_raster_pipeline(
    input_path="data/dem.tif",
    clip_path="aoi.gpkg",
    target_epsg="EPSG:3857",
    output_path="output/processed.tif",
    verbose=True
)
```

**Features**:
- Multi-stage raster processing
- Windowed I/O throughout pipeline
- Memory-efficient for large datasets
- Stage-level logging and validation

**Use cases**: Complex raster workflows, multi-step processing chains

---

## Week 3: Spatial Analysis & Enrichment

### 13. Batch Geocoder

Convert addresses to coordinates using Nominatim with batching and caching.

**Basic Usage**:
```bash
# Geocode address CSV file
python -m gis_bootcamp.batch_geocoder data/addresses.csv -o output/geocoded.geojson

# With custom delay between requests (rate limiting)
python -m gis_bootcamp.batch_geocoder data/addresses.csv -o output/geocoded.geojson --delay 2

# Verbose mode
python -m gis_bootcamp.batch_geocoder data/addresses.csv -o output/geocoded.geojson -v
```

**Input CSV Format**:
```csv
address
123 Main St, New York, NY
456 Oak Ave, Los Angeles, CA
789 Elm Blvd, Chicago, IL
```

**Python API**:
```python
from gis_bootcamp.batch_geocoder import geocode_addresses

results = geocode_addresses(
    input_path="data/addresses.csv",
    output_path="output/geocoded.geojson",
    delay=2,  # seconds between requests
    verbose=True
)

print(f"Successfully geocoded: {results['success_count']}")
print(f"Failed: {results['failed_count']}")
```

**Output Format**: GeoJSON with geometry and original address attributes

**Features**:
- Batch geocoding with rate limiting
- In-memory caching to prevent duplicate API calls
- Nominatim API integration (OpenStreetMap)
- Success/failure tracking
- GeoJSON output with coordinates

**Use cases**: Address to coordinate conversion, location analysis, data preparation

---

### 14. Reverse Geocoder

Convert coordinates to addresses using reverse geocoding.

**Basic Usage**:
```bash
# Reverse geocode from GeoJSON points
python -m gis_bootcamp.reverse_geocoder data/coordinates.geojson -o output/addresses.csv

# From CSV with lon/lat columns
python -m gis_bootcamp.reverse_geocoder data/coords.csv -o output/addresses.csv
```

**Python API**:
```python
from gis_bootcamp.reverse_geocoder import reverse_geocode

result = reverse_geocode(
    input_path="data/coordinates.geojson",
    output_path="output/addresses.csv"
)
```

**Features**:
- Coordinate to address lookup
- Batch processing
- Result caching
- CSV/GeoJSON output

**Use cases**: Address lookup, location naming, data enrichment

---

### 15. Routing Distance Client

Calculate distances and routing information between locations.

**Basic Usage**:
```bash
# Simple distance between two points
python -m gis_bootcamp.routing_distance_client \
  --origin "40.7128,-74.0060" --destination "40.7580,-73.9855"

# With alternative output format
python -m gis_bootcamp.routing_distance_client \
  --origin "40.7128,-74.0060" --destination "40.7580,-73.9855" --output json
```

**Python API**:
```python
from gis_bootcamp.routing_distance_client import calculate_distance

distance = calculate_distance(
    origin=(40.7128, -74.0060),  # lat, lon
    destination=(40.7580, -73.9855),
    profile="car"  # car, foot, bike
)

print(f"Distance: {distance['distance']} meters")
print(f"Duration: {distance['duration']} seconds")
```

**Routing profiles**: car, foot, bike

**Features**:
- Distance calculation
- Routing information retrieval
- Multiple routing profiles
- Matrix routing for many-to-many distances

**Use cases**: Route planning, accessibility analysis, travel time calculation

---

### 16. Hotspot Analysis

Identify spatial clustering and hotspots using Kernel Density Estimation (KDE).

**Basic Usage**:
```bash
# Default bandwidth
python -m gis_bootcamp.density_analysis data/crimes.geojson -o output/hotspots.tif

# Custom bandwidth (larger = smoother)
python -m gis_bootcamp.density_analysis data/crimes.geojson -o output/hotspots.tif \
  --bandwidth 1000

# With output CRS
python -m gis_bootcamp.density_analysis data/crimes.geojson -o output/hotspots.tif \
  --bandwidth 500 --output-crs 3857
```

**Python API**:
```python
from gis_bootcamp.density_analysis import analyze_density

result = analyze_density(
    input_path="data/crimes.geojson",
    output_path="output/hotspots.tif",
    bandwidth=1000,  # meters
    output_crs="EPSG:3857"
)

print(f"Hotspot raster created: {result['output_path']}")
print(f"CRS: {result['crs']}")
```

**Features**:
- Kernel Density Estimation (KDE)
- Hotspot identification
- Customizable bandwidth/search radius
- Raster output for visualization

**Use cases**: Crime hotspot detection, disease surveillance, event clustering, risk mapping

---

### 17. Map Renderer

Create interactive and static map visualizations from spatial data.

**Basic Usage**:
```bash
# Interactive map with default settings
python -m gis_bootcamp.map_renderer data/countries.gpkg -o output/map.html

# Choropleth map colored by attribute
python -m gis_bootcamp.map_renderer data/countries.gpkg -o output/map.html \
  --color-by population

# Custom basemap
python -m gis_bootcamp.map_renderer data/countries.gpkg -o output/map.html \
  --basemap cartodb_positron
```

**Python API**:
```python
from gis_bootcamp.map_renderer import render_map

render_map(
    input_path="data/countries.gpkg",
    output_path="output/map.html",
    color_column="population",
    basemap="osm",
    zoom_to_fit=True
)
```

**Basemap options**: osm, cartodb_positron, cartodb_positron_nolabels, opentopomap

**Features**:
- Interactive map generation (Folium)
- Choropleth mapping with attribute coloring
- Multiple basemap options
- Custom styling and legends
- HTML output for web viewing

**Use cases**: Data visualization, map sharing, exploratory analysis

---

### 18. Enrichment Pipeline

Data enrichment through spatial joins and attribute lookups.

**Basic Usage**:
```bash
# Enrich customers with region information
python -m gis_bootcamp.enrichment_pipeline data/customers.gpkg \
  --enrich-with data/regions.gpkg --output output/enriched.gpkg

# Multiple enrichment sources
python -m gis_bootcamp.enrichment_pipeline data/customers.gpkg \
  --enrich-with data/regions.gpkg data/zones.gpkg \
  --output output/enriched.gpkg
```

**Python API**:
```python
from gis_bootcamp.enrichment_pipeline import enrich_data

enrich_data(
    input_path="data/customers.gpkg",
    enrich_sources=["data/regions.gpkg", "data/zones.gpkg"],
    output_path="output/enriched.gpkg"
)
```

**Features**:
- Spatial enrichment via joins
- Attribute lookup and merge
- Multi-source data integration
- Data quality tracking

**Use cases**: Customer segmentation, demographic analysis, property assessment

---

## Week 4: Production Engineering & REST APIs

### 19. Spatial API

FastAPI-based REST microservice for geospatial operations.

**Start Server**:
```bash
python -m gis_bootcamp.spatial_api
# Runs on http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

**Health Check**:
```bash
curl http://localhost:8000/health
```

**Clip Vector to Polygon**:
```bash
curl -X POST http://localhost:8000/clip/vector \
  -H "Content-Type: application/json" \
  -d '{
    "vector_path": "data/countries.gpkg",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[10,20],[30,20],[30,40],[10,40],[10,20]]]
    },
    "output_crs": "EPSG:4326"
  }'
```

**Clip Raster to Bounding Box**:
```bash
curl -X POST http://localhost:8000/clip/raster \
  -H "Content-Type: application/json" \
  -d '{
    "raster_path": "data/dem.tif",
    "bbox": [10, 20, 30, 40],
    "output_crs": "EPSG:4326"
  }'
```

**Create Buffer**:
```bash
curl -X POST http://localhost:8000/buffer \
  -H "Content-Type: application/json" \
  -d '{
    "vector_path": "data/roads.gpkg",
    "distance": 1000,
    "dissolve": true
  }'
```

**Available Endpoints**:
- `GET /health` — Service health check
- `POST /clip/vector` — Clip vector to polygon
- `POST /clip/raster` — Clip raster to bounding box
- `POST /buffer` — Create buffer zones
- `POST /spatial-join` — Perform spatial joins
- `POST /reproject` — Reproject datasets

**Error Handling**:
- `422 Unprocessable Entity` — Invalid request parameters (Pydantic validation)
- `500 Internal Server Error` — Processing error

**Python Integration**:
```python
import requests

response = requests.post(
    "http://localhost:8000/clip/vector",
    json={
        "vector_path": "data/countries.gpkg",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[10,20],[30,20],[30,40],[10,40],[10,20]]]
        }
    }
)

result = response.json()
```

**Features**:
- Pydantic input validation with strict typing
- Async request handling
- Comprehensive API documentation (Swagger)
- Production-ready error handling

**Use cases**: Web application backend, microservice architecture, serverless integration

---

### 20. PostGIS Client

Connect to and query PostGIS-enabled PostgreSQL databases.

**Basic Usage**:
```python
from gis_bootcamp.postgis_client import PostGISClient

# Connect to database
client = PostGISClient("postgresql://user:password@localhost:5432/gisdb")

# Query features
features = client.query("SELECT * FROM countries WHERE area > 1000000")

# Spatial query
from shapely.geometry import Point
geometry = Point(0, 0)
within = client.spatial_query(
    "SELECT * FROM cities WHERE ST_Within(geom, %s)",
    geometry
)

# Close connection
client.close()
```

**Features**:
- Connection pooling
- Parameterized queries for security
- Spatial query support
- GeoJSON serialization
- Automatic CRS handling

**Use cases**: Production database backend, data warehousing, large-scale analysis

---

### 21. Spatial QA Framework

Quality assurance toolkit for spatial data validation.

**Basic Usage**:
```bash
# Generate QA report
python -m gis_bootcamp.spatial_qa data/dataset.gpkg --output-format json > report.json

# Generate human-readable report
python -m gis_bootcamp.spatial_qa data/dataset.gpkg --output-format human
```

**Python API**:
```python
from gis_bootcamp.spatial_qa import validate_spatial_data

report = validate_spatial_data(
    input_path="data/dataset.gpkg",
    checks=["geometry", "crs", "attributes"]
)

if report["all_passed"]:
    print("✓ All checks passed")
else:
    for failure in report["failures"]:
        print(f"✗ {failure['check']}: {failure['message']}")
```

**Checks Performed**:
- Geometry validity
- CRS consistency
- Attribute completeness
- Feature count validation
- NULL geometry detection

**Use cases**: Pre-processing validation, data governance, quality reporting

---

### 22. GIS Linter

Lint geospatial files for common issues and best practices.

**Basic Usage**:
```bash
# Lint entire directory
python -m gis_bootcamp.gis_linter data/

# Check specific rules
python -m gis_bootcamp.gis_linter data/ --rules geometry,crs,attributes

# Output as JSON
python -m gis_bootcamp.gis_linter data/ --format json > lint_report.json
```

**Available Rules**: geometry, crs, attributes, naming, data_types

**Features**:
- Rule-based file linting
- Custom rule definitions
- Configurable output formats
- Integration with CI/CD pipelines

**Use cases**: Data standardization, style guide enforcement, pre-processing checks

---

### 23. Nearest Feature Lookup

Find nearest features efficiently using spatial indexing.

**Basic Usage**:
```python
from gis_bootcamp.nearest_feature_lookup import NearestFeatureLookup

# Build index
lookup = NearestFeatureLookup("data/cities.gpkg")

# Find nearest city to a point
from shapely.geometry import Point
query_point = Point(-74.0, 40.7)
nearest = lookup.find_nearest(query_point, max_distance=5000)

print(f"Nearest city: {nearest['properties']['name']}")
print(f"Distance: {nearest['distance']} meters")
```

**Batch Queries**:
```python
from geopandas import GeoDataFrame

# Query GeoDataFrame of points
stores = GeoDataFrame.from_file("data/stores.gpkg")
lookup = NearestFeatureLookup("data/cities.gpkg")

for idx, store in stores.iterrows():
    nearest = lookup.find_nearest(store.geometry)
    print(f"Store at index {idx} nearest to {nearest['properties']['name']}")
```

**Features**:
- Efficient spatial indexing (STRtree)
- Distance-based filtering
- Batch nearest-neighbor queries
- Performance optimized for large datasets

**Use cases**: Proximity analysis, location matching, facility allocation

---

## Capstone Projects

### Option A: Geospatial ETL Platform

**Configuration Example** (`pipeline.json`):
```json
{
  "name": "country_analysis",
  "steps": [
    {
      "name": "load_countries",
      "operation": "load",
      "params": {"path": "data/countries.shp"}
    },
    {
      "name": "validate_geometries",
      "operation": "validate",
      "params": {}
    },
    {
      "name": "reproject_to_web_mercator",
      "operation": "reproject",
      "params": {"target_crs": "EPSG:3857"}
    },
    {
      "name": "dissolve_by_continent",
      "operation": "dissolve",
      "params": {"by": "continent"}
    },
    {
      "name": "export_geojson",
      "operation": "export",
      "params": {"output_format": "geojson"}
    }
  ]
}
```

**Run Pipeline**:
```bash
python -m gis_bootcamp.geospatial_etl --config pipeline.json --output output.gpkg
```

**Available Transforms**:
- `load` — Load vector dataset
- `validate` — Check and repair geometries
- `reproject` — Transform CRS
- `clip` — Clip to geometry
- `buffer` — Create buffer zones
- `dissolve` — Merge features
- `join` — Spatial join with another dataset
- `enrich` — Data enrichment
- `export` — Export to different format
- `simplify` — Simplify geometries
- `aggregate` — Aggregate geometries

**Python API**:
```python
from gis_bootcamp.geospatial_etl import run_pipeline_from_config

result = run_pipeline_from_config("pipeline.json")
print(f"Output saved to: {result['output_path']}")
print(f"Features: {result['feature_count']}")
```

---

### Option B: Tile/Clip Service

**Start Service**:
```bash
python -m gis_bootcamp.tile_clip_service
# Runs on http://localhost:8000
```

**Get Bounding Box Metadata**:
```bash
curl "http://localhost:8000/bbox/metadata?path=data/dem.tif"
```

**Clip Vector**:
```bash
curl -X POST http://localhost:8000/clip/vector \
  -H "Content-Type: application/json" \
  -d '{
    "vector_path": "data/countries.gpkg",
    "geometry": {"type": "Polygon", "coordinates": [[[10,20],[30,20],[30,40],[10,40],[10,20]]]}
  }'
```

**Clip Raster**:
```bash
curl -X POST http://localhost:8000/clip/raster \
  -H "Content-Type: application/json" \
  -d '{
    "raster_path": "data/dem.tif",
    "bbox": [10, 20, 30, 40],
    "output_crs": "EPSG:4326"
  }'
```

---

### Option C: GIS Data Quality & Validation Toolkit

**Configuration Example** (`validation.json`):
```json
{
  "name": "parcels_validation",
  "rules": [
    {
      "type": "vector",
      "path": "data/parcels.gpkg",
      "rules": [
        {
          "check": "crs",
          "params": {"expected_crs": "EPSG:4326"}
        },
        {
          "check": "geometry_validity"
        },
        {
          "check": "no_null_geometries"
        },
        {
          "check": "feature_count",
          "params": {"min_count": 100, "max_count": 10000}
        },
        {
          "check": "columns_present",
          "params": {"columns": ["id", "owner", "area"]}
        }
      ]
    }
  ]
}
```

**Run Validation**:
```bash
# JSON output
python -m gis_bootcamp.gis_data_quality validate --config validation.json --output report.json

# Human-readable output
python -m gis_bootcamp.gis_data_quality validate --config validation.json --format human

# Exit code for CI/CD
python -m gis_bootcamp.gis_data_quality validate --config validation.json
echo $?  # 0 if all passed, 1 if any failed
```

**Python API**:
```python
from gis_bootcamp.gis_data_quality import validate_vector, validate_from_config

# Direct validation
result = validate_vector("data/parcels.gpkg", checks=[
    {"check": "crs", "params": {"expected_crs": "EPSG:4326"}},
    {"check": "geometry_validity"},
    {"check": "feature_count", "params": {"min_count": 100}}
])

if result["all_passed"]:
    print("✓ Validation passed")
else:
    for failure in result["failures"]:
        print(f"✗ {failure['check_name']}: {failure['message']}")

# JSON config-based validation
report = validate_from_config("validation.json")
if not report["all_passed"]:
    report.to_json("failures.json")
```

**Available Checks**:

**Vector**:
- `crs` — CRS matches expected value
- `geometry_validity` — All geometries are valid
- `no_null_geometries` — No null/empty geometries
- `feature_count` — Feature count in range
- `bbox_within` — Bounding box within region
- `columns_present` — Required columns exist
- `attribute_range` — Numeric attributes in range

**Raster**:
- `crs` — CRS matches expected value
- `dimensions` — Dimensions match expected
- `band_count` — Correct number of bands
- `nodata_defined` — NoData value is defined
- `dtype` — Data type is correct

---

## Architecture Patterns

### CLI Entry Points

All modules support command-line usage:
```bash
python -m gis_bootcamp.<module_name> [args]
```

### Python Library API

All modules are importable:
```python
from gis_bootcamp.<module_name> import <function_name>

result = <function_name>(...)
```

### Registry Pattern

Extensible registries allow adding custom transforms/checks:

```python
# ETL: Add custom transform
from gis_bootcamp.geospatial_etl import _TRANSFORMS

def my_transform(data, params):
    # Your logic
    return data

_TRANSFORMS["my_custom"] = my_transform

# QA: Add custom validation check
from gis_bootcamp.gis_data_quality import VECTOR_CHECKS

def my_check(data, params):
    # Your logic
    return CheckResult(passed=True, check_name="my_check", message="...")

VECTOR_CHECKS["my_check"] = my_check
```

### Pydantic Validation

REST APIs use Pydantic for strict input validation:
```python
from pydantic import BaseModel

class MyRequest(BaseModel):
    required_field: str
    optional_field: int = 10
    nested_object: dict

# Invalid requests return 422 Unprocessable Entity
```

---

## Performance Optimization Tips

### Vector Operations
- Use spatial indexing (STRtree) for large datasets
- Pre-filter with bounding boxes before spatial joins
- Dissolve features to reduce geometry count

### Raster Operations
- Use windowed I/O for large rasters (not in-memory)
- Convert to COG format for cloud-friendly access
- Use appropriate compression (LZW, ZSTD)

### Database Operations
- Use connection pooling
- Create spatial indexes on PostGIS tables
- Use parameterized queries

### General Tips
- Cache API results when possible
- Use appropriate data formats (GeoParquet for analytics)
- Partition large datasets by region/time
- Monitor memory usage for large files

---

## Error Handling & Troubleshooting

**CRS Mismatch**: All modules automatically reproject when needed

**Invalid Geometries**: Geometry Validation module repairs using `make_valid()`

**API Validation Errors**: Check request JSON schema in Swagger docs

**Memory Issues**: Use windowed I/O for large rasters

**Database Connection**: Check PostgreSQL connection string format

See individual module documentation for specific error handling strategies.
