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

### Day 3: Spatial Join Engine ✓

**What it does:**
CLI tool that reads two vector datasets, ensures they share a CRS (reprojecting if needed), performs a spatial join with a specified predicate, and writes the result with all attributes from both datasets.

**Inputs:**
- Left dataset (base, keep all rows in left join)
- Right dataset (join target)
- Spatial predicate: `intersects`, `within`, `contains`
- Join type: `left`, `right`, `inner`, `outer`

**Outputs:**
- Joined vector file with combined attributes
- Console report showing feature counts before/after, predicates, CRS info

**Code:**
- `gis_bootcamp/spatial_join.py` — main module
- `tests/test_spatial_join.py` — full test suite (14 test cases)

**How to run:**

Point-in-polygon (cities within countries):
```bash
python -m gis_bootcamp.spatial_join \
  data/cities.gpkg data/countries.gpkg \
  -o output/cities_in_countries.gpkg -p within
```

Intersecting features (roads crossing streams):
```bash
python -m gis_bootcamp.spatial_join \
  data/roads.shp data/streams.shp \
  -o output/road_stream_intersections.gpkg
```

Inner join (only matching features):
```bash
python -m gis_bootcamp.spatial_join \
  data/left.gpkg data/right.gpkg \
  -o output/result.gpkg -p contains -how inner
```

Run tests:
```bash
python -m unittest tests.test_spatial_join -v
```

**What's tested:**
- All three predicates: intersects, within, contains
- All four join types: left, right, inner, outer
- CRS mismatch handling (auto-reproject right to left)
- Attribute preservation from both datasets
- File not found errors (left and right)
- Invalid predicate error
- Empty dataset handling (left and right)
- Missing CRS handling (left and right)
- Output directory auto-creation

All 14 tests passing ✓

---
