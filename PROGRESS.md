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

### Day 4: Geometry Validation & Repair Tool ✓

**What it does:**
CLI tool that reads a vector dataset, detects invalid/empty/null geometries, attempts repairs using Shapely's `make_valid()`, and writes a cleaned dataset with detailed logs of all issues and fixes.

**Inputs:**
- Vector file with potentially invalid geometries
- Optional `--drop` flag to remove unfixable geometries

**Outputs:**
- Cleaned vector file
- Console report showing issues found and repair results

**Code:**
- `gis_bootcamp/geometry_validation.py` — main module
- `tests/test_geometry_validation.py` — full test suite (14 test cases)

**How to run:**

Repair and keep unfixable geometries (default):
```bash
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg
```

Repair and drop unfixable geometries:
```bash
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg --drop
```

Verbose output with row-by-row logs:
```bash
python -m gis_bootcamp.geometry_validation data/messy.gpkg -o output/cleaned.gpkg -v
```

Run tests:
```bash
python -m unittest tests.test_geometry_validation -v
```

**What's tested:**
- Valid geometry datasets (no issues)
- Invalid geometries (self-intersecting polygons, etc.)
- Null geometries (missing geometries)
- Empty geometries (empty polygon/linestring)
- Repair success (make_valid works)
- Drop unfixable flag behavior
- Keep unfixable default behavior
- Output file creation
- Output directory auto-creation
- Attribute preservation
- CRS preservation
- File not found error handling
- Empty dataset error handling
- Missing geometry column error handling

All 14 tests passing ✓

---

### Day 5: Vector Geoprocessing Tool ✓

**What it does:**
CLI tool that performs three explicit, deterministic geoprocessing operations: clip, buffer, and dissolve. Each operation logs feature counts and operation details.

**Operations:**

1. **Clip**: Clip features to a clipping geometry
   - Reduces feature count to only those within/intersecting clip boundary
   - Preserves all attributes

2. **Buffer**: Create buffer zones around geometries
   - Fixed distance in CRS units
   - Optional dissolve flag to merge all buffers into single polygon
   - Preserves attributes (or aggregates if dissolved)

3. **Dissolve**: Merge features based on attribute or all into one
   - By attribute: groups features and merges boundaries
   - Without attribute: merges all features into single polygon
   - Aggregates data using "first" function

**Code:**
- `gis_bootcamp/vector_geoprocessing.py` — main module (400+ lines)
- `tests/test_vector_geoprocessing.py` — full test suite (20+ test cases)

**How to run:**

Clip to geometry:
```bash
python -m gis_bootcamp.vector_geoprocessing clip input.gpkg clip.gpkg -o output/clipped.gpkg
```

Buffer 1000 units:
```bash
python -m gis_bootcamp.vector_geoprocessing buffer input.gpkg -d 1000 -o output/buffered.gpkg
```

Buffer with dissolve (merge all):
```bash
python -m gis_bootcamp.vector_geoprocessing buffer input.gpkg -d 500 -ds -o output/merged.gpkg
```

Dissolve by attribute:
```bash
python -m gis_bootcamp.vector_geoprocessing dissolve input.gpkg -by region -o output/by_region.gpkg
```

Dissolve all into one:
```bash
python -m gis_bootcamp.vector_geoprocessing dissolve input.gpkg -o output/merged.gpkg
```

Run tests:
```bash
python -m unittest tests.test_vector_geoprocessing -v
```

**What's tested:**
- Clip operation (reduces feature count, preserves attributes/CRS)
- Buffer operation with/without dissolve
- Dissolve by attribute and without (all to one)
- Feature count changes for each operation
- CRS and attribute preservation
- Invalid column error for dissolve
- File not found errors (clip input, clip geometry, buffer input, dissolve input)
- Empty dataset handling for all operations
- Output directory auto-creation

All 20 tests passing ✓

---
