# GIS Bootcamp

Production-grade GIS tools built incrementally. Week 1: Vector. Week 2: Raster.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
# Optional: add alias for easier CLI access
alias geometry_inspector="python -m gis_bootcamp.geometry_inspector"
```

## Week 1: Vector GIS

### Day 1: Geometry Inspector
CLI tool to inspect vector datasets (GeoPackage, Shapefile, GeoJSON).

```bash
python -m gis_bootcamp.geometry_inspector data/your_file.gpkg
```

Outputs:
- Feature count
- Geometry types and counts
- CRS
- Bounding box
- Attribute columns
- Null geometry count

### Day 2: Vector Reprojection Tool
CLI tool to reproject vector datasets to a target EPSG code.

```bash
python -m gis_bootcamp.vector_reprojection data/your_file.gpkg -t EPSG:3857 -o output/reprojected.gpkg
```

Requires:
- Input vector file with defined CRS
- Target EPSG code (e.g., EPSG:3857, EPSG:4269, EPSG:32633)

Preserves:
- All attributes
- Geometry types
- Feature count

Examples:
```bash
# WGS84 to Web Mercator
python -m gis_bootcamp.vector_reprojection data/roads.gpkg -t EPSG:3857 -o output/roads_web.gpkg

# WGS84 to UTM Zone 33N
python -m gis_bootcamp.vector_reprojection data/points.shp -t EPSG:32633 -o output/points_utm.shp

# Any CRS to NAD83
python -m gis_bootcamp.vector_reprojection data/parcels.geojson -t EPSG:4269 -o output/parcels_nad83.geojson
```

### Day 3: Spatial Join Engine
CLI tool to perform spatial joins between two vector datasets.

```bash
python -m gis_bootcamp.spatial_join left.gpkg right.gpkg -o output/joined.gpkg -p within
```

Features:
- Three spatial predicates: `intersects`, `within`, `contains`
- Four join types: `left`, `right`, `inner`, `outer`
- Automatic CRS alignment (right dataset reprojected to left if needed)
- Preserves all attributes from both datasets
- Logs feature counts before/after join

Examples:
```bash
# Point-in-polygon (cities within countries)
python -m gis_bootcamp.spatial_join \
  data/cities.gpkg data/countries.gpkg \
  -o output/cities_in_countries.gpkg -p within

# Find intersecting features (roads crossing streams)
python -m gis_bootcamp.spatial_join \
  data/roads.shp data/streams.shp \
  -o output/road_stream_intersections.gpkg

# Find containing features (districts containing points)
python -m gis_bootcamp.spatial_join \
  data/districts.gpkg data/points.geojson \
  -o output/points_by_district.gpkg -p contains -how inner

# Right join (keep all right features)
python -m gis_bootcamp.spatial_join \
  data/left.gpkg data/right.gpkg \
  -o output/result.gpkg -how right
```

### Day 4: Geometry Validation & Repair Tool
CLI tool to detect and repair invalid geometries in vector datasets.

```bash
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg
```

Features:
- Detects invalid, empty, and null geometries
- Repairs invalid geometries using Shapely's `make_valid()`
- Keeps or drops unfixable geometries via `--drop` flag
- Detailed logging of all issues by row
- Preserves all attributes and CRS

Examples:
```bash
# Repair and keep unfixable geometries (default)
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg

# Repair and drop unfixable geometries
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg --drop

# Verbose output with detailed row-by-row logs
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg -v
```

Run tests:
```bash
python -m unittest discover tests

# Run specific test file
python -m unittest tests.test_geometry_inspector -v
python -m unittest tests.test_vector_reprojection -v
python -m unittest tests.test_spatial_join -v
python -m unittest tests.test_geometry_validation -v
```
