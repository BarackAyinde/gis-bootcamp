"""
Tests for map_renderer.py

Uses synthetic in-memory geometries written to temp GeoPackages.
No display required — Agg backend is enforced before any pyplot import.
"""

import os
import tempfile
import unittest
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # must come before pyplot (and before importing the module)

import geopandas as gpd
from shapely.geometry import Point, box

from gis_bootcamp.map_renderer import render_map

CRS = "EPSG:4326"
CRS_3857 = "EPSG:3857"


def _write_gpkg(gdf: gpd.GeoDataFrame, path: str) -> str:
    gdf.to_file(path, driver="GPKG")
    return path


def _poly_layer(path: str, n_cols: int = 3, n_rows: int = 3, crs: str = CRS) -> str:
    """Write a polygon fishnet GeoPackage."""
    cells = [box(c, r, c + 1, r + 1) for c in range(n_cols) for r in range(n_rows)]
    gdf = gpd.GeoDataFrame({"id": range(len(cells))}, geometry=cells, crs=crs)
    return _write_gpkg(gdf, path)


def _point_layer(path: str, coords: list[tuple], crs: str = CRS) -> str:
    """Write a point GeoPackage."""
    gdf = gpd.GeoDataFrame(
        {"id": range(len(coords))},
        geometry=[Point(x, y) for x, y in coords],
        crs=crs,
    )
    return _write_gpkg(gdf, path)


class TestMapRenderer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Output file creation
    # ------------------------------------------------------------------

    def test_png_output_created(self):
        """PNG output file is created."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        result = render_map([{"path": layer}], out)

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_format"], "png")

    def test_svg_output_created(self):
        """SVG output file is created."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.svg")

        result = render_map([{"path": layer}], out)

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_format"], "svg")

    def test_jpg_output_created(self):
        """JPG output file is created and format normalised to 'jpeg'."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.jpg")

        result = render_map([{"path": layer}], out)

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_format"], "jpeg")

    def test_output_file_has_nonzero_size(self):
        """Output file is non-empty."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        render_map([{"path": layer}], out)

        self.assertGreater(Path(out).stat().st_size, 0)

    def test_output_directory_auto_created(self):
        """Nested output directory is auto-created."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("sub/nested/map.png")

        render_map([{"path": layer}], out)

        self.assertTrue(Path(out).exists())

    # ------------------------------------------------------------------
    # Result dict
    # ------------------------------------------------------------------

    def test_result_dict_structure(self):
        """Result dict contains all expected keys."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        result = render_map([{"path": layer}], out)

        expected = {
            "output_path", "output_format", "layer_count", "feature_count",
            "crs", "bbox", "figsize", "dpi",
        }
        self.assertEqual(expected, set(result.keys()))

    def test_layer_count_correct(self):
        """layer_count equals the number of input layers."""
        l1 = _poly_layer(self._p("l1.gpkg"))
        l2 = _point_layer(self._p("l2.gpkg"), [(0.5, 0.5), (1.5, 1.5)])
        out = self._p("map.png")

        result = render_map([{"path": l1}, {"path": l2}], out)

        self.assertEqual(result["layer_count"], 2)

    def test_feature_count_is_total_across_layers(self):
        """feature_count is the sum of all features across all layers."""
        l1 = _poly_layer(self._p("l1.gpkg"), n_cols=2, n_rows=2)   # 4 features
        l2 = _point_layer(self._p("l2.gpkg"), [(0.5, 0.5), (1.5, 1.5)])  # 2 features
        out = self._p("map.png")

        result = render_map([{"path": l1}, {"path": l2}], out)

        self.assertEqual(result["feature_count"], 6)

    def test_bbox_is_four_floats_covering_extent(self):
        """bbox is a 4-tuple (xmin, ymin, xmax, ymax) covering the layer extent."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        result = render_map([{"path": layer}], out)

        self.assertEqual(len(result["bbox"]), 4)
        xmin, ymin, xmax, ymax = result["bbox"]
        self.assertLess(xmin, xmax)
        self.assertLess(ymin, ymax)

    def test_crs_matches_first_layer_by_default(self):
        """crs in result matches the first layer's CRS when target_crs is not set."""
        layer = _poly_layer(self._p("poly.gpkg"), crs=CRS)
        out = self._p("map.png")

        result = render_map([{"path": layer}], out)

        self.assertIn("4326", result["crs"])

    def test_figsize_and_dpi_returned(self):
        """figsize and dpi passed in are reflected in the result dict."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        result = render_map([{"path": layer}], out, figsize=(8.0, 6.0), dpi=72)

        self.assertEqual(result["figsize"], (8.0, 6.0))
        self.assertEqual(result["dpi"], 72)

    # ------------------------------------------------------------------
    # Multi-layer and styling
    # ------------------------------------------------------------------

    def test_multi_layer_renders_without_error(self):
        """Polygon + point layers render together without error."""
        l1 = _poly_layer(self._p("poly.gpkg"))
        l2 = _point_layer(self._p("pts.gpkg"), [(0.5, 0.5), (2.5, 2.5)])
        out = self._p("map.png")

        result = render_map(
            [{"path": l1, "color": "lightblue"}, {"path": l2, "color": "red"}], out
        )

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["layer_count"], 2)

    def test_layer_styling_accepted(self):
        """All styling kwargs (color, alpha, linewidth, edge_color) accepted without error."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        result = render_map(
            [{"path": layer, "color": "#2ca02c", "alpha": 0.5,
              "linewidth": 1.5, "edge_color": "#000000"}],
            out,
        )

        self.assertTrue(Path(out).exists())

    def test_label_adds_legend_without_error(self):
        """Layer with 'label' key renders without error (legend is built)."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        result = render_map([{"path": layer, "label": "Polygons"}], out)

        self.assertTrue(Path(out).exists())

    def test_title_accepted(self):
        """Map title is accepted and map renders without error."""
        layer = _poly_layer(self._p("poly.gpkg"))
        out = self._p("map.png")

        result = render_map([{"path": layer}], out, title="Test Map Title")

        self.assertTrue(Path(out).exists())

    def test_multi_layer_bbox_covers_all_layers(self):
        """bbox covers the union of all layer extents."""
        l1 = _poly_layer(self._p("l1.gpkg"), n_cols=2, n_rows=2)   # extent: 0-2, 0-2
        l2 = _point_layer(self._p("l2.gpkg"), [(10.0, 10.0)])       # extent: 10, 10
        out = self._p("map.png")

        result = render_map([{"path": l1}, {"path": l2}], out)

        xmin, ymin, xmax, ymax = result["bbox"]
        self.assertLessEqual(xmin, 0.0)
        self.assertGreaterEqual(xmax, 10.0)
        self.assertGreaterEqual(ymax, 10.0)

    # ------------------------------------------------------------------
    # CRS handling
    # ------------------------------------------------------------------

    def test_crs_mismatch_auto_reprojected(self):
        """Second layer in a different CRS is reprojected to match the first."""
        l1 = _poly_layer(self._p("l1.gpkg"), crs=CRS)
        l2 = _point_layer(self._p("l2.gpkg"), [(0.5, 0.5)], crs=CRS_3857)
        out = self._p("map.png")

        result = render_map([{"path": l1}, {"path": l2}], out)

        self.assertTrue(Path(out).exists())
        self.assertIn("4326", result["crs"])    # first layer's CRS wins

    def test_target_crs_overrides_first_layer_crs(self):
        """target_crs forces all layers into the specified CRS."""
        layer = _poly_layer(self._p("poly.gpkg"), crs=CRS)
        out = self._p("map.png")

        result = render_map([{"path": layer}], out, target_crs=CRS_3857)

        self.assertIn("3857", result["crs"])

    # ------------------------------------------------------------------
    # Error tests
    # ------------------------------------------------------------------

    def test_empty_layers_raises_value_error(self):
        """ValueError raised when the layers list is empty."""
        with self.assertRaises(ValueError):
            render_map([], self._p("map.png"))

    def test_missing_path_key_raises_value_error(self):
        """ValueError raised when a layer dict has no 'path' key."""
        with self.assertRaises(ValueError):
            render_map([{"color": "red"}], self._p("map.png"))

    def test_missing_file_raises_file_not_found(self):
        """FileNotFoundError raised for a non-existent layer file."""
        with self.assertRaises(FileNotFoundError):
            render_map([{"path": "no_such.gpkg"}], self._p("map.png"))

    def test_invalid_output_format_raises_value_error(self):
        """ValueError raised for an unsupported output extension."""
        layer = _poly_layer(self._p("poly.gpkg"))
        with self.assertRaises(ValueError):
            render_map([{"path": layer}], self._p("map.xyz"))

    def test_no_extension_raises_value_error(self):
        """ValueError raised when output_path has no file extension."""
        layer = _poly_layer(self._p("poly.gpkg"))
        with self.assertRaises(ValueError):
            render_map([{"path": layer}], self._p("map"))

    def test_invalid_dpi_raises_value_error(self):
        """ValueError raised for dpi <= 0."""
        layer = _poly_layer(self._p("poly.gpkg"))
        with self.assertRaises(ValueError):
            render_map([{"path": layer}], self._p("map.png"), dpi=0)

    def test_invalid_figsize_raises_value_error(self):
        """ValueError raised for a figsize with a non-positive dimension."""
        layer = _poly_layer(self._p("poly.gpkg"))
        with self.assertRaises(ValueError):
            render_map([{"path": layer}], self._p("map.png"), figsize=(-1.0, 10.0))

    def test_layer_missing_crs_raises_value_error(self):
        """ValueError raised when a layer file has no CRS defined."""
        no_crs = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)])
        path = self._p("no_crs.gpkg")
        no_crs.to_file(path, driver="GPKG")
        with self.assertRaises(ValueError):
            render_map([{"path": path}], self._p("map.png"))


if __name__ == "__main__":
    unittest.main()
