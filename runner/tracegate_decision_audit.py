#!/usr/bin/env python3
"""Audit TraceGate DECISIONS.jsonl for unresolved or weakly approved decisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from tracegate_common import Check, load_json, make_report, print_report, read_jsonl, status_code


VALID_STATUSES = {"OPEN", "ACCEPTED", "REJECTED", "MITIGATED", "SUPERSEDED"}
VALID_SEVERITIES = {"INFO", "WARN", "BLOCK", "CRITICAL"}
APPROVAL_REQUIRED_KINDS = {
    "human_override",
    "threshold_change",
    "parameter_acceptance",
    "source_incomplete_resolution",
    "external_audit_resolution",
}
VALID_APPROVERS = {"human", "external_model", "separate_runner", "separate_agent"}


def open_from_state(project: Path) -> list[str]:
    state, err = load_json(project / "STATE.json")
    if err or not isinstance(state, dict):
        return []
    value = state.get("open_decisions")
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    checks: list[Check] = []
    rows, errors = read_jsonl(project / "DECISIONS.jsonl")
    for error in errors:
        checks.append(Check("BLOCK", "decisions_parse_error", error))
    if not errors:
        checks.append(Check("PASS", "decisions_parse", "DECISIONS.jsonl parses as JSONL"))

    seen: set[str] = set()
    open_ids: list[str] = []
    for idx, row in enumerate(rows, 1):
        decision_id = str(row.get("decision_id") or f"line-{idx}")
        if decision_id in seen:
            checks.append(Check("BLOCK", "decision_id_duplicate", f"duplicate decision_id: {decision_id}"))
        seen.add(decision_id)

        status = row.get("status")
        severity = row.get("severity")
        kind = row.get("decision_kind")
        if status not in VALID_STATUSES:
            checks.append(Check("BLOCK", "decision_status_invalid", f"{decision_id}: invalid status {status!r}"))
        if severity is not None and severity not in VALID_SEVERITIES:
            checks.append(Check("BLOCK", "decision_severity_invalid", f"{decision_id}: invalid severity {severity!r}"))
        if status == "OPEN":
            open_ids.append(decision_id)
        if status == "ACCEPTED" and kind in APPROVAL_REQUIRED_KINDS:
            approver = row.get("approved_by_type")
            approval_artifact = row.get("approval_artifact_id")
            if approver not in VALID_APPROVERS:
                checks.append(Check("BLOCK", "decision_approval_missing", f"{decision_id}: accepted {kind} lacks valid approved_by_type"))
            if not approval_artifact:
                checks.append(Check("WARN", "decision_approval_artifact_missing", f"{decision_id}: no approval_artifact_id"))
        if row.get("approved_by_type") == "agent":
            checks.append(Check("BLOCK", "decision_self_approval", f"{decision_id}: agent cannot approve its own exception"))

    state_open = sorted(open_from_state(project))
    log_open = sorted(open_ids)
    if state_open != log_open:
        checks.append(Check("BLOCK", "decision_sync_mismatch", f"STATE.open_decisions={state_open} but DECISIONS open={log_open}"))
    else:
        checks.append(Check("PASS", "decision_sync", "STATE.open_decisions matches DECISIONS.jsonl"))

    if open_ids:
        checks.append(Check("WARN", "open_decisions", f"open decisions present: {', '.join(sorted(open_ids))}"))
    else:
        checks.append(Check("PASS", "open_decisions", "no open decisions"))
    return make_report(project, "tracegate_decision_audit", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit TraceGate decisions.")
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(Path(args.project_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report("TraceGate Decision Audit", report)
    return status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
