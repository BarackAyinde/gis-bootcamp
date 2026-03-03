"""
spatial_qa.py — Spatial QA Framework.

Provides reusable spatial validation checks for vector and raster datasets,
usable both programmatically (SpatialQAReport) and as unittest assertions
(SpatialQATestCase).

Vector checks:
  check_crs                  — CRS matches expected value
  check_crs_consistency      — all datasets share the same CRS
  check_geometry_validity    — all geometries pass shapely is_valid
  check_no_null_geometries   — no null or empty geometries
  check_feature_count        — row count within expected range
  check_columns_present      — required attribute columns exist
  check_geometry_type        — all geometries match expected type
  check_bbox_within          — all features fall within a bounding box
  check_no_duplicate_values  — no duplicate values in a column
  check_attribute_range      — numeric attribute values within range

Raster checks:
  check_raster_crs           — raster CRS matches expected value
  check_raster_dimensions    — raster width and height match expected
  check_raster_band_count    — number of bands matches expected
  check_raster_nodata        — nodata value is defined
  check_raster_dtype         — band dtype matches expected

Usage (programmatic):
    report = SpatialQAReport("parcels")
    report.add(check_crs(gdf, "EPSG:4326"))
    report.add(check_geometry_validity(gdf))
    report.add(check_feature_count(gdf, min_count=100))
    report.raise_if_failed()          # AssertionError with full summary if any failed

Usage (unittest):
    class TestMyData(SpatialQATestCase):
        def test_parcels(self):
            gdf = gpd.read_file("parcels.gpkg")
            self.assertCRS(gdf, "EPSG:4326")
            self.assertGeometryValidity(gdf)
            self.assertFeatureCount(gdf, min_count=1)
"""

import argparse
import logging
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
import rasterio

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Result of a single spatial QA check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.message}"


# ---------------------------------------------------------------------------
# Vector checks
# ---------------------------------------------------------------------------

def check_crs(gdf: gpd.GeoDataFrame, expected_crs: str) -> CheckResult:
    """Validate that a GeoDataFrame has the expected CRS.

    Args:
        gdf: Input GeoDataFrame.
        expected_crs: Expected CRS string (e.g. "EPSG:4326").

    Returns:
        CheckResult with passed=True if CRS matches.
    """
    from pyproj import CRS as ProjCRS

    if gdf.crs is None:
        return CheckResult(
            "check_crs", False,
            "Dataset has no CRS defined",
            {"expected": expected_crs, "actual": None},
        )
    try:
        actual = ProjCRS.from_user_input(gdf.crs)
        expected = ProjCRS.from_user_input(expected_crs)
        passed = actual.equals(expected)
        actual_str = gdf.crs.to_string()
    except Exception as exc:
        return CheckResult(
            "check_crs", False,
            f"CRS comparison failed: {exc}",
            {"expected": expected_crs, "actual": str(gdf.crs)},
        )

    return CheckResult(
        "check_crs", passed,
        f"CRS {actual_str!r} {'matches' if passed else 'does not match'} {expected_crs!r}",
        {"actual": actual_str, "expected": expected_crs},
    )


def check_crs_consistency(
    gdfs: list[gpd.GeoDataFrame],
    labels: Optional[list[str]] = None,
) -> CheckResult:
    """Validate that all GeoDataFrames share the same CRS.

    Args:
        gdfs: List of GeoDataFrames to compare.
        labels: Optional human-readable labels for each dataset.

    Returns:
        CheckResult with passed=True if all CRS strings are identical.
    """
    if labels is None:
        labels = [f"dataset_{i}" for i in range(len(gdfs))]

    if len(gdfs) <= 1:
        return CheckResult(
            "check_crs_consistency", True,
            "Only one dataset; trivially consistent",
            {},
        )

    crs_strings = [gdf.crs.to_string() if gdf.crs else None for gdf in gdfs]
    labeled = dict(zip(labels, crs_strings))
    unique = set(crs_strings)
    passed = len(unique) == 1

    mismatches = {lbl: crs for lbl, crs in labeled.items() if crs != crs_strings[0]}
    return CheckResult(
        "check_crs_consistency", passed,
        "All CRS values match" if passed else f"CRS mismatch across {len(mismatches)} dataset(s)",
        {"crs_by_dataset": labeled, "mismatches": mismatches},
    )


def check_geometry_validity(gdf: gpd.GeoDataFrame) -> CheckResult:
    """Validate that all geometries pass Shapely's is_valid predicate.

    Args:
        gdf: Input GeoDataFrame.

    Returns:
        CheckResult with passed=True if all geometries are valid.
    """
    if len(gdf) == 0:
        return CheckResult(
            "check_geometry_validity", True,
            "No features to validate",
            {"total": 0, "invalid_count": 0},
        )

    invalid_mask = ~gdf.geometry.is_valid
    n_invalid = int(invalid_mask.sum())
    passed = n_invalid == 0

    return CheckResult(
        "check_geometry_validity", passed,
        f"All {len(gdf)} geometries are valid" if passed
        else f"{n_invalid}/{len(gdf)} geometries are invalid",
        {
            "total": len(gdf),
            "invalid_count": n_invalid,
            "invalid_indices": gdf.index[invalid_mask].tolist(),
        },
    )


def check_no_null_geometries(gdf: gpd.GeoDataFrame) -> CheckResult:
    """Validate that no geometries are null or empty.

    Args:
        gdf: Input GeoDataFrame.

    Returns:
        CheckResult with passed=True if no null or empty geometries found.
    """
    if len(gdf) == 0:
        return CheckResult(
            "check_no_null_geometries", True,
            "No features to validate",
            {"total": 0, "null_count": 0, "empty_count": 0},
        )

    null_mask = gdf.geometry.isna()
    n_null = int(null_mask.sum())

    # Check for empty geometries only on non-null rows
    non_null_geoms = gdf.geometry.loc[~null_mask]
    n_empty = int(non_null_geoms.is_empty.sum()) if len(non_null_geoms) > 0 else 0

    n_problematic = n_null + n_empty
    passed = n_problematic == 0

    return CheckResult(
        "check_no_null_geometries", passed,
        "No null or empty geometries" if passed
        else f"{n_problematic} null/empty geometry(ies) found ({n_null} null, {n_empty} empty)",
        {"total": len(gdf), "null_count": n_null, "empty_count": n_empty},
    )


def check_feature_count(
    gdf: gpd.GeoDataFrame,
    min_count: int,
    max_count: Optional[int] = None,
) -> CheckResult:
    """Validate that the feature count falls within an expected range.

    Args:
        gdf: Input GeoDataFrame.
        min_count: Minimum expected row count (inclusive).
        max_count: Optional maximum expected row count (inclusive).

    Returns:
        CheckResult with passed=True if count is within range.
    """
    n = len(gdf)
    if max_count is None:
        passed = n >= min_count
        msg = f"{n} features {'≥' if passed else '<'} minimum {min_count}"
    else:
        passed = min_count <= n <= max_count
        msg = (
            f"{n} features within [{min_count}, {max_count}]" if passed
            else f"{n} features outside expected range [{min_count}, {max_count}]"
        )

    return CheckResult(
        "check_feature_count", passed, msg,
        {"count": n, "min": min_count, "max": max_count},
    )


def check_columns_present(
    gdf: gpd.GeoDataFrame,
    required_columns: list[str],
) -> CheckResult:
    """Validate that all required attribute columns are present.

    Args:
        gdf: Input GeoDataFrame.
        required_columns: Column names that must exist (geometry column excluded).

    Returns:
        CheckResult with passed=True if all columns are present.
    """
    missing = [c for c in required_columns if c not in gdf.columns]
    passed = len(missing) == 0

    return CheckResult(
        "check_columns_present", passed,
        "All required columns present" if passed else f"Missing columns: {missing}",
        {
            "required": required_columns,
            "missing": missing,
            "present": list(gdf.columns),
        },
    )


def check_geometry_type(
    gdf: gpd.GeoDataFrame,
    expected_type: str,
) -> CheckResult:
    """Validate that all geometries are of the expected type.

    Args:
        gdf: Input GeoDataFrame.
        expected_type: Expected Shapely geometry type string (e.g. "Point", "Polygon").

    Returns:
        CheckResult with passed=True if all geometries match the expected type.
    """
    if len(gdf) == 0:
        return CheckResult(
            "check_geometry_type", True,
            "No features to validate",
            {"expected": expected_type, "actual_types": []},
        )

    actual_types = sorted(set(gdf.geom_type.dropna().tolist()))
    passed = actual_types == [expected_type]

    return CheckResult(
        "check_geometry_type", passed,
        f"All geometries are {expected_type!r}" if passed
        else f"Expected {expected_type!r}, found types: {actual_types}",
        {"expected": expected_type, "actual_types": actual_types},
    )


def check_bbox_within(
    gdf: gpd.GeoDataFrame,
    bbox: tuple[float, float, float, float],
) -> CheckResult:
    """Validate that all features fall within the given bounding box.

    Args:
        gdf: Input GeoDataFrame.
        bbox: (minx, miny, maxx, maxy) bounding box.

    Returns:
        CheckResult with passed=True if all features are within the bbox.
    """
    if len(gdf) == 0:
        return CheckResult(
            "check_bbox_within", True,
            "No features to validate",
            {"bbox": bbox},
        )

    minx, miny, maxx, maxy = bbox
    actual = gdf.total_bounds  # [minx, miny, maxx, maxy]
    passed = (
        actual[0] >= minx
        and actual[1] >= miny
        and actual[2] <= maxx
        and actual[3] <= maxy
    )

    return CheckResult(
        "check_bbox_within", passed,
        "All features are within the expected bounding box" if passed
        else "One or more features extend outside the expected bounding box",
        {"bbox": list(bbox), "actual_bounds": actual.tolist()},
    )


def check_no_duplicate_values(
    gdf: gpd.GeoDataFrame,
    column: str,
) -> CheckResult:
    """Validate that a column contains no duplicate values.

    Args:
        gdf: Input GeoDataFrame.
        column: Attribute column to check for duplicates.

    Returns:
        CheckResult with passed=True if no duplicates are found.
    """
    if column not in gdf.columns:
        return CheckResult(
            "check_no_duplicate_values", False,
            f"Column '{column}' not found in dataset",
            {"column": column},
        )

    n_dupes = int(gdf[column].duplicated().sum())
    passed = n_dupes == 0

    return CheckResult(
        "check_no_duplicate_values", passed,
        f"No duplicate values in '{column}'" if passed
        else f"{n_dupes} duplicate value(s) found in '{column}'",
        {"column": column, "duplicate_count": n_dupes, "total": len(gdf)},
    )


def check_attribute_range(
    gdf: gpd.GeoDataFrame,
    column: str,
    min_val: float,
    max_val: float,
) -> CheckResult:
    """Validate that numeric column values fall within [min_val, max_val].

    Args:
        gdf: Input GeoDataFrame.
        column: Numeric attribute column to check.
        min_val: Inclusive lower bound.
        max_val: Inclusive upper bound.

    Returns:
        CheckResult with passed=True if all values are within range.
    """
    if column not in gdf.columns:
        return CheckResult(
            "check_attribute_range", False,
            f"Column '{column}' not found in dataset",
            {"column": column},
        )

    vals = gdf[column].dropna()
    out_of_range = int(((vals < min_val) | (vals > max_val)).sum())
    passed = out_of_range == 0

    return CheckResult(
        "check_attribute_range", passed,
        f"All '{column}' values within [{min_val}, {max_val}]" if passed
        else f"{out_of_range} value(s) in '{column}' outside [{min_val}, {max_val}]",
        {
            "column": column,
            "min": min_val,
            "max": max_val,
            "out_of_range_count": out_of_range,
            "actual_min": float(vals.min()) if len(vals) else None,
            "actual_max": float(vals.max()) if len(vals) else None,
        },
    )


# ---------------------------------------------------------------------------
# Raster checks
# ---------------------------------------------------------------------------

def check_raster_crs(raster_path: str, expected_crs: str) -> CheckResult:
    """Validate that a raster file has the expected CRS.

    Args:
        raster_path: Path to the raster file.
        expected_crs: Expected CRS string (e.g. "EPSG:4326").

    Returns:
        CheckResult with passed=True if CRS matches.
    """
    from pyproj import CRS as ProjCRS

    with rasterio.open(raster_path) as src:
        actual_crs = src.crs

    if actual_crs is None:
        return CheckResult(
            "check_raster_crs", False,
            "Raster has no CRS defined",
            {"expected": expected_crs, "actual": None},
        )

    try:
        actual = ProjCRS.from_user_input(actual_crs)
        expected = ProjCRS.from_user_input(expected_crs)
        passed = actual.equals(expected)
        actual_str = str(actual_crs)
    except Exception as exc:
        return CheckResult(
            "check_raster_crs", False,
            f"CRS comparison failed: {exc}",
            {"expected": expected_crs, "actual": str(actual_crs)},
        )

    return CheckResult(
        "check_raster_crs", passed,
        f"Raster CRS {actual_str!r} {'matches' if passed else 'does not match'} {expected_crs!r}",
        {"actual": actual_str, "expected": expected_crs},
    )


def check_raster_dimensions(
    raster_path: str,
    width: int,
    height: int,
) -> CheckResult:
    """Validate that a raster has the expected pixel dimensions.

    Args:
        raster_path: Path to the raster file.
        width: Expected pixel width.
        height: Expected pixel height.

    Returns:
        CheckResult with passed=True if dimensions match.
    """
    with rasterio.open(raster_path) as src:
        actual_w, actual_h = src.width, src.height

    passed = actual_w == width and actual_h == height

    return CheckResult(
        "check_raster_dimensions", passed,
        (
            f"Raster dimensions {actual_w}×{actual_h} match expected {width}×{height}"
            if passed
            else f"Raster dimensions {actual_w}×{actual_h} do not match expected {width}×{height}"
        ),
        {
            "actual": {"width": actual_w, "height": actual_h},
            "expected": {"width": width, "height": height},
        },
    )


def check_raster_band_count(raster_path: str, expected_bands: int) -> CheckResult:
    """Validate that a raster has the expected number of bands.

    Args:
        raster_path: Path to the raster file.
        expected_bands: Expected band count.

    Returns:
        CheckResult with passed=True if band count matches.
    """
    with rasterio.open(raster_path) as src:
        actual = src.count

    passed = actual == expected_bands

    return CheckResult(
        "check_raster_band_count", passed,
        f"Raster has {actual} band(s) ({'matches' if passed else f'expected {expected_bands}'})",
        {"actual": actual, "expected": expected_bands},
    )


def check_raster_nodata(raster_path: str) -> CheckResult:
    """Validate that a raster has a nodata value defined.

    Args:
        raster_path: Path to the raster file.

    Returns:
        CheckResult with passed=True if nodata is set.
    """
    with rasterio.open(raster_path) as src:
        nodata = src.nodata

    passed = nodata is not None

    return CheckResult(
        "check_raster_nodata", passed,
        f"Nodata value is set to {nodata}" if passed else "No nodata value is defined",
        {"nodata": nodata},
    )


def check_raster_dtype(
    raster_path: str,
    expected_dtype: str,
    band: int = 1,
) -> CheckResult:
    """Validate that a raster band has the expected data type.

    Args:
        raster_path: Path to the raster file.
        expected_dtype: Expected dtype string (e.g. "float32", "uint8").
        band: 1-based band index (default: 1).

    Returns:
        CheckResult with passed=True if dtype matches.
    """
    with rasterio.open(raster_path) as src:
        actual = src.dtypes[band - 1]

    passed = actual == expected_dtype

    return CheckResult(
        "check_raster_dtype", passed,
        f"Band {band} dtype {actual!r} {'matches' if passed else 'does not match'} {expected_dtype!r}",
        {"band": band, "actual": actual, "expected": expected_dtype},
    )


# ---------------------------------------------------------------------------
# SpatialQAReport
# ---------------------------------------------------------------------------

class SpatialQAReport:
    """Accumulates CheckResult objects and generates a structured summary.

    Example:
        report = SpatialQAReport("my_dataset")
        report.add(check_crs(gdf, "EPSG:4326"))
        report.add(check_geometry_validity(gdf))
        report.raise_if_failed()
    """

    def __init__(self, name: str = "spatial_qa") -> None:
        self.name = name
        self.results: list[CheckResult] = []

    def add(self, result: CheckResult) -> "SpatialQAReport":
        """Record a CheckResult. Returns self for method chaining."""
        self.results.append(result)
        logger.log(
            logging.INFO if result.passed else logging.WARNING,
            "[%s] %s: %s",
            "PASS" if result.passed else "FAIL",
            result.name,
            result.message,
        )
        return self

    @property
    def passed(self) -> bool:
        """True if all checks passed."""
        return all(r.passed for r in self.results)

    @property
    def failed_checks(self) -> list[CheckResult]:
        """List of failed CheckResults."""
        return [r for r in self.results if not r.passed]

    def summary(self) -> dict[str, Any]:
        """Return a structured summary dict."""
        return {
            "name": self.name,
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": len(self.failed_checks),
            "checks": [
                {"name": r.name, "passed": r.passed, "message": r.message}
                for r in self.results
            ],
        }

    def raise_if_failed(self) -> None:
        """Raise AssertionError if any check failed, listing all failures."""
        if not self.passed:
            lines = "\n".join(f"  - {r}" for r in self.failed_checks)
            raise AssertionError(
                f"SpatialQA '{self.name}': "
                f"{len(self.failed_checks)}/{len(self.results)} check(s) failed:\n{lines}"
            )

    def __str__(self) -> str:
        s = self.summary()
        lines = [
            f"SpatialQAReport '{self.name}': "
            f"{s['passed']}/{s['total']} passed, {s['failed']} failed"
        ]
        for r in self.results:
            lines.append(f"  {r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SpatialQATestCase
# ---------------------------------------------------------------------------

class SpatialQATestCase(unittest.TestCase):
    """
    unittest.TestCase subclass with built-in spatial assertion methods.

    Each assertSpatial* method runs the corresponding check function and
    calls self.fail() if the check does not pass, providing a clear error
    message with check details.

    Example:
        class TestMyData(SpatialQATestCase):
            def test_parcels_crs(self):
                gdf = gpd.read_file("parcels.gpkg")
                self.assertCRS(gdf, "EPSG:4326")
                self.assertGeometryValidity(gdf)
                self.assertFeatureCount(gdf, min_count=1)
    """

    def _assert_check(self, result: CheckResult) -> None:
        if not result.passed:
            self.fail(str(result))

    # Vector assertions

    def assertCRS(self, gdf: gpd.GeoDataFrame, expected_crs: str) -> None:
        """Assert that the GeoDataFrame has the expected CRS."""
        self._assert_check(check_crs(gdf, expected_crs))

    def assertCRSConsistency(
        self,
        gdfs: list[gpd.GeoDataFrame],
        labels: Optional[list[str]] = None,
    ) -> None:
        """Assert that all GeoDataFrames share the same CRS."""
        self._assert_check(check_crs_consistency(gdfs, labels))

    def assertGeometryValidity(self, gdf: gpd.GeoDataFrame) -> None:
        """Assert that all geometries are valid."""
        self._assert_check(check_geometry_validity(gdf))

    def assertNoNullGeometries(self, gdf: gpd.GeoDataFrame) -> None:
        """Assert that no geometries are null or empty."""
        self._assert_check(check_no_null_geometries(gdf))

    def assertFeatureCount(
        self,
        gdf: gpd.GeoDataFrame,
        min_count: int,
        max_count: Optional[int] = None,
    ) -> None:
        """Assert that feature count is within the expected range."""
        self._assert_check(check_feature_count(gdf, min_count, max_count))

    def assertColumnsPresent(
        self,
        gdf: gpd.GeoDataFrame,
        required_columns: list[str],
    ) -> None:
        """Assert that all required columns are present."""
        self._assert_check(check_columns_present(gdf, required_columns))

    def assertGeometryType(
        self,
        gdf: gpd.GeoDataFrame,
        expected_type: str,
    ) -> None:
        """Assert that all geometries are of the expected type."""
        self._assert_check(check_geometry_type(gdf, expected_type))

    def assertBBoxWithin(
        self,
        gdf: gpd.GeoDataFrame,
        bbox: tuple[float, float, float, float],
    ) -> None:
        """Assert that all features fall within the given bounding box."""
        self._assert_check(check_bbox_within(gdf, bbox))

    def assertNoDuplicateValues(self, gdf: gpd.GeoDataFrame, column: str) -> None:
        """Assert that a column has no duplicate values."""
        self._assert_check(check_no_duplicate_values(gdf, column))

    def assertAttributeRange(
        self,
        gdf: gpd.GeoDataFrame,
        column: str,
        min_val: float,
        max_val: float,
    ) -> None:
        """Assert that all values in a numeric column are within range."""
        self._assert_check(check_attribute_range(gdf, column, min_val, max_val))

    # Raster assertions

    def assertRasterCRS(self, raster_path: str, expected_crs: str) -> None:
        """Assert that the raster has the expected CRS."""
        self._assert_check(check_raster_crs(raster_path, expected_crs))

    def assertRasterDimensions(self, raster_path: str, width: int, height: int) -> None:
        """Assert that the raster has the expected pixel dimensions."""
        self._assert_check(check_raster_dimensions(raster_path, width, height))

    def assertRasterBandCount(self, raster_path: str, expected_bands: int) -> None:
        """Assert that the raster has the expected number of bands."""
        self._assert_check(check_raster_band_count(raster_path, expected_bands))

    def assertRasterNodata(self, raster_path: str) -> None:
        """Assert that the raster has a nodata value defined."""
        self._assert_check(check_raster_nodata(raster_path))

    def assertRasterDtype(
        self,
        raster_path: str,
        expected_dtype: str,
        band: int = 1,
    ) -> None:
        """Assert that the raster band has the expected data type."""
        self._assert_check(check_raster_dtype(raster_path, expected_dtype, band))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_vector_checks(args) -> SpatialQAReport:
    if not Path(args.input).exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    gdf = gpd.read_file(args.input)
    report = SpatialQAReport(Path(args.input).name)

    report.add(check_no_null_geometries(gdf))
    report.add(check_geometry_validity(gdf))

    if args.crs:
        report.add(check_crs(gdf, args.crs))
    if args.min_features is not None or args.max_features is not None:
        report.add(check_feature_count(
            gdf,
            min_count=args.min_features or 0,
            max_count=args.max_features,
        ))
    if args.geometry_type:
        report.add(check_geometry_type(gdf, args.geometry_type))
    if args.columns:
        report.add(check_columns_present(gdf, args.columns.split(",")))

    return report


def _run_raster_checks(args) -> SpatialQAReport:
    if not Path(args.input).exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    report = SpatialQAReport(Path(args.input).name)

    report.add(check_raster_nodata(args.input))

    if args.crs:
        report.add(check_raster_crs(args.input, args.crs))
    if args.width is not None and args.height is not None:
        report.add(check_raster_dimensions(args.input, args.width, args.height))
    if args.bands is not None:
        report.add(check_raster_band_count(args.input, args.bands))
    if args.dtype:
        report.add(check_raster_dtype(args.input, args.dtype))

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Spatial QA — validate vector or raster datasets"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_vec = subparsers.add_parser("check-vector", help="Run QA checks on a vector file")
    p_vec.add_argument("input", help="Input vector file path")
    p_vec.add_argument("--crs", default=None, help="Expected CRS (e.g. EPSG:4326)")
    p_vec.add_argument("--min-features", type=int, default=None, help="Minimum feature count")
    p_vec.add_argument("--max-features", type=int, default=None, help="Maximum feature count")
    p_vec.add_argument("--geometry-type", default=None, help="Expected geometry type (e.g. Point)")
    p_vec.add_argument("--columns", default=None, help="Comma-separated required column names")

    p_ras = subparsers.add_parser("check-raster", help="Run QA checks on a raster file")
    p_ras.add_argument("input", help="Input raster file path")
    p_ras.add_argument("--crs", default=None, help="Expected CRS (e.g. EPSG:4326)")
    p_ras.add_argument("--width", type=int, default=None, help="Expected pixel width")
    p_ras.add_argument("--height", type=int, default=None, help="Expected pixel height")
    p_ras.add_argument("--bands", type=int, default=None, help="Expected band count")
    p_ras.add_argument("--dtype", default=None, help="Expected band dtype (e.g. float32)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        if args.command == "check-vector":
            report = _run_vector_checks(args)
        else:
            report = _run_raster_checks(args)

        print(report)
        s = report.summary()
        print(f"\nResult: {'PASS' if report.passed else 'FAIL'} "
              f"({s['passed']}/{s['total']} checks passed)")
        return 0 if report.passed else 1

    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
