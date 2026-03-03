# GIS Bootcamp

## Week 1: Vector GIS

### Day 1: Geometry Inspector ✓

**What it does:**
CLI tool that reads a vector file and prints geometry metadata.

**Outputs:**
- Feature count
- Geometry types + counts
- CRS
- Bounding box (minx, miny, maxx, maxy)
- All attribute columns
- Null geometry count

**Code:**
- `src/geometry_inspector.py` — main module, CLI entry point
- `tests/test_geometry_inspector.py` — full test suite

**How to run:**

Setup:
```bash
cd gis-bootcamp
python -m venv venv
source venv/bin/activate
pip install -e .
```

Inspect a dataset:
```bash
geometry_inspector data/your_file.gpkg
geometry_inspector data/roads.shp
geometry_inspector data/points.geojson
```

Run tests:
```bash
python -m unittest discover tests
```

**What's tested:**
- Point, polygon, mixed geometries
- CRS present and absent
- Bounding box calculation
- File not found error handling
- Empty dataset error handling
- Missing geometry column error handling
- All attributes captured

---

### Day 2: Vector Reprojection Tool ✓

**What it does:**
CLI tool that reads a vector file, validates it has a CRS, reprojects to a target EPSG code, and writes the output with all attributes preserved.

**Inputs:**
- Vector file (GeoPackage, Shapefile, GeoJSON)
- Target EPSG code (e.g., EPSG:3857, EPSG:4269)
- Output path

**Outputs:**
- Reprojected vector file (same format as input)
- Console report showing source/target CRS, feature count, geometry types

**Code:**
- `gis_bootcamp/vector_reprojection.py` — main module
- `tests/test_vector_reprojection.py` — full test suite (9 test cases)

**How to run:**

Reproject WGS84 to Web Mercator:
```bash
python -m gis_bootcamp.vector_reprojection data/roads.gpkg -t EPSG:3857 -o output/roads_3857.gpkg
```

Reproject to UTM:
```bash
python -m gis_bootcamp.vector_reprojection data/points.shp -t EPSG:32633 -o output/points_utm.shp
```

Run tests:
```bash
python -m unittest tests.test_vector_reprojection -v
```

**What's tested:**
- Successful reprojection (WGS84 → Web Mercator, UTM)
- Attribute preservation (all columns intact)
- Geometry type preservation
- Feature count preservation
- CRS validation (missing CRS error handling)
- EPSG format validation
- File not found error handling
- Empty dataset error handling
- Output directory auto-creation

All 9 tests passing ✓

---
