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

Run tests:
```bash
python -m pytest tests/test_geometry_inspector.py -v
```

Or with unittest:
```bash
python -m unittest discover tests
```
