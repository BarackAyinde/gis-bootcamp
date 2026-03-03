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

Run tests:
```bash
python -m pytest tests/ -v
```

Or with unittest:
```bash
python -m unittest discover tests

# Run specific test file
python -m unittest tests.test_geometry_inspector -v
python -m unittest tests.test_vector_reprojection -v
```
