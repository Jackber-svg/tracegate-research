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


BAD_BASELINE_SOURCE_STATUSES = {"SOURCE_MISSING", "SOURCE_REJECTED", "SOURCE_UNVERIFIED"}

PRIMARY_SOURCE_CLASSES = {
    "primary_measurement",
    "primary_experiment",
    "primary_dataset",
    "primary_datasheet",
    "direct_measurement",
    "lab_measurement",
    "instrument_export",
    "standard",
}

RELAY_SOURCE_CLASSES = {
    "secondary_source",
    "secondary_figure",
    "secondary_fit",
    "compiled_table",
    "review",
    "literature_range",
    "figure_digitized",
    "digitized_fit",
    "model_fit_from_literature_figure",
    "derived_from_secondary",
    "transcribed_secondary",
    "proxy",
}

PRIMARY_VERIFIED_STATUSES = {
    "VERIFIED",
    "PRIMARY_SOURCE_VERIFIED",
    "VERIFIED_AGAINST_PRIMARY",
    "VERIFIED_AGAINST_PARENT",
    "CROSS_CHECKED_TO_PRIMARY",
}


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


def source_index(source_manifest: dict[str, Any]) -> tuple[set[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    sources: set[str] = set()
    source_rows: dict[str, dict[str, Any]] = {}
    for source in source_manifest.get("sources", []):
        if isinstance(source, dict) and source.get("source_id"):
            source_id = str(source["source_id"])
            sources.add(source_id)
            source_rows[source_id] = source
    values: dict[str, dict[str, Any]] = {}
    for value in source_manifest.get("values", []):
        if isinstance(value, dict) and value.get("parameter"):
            values[str(value["parameter"])] = value
    return sources, source_rows, values


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def check_primary_provenance(parameter: str, row: dict[str, Any], source_id: str, source: dict[str, Any], source_rows: dict[str, dict[str, Any]]) -> list[Check]:
    checks: list[Check] = []
    baseline_allowed = row.get("baseline_allowed") is True
    source_class = first_string(
        source.get("source_class"),
        source.get("source_kind"),
        source.get("class"),
        row.get("source_class"),
    )

    if baseline_allowed and source_class is None:
        checks.append(Check("BLOCK", "baseline_source_class_missing", f"{parameter}: baseline source {source_id} must declare source_class/source_kind so primary vs relay status is auditable"))
        return checks
    if source_class is None:
        checks.append(Check("WARN", "source_class_missing", f"{parameter}: source {source_id} does not declare primary/relay source class"))
        return checks

    normalized_class = source_class.lower()
    if normalized_class in PRIMARY_SOURCE_CLASSES:
        checks.append(Check("PASS", "primary_source_declared", f"{parameter}: source {source_id} is declared as {normalized_class}"))
        return checks

    if normalized_class not in RELAY_SOURCE_CLASSES:
        if baseline_allowed:
            checks.append(Check("BLOCK", "baseline_source_class_unknown", f"{parameter}: baseline source {source_id} has unknown source_class {source_class!r}; cannot determine whether it is primary or relayed"))
        else:
            checks.append(Check("WARN", "source_class_unknown", f"{parameter}: source {source_id} has unknown source_class {source_class!r}"))
        return checks

    primary_source_id = first_string(
        source.get("primary_source_id"),
        source.get("original_source_id"),
        row.get("primary_source_id"),
    )
    if not primary_source_id:
        status = "BLOCK" if baseline_allowed else "WARN"
        checks.append(Check(status, "primary_source_missing", f"{parameter}: relay source {source_id} ({normalized_class}) lacks primary_source_id"))
        return checks
    if primary_source_id not in source_rows:
        status = "BLOCK" if baseline_allowed else "WARN"
        checks.append(Check(status, "primary_source_not_found", f"{parameter}: primary_source_id {primary_source_id} is not listed in SOURCE_MANIFEST.sources[]"))
        return checks

    chain = source.get("provenance_chain")
    if not isinstance(chain, list) or len(chain) < 2:
        status = "BLOCK" if baseline_allowed else "WARN"
        checks.append(Check(status, "provenance_chain_incomplete", f"{parameter}: relay source {source_id} must include provenance_chain from primary source to cited/encoded source"))
        return checks

    seen_primary = False
    seen_current = False
    bad_hops: list[str] = []
    for idx, hop in enumerate(chain):
        if not isinstance(hop, dict):
            bad_hops.append(f"hop {idx} is not an object")
            continue
        hop_source_id = first_string(hop.get("source_id"))
        role = first_string(hop.get("role")) or ""
        verification = first_string(hop.get("verification_status"))
        if not hop_source_id:
            bad_hops.append(f"hop {idx} lacks source_id")
        if not role:
            bad_hops.append(f"hop {idx} lacks role")
        if not verification or verification not in PRIMARY_VERIFIED_STATUSES:
            bad_hops.append(f"hop {idx} has unverified status {verification!r}")
        if hop_source_id == primary_source_id or "primary" in role.lower():
            seen_primary = True
        if hop_source_id == source_id or role.lower() in {"current", "cited_source", "encoded_source", "digitized_fit"}:
            seen_current = True

    if bad_hops:
        status = "BLOCK" if baseline_allowed else "WARN"
        checks.append(Check(status, "provenance_chain_unverified", f"{parameter}: " + "; ".join(bad_hops)))
        return checks
    if not seen_primary:
        status = "BLOCK" if baseline_allowed else "WARN"
        checks.append(Check(status, "provenance_chain_missing_primary", f"{parameter}: provenance_chain does not include primary source {primary_source_id}"))
        return checks
    if not seen_current:
        status = "BLOCK" if baseline_allowed else "WARN"
        checks.append(Check(status, "provenance_chain_missing_current", f"{parameter}: provenance_chain does not include cited source {source_id}"))
        return checks

    primary_row = source_rows[primary_source_id]
    primary_class = first_string(primary_row.get("source_class"), primary_row.get("source_kind"), primary_row.get("class"))
    if primary_class and primary_class.lower() in RELAY_SOURCE_CLASSES:
        status = "BLOCK" if baseline_allowed else "WARN"
        checks.append(Check(status, "primary_source_is_relay", f"{parameter}: declared primary source {primary_source_id} is itself marked as relay class {primary_class}"))
        return checks

    if baseline_allowed and normalized_class in RELAY_SOURCE_CLASSES and not first_string(row.get("source_decision_id"), source.get("provenance_decision_id")):
        checks.append(Check("BLOCK", "relay_source_decision_missing", f"{parameter}: baseline use of relay source {source_id} requires source_decision_id or provenance_decision_id"))
        return checks

    checks.append(Check("PASS", "primary_provenance_chain", f"{parameter}: relay source {source_id} is chained to primary source {primary_source_id}"))
    return checks


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
        checks.append(Check("SKIPPED_NOT_CONFIGURED", "source_check_skipped", "no PARAMETER_REGISTRY.json or SOURCE_MANIFEST.json"))
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

    source_ids, source_rows, source_values = source_index(source_manifest)
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
            checks.extend(check_primary_provenance(parameter, row, source_id, source_rows[source_id], source_rows))
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
