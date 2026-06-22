#!/usr/bin/env python3
"""Check declared equation forms against adapter-exported runtime expressions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from tracegate_common import Check, load_json, make_report, print_report, status_code


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return []


def runtime_index(runtime: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = runtime.get("equations", runtime.get("expressions", []))
    out: dict[str, dict[str, Any]] = {}
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                key = entry.get("equation_id") or entry.get("id") or entry.get("name")
                if key:
                    out[str(key)] = entry
    return out


def compare_equation(expected: dict[str, Any], actual: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    equation_id = str(expected.get("equation_id") or expected.get("id") or "<missing-id>")
    for field in ["term_count", "nonlinearity_class"]:
        if field in expected:
            if actual.get(field) == expected.get(field):
                checks.append(Check("PASS", "equation_field_match", f"{equation_id}: {field} matches"))
            else:
                checks.append(Check("BLOCK", "equation_field_mismatch", f"{equation_id}: {field} expected {expected.get(field)!r}, actual {actual.get(field)!r}"))
    for field in ["variable_list", "sign_vector"]:
        expected_values = list_value(expected.get(field))
        actual_values = list_value(actual.get(field))
        if expected_values and expected_values == actual_values:
            checks.append(Check("PASS", "equation_list_match", f"{equation_id}: {field} matches"))
        elif expected_values:
            checks.append(Check("BLOCK", "equation_list_mismatch", f"{equation_id}: {field} expected {expected_values!r}, actual {actual_values!r}"))
    required_terms = set(list_value(expected.get("required_terms")))
    actual_terms = set(list_value(actual.get("terms", actual.get("required_terms"))))
    missing = sorted(required_terms - actual_terms)
    if missing:
        checks.append(Check("BLOCK", "equation_required_terms_missing", f"{equation_id}: missing required terms {missing}"))
    elif required_terms:
        checks.append(Check("PASS", "equation_required_terms", f"{equation_id}: required terms present"))
    forbidden_terms = set(list_value(expected.get("forbidden_terms")))
    present_forbidden = sorted(forbidden_terms & actual_terms)
    expression_text = str(actual.get("expression", ""))
    for token in forbidden_terms:
        if token and token in expression_text and token not in present_forbidden:
            present_forbidden.append(token)
    if present_forbidden:
        checks.append(Check("BLOCK", "equation_forbidden_terms", f"{equation_id}: forbidden terms present {present_forbidden}"))
    elif forbidden_terms:
        checks.append(Check("PASS", "equation_forbidden_terms", f"{equation_id}: forbidden terms absent"))
    return checks


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    checks: list[Check] = []
    manifest_path = project / "EQUATION_MANIFEST.json"
    runtime_path = project / "runtime_expression_dump.json"
    if not manifest_path.exists():
        checks.append(Check("SKIPPED_NOT_CONFIGURED", "equation_check_skipped", "EQUATION_MANIFEST.json is absent"))
        return make_report(project, "tracegate_equation_check", checks)
    if not runtime_path.is_file():
        checks.append(Check("BLOCK", "runtime_expression_dump_missing", "EQUATION_MANIFEST exists but runtime_expression_dump.json is missing"))
        return make_report(project, "tracegate_equation_check", checks)
    manifest, err = load_json(manifest_path)
    runtime, runtime_err = load_json(runtime_path)
    if err or not isinstance(manifest, dict):
        checks.append(Check("BLOCK", "equation_manifest_parse_error", f"EQUATION_MANIFEST.json parse failed: {err}"))
        return make_report(project, "tracegate_equation_check", checks)
    if runtime_err or not isinstance(runtime, dict):
        checks.append(Check("BLOCK", "runtime_expression_parse_error", f"runtime_expression_dump.json parse failed: {runtime_err}"))
        return make_report(project, "tracegate_equation_check", checks)
    equations = manifest.get("equations")
    if not isinstance(equations, list):
        checks.append(Check("BLOCK", "equation_manifest_shape", "EQUATION_MANIFEST.json must contain equations[]"))
        return make_report(project, "tracegate_equation_check", checks)
    runtime_by_id = runtime_index(runtime)
    for equation in equations:
        if not isinstance(equation, dict):
            checks.append(Check("BLOCK", "equation_row_invalid", "equation row is not an object"))
            continue
        equation_id = str(equation.get("equation_id") or equation.get("id") or "")
        if not equation_id:
            checks.append(Check("BLOCK", "equation_id_missing", "equation row missing equation_id"))
            continue
        actual = runtime_by_id.get(equation_id)
        if not actual:
            checks.append(Check("BLOCK", "equation_runtime_missing", f"{equation_id}: no matching runtime expression"))
            continue
        checks.extend(compare_equation(equation, actual))
    return make_report(project, "tracegate_equation_check", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TraceGate equation form closure.")
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(Path(args.project_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report("TraceGate Equation Check", report)
    return status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
