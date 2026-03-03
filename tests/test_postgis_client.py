"""
Tests for postgis_client.py

No real PostgreSQL/PostGIS server required.
- postgis_read / postgis_query: patch geopandas.read_postgis to return synthetic GeoDataFrames.
- postgis_write: patch GeoDataFrame.to_postgis to capture the call without touching a DB.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import geopandas as gpd
from shapely.geometry import Point, Polygon

from gis_bootcamp.postgis_client import (
    postgis_query,
    postgis_read,
    postgis_write,
)

CRS = "EPSG:4326"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gdf(n: int = 4, crs: str = CRS) -> gpd.GeoDataFrame:
    """Synthetic point GeoDataFrame."""
    return gpd.GeoDataFrame(
        {"id": range(n), "name": [f"feat_{i}" for i in range(n)]},
        geometry=[Point(float(i), float(i)) for i in range(n)],
        crs=crs,
    )


def _make_poly_gdf(n: int = 2, crs: str = CRS) -> gpd.GeoDataFrame:
    """Synthetic polygon GeoDataFrame."""
    from shapely.geometry import box
    return gpd.GeoDataFrame(
        {"id": range(n), "region": [f"zone_{i}" for i in range(n)]},
        geometry=[box(float(i), float(i), float(i) + 1, float(i) + 1) for i in range(n)],
        crs=crs,
    )


def _write_gpkg(path: str, gdf: gpd.GeoDataFrame) -> str:
    gdf.to_file(path, driver="GPKG")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPostgisRead(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mock_con = MagicMock()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_feature_count_correct(self):
        """feature_count in result matches the number of rows returned."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf(6)):
            result = postgis_read("parcels", self.mock_con)
        self.assertEqual(result["feature_count"], 6)

    def test_result_dict_structure(self):
        """Result dict contains all expected keys."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_read("parcels", self.mock_con)
        expected = {"output_path", "feature_count", "crs", "columns", "geometry_types"}
        self.assertEqual(expected, set(result.keys()))

    def test_crs_in_result(self):
        """crs in result reflects the GeoDataFrame CRS."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf(crs="EPSG:3857")):
            result = postgis_read("parcels", self.mock_con)
        self.assertIn("3857", result["crs"])

    def test_geometry_types_in_result(self):
        """geometry_types lists unique geometry type strings."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_read("parcels", self.mock_con)
        self.assertEqual(result["geometry_types"], ["Point"])

    def test_columns_exclude_geometry(self):
        """columns list excludes the geometry column."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_read("parcels", self.mock_con)
        self.assertNotIn("geometry", result["columns"])
        self.assertIn("id", result["columns"])
        self.assertIn("name", result["columns"])

    def test_output_path_none_when_not_provided(self):
        """output_path is None when no output_path argument is given."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_read("parcels", self.mock_con)
        self.assertIsNone(result["output_path"])

    def test_writes_gpkg_when_output_path_given(self):
        """Result is written to a GPKG when output_path is provided."""
        out = self._p("parcels.gpkg")
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_read("parcels", self.mock_con, output_path=out)
        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_path"], out)

    def test_where_clause_appended_to_sql(self):
        """WHERE clause is appended to the generated SQL."""
        captured = {}
        def fake_read_postgis(sql, con, **kwargs):
            captured["sql"] = sql
            return _make_gdf()

        with patch.object(gpd, "read_postgis", side_effect=fake_read_postgis):
            postgis_read("parcels", self.mock_con, where="population > 100")

        self.assertIn("WHERE population > 100", captured["sql"])

    def test_empty_result_raises_value_error(self):
        """ValueError raised when the table returns no rows."""
        empty = gpd.GeoDataFrame({"id": []}, geometry=[], crs=CRS)
        with patch.object(gpd, "read_postgis", return_value=empty):
            with self.assertRaises(ValueError):
                postgis_read("empty_table", self.mock_con)

    def test_unsafe_table_name_raises_value_error(self):
        """ValueError raised for table names containing unsafe characters."""
        with self.assertRaises(ValueError):
            postgis_read("users; DROP TABLE users--", self.mock_con)

    def test_unsafe_schema_name_raises_value_error(self):
        """ValueError raised for schema names containing unsafe characters."""
        with self.assertRaises(ValueError):
            postgis_read("parcels", self.mock_con, schema="pub lic")


class TestPostgisWrite(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mock_con = MagicMock()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def _make_input(self, name: str = "pts.gpkg", n: int = 4) -> str:
        return _write_gpkg(self._p(name), _make_gdf(n))

    def test_result_dict_structure(self):
        """Result dict contains all expected keys."""
        src = self._make_input()
        with patch.object(gpd.GeoDataFrame, "to_postgis", return_value=None):
            result = postgis_write(src, "parcels", self.mock_con)
        expected = {"table_name", "schema", "feature_count", "crs", "if_exists"}
        self.assertEqual(expected, set(result.keys()))

    def test_feature_count_correct(self):
        """feature_count reflects the number of features written."""
        src = self._make_input(n=7)
        with patch.object(gpd.GeoDataFrame, "to_postgis", return_value=None):
            result = postgis_write(src, "parcels", self.mock_con)
        self.assertEqual(result["feature_count"], 7)

    def test_to_postgis_called_once(self):
        """to_postgis is called exactly once."""
        src = self._make_input()
        with patch.object(gpd.GeoDataFrame, "to_postgis", return_value=None) as mock_write:
            postgis_write(src, "parcels", self.mock_con)
        mock_write.assert_called_once()

    def test_table_and_schema_in_result(self):
        """table_name and schema are reflected in the result."""
        src = self._make_input()
        with patch.object(gpd.GeoDataFrame, "to_postgis", return_value=None):
            result = postgis_write(src, "my_table", self.mock_con, schema="data")
        self.assertEqual(result["table_name"], "my_table")
        self.assertEqual(result["schema"], "data")

    def test_missing_input_raises_file_not_found(self):
        """FileNotFoundError raised for a non-existent input file."""
        with self.assertRaises(FileNotFoundError):
            postgis_write("/no/such.gpkg", "parcels", self.mock_con)

    def test_invalid_if_exists_raises_value_error(self):
        """ValueError raised for an unsupported if_exists value."""
        src = self._make_input()
        with self.assertRaises(ValueError):
            postgis_write(src, "parcels", self.mock_con, if_exists="overwrite")

    def test_empty_input_raises_value_error(self):
        """ValueError raised for an empty input file."""
        empty = gpd.GeoDataFrame({"id": []}, geometry=[], crs=CRS)
        src = _write_gpkg(self._p("empty.gpkg"), empty)
        with self.assertRaises(ValueError):
            postgis_write(src, "parcels", self.mock_con)

    def test_missing_crs_raises_value_error(self):
        """ValueError raised when the input dataset has no CRS."""
        no_crs = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)])
        src = self._p("no_crs.gpkg")
        no_crs.to_file(src, driver="GPKG")
        with self.assertRaises(ValueError):
            postgis_write(src, "parcels", self.mock_con)


class TestPostgisQuery(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mock_con = MagicMock()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    def test_feature_count_correct(self):
        """feature_count matches the number of rows returned by the query."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf(3)):
            result = postgis_query("SELECT * FROM parcels", self.mock_con)
        self.assertEqual(result["feature_count"], 3)

    def test_result_dict_structure(self):
        """Result dict contains all expected keys."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_query("SELECT * FROM parcels", self.mock_con)
        expected = {"output_path", "feature_count", "crs", "columns", "geometry_types"}
        self.assertEqual(expected, set(result.keys()))

    def test_writes_output_file_when_path_given(self):
        """Result is written to a GPKG when output_path is provided."""
        out = self._p("result.gpkg")
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_query(
                "SELECT * FROM parcels WHERE ST_Area(geom) > 10",
                self.mock_con, output_path=out,
            )
        self.assertTrue(Path(out).exists())
        self.assertEqual(result["output_path"], out)

    def test_output_path_none_when_not_provided(self):
        """output_path is None when not given."""
        with patch.object(gpd, "read_postgis", return_value=_make_gdf()):
            result = postgis_query("SELECT * FROM parcels", self.mock_con)
        self.assertIsNone(result["output_path"])

    def test_polygon_geometry_type_reported(self):
        """geometry_types correctly reports Polygon for polygon results."""
        with patch.object(gpd, "read_postgis", return_value=_make_poly_gdf()):
            result = postgis_query("SELECT * FROM zones", self.mock_con)
        self.assertEqual(result["geometry_types"], ["Polygon"])

    def test_empty_sql_raises_value_error(self):
        """ValueError raised for an empty SQL string."""
        with self.assertRaises(ValueError):
            postgis_query("", self.mock_con)

    def test_whitespace_sql_raises_value_error(self):
        """ValueError raised for a whitespace-only SQL string."""
        with self.assertRaises(ValueError):
            postgis_query("   ", self.mock_con)

    def test_empty_result_raises_value_error(self):
        """ValueError raised when the query returns no rows."""
        empty = gpd.GeoDataFrame({"id": []}, geometry=[], crs=CRS)
        with patch.object(gpd, "read_postgis", return_value=empty):
            with self.assertRaises(ValueError):
                postgis_query("SELECT * FROM parcels WHERE false", self.mock_con)


if __name__ == "__main__":
    unittest.main()
