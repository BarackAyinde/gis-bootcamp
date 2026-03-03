"""
gis_data_quality.py — GIS Data Quality & Validation Toolkit.

Enterprise-grade spatial data validation system with configurable rules,
structured reporting, and CI/CD integration.

Features:
  - Modular rule registry (vector + raster rules)
  - JSON/YAML configuration support
  - Structured JSON reports
  - CLI with exit codes for CI integration
  - Logging for observability
  - No silent fixes (fail-fast on violations)

Validation Categories:
  Vector:
    - CRS existence/enforcement
    - Geometry validity and no empty geometries
    - Feature count constraints
    - Bounding box constraints
    - Attribute completeness
    - Custom attribute value ranges
    
  Raster:
    - CRS existence/enforcement
    - Dimension constraints
    - Band count validation
    - No-data value existence
    - Data type validation

Configuration Example (JSON):
{
  "name": "parcels_validation",
  "rules": [
    {
      "type": "vector",
      "path": "data/parcels.gpkg",
      "rules": [
        {"check": "crs", "params": {"expected": "EPSG:4326"}},
        {"check": "geometry_validity"},
        {"check": "no_null_geometries"},
        {"check": "feature_count", "params": {"min": 100, "max": 10000}},
        {"check": "bbox", "params": {"minx": -180, "miny": -90, "maxx": 180, "maxy": 90}},
        {"check": "columns", "params": {"required": ["id", "area_m2"]}}
      ]
    },
    {
      "type": "raster",
      "path": "data/dem.tif",
      "rules": [
        {"check": "crs", "params": {"expected": "EPSG:3857"}},
        {"check": "dimensions", "params": {"width": 256, "height": 256}},
        {"check": "band_count", "params": {"expected": 1}},
        {"check": "nodata_defined"}
      ]
    }
  ]
}

Usage:
  from gis_bootcamp.gis_data_quality import validate_from_config, QualityReport
  
  report = validate_from_config("validation.json")
  if not report.all_passed:
      print(report.summary)
      sys.exit(1)
  
  print(f"✓ All {len(report.results)} checks passed")
  report.to_json("report.json")

CLI:
  python -m gis_bootcamp.gis_data_quality validation.json
  python -m gis_bootcamp.gis_data_quality validation.json --format json --output report.json
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import geopandas as gpd
import rasterio
from pyproj import CRS as ProjCRS
from shapely.geometry import box as shapely_box

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CheckResult and QualityReport
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Result of a single validation check."""

    dataset_path: str
    check_name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "✓" if self.passed else "✗"
        return f"{status} {self.dataset_path}: {self.check_name} — {self.message}"


@dataclass
class QualityReport:
    """Aggregated validation report."""

    name: str
    results: list[CheckResult] = field(default_factory=list)
    timestamp: str = ""
    duration_seconds: float = 0.0

    @property
    def all_passed(self) -> bool:
        """Return True if all checks passed."""
        return all(r.passed for r in self.results)

    @property
    def passed_count(self) -> int:
        """Count of passed checks."""
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        """Count of failed checks."""
        return sum(1 for r in self.results if not r.passed)

    @property
    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Quality Report: {self.name}",
            f"  Passed: {self.passed_count}/{len(self.results)}",
            f"  Failed: {self.failed_count}/{len(self.results)}",
            f"  Duration: {self.duration_seconds:.3f}s",
        ]
        if self.failed_count > 0:
            lines.append("\nFailed checks:")
            for r in self.results:
                if not r.passed:
                    lines.append(f"  {r}")
        return "\n".join(lines)

    def to_json(self, path: str) -> None:
        """Write report to JSON file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "name": self.name,
            "all_passed": self.all_passed,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "results": [asdict(r) for r in self.results],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Report written to {path}")


# ---------------------------------------------------------------------------
# Vector validation functions
# ---------------------------------------------------------------------------

def check_vector_crs(gdf: gpd.GeoDataFrame, expected_crs: str) -> CheckResult:
    """Validate vector CRS matches expected value."""
    dataset_path = getattr(gdf, "_file_path", "unknown")
    
    if gdf.crs is None:
        return CheckResult(
            dataset_path, "crs", False,
            f"No CRS defined; expected {expected_crs}",
            {"expected": expected_crs, "actual": None},
        )
    
    try:
        actual = ProjCRS.from_user_input(gdf.crs)
        expected = ProjCRS.from_user_input(expected_crs)
        passed = actual.equals(expected)
        actual_str = gdf.crs.to_string()
    except Exception as exc:
        return CheckResult(
            dataset_path, "crs", False,
            f"CRS comparison failed: {exc}",
            {"expected": expected_crs, "actual": str(gdf.crs)},
        )

    return CheckResult(
        dataset_path, "crs", passed,
        f"CRS {actual_str} {'✓' if passed else '✗ expected'} {expected_crs}",
        {"actual": actual_str, "expected": expected_crs},
    )


def check_vector_geometry_validity(gdf: gpd.GeoDataFrame) -> CheckResult:
    """Validate all geometries are valid (no self-intersections, etc.)."""
    dataset_path = getattr(gdf, "_file_path", "unknown")
    
    if len(gdf) == 0:
        return CheckResult(
            dataset_path, "geometry_validity", True,
            "Empty dataset; trivially valid",
            {"total": 0, "invalid": 0},
        )
    
    invalid_mask = ~gdf.geometry.is_valid
    invalid_count = invalid_mask.sum()
    passed = invalid_count == 0

    return CheckResult(
        dataset_path, "geometry_validity", passed,
        f"{invalid_count} invalid geometries" if not passed else "All geometries valid",
        {"total": len(gdf), "invalid": int(invalid_count), "valid": int(len(gdf) - invalid_count)},
    )


def check_vector_no_null_geometries(gdf: gpd.GeoDataFrame) -> CheckResult:
    """Validate no null or empty geometries."""
    dataset_path = getattr(gdf, "_file_path", "unknown")
    
    if len(gdf) == 0:
        return CheckResult(
            dataset_path, "no_null_geometries", True,
            "Empty dataset; trivially valid",
            {"total": 0, "null_or_empty": 0},
        )
    
    null_mask = gdf.geometry.isna()
    empty_mask = gdf.geometry.is_empty
    combined_mask = null_mask | empty_mask
    null_count = combined_mask.sum()
    passed = null_count == 0

    return CheckResult(
        dataset_path, "no_null_geometries", passed,
        f"{null_count} null/empty geometries" if not passed else "No null or empty geometries",
        {"total": len(gdf), "null_or_empty": int(null_count)},
    )


def check_vector_feature_count(gdf: gpd.GeoDataFrame, min_count: Optional[int] = None,
                                 max_count: Optional[int] = None) -> CheckResult:
    """Validate feature count is within expected range."""
    dataset_path = getattr(gdf, "_file_path", "unknown")
    count = len(gdf)
    passed = True
    reason = []

    if min_count is not None and count < min_count:
        passed = False
        reason.append(f"< {min_count}")
    if max_count is not None and count > max_count:
        passed = False
        reason.append(f"> {max_count}")

    message = f"{count} features"
    if reason:
        message += f" ({'; '.join(reason)})"
    else:
        message += " ✓"

    return CheckResult(
        dataset_path, "feature_count", passed, message,
        {"actual": count, "min": min_count, "max": max_count},
    )


def check_vector_bbox_within(gdf: gpd.GeoDataFrame, minx: float, miny: float,
                              maxx: float, maxy: float) -> CheckResult:
    """Validate all features fall within bounding box."""
    dataset_path = getattr(gdf, "_file_path", "unknown")
    
    if len(gdf) == 0:
        return CheckResult(
            dataset_path, "bbox_within", True,
            "Empty dataset; trivially within bounds",
            {"bounds": [minx, miny, maxx, maxy], "violations": 0},
        )
    
    bounds_geom = shapely_box(minx, miny, maxx, maxy)
    within_mask = gdf.geometry.within(bounds_geom)
    violations = (~within_mask).sum()
    passed = violations == 0

    return CheckResult(
        dataset_path, "bbox_within", passed,
        f"{violations} features outside bounds" if not passed else "All features within bounds",
        {
            "bounds": [minx, miny, maxx, maxy],
            "violations": int(violations),
            "within": int(within_mask.sum()),
        },
    )


def check_vector_columns_present(gdf: gpd.GeoDataFrame, required: list[str]) -> CheckResult:
    """Validate required columns exist."""
    dataset_path = getattr(gdf, "_file_path", "unknown")
    missing = [col for col in required if col not in gdf.columns]
    passed = len(missing) == 0

    return CheckResult(
        dataset_path, "columns_present", passed,
        f"Missing columns: {missing}" if not passed else "All required columns present",
        {"required": required, "missing": missing, "present": list(gdf.columns)},
    )


def check_vector_attribute_range(gdf: gpd.GeoDataFrame, column: str,
                                  min_val: Optional[float] = None,
                                  max_val: Optional[float] = None) -> CheckResult:
    """Validate numeric column values are within range."""
    dataset_path = getattr(gdf, "_file_path", "unknown")
    
    if column not in gdf.columns:
        return CheckResult(
            dataset_path, f"attribute_range[{column}]", False,
            f"Column '{column}' does not exist",
            {"column": column, "min": min_val, "max": max_val},
        )
    
    col_data = gdf[column]
    if col_data.isna().all():
        return CheckResult(
            dataset_path, f"attribute_range[{column}]", False,
            f"Column '{column}' has all null values",
            {"column": column},
        )
    
    col_data_valid = col_data.dropna()
    violations = 0
    details = {"column": column, "min": min_val, "max": max_val, "violations": 0}

    if min_val is not None:
        below = (col_data_valid < min_val).sum()
        violations += below
        details["below_min"] = int(below)

    if max_val is not None:
        above = (col_data_valid > max_val).sum()
        violations += above
        details["above_max"] = int(above)

    passed = violations == 0
    message = f"{violations} values out of range" if not passed else "All values in range"

    return CheckResult(
        dataset_path, f"attribute_range[{column}]", passed, message, details,
    )


# ---------------------------------------------------------------------------
# Raster validation functions
# ---------------------------------------------------------------------------

def check_raster_crs(raster_path: str, expected_crs: str) -> CheckResult:
    """Validate raster CRS matches expected value."""
    with rasterio.open(raster_path) as src:
        actual_crs = src.crs

    if actual_crs is None:
        return CheckResult(
            raster_path, "crs", False,
            f"No CRS defined; expected {expected_crs}",
            {"expected": expected_crs, "actual": None},
        )

    try:
        actual = ProjCRS.from_user_input(actual_crs)
        expected = ProjCRS.from_user_input(expected_crs)
        passed = actual.equals(expected)
        actual_str = actual_crs.to_string()
    except Exception as exc:
        return CheckResult(
            raster_path, "crs", False,
            f"CRS comparison failed: {exc}",
            {"expected": expected_crs, "actual": str(actual_crs)},
        )

    return CheckResult(
        raster_path, "crs", passed,
        f"CRS {actual_str} {'✓' if passed else '✗ expected'} {expected_crs}",
        {"actual": actual_str, "expected": expected_crs},
    )


def check_raster_dimensions(raster_path: str, width: Optional[int] = None,
                             height: Optional[int] = None) -> CheckResult:
    """Validate raster width and height."""
    with rasterio.open(raster_path) as src:
        actual_width = src.width
        actual_height = src.height

    passed = True
    mismatches = []

    if width is not None and actual_width != width:
        passed = False
        mismatches.append(f"width {actual_width} ≠ {width}")

    if height is not None and actual_height != height:
        passed = False
        mismatches.append(f"height {actual_height} ≠ {height}")

    message = "; ".join(mismatches) if mismatches else f"{actual_width}×{actual_height} ✓"

    return CheckResult(
        raster_path, "dimensions", passed, message,
        {"actual": (actual_width, actual_height), "expected": (width, height)},
    )


def check_raster_band_count(raster_path: str, expected: int) -> CheckResult:
    """Validate raster band count."""
    with rasterio.open(raster_path) as src:
        actual = src.count

    passed = actual == expected
    message = f"{actual} bands {'✓' if passed else f'✗ expected {expected}'}"

    return CheckResult(
        raster_path, "band_count", passed, message,
        {"actual": actual, "expected": expected},
    )


def check_raster_nodata_defined(raster_path: str) -> CheckResult:
    """Validate raster has nodata value defined."""
    with rasterio.open(raster_path) as src:
        nodata = src.nodata

    passed = nodata is not None
    message = f"Nodata: {nodata}" if passed else "Nodata value not defined"

    return CheckResult(
        raster_path, "nodata_defined", passed, message,
        {"nodata": nodata},
    )


def check_raster_dtype(raster_path: str, expected_dtype: str) -> CheckResult:
    """Validate raster data type."""
    with rasterio.open(raster_path) as src:
        actual_dtype = src.dtypes[0]  # First band

    passed = actual_dtype == expected_dtype
    message = f"Dtype {actual_dtype} {'✓' if passed else f'✗ expected {expected_dtype}'}"

    return CheckResult(
        raster_path, "dtype", passed, message,
        {"actual": actual_dtype, "expected": expected_dtype},
    )


# ---------------------------------------------------------------------------
# Rule registry and validation engine
# ---------------------------------------------------------------------------

VECTOR_CHECKS: dict[str, Callable] = {
    "crs": check_vector_crs,
    "geometry_validity": check_vector_geometry_validity,
    "no_null_geometries": check_vector_no_null_geometries,
    "feature_count": check_vector_feature_count,
    "bbox": check_vector_bbox_within,
    "columns": check_vector_columns_present,
    "attribute_range": check_vector_attribute_range,
}

RASTER_CHECKS: dict[str, Callable] = {
    "crs": check_raster_crs,
    "dimensions": check_raster_dimensions,
    "band_count": check_raster_band_count,
    "nodata_defined": check_raster_nodata_defined,
    "dtype": check_raster_dtype,
}


def validate_vector(path: str, rules: list[dict]) -> list[CheckResult]:
    """Run all vector validation rules on a dataset.

    Args:
        path: Path to vector dataset.
        rules: List of rule dicts, each with 'check' key and optional 'params'.

    Returns:
        List of CheckResult objects.
    """
    results = []

    logger.info(f"Validating vector: {path}")
    gdf = gpd.read_file(path)
    gdf._file_path = path  # Store path for error reporting

    for rule in rules:
        check_name = rule.get("check")
        params = rule.get("params", {})

        if check_name not in VECTOR_CHECKS:
            logger.warning(f"Unknown check: {check_name}")
            continue

        fn = VECTOR_CHECKS[check_name]
        try:
            result = fn(gdf, **params) if params else fn(gdf)
            results.append(result)
            logger.info(f"  {result}")
        except Exception as exc:
            logger.exception(f"Check {check_name} failed: {exc}")
            results.append(CheckResult(
                path, check_name, False,
                f"Check execution failed: {exc}",
                {"error": str(exc)},
            ))

    return results


def validate_raster(path: str, rules: list[dict]) -> list[CheckResult]:
    """Run all raster validation rules on a dataset.

    Args:
        path: Path to raster dataset.
        rules: List of rule dicts, each with 'check' key and optional 'params'.

    Returns:
        List of CheckResult objects.
    """
    results = []

    logger.info(f"Validating raster: {path}")

    for rule in rules:
        check_name = rule.get("check")
        params = rule.get("params", {})

        if check_name not in RASTER_CHECKS:
            logger.warning(f"Unknown check: {check_name}")
            continue

        fn = RASTER_CHECKS[check_name]
        try:
            result = fn(path, **params) if params else fn(path)
            results.append(result)
            logger.info(f"  {result}")
        except Exception as exc:
            logger.exception(f"Check {check_name} failed: {exc}")
            results.append(CheckResult(
                path, check_name, False,
                f"Check execution failed: {exc}",
                {"error": str(exc)},
            ))

    return results


def validate_from_config(config_path: str) -> QualityReport:
    """Run validation from a JSON config file.

    Config structure:
    {
        "name": "validation_name",
        "rules": [
            {
                "type": "vector",
                "path": "data.gpkg",
                "rules": [{"check": "crs", "params": {"expected": "EPSG:4326"}}, ...]
            },
            {
                "type": "raster",
                "path": "data.tif",
                "rules": [{"check": "crs", "params": {"expected": "EPSG:3857"}}, ...]
            }
        ]
    }

    Args:
        config_path: Path to JSON config file.

    Returns:
        QualityReport with all results.
    """
    import time
    
    t0 = time.perf_counter()
    logger.info(f"Loading config from {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    report = QualityReport(name=config.get("name", "validation"))

    for rule_set in config.get("rules", []):
        dataset_type = rule_set.get("type")
        path = rule_set.get("path")
        rules = rule_set.get("rules", [])

        logger.info(f"Processing {dataset_type}: {path}")

        if dataset_type == "vector":
            results = validate_vector(path, rules)
        elif dataset_type == "raster":
            results = validate_raster(path, rules)
        else:
            logger.warning(f"Unknown dataset type: {dataset_type}")
            continue

        report.results.extend(results)

    report.duration_seconds = round(time.perf_counter() - t0, 4)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GIS Data Quality & Validation Toolkit",
    )
    parser.add_argument("config", help="Path to JSON validation config")
    parser.add_argument("--format", choices=["human", "json"], default="human",
                        help="Output format (default: human)")
    parser.add_argument("--output", help="Output file path (for json format)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        report = validate_from_config(args.config)
    except Exception as exc:
        logger.error(f"Validation failed: {exc}", exc_info=args.verbose)
        return 2

    if args.format == "json":
        output = args.output or "quality_report.json"
        report.to_json(output)
        print(f"Report written to {output}")
    else:
        print(report.summary)

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
