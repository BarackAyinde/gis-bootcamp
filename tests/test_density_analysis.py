"""
Tests for density_analysis.py

Uses synthetic point datasets written to temp GeoPackages.
No external data required.
"""

import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import Point

from gis_bootcamp.density_analysis import analyze_density

CRS = "EPSG:3857"   # projected CRS for realistic cell_size values (metres)
CRS_GEO = "EPSG:4326"


def _write_points(path: str, coords: list[tuple], crs: str = CRS) -> str:
    gdf = gpd.GeoDataFrame(
        {"id": range(len(coords))},
        geometry=[Point(x, y) for x, y in coords],
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _cluster(cx: float, cy: float, n: int = 20, spread: float = 50.0) -> list[tuple]:
    """Generate n points clustered around (cx, cy) with given spread (metres)."""
    rng = np.random.default_rng(42)
    return [
        (cx + rng.uniform(-spread, spread), cy + rng.uniform(-spread, spread))
        for _ in range(n)
    ]


class TestDensityAnalysis(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Raster mode tests
    # ------------------------------------------------------------------

    def test_raster_output_file_created(self):
        """Raster output GeoTIFF is created."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde.tif")

        result = analyze_density(src, out, cell_size=50.0, output_type="raster")

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_type"], "raster")

    def test_raster_is_readable_geotiff(self):
        """Output raster can be opened by rasterio with correct properties."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde.tif")

        analyze_density(src, out, cell_size=50.0, output_type="raster")

        with rasterio.open(out) as ds:
            self.assertEqual(ds.count, 1)
            self.assertEqual(ds.dtypes[0], "float32")
            self.assertIsNotNone(ds.crs)

    def test_raster_crs_matches_input(self):
        """Raster CRS matches input point CRS."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde.tif")

        analyze_density(src, out, cell_size=50.0, output_type="raster")

        with rasterio.open(out) as ds:
            self.assertEqual(ds.crs.to_epsg(), 3857)

    def test_raster_values_nonnegative(self):
        """All KDE raster values are non-negative."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde.tif")

        analyze_density(src, out, cell_size=50.0, output_type="raster")

        with rasterio.open(out) as ds:
            data = ds.read(1)
        self.assertTrue((data >= 0).all())

    def test_raster_cluster_peak_at_center(self):
        """Dense cluster produces highest density near the cluster centroid."""
        coords = _cluster(1000.0, 2000.0, n=50, spread=30.0)
        src = _write_points(self._p("pts.gpkg"), coords)
        out = self._p("kde.tif")

        analyze_density(src, out, cell_size=20.0, output_type="raster")

        with rasterio.open(out) as ds:
            data = ds.read(1)
            transform = ds.transform

        # Find pixel of cluster centre
        row, col = rasterio.transform.rowcol(transform, 1000.0, 2000.0)
        center_val = data[row, col]
        mean_val = data[data > 0].mean()
        self.assertGreater(center_val, mean_val)

    def test_raster_dimensions_reflect_extent(self):
        """Grid width and height grow with larger point extents."""
        small = _write_points(self._p("small.gpkg"), _cluster(0, 0, spread=50))
        large = _write_points(self._p("large.gpkg"), _cluster(0, 0, spread=500))

        r_small = analyze_density(small, self._p("s.tif"), cell_size=50.0)
        r_large = analyze_density(large, self._p("l.tif"), cell_size=50.0)

        total_small = r_small["grid_width"] * r_small["grid_height"]
        total_large = r_large["grid_width"] * r_large["grid_height"]
        self.assertGreater(total_large, total_small)

    def test_raster_custom_bandwidth(self):
        """Custom bandwidth is accepted without error; result bandwidth is reported."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde_bw.tif")

        result = analyze_density(src, out, cell_size=50.0, bandwidth=100.0)

        self.assertIsNotNone(result["bandwidth"])
        self.assertGreater(result["bandwidth"], 0)

    def test_raster_scotts_rule_when_bandwidth_none(self):
        """None bandwidth uses Scott's rule; bandwidth is still reported."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde_auto.tif")

        result = analyze_density(src, out, cell_size=50.0, bandwidth=None)

        self.assertIsNotNone(result["bandwidth"])
        self.assertGreater(result["bandwidth"], 0)

    def test_raster_hotspot_cells_count(self):
        """hotspot_cells > 0 for a dataset with real points."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde.tif")

        result = analyze_density(src, out, cell_size=50.0)

        self.assertGreater(result["hotspot_cells"], 0)
        self.assertLessEqual(result["hotspot_cells"], result["total_cells"])

    # ------------------------------------------------------------------
    # Vector mode tests
    # ------------------------------------------------------------------

    def test_vector_output_file_created(self):
        """Vector output GeoPackage is created."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("grid.gpkg")

        result = analyze_density(src, out, cell_size=100.0, output_type="vector")

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_type"], "vector")

    def test_vector_has_point_count_column(self):
        """Output GeoPackage has a point_count column."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("grid.gpkg")

        analyze_density(src, out, cell_size=100.0, output_type="vector")

        gdf = gpd.read_file(out)
        self.assertIn("point_count", gdf.columns)

    def test_vector_total_count_matches_input(self):
        """Sum of point_count across all cells equals the input point count."""
        coords = _cluster(0, 0, n=30)
        src = _write_points(self._p("pts.gpkg"), coords)
        out = self._p("grid.gpkg")

        result = analyze_density(src, out, cell_size=100.0, output_type="vector")

        gdf = gpd.read_file(out)
        self.assertEqual(gdf["point_count"].sum(), result["point_count"])

    def test_vector_crs_matches_input(self):
        """Vector output CRS matches input CRS."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("grid.gpkg")

        analyze_density(src, out, cell_size=100.0, output_type="vector")

        gdf = gpd.read_file(out)
        self.assertEqual(gdf.crs.to_epsg(), 3857)

    def test_vector_hotspot_cells_correct(self):
        """hotspot_cells equals number of cells with point_count > 0."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("grid.gpkg")

        result = analyze_density(src, out, cell_size=100.0, output_type="vector")

        gdf = gpd.read_file(out)
        expected = int((gdf["point_count"] > 0).sum())
        self.assertEqual(result["hotspot_cells"], expected)

    def test_vector_bandwidth_is_none(self):
        """bandwidth is None in result for vector mode."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("grid.gpkg")

        result = analyze_density(src, out, cell_size=100.0, output_type="vector")

        self.assertIsNone(result["bandwidth"])

    # ------------------------------------------------------------------
    # General / result dict
    # ------------------------------------------------------------------

    def test_result_dict_structure(self):
        """Result dict has all expected keys."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("kde.tif")

        result = analyze_density(src, out, cell_size=50.0)

        expected = {
            "output_path", "output_type", "point_count", "crs",
            "cell_size", "bandwidth", "grid_width", "grid_height",
            "total_cells", "hotspot_cells",
        }
        self.assertEqual(expected, set(result.keys()))

    def test_point_count_in_result_matches_input(self):
        """point_count in result equals number of input features."""
        n = 25
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0, n=n))
        out = self._p("kde.tif")

        result = analyze_density(src, out, cell_size=50.0)

        self.assertEqual(result["point_count"], n)

    def test_output_directory_auto_created(self):
        """Nested output directory is created automatically."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        out = self._p("sub/nested/kde.tif")

        result = analyze_density(src, out, cell_size=50.0)

        self.assertTrue(Path(out).exists())

    # ------------------------------------------------------------------
    # Error tests
    # ------------------------------------------------------------------

    def test_invalid_output_type_raises_value_error(self):
        """ValueError raised for unsupported output_type."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        with self.assertRaises(ValueError):
            analyze_density(src, self._p("out.tif"), cell_size=50.0, output_type="hexbin")

    def test_negative_cell_size_raises_value_error(self):
        """ValueError raised for cell_size <= 0."""
        src = _write_points(self._p("pts.gpkg"), _cluster(0, 0))
        with self.assertRaises(ValueError):
            analyze_density(src, self._p("out.tif"), cell_size=-10.0)

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised for non-existent input."""
        with self.assertRaises(FileNotFoundError):
            analyze_density("no_such.gpkg", self._p("out.tif"), cell_size=50.0)

    def test_empty_dataset_raises_value_error(self):
        """ValueError raised for empty point dataset."""
        empty = gpd.GeoDataFrame({"id": []}, geometry=[], crs=CRS)
        src = self._p("empty.gpkg")
        empty.to_file(src, driver="GPKG")
        with self.assertRaises(ValueError):
            analyze_density(src, self._p("out.tif"), cell_size=50.0)

    def test_missing_crs_raises_value_error(self):
        """ValueError raised when dataset has no CRS."""
        no_crs = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)])
        src = self._p("no_crs.gpkg")
        no_crs.to_file(src, driver="GPKG")
        with self.assertRaises(ValueError):
            analyze_density(src, self._p("out.tif"), cell_size=50.0)


if __name__ == "__main__":
    unittest.main()
