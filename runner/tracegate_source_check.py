#!/usr/bin/env python3
"""Check PARAMETER_REGISTRY and SOURCE_MANIFEST source-lock consistency."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from tracegate_common import Check, load_json, make_report, print_report, status_code


BAD_BASELINE_SOURCE_STATUSES = {"SOURCE_MISSING", "SOURCE_REJECTED"}


def as_number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def value_payload(value: Any) -> tuple[str | None, Any, str | None]:
    if not isinstance(value, dict):
        return None, None, None
    return value.get("type"), value.get("data"), value.get("unit")


def numeric_close(left: float, right: float, tolerance: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def source_index(source_manifest: dict[str, Any]) -> tuple[set[str], dict[str, dict[str, Any]]]:
    sources: set[str] = set()
    for source in source_manifest.get("sources", []):
        if isinstance(source, dict) and source.get("source_id"):
            sources.add(str(source["source_id"]))
    values: dict[str, dict[str, Any]] = {}
    for value in source_manifest.get("values", []):
        if isinstance(value, dict) and value.get("parameter"):
            values[str(value["parameter"])] = value
    return sources, values


def compare_encoded_value(parameter: str, row: dict[str, Any], source_value: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    row_type, row_data, row_unit = value_payload(row.get("value"))
    src_type, src_data, src_unit = value_payload(source_value.get("encoded_value"))
    if row_type != src_type:
        return [Check("BLOCK", "source_encoded_type_mismatch", f"{parameter}: registry value type {row_type!r} != source encoded type {src_type!r}")]
    if row_unit != src_unit:
        checks.append(Check("BLOCK", "source_encoded_unit_mismatch", f"{parameter}: registry unit {row_unit!r} != source encoded unit {src_unit!r}"))
    if row_type == "number":
        left = as_number(row_data)
        right = as_number(src_data)
        tolerance = 0.0
        comparison = row.get("comparison")
        if isinstance(comparison, dict):
            tolerance = float(comparison.get("tolerance", 0.0) or 0.0)
        if left is None or right is None:
            checks.append(Check("BLOCK", "source_encoded_number_invalid", f"{parameter}: encoded number is not numeric"))
        elif numeric_close(left, right, tolerance):
            checks.append(Check("PASS", "source_encoded_value", f"{parameter}: encoded value matches source manifest"))
        else:
            checks.append(Check("BLOCK", "source_encoded_value_mismatch", f"{parameter}: registry {left} != source {right} within tolerance {tolerance}"))
    else:
        if row_data == src_data:
            checks.append(Check("PASS", "source_encoded_value", f"{parameter}: encoded value matches source manifest"))
        else:
            checks.append(Check("WARN", "source_encoded_value_unchecked", f"{parameter}: non-number value differs or needs domain comparison"))
    return checks


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    checks: list[Check] = []
    registry_path = project / "PARAMETER_REGISTRY.json"
    source_path = project / "SOURCE_MANIFEST.json"
    if not registry_path.exists() and not source_path.exists():
        checks.append(Check("PASS", "source_check_skipped", "SKIPPED_NOT_CONFIGURED: no PARAMETER_REGISTRY.json or SOURCE_MANIFEST.json"))
        return make_report(project, "tracegate_source_check", checks)
    if not registry_path.is_file():
        checks.append(Check("BLOCK", "parameter_registry_missing", "SOURCE_MANIFEST exists but PARAMETER_REGISTRY.json is missing"))
        return make_report(project, "tracegate_source_check", checks)
    if not source_path.is_file():
        checks.append(Check("BLOCK", "source_manifest_missing", "PARAMETER_REGISTRY exists but SOURCE_MANIFEST.json is missing"))
        return make_report(project, "tracegate_source_check", checks)

    registry, err = load_json(registry_path)
    source_manifest, src_err = load_json(source_path)
    if err or not isinstance(registry, dict):
        checks.append(Check("BLOCK", "parameter_registry_parse_error", f"PARAMETER_REGISTRY.json parse failed: {err}"))
        return make_report(project, "tracegate_source_check", checks)
    if src_err or not isinstance(source_manifest, dict):
        checks.append(Check("BLOCK", "source_manifest_parse_error", f"SOURCE_MANIFEST.json parse failed: {src_err}"))
        return make_report(project, "tracegate_source_check", checks)

    rows = registry.get("rows")
    if not isinstance(rows, list):
        checks.append(Check("BLOCK", "parameter_registry_rows_missing", "PARAMETER_REGISTRY.json must contain rows[]"))
        return make_report(project, "tracegate_source_check", checks)

    source_ids, source_values = source_index(source_manifest)
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            checks.append(Check("BLOCK", "parameter_row_invalid", f"row {idx} is not an object"))
            continue
        parameter = str(row.get("parameter") or f"row-{idx}")
        source_status = row.get("source_status")
        baseline_allowed = row.get("baseline_allowed") is True
        anchor = row.get("source_anchor")
        if baseline_allowed and source_status in BAD_BASELINE_SOURCE_STATUSES:
            checks.append(Check("BLOCK", "baseline_bad_source_status", f"{parameter}: baseline_allowed with {source_status}"))
        if source_status == "SOURCE_INCOMPLETE" and not row.get("source_decision_id"):
            checks.append(Check("BLOCK", "source_incomplete_unresolved", f"{parameter}: SOURCE_INCOMPLETE requires source_decision_id"))
        if not isinstance(anchor, dict) or not anchor.get("source_id"):
            if baseline_allowed:
                checks.append(Check("BLOCK", "source_anchor_missing", f"{parameter}: baseline parameter lacks source_anchor.source_id"))
            else:
                checks.append(Check("WARN", "source_anchor_missing", f"{parameter}: no source_anchor.source_id"))
            continue
        source_id = str(anchor["source_id"])
        if source_id not in source_ids:
            checks.append(Check("BLOCK", "source_id_missing", f"{parameter}: source_id {source_id} not found in SOURCE_MANIFEST.sources[]"))
        else:
            checks.append(Check("PASS", "source_id_resolved", f"{parameter}: source_id {source_id} resolved"))
        source_value = source_values.get(parameter)
        if source_value:
            checks.extend(compare_encoded_value(parameter, row, source_value))
            original = source_value.get("original_value")
            encoded = source_value.get("encoded_value")
            if isinstance(original, dict) and isinstance(encoded, dict) and original.get("unit") != encoded.get("unit"):
                if "conversion_factor" not in source_value or not source_value.get("conversion_note"):
                    checks.append(Check("BLOCK", "unit_conversion_record_missing", f"{parameter}: unit conversion lacks factor or note"))
                else:
                    checks.append(Check("PASS", "unit_conversion_record", f"{parameter}: unit conversion record present"))
        else:
            checks.append(Check("WARN", "source_value_missing", f"{parameter}: no SOURCE_MANIFEST.values[] entry"))

    return make_report(project, "tracegate_source_check", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TraceGate source-lock consistency.")
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(Path(args.project_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report("TraceGate Source Check", report)
    return status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
