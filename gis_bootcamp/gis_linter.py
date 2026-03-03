"""
gis_linter.py — GIS Data Linter.

Applies configurable validation rules to vector or raster datasets and
produces a structured report (JSON or plain text). Designed for use in
CI/CD pipelines: exits 0 when all error-severity rules pass, 1 otherwise.
Warning-severity failures are reported but do not affect exit status.

Rule registry covers all 15 spatial_qa check functions:

  Vector rules:
    crs               — expected_crs (str)
    geometry_validity — (no params)
    no_null_geometries — (no params)
    feature_count     — min_count (int), max_count (int, optional)
    columns_present   — required_columns (list[str])
    geometry_type     — expected_type (str)
    bbox_within       — bbox (list[float]: [minx, miny, maxx, maxy])
    no_duplicate_values — column (str)
    attribute_range   — column (str), min_val (float), max_val (float)

  Raster rules:
    raster_crs        — expected_crs (str)
    raster_dimensions — width (int), height (int)
    raster_band_count — expected_bands (int)
    raster_nodata     — (no params)
    raster_dtype      — expected_dtype (str), band (int, optional, default 1)

JSON config format:
    {
        "dataset": "parcels.gpkg",
        "rules": [
            {"check": "crs", "expected_crs": "EPSG:4326", "severity": "error"},
            {"check": "geometry_validity", "severity": "error"},
            {"check": "feature_count", "min_count": 100, "severity": "warning"}
        ]
    }

Example:
    python -m gis_bootcamp.gis_linter config.json
    python -m gis_bootcamp.gis_linter config.json --output report.json
    python -m gis_bootcamp.gis_linter config.json --format text
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd

from gis_bootcamp.spatial_qa import (
    CheckResult,
    check_attribute_range,
    check_bbox_within,
    check_columns_present,
    check_crs,
    check_feature_count,
    check_geometry_type,
    check_geometry_validity,
    check_no_duplicate_values,
    check_no_null_geometries,
    check_raster_band_count,
    check_raster_crs,
    check_raster_dimensions,
    check_raster_dtype,
    check_raster_nodata,
)

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = ("error", "warning")

_RASTER_EXTS = {".tif", ".tiff", ".img", ".vrt", ".nc", ".hdf", ".h5"}

# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

# Maps rule name → callable(input_path_or_gdf, **rule_params) → CheckResult
# Vector rules receive a GeoDataFrame; raster rules receive a file path.
# The dispatch key is the 'check' field in the rule dict.

def _vec(fn, gdf_kwarg: bool = False):
    """Wrap a vector check function; receives a GeoDataFrame as first arg."""
    return ("vector", fn)


def _ras(fn):
    """Wrap a raster check function; receives a file path as first arg."""
    return ("raster", fn)


_REGISTRY: dict[str, tuple[str, Any]] = {
    "crs":                  _vec(check_crs),
    "geometry_validity":    _vec(check_geometry_validity),
    "no_null_geometries":   _vec(check_no_null_geometries),
    "feature_count":        _vec(check_feature_count),
    "columns_present":      _vec(check_columns_present),
    "geometry_type":        _vec(check_geometry_type),
    "bbox_within":          _vec(check_bbox_within),
    "no_duplicate_values":  _vec(check_no_duplicate_values),
    "attribute_range":      _vec(check_attribute_range),
    "raster_crs":           _ras(check_raster_crs),
    "raster_dimensions":    _ras(check_raster_dimensions),
    "raster_band_count":    _ras(check_raster_band_count),
    "raster_nodata":        _ras(check_raster_nodata),
    "raster_dtype":         _ras(check_raster_dtype),
}


# ---------------------------------------------------------------------------
# LintFinding
# ---------------------------------------------------------------------------

@dataclass
class LintFinding:
    """Result of applying a single linting rule."""

    check: str
    severity: str       # "error" or "warning"
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"  [{status}] [{self.severity}] {self.check}: {self.message}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_raster(path: str) -> bool:
    return Path(path).suffix.lower() in _RASTER_EXTS


def _validate_rule(rule: dict) -> None:
    check = rule.get("check")
    if not check:
        raise ValueError("Each rule must have a 'check' key")
    if check not in _REGISTRY:
        raise ValueError(
            f"Unknown check '{check}'. Available: {sorted(_REGISTRY)}"
        )
    severity = rule.get("severity", "error")
    if severity not in _VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Must be one of {_VALID_SEVERITIES}"
        )


def _extract_params(rule: dict) -> dict:
    """Strip control keys; return only the check function params."""
    return {k: v for k, v in rule.items() if k not in ("check", "severity")}


def _apply_rule(rule: dict, input_path: str, gdf: Optional[gpd.GeoDataFrame]) -> LintFinding:
    """Apply one rule to the dataset and return a LintFinding."""
    check_name = rule["check"]
    severity = rule.get("severity", "error")
    params = _extract_params(rule)
    kind, fn = _REGISTRY[check_name]

    try:
        if kind == "vector":
            if gdf is None:
                return LintFinding(
                    check_name, severity, False,
                    "Vector check requires a vector dataset",
                )
            result: CheckResult = fn(gdf, **params)
        else:  # raster
            result = fn(input_path, **params)
    except TypeError as exc:
        return LintFinding(
            check_name, severity, False,
            f"Rule misconfigured: {exc}",
        )

    return LintFinding(
        check=check_name,
        severity=severity,
        passed=result.passed,
        message=result.message,
        details=result.details,
    )


def _build_summary(input_path: str, rules: list[dict], findings: list[LintFinding]) -> dict:
    """Assemble the top-level result dict."""
    n_errors = sum(1 for f in findings if not f.passed and f.severity == "error")
    n_warnings = sum(1 for f in findings if not f.passed and f.severity == "warning")
    n_passed = sum(1 for f in findings if f.passed)

    return {
        "input_path": input_path,
        "total": len(findings),
        "passed": n_passed,
        "errors": n_errors,
        "warnings": n_warnings,
        "status": "fail" if n_errors > 0 else "pass",
        "findings": [f.to_dict() for f in findings],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lint(
    input_path: str,
    rules: list[dict],
    output_path: Optional[str] = None,
    output_format: str = "json",
) -> dict:
    """
    Apply a list of linting rules to a vector or raster dataset.

    Args:
        input_path: Path to the vector or raster file to lint.
        rules: List of rule dicts. Each must have a 'check' key and optional
               'severity' key ("error" or "warning"; default "error").
               All other keys are passed as keyword arguments to the check fn.
        output_path: Optional path to write the report (format set by output_format).
        output_format: "json" (default) or "text".

    Returns:
        dict with: input_path, total, passed, errors, warnings, status, findings.

    Raises:
        FileNotFoundError: input_path does not exist.
        ValueError: A rule references an unknown check or has invalid severity.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    for rule in rules:
        _validate_rule(rule)

    # Load vector dataset once if any vector rules exist
    has_vector_rules = any(_REGISTRY[r["check"]][0] == "vector" for r in rules)
    gdf: Optional[gpd.GeoDataFrame] = None
    if has_vector_rules and not _is_raster(input_path):
        logger.info("Loading vector dataset: %s", input_path)
        gdf = gpd.read_file(input_path)
    elif has_vector_rules and _is_raster(input_path):
        logger.warning(
            "Vector rules requested but input appears to be a raster: %s", input_path
        )

    logger.info("Running %d rule(s) on %s", len(rules), input_path)
    findings = [_apply_rule(rule, input_path, gdf) for rule in rules]

    for f in findings:
        logger.log(
            logging.INFO if f.passed else (logging.ERROR if f.severity == "error" else logging.WARNING),
            "[%s] [%s] %s: %s",
            "PASS" if f.passed else "FAIL", f.severity, f.check, f.message,
        )

    result = _build_summary(input_path, rules, findings)
    logger.info(
        "Lint complete: status=%s  errors=%d  warnings=%d  passed=%d/%d",
        result["status"], result["errors"], result["warnings"],
        result["passed"], result["total"],
    )

    if output_path:
        report_str = format_report(result, output_format)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report_str, encoding="utf-8")
        logger.info("Report written to: %s", output_path)
        result["report_path"] = output_path

    return result


def lint_from_config(
    config_path: str,
    output_path: Optional[str] = None,
    output_format: str = "json",
) -> dict:
    """
    Load a JSON lint config and run lint().

    Config format:
        {
            "dataset": "path/to/file.gpkg",
            "rules": [
                {"check": "crs", "expected_crs": "EPSG:4326", "severity": "error"},
                ...
            ]
        }

    Args:
        config_path: Path to the JSON config file.
        output_path: Optional path for the report output.
        output_format: "json" or "text".

    Returns:
        Result dict from lint().

    Raises:
        FileNotFoundError: Config or dataset file not found.
        ValueError: Missing required config keys or invalid rule definitions.
    """
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    if "dataset" not in config:
        raise ValueError("Config must contain a 'dataset' key")
    if "rules" not in config or not isinstance(config["rules"], list):
        raise ValueError("Config must contain a 'rules' list")

    dataset = config["dataset"]
    # Resolve dataset path relative to the config file's directory
    if not Path(dataset).is_absolute():
        dataset = str(Path(config_path).parent / dataset)

    return lint(
        input_path=dataset,
        rules=config["rules"],
        output_path=output_path,
        output_format=output_format,
    )


def format_report(result: dict, fmt: str = "json") -> str:
    """
    Format a lint result dict as a JSON or plain-text string.

    Args:
        result: Dict returned by lint().
        fmt: "json" or "text".

    Returns:
        Formatted report string.
    """
    if fmt == "json":
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ── text ─────────────────────────────────────────────────────────────────
    status_label = "PASS" if result["status"] == "pass" else "FAIL"
    lines = [
        "GIS Linter Report",
        "=" * 40,
        f"Input   : {result['input_path']}",
        f"Rules   : {result['total']} | "
        f"Passed: {result['passed']} | "
        f"Errors: {result['errors']} | "
        f"Warnings: {result['warnings']}",
        f"Status  : {status_label}",
        "",
        "Findings:",
    ]
    for f in result["findings"]:
        status = "PASS" if f["passed"] else "FAIL"
        lines.append(f"  [{status}] [{f['severity']}] {f['check']}: {f['message']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "GIS Data Linter — apply configurable validation rules to a "
            "vector or raster dataset"
        )
    )
    parser.add_argument(
        "config",
        help="JSON lint config file (must contain 'dataset' and 'rules' keys)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Path to write the report (default: print to stdout)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Report format: json or text (default: text)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        result = lint_from_config(
            config_path=args.config,
            output_path=args.output,
            output_format=args.format,
        )

        report_str = format_report(result, args.format)
        if not args.output:
            print(report_str)
        else:
            print(f"Report written to: {args.output}")

        return 0 if result["status"] == "pass" else 1

    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
