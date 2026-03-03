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

### Day 6: Vector ETL Pipeline ✓

**What it does:**
End-of-week composition project that chains all 5 Week 1 tools into a single production-grade vector ETL workflow.

**Pipeline stages:**
1. **Load and Inspect** - Load raw vector dataset, inspect metadata (CRS, geometry types, counts)
2. **Validate & Repair** - Detect and fix invalid geometries using Shapely validation
3. **Reproject** - Transform to target EPSG code, preserve all attributes
4. **Geoprocessing** (Optional) - Clip, Buffer, or Dissolve based on user input
5. **Write Output** - Save cleaned, production-ready dataset to GeoPackage

**Features:**
- Optional geoprocessing operation (none, clip, buffer, dissolve)
- Deterministic logging at each stage showing feature counts and operations
- Full error handling with validation of operation-specific parameters
- CRS transformation with attribute preservation
- Automatic output directory creation
- Verbose mode for debugging
- Summary output with stage results and statistics

**Code:**
- `gis_bootcamp/vector_etl_pipeline.py` — main ETL module (450+ lines)
- `tests/test_vector_etl_pipeline.py` — comprehensive test suite (19 tests)

**How to run:**

Reproject only (validate + reproject):
```bash
python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 -o output.gpkg
```

Full pipeline with clip:
```bash
python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 \
  -op clip -cp clip_geometry.gpkg -o output.gpkg
```

Full pipeline with dissolve by attribute:
```bash
python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 \
  -op dissolve -dby region -o output.gpkg
```

Full pipeline with buffer + dissolve:
```bash
python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 \
  -op buffer -dist 1000 -ds -o output.gpkg
```

Verbose output:
```bash
python -m gis_bootcamp.vector_etl_pipeline input.shp -e 3857 -o output.gpkg -v
```

Run tests:
```bash
python -m unittest tests.test_vector_etl_pipeline -v
```

**What's tested:**
- ETL with no geoprocessing (validate → reproject → output)
- ETL with clip operation (reduces feature count)
- ETL with buffer operation (with and without dissolve)
- ETL with dissolve operation (by attribute and all-to-one)
- CRS transformation (4326→3857, 4326→32633)
- Attribute preservation through all stages
- Output directory auto-creation
- Feature count tracking across stages
- Error handling (missing files, invalid parameters, invalid columns)
- ETL summary structure and completeness
- Complex multi-stage workflows

All 19 tests passing ✓

**Real-world data validation (Natural Earth countries, 258 countries):**
- ✓ Validate → Reproject (4326→3857) → Dissolve by continent: 258 → 8 features
- ✓ Validate → Reproject → Clip to Europe: 258 → 61 countries  
- ✓ Validate → Reproject (4326→32633 UTM): 258 → 258 countries
- ✓ All 19 unit tests passing
- ✓ Full pipeline execution with all stage logging

---

## Week 1 Summary

**Complete vector GIS toolset built and tested:**

| Day | Tool | Purpose | Tests | Real-data |
|-----|------|---------|-------|-----------|
| 1 | Geometry Inspector | Inspect dataset metadata | 9 ✓ | 258 countries ✓ |
| 2 | Vector Reprojection | Reproject to target EPSG | 10 ✓ | 4326→3857 ✓ |
| 3 | Spatial Join | Join with spatial predicates | 15 ✓ | Point-in-polygon ✓ |
| 4 | Geometry Validation | Detect & repair invalid geoms | 14 ✓ | 2 invalid→repaired ✓ |
| 5 | Vector Geoprocessing | Clip, Buffer, Dissolve ops | 21 ✓ | Europe clip, continent dissolve ✓ |
| 6 | Vector ETL Pipeline | Compose all 5 tools | 19 ✓ | 3-stage workflows ✓ |

**Total: 98 unit tests, all passing ✓**

**Production-ready features:**
- Comprehensive error handling and validation
- Detailed logging with operation tracking
- CRS handling and attribute preservation
- Real-world data tested on Natural Earth dataset (258 countries)
- CLI entry points for all tools
- Full unittest coverage

---

## Week 2: Raster GIS

### Day 1: Raster Metadata Inspector ✓

**What it does:**
CLI tool that reads a raster file and prints metadata without loading full pixel data into memory.

**Outputs:**
- CRS
- Resolution (pixel size)
- Bounds (geographic extent)
- Number of bands
- Data type per band
- Nodata value
- Raster dimensions (width, height)
- Affine transform details
- Driver and compression info

**Code:**
- `gis_bootcamp/raster_metadata_inspector.py` — main module, CLI entry point
- `tests/test_raster_metadata_inspector.py` — full test suite

**How to run:**

Inspect a raster dataset (pretty-printed):
```bash
raster_metadata_inspector data/dem.tif
raster_metadata_inspector data/ortho.tif --verbose
```

Inspect and output JSON:
```bash
raster_metadata_inspector data/dem.tif --json
```

Run tests:
```bash
python -m unittest tests.test_raster_metadata_inspector -v
```

**What's tested:**
- Single-band raster inspection (WGS84)
- Multi-band raster inspection (RGB)
- Metadata structure and completeness
- Bounds handling and structure
- Band details extraction
- Nodata value capture
- Pixel size calculations
- CRS handling (EPSG:4326, EPSG:3857, UTM)
- Transform matrix extraction
- Driver identification
- JSON serialization
- File not found error handling
- Invalid raster file error handling
- Consistency across multiple inspections

All 14 tests passing ✓

**Key design:**
- Uses rasterio to read only metadata (no pixel I/O)
- Supports formatted text output or JSON
- Handles all raster types (GeoTIFF, COG, etc.)
- Proper logging and error messages
- No full raster data in memory

---

### Day 2: Raster Clipper ✓

**What it does:**
CLI tool that clips a raster using either a bounding box or vector mask geometry. Handles CRS alignment with auto-reprojection and preserves nodata values.

**Inputs:**
- Raster file (GeoTIFF, COG, etc.)
- Clipping method: either bounding box (minx, miny, maxx, maxy) or vector mask (GeoPackage, Shapefile, GeoJSON)
- Output path

**Outputs:**
- Clipped raster file with proper geospatial metadata
- Clipping report with dimensions, bounds, CRS, nodata info

**Code:**
- `gis_bootcamp/raster_clipper.py` — main module, CLI entry point
- `tests/test_raster_clipper.py` — full test suite

**How to run:**

Clip with bounding box:
```bash
raster_clipper data/dem.tif -bbox -180 0 0 45 -o output/clipped.tif
raster_clipper data/ortho.tif -bbox -10 -10 10 10 -o output/subset.tif -v
```

Clip with vector mask:
```bash
raster_clipper data/dem.tif -mask polygon.gpkg -o output/clipped.tif
raster_clipper data/dem.tif -mask countries.shp -o output/clipped.tif
```

Run tests:
```bash
python -m unittest tests.test_raster_clipper -v
```

**What's tested:**
- Clipping with bounding box (valid bbox, dimensions reduction)
- Clipping with vector mask (single/multi-feature masks)
- CRS alignment (auto-reprojection of mask to raster CRS)
- Output file creation and directory auto-creation
- Nodata value preservation in clipped output
- CRS preservation in clipped output
- Bounds calculation and validity
- Error handling:
  - Missing raster file
  - Missing mask file
  - Invalid bounding box coordinates (minx >= maxx, etc.)
  - Bounding box with no overlap
  - Empty mask (no features)
- Result dictionary structure validation
- Multiple clipping operations on same file

All 16 tests passing ✓

**Real-world test:** ✓ Clipped 256×256 raster to half height (256×128) using bbox -180 0 0 45, verified output with metadata inspector.

**Key design:**
- Windowed reads for efficient clipping (avoids loading full raster)
- rasterio.mask for polygon masking with automatic crop
- CRS mismatch detection and auto-reprojection via GeoPandas
- Proper transform and metadata preservation
- Nodata values carried through clipping operation

---

### Day 3: GeoTIFF → Cloud Optimized GeoTIFF (COG) ✓

**What it does:**
CLI tool that converts standard GeoTIFF to Cloud Optimized GeoTIFF (COG) format with internal overviews and tiling for efficient cloud-based access. Includes COG validation.

**Inputs:**
- GeoTIFF file
- Output path
- Optional: block size (default 512)
- Optional: create and validate modes

**Outputs:**
- Cloud Optimized GeoTIFF with:
  - Tiling (512x512 or custom blocks)
  - Internal overviews (multi-scale levels)
  - LZW compression
  - Proper GeoTIFF structure

**Code:**
- `gis_bootcamp/geotiff_to_cog.py` — main module, CLI entry point
- `tests/test_geotiff_to_cog.py` — full test suite

**How to run:**

Create COG:
```bash
geotiff_to_cog input.tif -o output_cog.tif
geotiff_to_cog input.tif -o output_cog.tif -b 256
geotiff_to_cog input.tif -o output_cog.tif -b 512 -v
```

Validate existing raster for COG compliance:
```bash
geotiff_to_cog raster.tif --validate
```

Create and validate output:
```bash
geotiff_to_cog input.tif -o output_cog.tif --validate-output
```

Run tests:
```bash
python -m unittest tests.test_geotiff_to_cog -v
```

**What's tested:**
- COG creation on large rasters (1024×1024, 4096×4096)
- COG creation on small rasters (256×256)
- COG creation on non-square rasters
- Custom block sizes
- Overview level auto-computation
- Output file creation and directory auto-creation
- Metadata preservation (CRS, dtype, dimensions)
- Compression application
- COG validation (compliant rasters, non-compliant rasters)
- Result dictionary structure
- Error handling (missing input files)
- Multiple COG creations from same input

All 18 tests passing ✓

**Real-world test:** ✓ Converted 256×256 test_dem.tif to COG, validated as COG-compliant with tiling, overviews, and LZW compression.

**Key design:**
- Auto-computed overview levels based on raster size
- Tiling enabled with configurable block size
- LZW compression for cloud efficiency
- Validation checks: tiling, block size, overviews, compression
- COG-compliant metadata structure

---

### Day 4: Raster Mosaic Tool ✓

**What it does:**
CLI tool that accepts multiple raster inputs, reprojects any with mismatched CRS on-the-fly, mosaics them into a single output raster, and writes the result with nodata and metadata preserved.

**Inputs:**
- Two or more raster file paths (GeoTIFF, COG, etc.)
- Output raster path
- Optional target CRS (defaults to first raster's CRS)

**Outputs:**
- Single mosaicked GeoTIFF with correct CRS, dimensions, and nodata

**Code:**
- `gis_bootcamp/raster_mosaic.py` — main module, CLI entry point
- `tests/test_raster_mosaic.py` — full test suite (14 test cases)

**How to run:**

Mosaic two adjacent tiles:
```bash
python -m gis_bootcamp.raster_mosaic tile_west.tif tile_east.tif -o output/mosaic.tif
```

Mosaic with explicit target CRS:
```bash
python -m gis_bootcamp.raster_mosaic *.tif -o output/mosaic.tif -crs EPSG:3857
```

Verbose output:
```bash
python -m gis_bootcamp.raster_mosaic a.tif b.tif c.tif -o output/mosaic.tif -v
```

Run tests:
```bash
python -m unittest tests.test_raster_mosaic -v
```

**What's tested:**
- Two adjacent tiles produce a wider mosaic
- Single raster passthrough (correct dimensions)
- Output CRS defaults to first raster CRS
- Mismatched CRS auto-reprojected via WarpedVRT
- User-specified target CRS applied
- Output directory auto-creation (nested)
- Nodata value preserved in output file
- Multi-band rasters (3-band) mosaicked correctly
- Overlapping rasters merged without error
- Result dict structure completeness
- Three-tile full-globe mosaic
- Empty input list raises ValueError
- Missing input file raises FileNotFoundError
- Raster without CRS raises ValueError

All 14 tests passing ✓

**Key design:**
- WarpedVRT for on-the-fly CRS reprojection (no temp files written)
- `rasterio.merge.merge()` with nodata propagation
- First-wins merge strategy for overlapping pixels
- Nodata and metadata carried from first input raster
- Output directory auto-created

---

### Day 5: Vector → GeoParquet Converter ✓

**What it does:**
CLI tool that loads a vector dataset, validates CRS and geometry presence, and writes a GeoParquet file using GeoPandas + pyarrow. All attributes, geometry, and spatial metadata are preserved.

**Inputs:**
- Vector file (GeoPackage, Shapefile, GeoJSON)
- Output `.parquet` path
- Optional `--layer` for multi-layer sources

**Outputs:**
- GeoParquet file with preserved CRS, geometry, and attributes

**Code:**
- `gis_bootcamp/vector_to_geoparquet.py` — main module, CLI entry point
- `tests/test_vector_to_geoparquet.py` — full test suite (15 test cases)

**How to run:**

Convert a GeoPackage:
```bash
python -m gis_bootcamp.vector_to_geoparquet data/countries.gpkg -o output/countries.parquet
```

Convert with explicit layer:
```bash
python -m gis_bootcamp.vector_to_geoparquet data/multi.gpkg -l roads -o output/roads.parquet
```

Verbose output:
```bash
python -m gis_bootcamp.vector_to_geoparquet data/points.geojson -o output/points.parquet -v
```

Run tests:
```bash
python -m unittest tests.test_vector_to_geoparquet -v
```

**What's tested:**
- Point, polygon, and linestring conversion
- CRS preserved and readable via round-trip read
- All attribute columns preserved after round-trip
- Feature count preserved (10 features in → 10 out)
- Geometry types reported in result dict
- Output directory auto-creation (nested)
- Result dict structure completeness
- File size is non-zero
- Non-WGS84 CRS (EPSG:3857) preserved correctly
- Round-trip geometry coordinates intact
- Missing input raises FileNotFoundError
- Missing CRS raises ValueError
- Empty dataset raises ValueError (via empty GeoJSON)
- Polygon and LineString geometry types
- `output_path` in result matches argument

All 15 tests passing ✓

**Key design:**
- `gdf.to_parquet(engine="pyarrow")` — standard GeoParquet writer
- CRS validated before write (fail-fast, not silent)
- Geometry types logged via `geom_type.value_counts()`
- Output directory auto-created
- `pyarrow>=14.0.0` added to project dependencies

---

### Day 6: Raster Processing Pipeline ✓

**What it does:**
End-of-week composition project that chains all 4 Week 2 raster tools into a single production-grade pipeline: inspect → mosaic → clip (optional) → COG → metadata JSON.

**Pipeline stages:**
1. **Inspect** — Extract and log metadata for each input raster
2. **Mosaic** — Merge all inputs into `mosaic.tif` (with optional CRS reprojection)
3. **Clip** (optional) — Clip mosaic to AOI via bbox or vector mask → `clipped.tif`
4. **COG** — Convert to Cloud Optimized GeoTIFF → `output.cog.tif`
5. **Metadata JSON** — Write structured pipeline summary → `metadata.json`

**Inputs:**
- One or more raster file paths
- Output directory
- Optional: `-bbox minx miny maxx maxy` or `-mask vector.gpkg`
- Optional: `-crs EPSG:XXXX`, `-b block_size`

**Outputs:**
- `output.cog.tif` — final COG raster
- `metadata.json` — pipeline summary (stages, dimensions, CRS, timestamps)

**Code:**
- `gis_bootcamp/raster_pipeline.py` — main pipeline module, CLI entry point
- `tests/test_raster_pipeline.py` — full test suite (18 test cases)

**How to run:**

Inspect + mosaic + COG (no clip):
```bash
python -m gis_bootcamp.raster_pipeline tile1.tif tile2.tif -o output/pipeline/
```

Full pipeline with bbox clip:
```bash
python -m gis_bootcamp.raster_pipeline dem.tif -o output/pipeline/ -bbox -10 45 30 75
```

Full pipeline with vector mask:
```bash
python -m gis_bootcamp.raster_pipeline dem.tif -o output/pipeline/ -mask aoi.gpkg
```

Custom CRS and block size:
```bash
python -m gis_bootcamp.raster_pipeline *.tif -o output/pipeline/ -crs EPSG:3857 -b 256
```

Run tests:
```bash
python -m unittest tests.test_raster_pipeline -v
```

**What's tested:**
- Single input, no clip (passthrough mosaic → COG)
- Two inputs mosaicked then COG'd
- Full pipeline with bbox clip (clip stage completed)
- Full pipeline with vector mask clip
- COG file exists at expected path in output dir
- Metadata JSON exists at expected path in output dir
- Metadata JSON top-level structure (11 required keys)
- Metadata JSON stages structure (inspect/mosaic/clip/cog)
- Clip stage marked "skipped" when no AOI provided
- Clip stage marked "completed" + method="bbox" when bbox provided
- 1024×1024 raster produces COG-valid output (overviews built)
- Result dict structure (5 required keys)
- Output directory auto-creation (nested)
- mosaic.tif intermediate file present in output dir
- input_count matches both result dict and metadata.json
- Empty input list raises ValueError
- Missing input raises FileNotFoundError
- Both bbox and mask_path raises ValueError

All 18 tests passing ✓

**Key design:**
- Imports core functions from all Week 2 tools (no reimplementation)
- Clip step is optional — pipeline degrades gracefully to mosaic → COG if no AOI
- `metadata.json` is always written last (pipeline summary, not log)
- COG validity checked with `validate_cog()` and recorded in metadata
- 1024×1024 test rasters used to ensure overviews are generated and COG is valid

---

## Week 2 Summary

**Complete raster GIS toolset built and tested:**

| Day | Tool | Purpose | Tests |
|-----|------|---------|-------|
| 1 | Raster Metadata Inspector | Inspect raster without loading pixels | 14 ✓ |
| 2 | Raster Clipper | Clip by bbox or vector mask | 16 ✓ |
| 3 | GeoTIFF → COG | Convert with tiling, overviews, compression | 18 ✓ |
| 4 | Raster Mosaic | Merge N rasters with CRS reprojection | 14 ✓ |
| 5 | Vector → GeoParquet | Convert vector to big-data format | 15 ✓ |
| 6 | Raster Pipeline | Compose all raster tools | 18 ✓ |

**Total Week 2: 95 unit tests, all passing ✓**
**Grand total Weeks 1+2: 193 unit tests, all passing ✓**

---

## Week 3: Spatial Analysis

### Day 1: Batch Geocoder ✓

**What it does:**
CLI tool that reads a CSV of addresses, geocodes each row via Nominatim (OpenStreetMap), handles rate limiting, retries, and failures gracefully, and writes a geospatial point dataset with status columns.

**Inputs:**
- CSV file with an address column (configurable name, default `address`)
- Output path (GPKG or GeoParquet)
- Optional: `--user-agent`, `--delay`, `--retries`, `--format`

**Outputs:**
- Point dataset with original columns plus: `latitude`, `longitude`, `geocode_matched_address`, `geocode_status`
- `geocode_status` values: `success`, `not_found`, `error`, `skipped`

**Code:**
- `gis_bootcamp/batch_geocoder.py` — main module, CLI entry point
- `tests/test_batch_geocoder.py` — full test suite (16 test cases, all mocked)

**How to run:**

Geocode a CSV:
```bash
python -m gis_bootcamp.batch_geocoder addresses.csv -o output/geocoded.gpkg
```

Custom column, parquet output:
```bash
python -m gis_bootcamp.batch_geocoder data.csv -col location -o output/geocoded.parquet -f parquet
```

Run tests (no real HTTP calls):
```bash
python -m unittest tests.test_batch_geocoder -v
```

**What's tested:**
- All rows succeed → GPKG output with correct counts
- GeoParquet output format (round-trip read)
- Point geometries have correct lat/lon for successful rows
- Original CSV attributes preserved in output
- `geocode_status` and `geocode_matched_address` columns added
- Not-found rows get null geometry and `not_found` status
- Empty/NaN address rows counted as `skipped`, not errored
- Transient errors caught, logged, counted without crashing pipeline
- Output directory auto-creation (nested)
- Result dict structure (6 required keys)
- Custom `address_column` name respected
- Output CRS is EPSG:4326
- Mixed success/not_found/error counts all correct
- Missing input raises FileNotFoundError
- Empty CSV raises ValueError
- Missing address column raises ValueError

All 16 tests passing ✓ (all mocked — no real HTTP)

**Key design:**
- `_geocoder` injectable parameter for testing (bypasses real Nominatim)
- `geopy.extra.rate_limiter.RateLimiter` enforces OSM's 1 req/sec limit
- Per-row retry with exponential back-off (1s, 2s, ... between attempts)
- `geocode_status` column makes success/failure queryable in downstream tools
- `geopy>=2.4.0` added to project dependencies

---

### Day 2: Reverse Geocoder / Nearest-Feature Lookup ✓

**What it does:**
CLI tool that loads a point dataset and a reference dataset, enriches each point with attributes from the spatially matching or nearest reference feature, and logs match rates and unmatched counts.

**Inputs:**
- Point dataset (GPKG, Shapefile, GeoJSON)
- Reference dataset (polygons, points, or lines)
- Join mode: `nearest`, `within`, or `contains`
- Output path

**Outputs:**
- Enriched point dataset with reference attributes and `match_status` column

**Code:**
- `gis_bootcamp/nearest_feature_lookup.py` — main module, CLI entry point
- `tests/test_nearest_feature_lookup.py` — full test suite (19 test cases)

**How to run:**

Nearest feature (always matches):
```bash
python -m gis_bootcamp.nearest_feature_lookup points.gpkg reference.gpkg -o output/enriched.gpkg
```

Point-in-polygon:
```bash
python -m gis_bootcamp.nearest_feature_lookup points.gpkg polygons.gpkg -o output/enriched.gpkg -m within
```

Run tests:
```bash
python -m unittest tests.test_nearest_feature_lookup -v
```

**What's tested:**
- nearest: all points matched (matched=N, unmatched=0)
- nearest: reference attributes present in output
- nearest: `match_distance` column added
- nearest: works with point reference (not just polygons)
- within: correct matched/unmatched split (2 inside, 1 outside)
- within: match_rate calculated correctly (50.0%)
- within: `match_status` column present with correct values
- within: matched rows have reference attributes, unmatched have NaN
- CRS mismatch auto-reprojected (reference → points CRS)
- Output CRS matches points CRS
- Original point attributes preserved
- Output directory auto-creation (nested)
- Result dict structure (5 required keys)
- Feature count preserved (one row per input point)
- Invalid mode raises ValueError
- Missing points file raises FileNotFoundError
- Missing reference file raises FileNotFoundError
- Empty points dataset raises ValueError
- Points without CRS raises ValueError

All 19 tests passing ✓

**Key design:**
- `sjoin_nearest()` for nearest mode (STRtree spatial index, always matches)
- `sjoin(predicate=...)` for within/contains (left join, unmatched rows preserved)
- Deduplication after join (one output row per input point)
- CRS alignment via `to_crs()` before join
- `match_status` column: `matched` or `unmatched`
- `match_distance` column added only for nearest mode (in CRS units)
- Note: for accurate `match_distance`, reproject to a projected CRS first

---

### Day 3: Routing Distance Client ✓

**What it does:**
CLI tool that reads a CSV of origin/destination coordinate pairs, queries the OSRM Route API for each pair, and writes structured output with distance and duration columns.

**Inputs:**
- CSV with `origin_lat`, `origin_lon`, `dest_lat`, `dest_lon` columns (configurable names)
- OSRM-compatible endpoint URL (default: public `router.project-osrm.org`)
- Output path (CSV or JSON)

**Outputs:**
- All input columns plus: `distance_m`, `distance_km`, `duration_s`, `duration_min`, `routing_status`
- `routing_status` values: `success`, `no_route`, `error`, `skipped`

**Code:**
- `gis_bootcamp/routing_distance_client.py` — main module, CLI entry point
- `tests/test_routing_distance_client.py` — full test suite (17 test cases, all mocked)

**How to run:**

Route a CSV of OD pairs:
```bash
python -m gis_bootcamp.routing_distance_client od_pairs.csv -o output/routes.csv
```

Custom endpoint and column names:
```bash
python -m gis_bootcamp.routing_distance_client od.csv -o out.csv \
  -e http://localhost:5000 --origin-lat from_lat --origin-lon from_lon \
  --dest-lat to_lat --dest-lon to_lon
```

JSON output:
```bash
python -m gis_bootcamp.routing_distance_client od.csv -o output/routes.json -f json
```

Run tests (no real HTTP calls):
```bash
python -m unittest tests.test_routing_distance_client -v
```

**What's tested:**
- All rows succeed → CSV with correct counts
- `distance_m/km` and `duration_s/min` computed correctly (10km, 12min)
- `routing_status=success` for successful rows
- `no_route` response counted and status set correctly
- Timeout counted as `error`
- ConnectionError counted as `error`
- Missing coordinates skipped (NaN in any coord column)
- Original columns (e.g. `trip_id`) preserved in output
- JSON output format: parseable with expected fields
- Output directory auto-creation (nested)
- Result dict structure (6 required keys)
- Custom column names respected
- Mixed statuses (success/no_route/error/skipped) all counted correctly
- Feature count in output matches input row count
- Missing input raises FileNotFoundError
- Empty CSV raises ValueError
- Missing coordinate columns raises ValueError

All 17 tests passing ✓ (all mocked — no real routing service)

**Key design:**
- `_session` injectable parameter bypasses real HTTP for testing
- OSRM URL: `{endpoint}/route/v1/driving/{olon},{olat};{dlon},{dlat}?overview=false`
- NaN coordinate rows skipped before HTTP call
- Per-row error isolation: one failure never stops the pipeline
- `requests>=2.31.0` added to project dependencies

### Day 4: Hotspot / Density Analysis ✓

**What it does:**
Computes point density using two output modes:
- **raster**: Kernel Density Estimation (KDE) via `scipy.stats.gaussian_kde`, written as a float32 GeoTIFF
- **vector**: Regular fishnet grid with per-cell point counts, written as GeoPackage

**Outputs (raster mode):**
- Single-band float32 GeoTIFF, CRS-aligned to input, density values ≥ 0
- Auto-computed or user-specified KDE bandwidth (Scott's rule default)

**Outputs (vector mode):**
- GeoPackage with square grid cells, each with `point_count` column
- All cells present; zero-count cells retained

**Result dict keys:** `output_path`, `output_type`, `point_count`, `crs`, `cell_size`, `bandwidth`, `grid_width`, `grid_height`, `total_cells`, `hotspot_cells`

**Code:**
- `gis_bootcamp/density_analysis.py` — main module, CLI entry point
- `tests/test_density_analysis.py` — full test suite (23 test cases)

**How to run:**
```bash
# KDE raster
python -m gis_bootcamp.density_analysis points.gpkg -o output/kde.tif -c 50

# Vector fishnet count grid
python -m gis_bootcamp.density_analysis points.gpkg -o output/grid.gpkg -c 100 -t vector

# KDE with explicit bandwidth
python -m gis_bootcamp.density_analysis points.gpkg -o output/kde_bw.tif -c 50 -bw 200

# Run tests
python -m unittest tests.test_density_analysis -v
```

**Key design notes:**
- KDE grid: x increases left→right, y decreases top→bottom (rasterio convention) — `yi = np.arange(ymax, ymin, -cell_size)`
- `from_origin(west, north, xsize, ysize)` sets the raster geotransform correctly
- Vector counting uses numpy floor-division binning (not sjoin) to handle boundary points deterministically
- `bandwidth` param is in CRS units; converted to KDE `bw_method` (scale factor of std-dev) internally
- `scipy>=1.11.0` added to project dependencies

All 23 tests passing ✓

### Day 5: Static Cartographic Map Renderer ✓

**What it does:**
Renders one or more vector layers to a static map image using GeoPandas + matplotlib.
Supports polygons, lines, and points in the same map. All layers are reprojected to
a common CRS before rendering.

**Outputs:**
- PNG, SVG, PDF, or JPG image
- Configurable size (figsize), resolution (DPI), title, and per-layer styling
- Optional legend when layer dicts include a `"label"` key

**Layer dict keys:** `path` (required), `color`, `edge_color`, `alpha`, `linewidth`, `markersize`, `label`, `zorder`

**Result dict keys:** `output_path`, `output_format`, `layer_count`, `feature_count`, `crs`, `bbox`, `figsize`, `dpi`

**Code:**
- `gis_bootcamp/map_renderer.py` — main module, CLI entry point
- `tests/test_map_renderer.py` — full test suite (26 test cases)

**How to run:**
```bash
# Single layer
python -m gis_bootcamp.map_renderer data/countries.gpkg -o output/map.png --title "World Map"

# Multiple layers with colours
python -m gis_bootcamp.map_renderer data/regions.gpkg data/cities.gpkg \
    -o output/map.png --title "Regions and Cities" --dpi 300

# Custom figure size
python -m gis_bootcamp.map_renderer data/layer.gpkg -o output/map.svg --figsize 12 8

# Per-layer styles from JSON file
python -m gis_bootcamp.map_renderer data/l1.gpkg data/l2.gpkg \
    -o output/map.png --styles styles.json

# Run tests
python -m unittest tests.test_map_renderer -v
```

**Key design notes:**
- `matplotlib.use("Agg")` set at module load — non-interactive; safe for headless/server environments
- All layers reprojected to first layer's CRS unless `--crs` / `target_crs` is specified
- `pyproj.CRS.from_user_input()` used for CRS parsing (not `gpd.CRS` which doesn't exist)
- `plt.close(fig)` called after save to prevent memory leaks in batch usage
- `matplotlib>=3.7.0` added to project dependencies

All 26 tests passing ✓

### Day 6: Spatial Data Enrichment Pipeline ✓

**What it does:**
Composes all Week 3 tools into a single configurable pipeline:

| Stage | Tool | Triggered by |
|-------|------|--------------|
| 1 — Geocode | `batch_geocoder` | `geocode_column` parameter |
| 2 — Nearest-feature | `nearest_feature_lookup` | `reference_path` parameter |
| 3 — Density analysis | `density_analysis` | `density_cell_size` parameter |
| 4 — Render map | `map_renderer` | `render=True` parameter |

At least one stage must be configured. Stages share an output directory.
After geocoding, only successfully geocoded rows pass to downstream stages.

**Outputs (all written to `output_dir/`):**
- `geocoded.gpkg` — all geocoded rows (Stage 1)
- `points.gpkg` — success-only points from geocoding
- `enriched.gpkg` — points with reference attributes (Stage 2)
- `density.tif` or `density.gpkg` — hotspot analysis (Stage 3)
- `map.png` — rendered map (Stage 4)

**Result dict keys:** `output_dir`, `stages_run`, `enriched_path`, `point_count`, `geocode_stats`, `lookup_stats`, `density_stats`, `map_path`

**Code:**
- `gis_bootcamp/enrichment_pipeline.py` — main module, CLI entry point
- `tests/test_enrichment_pipeline.py` — full test suite (21 test cases)

**How to run:**
```bash
# Geocode addresses then enrich with reference polygons
python -m gis_bootcamp.enrichment_pipeline addresses.csv \
    -o output/enriched \
    --geocode-col address \
    --reference data/regions.gpkg \
    --render --map-title "Enriched Points"

# Existing points: nearest-feature lookup + density grid + map
python -m gis_bootcamp.enrichment_pipeline data/points.gpkg \
    -o output/enriched \
    --reference data/zones.gpkg \
    --density-cell-size 100 --density-type vector \
    --render

# Run tests
python -m unittest tests.test_enrichment_pipeline -v
```

**Key design notes:**
- Each stage is optional; pipeline raises ValueError if none are configured
- Geocode stage filters to `geocode_status == "success"` before downstream stages
- KDE density fails with collinear/identical points → use `--density-type vector` when geocoder mock returns fixed coords or with small synthetic test datasets
- `_geocoder` injectable bypasses real Nominatim HTTP in tests
- All four Week 3 tools imported and composed with no code duplication

All 21 tests passing ✓

## Week 4: Production Services

### Day 1: FastAPI Spatial Service ✓

**What it does:**
HTTP API exposing all GIS bootcamp tools as JSON endpoints. No file uploads —
all inputs/outputs are server-side paths. Geocoder dependency is injectable
for clean test isolation.

**Endpoints:**

| Method | Path | Tool wrapped | Notes |
|--------|------|-------------|-------|
| `GET` | `/health` | — | Liveness check |
| `POST` | `/geocode` | `batch_geocoder` | Nominatim injectable via FastAPI dep |
| `POST` | `/nearest-feature` | `nearest_feature_lookup` | Spatial attribute join |
| `POST` | `/density` | `density_analysis` | KDE raster or vector count grid |
| `POST` | `/render` | `map_renderer` | Static PNG/SVG/PDF map |
| `POST` | `/pipeline` | `enrichment_pipeline` | Full multi-stage pipeline |

**Error handling:**
- `FileNotFoundError` → HTTP 404
- `ValueError` → HTTP 400
- Pydantic validation errors → HTTP 422 (FastAPI default)

**Code:**
- `gis_bootcamp/spatial_api.py` — FastAPI app, Pydantic models, CLI entry point
- `tests/test_spatial_api.py` — full test suite (22 test cases, TestClient)

**How to run:**
```bash
# Start the server
python -m gis_bootcamp.spatial_api --port 8000

# Or with auto-reload for development
python -m gis_bootcamp.spatial_api --port 8000 --reload

# Example requests
curl http://localhost:8000/health
curl -X POST http://localhost:8000/nearest-feature \
  -H "Content-Type: application/json" \
  -d '{"points_path": "data/pts.gpkg", "reference_path": "data/ref.gpkg", "output_path": "output/enriched.gpkg"}'

# Run tests
python -m unittest tests.test_spatial_api -v
```

**Key design notes:**
- FastAPI dependency injection used for geocoder (`_default_geocoder`) — override in tests with `app.dependency_overrides`
- `render_map` returns tuples for `bbox`/`figsize`; route converts to lists for JSON
- TestClient (httpx-backed) used in unittest with class-level `setUpClass`
- `fastapi>=0.104.0`, `uvicorn>=0.24.0` added to project dependencies
- `httpx>=0.24.0` added to dev dependencies (TestClient backend)

All 22 tests passing ✓
