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

### Day 2: Vector Reprojection Tool (next)

---
