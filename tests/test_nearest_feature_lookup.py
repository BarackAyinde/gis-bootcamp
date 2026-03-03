"""
Tests for nearest_feature_lookup.py

Uses synthetic in-memory geometries written to temp GeoPackages.
No external data or HTTP calls required.
"""

import os
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, box

from gis_bootcamp.nearest_feature_lookup import nearest_feature_lookup

CRS = "EPSG:4326"


def _write_gpkg(gdf: gpd.GeoDataFrame, path: str) -> str:
    gdf.to_file(path, driver="GPKG")
    return path


def _points_gdf(*coords, extra_col: str = None, crs: str = CRS) -> gpd.GeoDataFrame:
    """Build a points GeoDataFrame from (x, y) tuples."""
    data = {"id": list(range(len(coords)))}
    if extra_col:
        data[extra_col] = [f"pt_{i}" for i in range(len(coords))]
    return gpd.GeoDataFrame(
        data,
        geometry=[Point(x, y) for x, y in coords],
        crs=crs,
    )


def _polygons_gdf(boxes: list[tuple], labels: list[str], crs: str = CRS) -> gpd.GeoDataFrame:
    """Build a polygon GeoDataFrame from (minx, miny, maxx, maxy) tuples."""
    return gpd.GeoDataFrame(
        {"region": labels},
        geometry=[box(*b) for b in boxes],
        crs=crs,
    )


class TestNearestFeatureLookup(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _p(self, name: str) -> str:
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # nearest mode
    # ------------------------------------------------------------------

    def test_nearest_all_points_matched(self):
        """nearest mode always matches every point."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5), (5.5, 5.5)), self._p("pts.gpkg"))
        ref = _write_gpkg(
            _polygons_gdf([(0, 0, 2, 2), (4, 4, 7, 7)], ["A", "B"]),
            self._p("ref.gpkg"),
        )
        out = self._p("out.gpkg")

        result = nearest_feature_lookup(pts, ref, out, mode="nearest")

        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["unmatched"], 0)
        self.assertEqual(result["match_rate"], 100.0)

    def test_nearest_reference_attributes_in_output(self):
        """Reference 'region' column is present in the output for nearest mode."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["Zone A"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        nearest_feature_lookup(pts, ref, out, mode="nearest")

        gdf = gpd.read_file(out)
        self.assertIn("region", gdf.columns)
        self.assertEqual(gdf["region"].iloc[0], "Zone A")

    def test_nearest_match_distance_column_added(self):
        """nearest mode adds a match_distance column."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        nearest_feature_lookup(pts, ref, out, mode="nearest")

        gdf = gpd.read_file(out)
        self.assertIn("match_distance", gdf.columns)
        self.assertGreaterEqual(gdf["match_distance"].iloc[0], 0.0)

    def test_nearest_point_to_point_reference(self):
        """nearest mode works with point reference dataset (not just polygons)."""
        pts = _write_gpkg(_points_gdf((0.0, 0.0), (10.0, 10.0)), self._p("pts.gpkg"))
        ref_gdf = gpd.GeoDataFrame(
            {"poi": ["Close", "Far"]},
            geometry=[Point(0.1, 0.1), Point(20, 20)],
            crs=CRS,
        )
        ref = _write_gpkg(ref_gdf, self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        result = nearest_feature_lookup(pts, ref, out, mode="nearest")

        gdf = gpd.read_file(out)
        # Point (0,0) should match "Close" (0.1, 0.1)
        self.assertEqual(gdf.loc[gdf["id"] == 0, "poi"].iloc[0], "Close")
        self.assertEqual(result["matched"], 2)

    # ------------------------------------------------------------------
    # within mode
    # ------------------------------------------------------------------

    def test_within_matched_and_unmatched(self):
        """within mode: points inside polygons matched, outside unmatched."""
        # 2 points inside polygon A, 1 outside all polygons
        pts = _write_gpkg(
            _points_gdf((0.5, 0.5), (1.5, 1.5), (9.0, 9.0)),
            self._p("pts.gpkg"),
        )
        ref = _write_gpkg(
            _polygons_gdf([(0, 0, 2, 2)], ["Inside"]),
            self._p("ref.gpkg"),
        )
        out = self._p("out.gpkg")

        result = nearest_feature_lookup(pts, ref, out, mode="within")

        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["unmatched"], 1)
        self.assertEqual(result["total_points"], 3)

    def test_within_match_rate_calculation(self):
        """match_rate is calculated as (matched / total) * 100."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5), (9.0, 9.0)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        result = nearest_feature_lookup(pts, ref, out, mode="within")

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["unmatched"], 1)
        self.assertEqual(result["match_rate"], 50.0)

    def test_within_match_status_column(self):
        """match_status column is 'matched' or 'unmatched' for within mode."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5), (9.0, 9.0)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        nearest_feature_lookup(pts, ref, out, mode="within")

        gdf = gpd.read_file(out)
        self.assertIn("match_status", gdf.columns)
        statuses = set(gdf["match_status"].tolist())
        self.assertTrue(statuses.issubset({"matched", "unmatched"}))

    def test_within_reference_attributes_for_matched(self):
        """Matched points have reference attributes; unmatched have NaN."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5), (9.0, 9.0)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["ZoneA"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        nearest_feature_lookup(pts, ref, out, mode="within")

        gdf = gpd.read_file(out).sort_values("id").reset_index(drop=True)
        self.assertIn("region", gdf.columns)
        self.assertEqual(gdf.loc[gdf["match_status"] == "matched", "region"].iloc[0], "ZoneA")

    # ------------------------------------------------------------------
    # CRS alignment
    # ------------------------------------------------------------------

    def test_crs_mismatch_auto_reprojected(self):
        """Reference in different CRS is reprojected to match points CRS."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        ref_gdf = _polygons_gdf([(0, 0, 2, 2)], ["A"])
        ref_3857 = ref_gdf.to_crs("EPSG:3857")
        ref = _write_gpkg(ref_3857, self._p("ref_3857.gpkg"))
        out = self._p("out.gpkg")

        result = nearest_feature_lookup(pts, ref, out, mode="nearest")

        self.assertTrue(Path(out).exists())
        self.assertEqual(result["total_points"], 1)

    def test_output_crs_matches_points_crs(self):
        """Output dataset CRS matches the input points CRS."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        nearest_feature_lookup(pts, ref, out, mode="nearest")

        gdf = gpd.read_file(out)
        self.assertEqual(gdf.crs.to_epsg(), 4326)

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------

    def test_original_point_attributes_preserved(self):
        """Original point columns are preserved in the output."""
        pts_gdf = _points_gdf((0.5, 0.5), extra_col="site_name")
        pts = _write_gpkg(pts_gdf, self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        nearest_feature_lookup(pts, ref, out, mode="nearest")

        gdf = gpd.read_file(out)
        self.assertIn("site_name", gdf.columns)

    def test_output_directory_auto_created(self):
        """Nested output directory is created automatically."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        out = self._p("sub/nested/out.gpkg")

        nearest_feature_lookup(pts, ref, out, mode="nearest")

        self.assertTrue(Path(out).exists())

    def test_result_dict_structure(self):
        """Result dict has all expected keys."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        out = self._p("out.gpkg")

        result = nearest_feature_lookup(pts, ref, out)

        expected = {"output_path", "total_points", "matched", "unmatched", "match_rate"}
        self.assertEqual(expected, set(result.keys()))

    def test_feature_count_preserved(self):
        """Output has exactly one row per input point."""
        pts = _write_gpkg(_points_gdf((0, 0), (1, 1), (2, 2), (3, 3)), self._p("pts.gpkg"))
        ref = _write_gpkg(
            _polygons_gdf([(0, 0, 1.5, 1.5), (2, 2, 4, 4)], ["A", "B"]),
            self._p("ref.gpkg"),
        )
        out = self._p("out.gpkg")

        result = nearest_feature_lookup(pts, ref, out, mode="nearest")

        self.assertEqual(result["total_points"], 4)
        gdf = gpd.read_file(out)
        self.assertEqual(len(gdf), 4)

    # ------------------------------------------------------------------
    # Error tests
    # ------------------------------------------------------------------

    def test_invalid_mode_raises_value_error(self):
        """ValueError raised for invalid mode string."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        with self.assertRaises(ValueError):
            nearest_feature_lookup(pts, ref, self._p("out.gpkg"), mode="intersects")

    def test_missing_points_file_raises_file_not_found(self):
        """FileNotFoundError raised for non-existent points file."""
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        with self.assertRaises(FileNotFoundError):
            nearest_feature_lookup("no_pts.gpkg", ref, self._p("out.gpkg"))

    def test_missing_reference_file_raises_file_not_found(self):
        """FileNotFoundError raised for non-existent reference file."""
        pts = _write_gpkg(_points_gdf((0.5, 0.5)), self._p("pts.gpkg"))
        with self.assertRaises(FileNotFoundError):
            nearest_feature_lookup(pts, "no_ref.gpkg", self._p("out.gpkg"))

    def test_empty_points_raises_value_error(self):
        """ValueError raised for empty points dataset."""
        empty = gpd.GeoDataFrame({"id": []}, geometry=[], crs=CRS)
        pts = _write_gpkg(empty, self._p("empty.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        with self.assertRaises(ValueError):
            nearest_feature_lookup(pts, ref, self._p("out.gpkg"))

    def test_points_missing_crs_raises_value_error(self):
        """ValueError raised when points dataset has no CRS."""
        no_crs = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)])
        pts = _write_gpkg(no_crs, self._p("pts_nocrs.gpkg"))
        ref = _write_gpkg(_polygons_gdf([(0, 0, 2, 2)], ["A"]), self._p("ref.gpkg"))
        with self.assertRaises(ValueError):
            nearest_feature_lookup(pts, ref, self._p("out.gpkg"))


if __name__ == "__main__":
    unittest.main()
