#!/usr/bin/env python3
"""Promote a TraceGate Research project to BASELINE when core checks pass."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from tracegate_check import Runner


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"BLOCK: failed to read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"BLOCK: {path} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_check(project: Path) -> dict[str, Any]:
    return Runner(project).run()


def status_code(report: dict[str, Any]) -> int:
    if report["status"] == "BLOCK":
        return 2
    if report["status"] == "WARN":
        return 1
    return 0


def rel(project: Path, maybe_path: str) -> Path:
    p = Path(maybe_path)
    return p if p.is_absolute() else project / p


def ensure_gate_report(project: Path, report_path: str) -> dict[str, Any]:
    path = rel(project, report_path)
    if not path.is_file():
        raise SystemExit(f"BLOCK: gate report does not exist: {report_path}")
    report = load_json(path)
    all_required_gates_pass = report.get("all_required_gates_pass")
    if not isinstance(all_required_gates_pass, bool) or all_required_gates_pass is not True:
        raise SystemExit(f"BLOCK: gate report does not declare all_required_gates_pass=true: {report_path}")
    return report


def promote(project: Path, gate_report: str | None = None, checkpoint_id: str | None = None) -> dict[str, Any]:
    project = project.resolve()
    before = run_check(project)
    if before["status"] != "PASS":
        return {
            "status": "BLOCK",
            "project_dir": str(project),
            "reason": "pre-promotion tracegate_check did not PASS",
            "precheck": before,
        }

    state_path = project / "STATE.json"
    state = load_json(state_path)
    mode = state.get("mode")
    if mode == "DISCOVERY":
        return {
            "status": "BLOCK",
            "project_dir": str(project),
            "reason": "DISCOVERY mode cannot promote directly to BASELINE",
            "precheck": before,
        }
    if mode == "BASELINE":
        return {
            "status": "PASS",
            "project_dir": str(project),
            "reason": "project is already BASELINE",
            "precheck": before,
            "postcheck": before,
            "changed": False,
        }

    checkpoint = state.get("last_checkpoint")
    if not isinstance(checkpoint, dict):
        return {
            "status": "BLOCK",
            "project_dir": str(project),
            "reason": "STATE.last_checkpoint is missing",
            "precheck": before,
        }

    report_path = gate_report or checkpoint.get("gate_report")
    if not report_path:
        return {
            "status": "BLOCK",
            "project_dir": str(project),
            "reason": "no gate report provided and STATE.last_checkpoint.gate_report is absent",
            "precheck": before,
        }
    ensure_gate_report(project, str(report_path))

    timestamp = datetime.now(timezone.utc).isoformat()
    state["mode"] = "BASELINE"
    state["next_allowed_actions"] = ["continue_from_baseline"]
    state["blocked_actions"] = ["modify_baseline_without_staging", "promote_baseline_with_open_decisions"]
    state["open_decisions"] = []
    state["last_checkpoint"] = {
        "checkpoint_id": checkpoint_id or checkpoint.get("checkpoint_id") or "CHK-BASELINE-001",
        "timestamp": timestamp,
        "gate_report": str(report_path),
        "all_required_gates_pass": True,
    }
    write_json(state_path, state)

    after = run_check(project)
    return {
        "status": after["status"],
        "project_dir": str(project),
        "changed": True,
        "precheck": before,
        "postcheck": after,
    }


def print_text(report: dict[str, Any]) -> None:
    print("TraceGate Baseline Promotion")
    print(f"Project: {report['project_dir']}")
    print(f"Status: {report['status']}")
    if report.get("reason"):
        print(f"Reason: {report['reason']}")
    if report.get("changed"):
        print("Changed: STATE.json mode set to BASELINE")
    if report.get("postcheck"):
        print(f"Postcheck: {report['postcheck']['status']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote a TraceGate project to BASELINE.")
    parser.add_argument("project_dir", nargs="?", default=".", help="TraceGate project directory")
    parser.add_argument("--gate-report", help="Gate report path to bind as the baseline checkpoint")
    parser.add_argument("--checkpoint-id", help="Checkpoint id to write into STATE.json")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)

    report = promote(Path(args.project_dir), gate_report=args.gate_report, checkpoint_id=args.checkpoint_id)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)
    return status_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
