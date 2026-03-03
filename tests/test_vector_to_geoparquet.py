"""
Tests for vector_to_geoparquet.py
"""

import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, LineString

from gis_bootcamp.vector_to_geoparquet import convert_to_geoparquet


def _make_points_gdf(crs="EPSG:4326", n=5) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": [f"p{i}" for i in range(n)], "value": list(range(n))},
        geometry=[Point(i, i) for i in range(n)],
        crs=crs,
    )


def _make_polygons_gdf(crs="EPSG:4326") -> gpd.GeoDataFrame:
    polys = [
        Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
        Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
    ]
    return gpd.GeoDataFrame(
        {"region": ["A", "B"], "area": [1.0, 1.0]},
        geometry=polys,
        crs=crs,
    )


def _make_lines_gdf(crs="EPSG:4326") -> gpd.GeoDataFrame:
    lines = [LineString([(0, 0), (1, 1)]), LineString([(2, 2), (3, 3)])]
    return gpd.GeoDataFrame(
        {"road": ["R1", "R2"]},
        geometry=lines,
        crs=crs,
    )


def _write_gpkg(gdf: gpd.GeoDataFrame, path: str) -> str:
    gdf.to_file(path, driver="GPKG")
    return path


class TestVectorToGeoParquet(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_basic_point_conversion(self):
        """Points GeoDataFrame converts to GeoParquet without error."""
        src = _write_gpkg(_make_points_gdf(), self._p("points.gpkg"))
        out = self._p("points.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["feature_count"], 5)

    def test_polygon_conversion(self):
        """Polygons are converted correctly."""
        src = _write_gpkg(_make_polygons_gdf(), self._p("polys.gpkg"))
        out = self._p("polys.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["feature_count"], 2)

    def test_linestring_conversion(self):
        """LineStrings are converted correctly."""
        src = _write_gpkg(_make_lines_gdf(), self._p("lines.gpkg"))
        out = self._p("lines.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["feature_count"], 2)

    def test_crs_preserved_in_output(self):
        """CRS is preserved and readable from the output GeoParquet."""
        src = _write_gpkg(_make_points_gdf(crs="EPSG:4326"), self._p("pts.gpkg"))
        out = self._p("pts.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertIn("4326", result["crs"])
        roundtrip = gpd.read_parquet(out)
        self.assertIsNotNone(roundtrip.crs)
        self.assertEqual(roundtrip.crs.to_epsg(), 4326)

    def test_attributes_preserved_in_output(self):
        """All attribute columns are preserved in the output."""
        src = _write_gpkg(_make_points_gdf(), self._p("pts.gpkg"))
        out = self._p("pts.parquet")

        convert_to_geoparquet(src, out)

        roundtrip = gpd.read_parquet(out)
        self.assertIn("name", roundtrip.columns)
        self.assertIn("value", roundtrip.columns)

    def test_feature_count_preserved(self):
        """Row count in output matches input."""
        gdf = _make_points_gdf(n=10)
        src = _write_gpkg(gdf, self._p("pts10.gpkg"))
        out = self._p("pts10.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertEqual(result["feature_count"], 10)
        roundtrip = gpd.read_parquet(out)
        self.assertEqual(len(roundtrip), 10)

    def test_geometry_types_reported(self):
        """geometry_types in result dict reflects input geometry types."""
        src = _write_gpkg(_make_points_gdf(), self._p("pts.gpkg"))
        out = self._p("pts.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertIn("Point", result["geometry_types"])

    def test_output_directory_auto_created(self):
        """Nested output directory is created if it doesn't exist."""
        src = _write_gpkg(_make_points_gdf(), self._p("pts.gpkg"))
        out = self._p("sub/nested/out.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertTrue(Path(out).exists())

    def test_result_dict_structure(self):
        """Result dict has all expected keys."""
        src = _write_gpkg(_make_points_gdf(), self._p("pts.gpkg"))
        out = self._p("pts.parquet")

        result = convert_to_geoparquet(src, out)

        expected_keys = {
            "output_path", "feature_count", "crs",
            "geometry_types", "columns", "file_size_bytes",
        }
        self.assertEqual(expected_keys, set(result.keys()))

    def test_file_size_nonzero(self):
        """Output file is non-empty."""
        src = _write_gpkg(_make_points_gdf(), self._p("pts.gpkg"))
        out = self._p("pts.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertGreater(result["file_size_bytes"], 0)

    def test_non_wgs84_crs(self):
        """Non-WGS84 CRS (Web Mercator) is preserved correctly."""
        gdf = _make_points_gdf(crs="EPSG:4326").to_crs("EPSG:3857")
        src = _write_gpkg(gdf, self._p("pts_3857.gpkg"))
        out = self._p("pts_3857.parquet")

        result = convert_to_geoparquet(src, out)

        self.assertIn("3857", result["crs"])
        roundtrip = gpd.read_parquet(out)
        self.assertEqual(roundtrip.crs.to_epsg(), 3857)

    def test_round_trip_geometry_intact(self):
        """Geometries read back from GeoParquet match original coordinates."""
        gdf = _make_points_gdf(n=3)
        src = _write_gpkg(gdf, self._p("pts.gpkg"))
        out = self._p("pts.parquet")

        convert_to_geoparquet(src, out)

        roundtrip = gpd.read_parquet(out)
        for orig, rt in zip(gdf.geometry, roundtrip.geometry):
            self.assertTrue(orig.equals(rt))

    # ------------------------------------------------------------------
    # Error / edge-case tests
    # ------------------------------------------------------------------

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised for non-existent input."""
        with self.assertRaises(FileNotFoundError):
            convert_to_geoparquet("no_such_file.gpkg", self._p("out.parquet"))

    def test_missing_crs_raises_value_error(self):
        """ValueError raised when dataset has no CRS."""
        gdf = gpd.GeoDataFrame(
            {"val": [1, 2]},
            geometry=[Point(0, 0), Point(1, 1)],
        )  # no crs set
        src = self._p("no_crs.gpkg")
        gdf.to_file(src, driver="GPKG")

        with self.assertRaises(ValueError):
            convert_to_geoparquet(src, self._p("out.parquet"))

    def test_empty_dataset_raises_value_error(self):
        """ValueError raised for an empty dataset."""
        gdf = gpd.GeoDataFrame({"val": []}, geometry=[], crs="EPSG:4326")
        src = self._p("empty.gpkg")
        # GeoPackage requires at least one feature; write directly via fiona workaround
        # Use a points GDF, then truncate on read by writing an empty parquet
        # Simplest: mock by writing a real file then replace with empty GDF
        _make_points_gdf(n=1).to_file(src, driver="GPKG")

        # Patch: directly call with an empty GeoDataFrame via a temp parquet trick
        # Instead: write a valid file and assert feature_count == 0 case separately
        # Cleanest approach: write empty GeoJSON (fiona supports empty GeoJSON)
        import json
        geojson_path = self._p("empty.geojson")
        with open(geojson_path, "w") as f:
            json.dump({"type": "FeatureCollection", "features": []}, f)

        with self.assertRaises(ValueError):
            convert_to_geoparquet(geojson_path, self._p("out.parquet"))


if __name__ == "__main__":
    unittest.main()
