#!/usr/bin/env python3
"""Check configured numeric KPI gates.

This runner is intentionally generic and dependency-free. It reads
PHYSICAL_KPI_GATES.json, loads JSON or CSV gate reports, and evaluates declared
numeric thresholds. It can enforce simple full-window metadata, but it does not
claim that the selected KPIs are scientifically sufficient.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from tracegate_common import Check, load_json, make_report, print_report, rel, status_code


CONFIG_FILE = "PHYSICAL_KPI_GATES.json"


def as_float(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except Exception:
        return None


def compare_numeric(observed: float, op: str, threshold: float) -> bool:
    if op in {"lt", "<"}:
        return observed < threshold
    if op in {"lte", "<="}:
        return observed <= threshold
    if op in {"gt", ">"}:
        return observed > threshold
    if op in {"gte", ">="}:
        return observed >= threshold
    if op in {"eq", "=="}:
        return observed == threshold
    raise ValueError(f"unsupported op {op!r}")


def state_mode(project: Path) -> str | None:
    state, err = load_json(project / "STATE.json")
    if err or not isinstance(state, dict):
        return None
    mode = state.get("mode")
    return str(mode) if isinstance(mode, str) else None


def load_metric_from_json(report: dict[str, Any], source: str, metric: str) -> float | None:
    if source == "metrics":
        metrics = report.get("metrics")
        if isinstance(metrics, dict):
            return as_float(metrics.get(metric))
        return None
    if source == "summary_rows":
        rows = report.get("summary_rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("metric") == metric:
                    return as_float(row.get("value"))
        return None
    if source.startswith("$."):
        return load_metric_from_json_path(report, source)
    return None


def load_metric_from_json_path(report: dict[str, Any], source: str) -> float | None:
    node: Any = report
    for part in source[2:].split("."):
        if not part:
            continue
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return as_float(node)


def load_metric_from_csv(path: Path, metric: str) -> float | None:
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("metric") == metric:
                return as_float(row.get("value"))
    return None


def report_is_full_window(report: dict[str, Any]) -> bool:
    if report.get("full_window") is True:
        return True
    window = report.get("window")
    if isinstance(window, dict):
        if window.get("full_window") is True:
            return True
        if window.get("coverage") == "full":
            return True
        if window.get("type") == "full":
            return True
    return False


def check_gate(project: Path, gate: dict[str, Any], mode: str | None) -> list[Check]:
    checks: list[Check] = []
    gate_id = str(gate.get("gate_id") or gate.get("id") or "UNKNOWN_KPI_GATE")

    allowed_modes = gate.get("allowed_modes")
    if isinstance(allowed_modes, list) and mode not in {str(item) for item in allowed_modes}:
        checks.append(Check("SKIPPED_NOT_APPLICABLE", "kpi_gate_mode_skip", f"{gate_id} skipped in mode {mode!r}"))
        return checks

    input_file = gate.get("input_file")
    if not isinstance(input_file, str) or not input_file:
        return [Check("BLOCK", "kpi_gate_input_missing", f"{gate_id} missing input_file")]
    input_path = rel(project, input_file)
    if not input_path.is_file():
        return [Check("BLOCK", "kpi_gate_input_missing", f"{gate_id} input missing: {input_file}")]

    thresholds = gate.get("thresholds")
    if not isinstance(thresholds, list) or not thresholds:
        return [Check("BLOCK", "kpi_gate_thresholds_missing", f"{gate_id} has no thresholds")]

    json_report: dict[str, Any] | None = None
    if input_path.suffix.lower() == ".json":
        data, err = load_json(input_path)
        if err or not isinstance(data, dict):
            return [Check("BLOCK", "kpi_gate_report_parse_error", f"{gate_id} could not parse {input_file}: {err}")]
        json_report = data
        if gate.get("requires_full_window") is True:
            if report_is_full_window(json_report):
                checks.append(Check("PASS", "kpi_gate_full_window", f"{gate_id} report declares full-window coverage"))
            else:
                checks.append(Check("BLOCK", "kpi_gate_full_window_missing", f"{gate_id} requires full-window coverage metadata"))
    elif gate.get("requires_full_window") is True:
        checks.append(Check("BLOCK", "kpi_gate_full_window_missing", f"{gate_id} requires full-window metadata but input is not JSON"))

    for idx, threshold_row in enumerate(thresholds):
        if not isinstance(threshold_row, dict):
            checks.append(Check("BLOCK", "kpi_gate_threshold_invalid", f"{gate_id} threshold {idx} is not an object"))
            continue
        metric = threshold_row.get("metric")
        op = threshold_row.get("op")
        threshold = as_float(threshold_row.get("value"))
        if not isinstance(metric, str) or not isinstance(op, str) or threshold is None:
            checks.append(Check("BLOCK", "kpi_gate_threshold_invalid", f"{gate_id} threshold {idx} needs metric, op, numeric value"))
            continue
        source = str(threshold_row.get("source", "metrics"))
        try:
            observed = (
                load_metric_from_json(json_report, source, metric)
                if json_report is not None
                else load_metric_from_csv(input_path, metric)
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("BLOCK", "kpi_gate_metric_read_error", f"{gate_id} could not read {metric}: {exc}"))
            continue
        if observed is None:
            checks.append(Check("BLOCK", "kpi_gate_metric_missing", f"{gate_id} metric missing or nonnumeric: {metric}"))
            continue
        try:
            passed = compare_numeric(observed, op, threshold)
        except Exception as exc:  # noqa: BLE001
            checks.append(Check("BLOCK", "kpi_gate_threshold_invalid", f"{gate_id} invalid threshold for {metric}: {exc}"))
            continue
        if passed:
            checks.append(Check("PASS", "kpi_gate_metric", f"{gate_id} {metric}={observed:g} satisfies {op} {threshold:g}"))
        else:
            fail_status = threshold_row.get("fail_status", "BLOCK_KPI_THRESHOLD")
            checks.append(Check("BLOCK", "kpi_gate_metric", f"{gate_id} {metric}={observed:g} violates {op} {threshold:g}: {fail_status}"))

    return checks


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    config_path = project / CONFIG_FILE
    checks: list[Check] = []
    if not config_path.is_file():
        checks.append(Check("SKIPPED_NOT_CONFIGURED", "kpi_gates_missing", f"{CONFIG_FILE} is not configured"))
        return make_report(project, "tracegate_kpi_check", checks)

    config, err = load_json(config_path)
    if err or not isinstance(config, dict):
        checks.append(Check("BLOCK", "kpi_gates_parse_error", f"{CONFIG_FILE} parse failed: {err}"))
        return make_report(project, "tracegate_kpi_check", checks)

    gates = config.get("gates")
    if not isinstance(gates, list) or not gates:
        checks.append(Check("BLOCK", "kpi_gates_empty", f"{CONFIG_FILE} must contain non-empty gates[]"))
        return make_report(project, "tracegate_kpi_check", checks)

    mode = state_mode(project)
    for gate in gates:
        if not isinstance(gate, dict):
            checks.append(Check("BLOCK", "kpi_gate_invalid", "gate row is not an object"))
            continue
        checks.extend(check_gate(project, gate, mode))

    return make_report(project, "tracegate_kpi_check", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TraceGate numeric KPI gates.")
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(Path(args.project_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report("TraceGate KPI Check", report)
    return status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
