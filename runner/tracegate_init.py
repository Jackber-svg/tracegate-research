#!/usr/bin/env python3
"""Create a minimal TraceGate Research project skeleton."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


VALID_MODES = {"DISCOVERY", "STAGING", "VALIDATION"}
VALID_PROFILES = {"lite", "full"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "tracegate-project"


def ensure_writable(project: Path, force: bool) -> None:
    required = ["STATE.json", "CONTRACT.yaml", "ARTIFACT_MANIFEST.json", "DECISIONS.jsonl"]
    existing = [name for name in required if (project / name).exists()]
    if existing and not force:
        raise SystemExit(
            "BLOCK: project already contains TraceGate files. "
            f"Use --force to overwrite: {', '.join(existing)}"
        )


def init_project(project: Path, project_name: str, mode: str, profile: str, force: bool) -> dict:
    if mode not in VALID_MODES:
        raise SystemExit(f"BLOCK: mode must be one of {sorted(VALID_MODES)}")
    if profile not in VALID_PROFILES:
        raise SystemExit(f"BLOCK: profile must be one of {sorted(VALID_PROFILES)}")

    project = project.resolve()
    ensure_writable(project, force)
    (project / "GATE_REPORTS").mkdir(parents=True, exist_ok=True)

    contract_text = f"""version: "1.0"
project: "{project_name}"
includes: []
rules:
  - id: CORE01
    layer: core
    category: contract_load_gate
    check_type: contract_load_check
    input_file: CONTRACT.yaml
    params:
      contract_files:
        - CONTRACT.yaml
      expected_hash_source: STATE.json:$.contract.files
      require_readable: true
      block_on_hash_mismatch: true
    fail_level: BLOCK
    output_artifact: GATE_REPORTS/contract_load.json
"""
    write_text(project / "CONTRACT.yaml", contract_text)
    write_text(project / "DECISIONS.jsonl", "")

    bootstrap = {
        "gate_report_id": "BOOTSTRAP-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "all_required_gates_pass": True,
        "checks": [
            {
                "status": "PASS",
                "code": "tracegate_init",
                "message": "Minimal TraceGate project initialized.",
            }
        ],
    }
    write_json(project / "GATE_REPORTS" / "bootstrap.json", bootstrap)

    manifest = {
        "version": "1.0",
        "artifacts": [
            {
                "artifact_id": "ART-CONTRACT-001",
                "type": "contract",
                "path": "CONTRACT.yaml",
                "hash": sha256_file(project / "CONTRACT.yaml"),
                "status": "current",
                "description": "Project contract.",
            },
            {
                "artifact_id": "ART-DECISIONS-001",
                "type": "decision_log",
                "path": "DECISIONS.jsonl",
                "hash": sha256_file(project / "DECISIONS.jsonl"),
                "status": "current",
                "description": "Decision log.",
            },
            {
                "artifact_id": "ART-GATE-BOOTSTRAP-001",
                "type": "gate_report",
                "path": "GATE_REPORTS/bootstrap.json",
                "hash": sha256_file(project / "GATE_REPORTS" / "bootstrap.json"),
                "status": "verified",
                "description": "Initialization gate report.",
            },
        ],
    }
    write_json(project / "ARTIFACT_MANIFEST.json", manifest)

    contract_hash = sha256_file(project / "CONTRACT.yaml")
    state = {
        "project": project_name,
        "mode": mode,
        "profile": profile,
        "contract": {
            "files": {
                "CONTRACT.yaml": contract_hash,
            },
            "primary": "CONTRACT.yaml",
        },
        "current_artifact": {
            "artifact_id": "ART-CONTRACT-001",
            "type": "contract",
            "path": "CONTRACT.yaml",
            "hash": contract_hash,
        },
        "last_checkpoint": {
            "checkpoint_id": "CHK-BOOTSTRAP-001",
            "timestamp": bootstrap["timestamp"],
            "gate_report": "GATE_REPORTS/bootstrap.json",
            "all_required_gates_pass": True,
        },
        "artifact_manifest_hash": sha256_file(project / "ARTIFACT_MANIFEST.json"),
        "external_anchor": {
            "type": "none",
            "value": None,
        },
        "next_allowed_actions": [
            "continue_staging" if mode == "STAGING" else "continue_discovery",
        ],
        "blocked_actions": [
            "promote_baseline_without_validation",
        ],
        "open_decisions": [],
    }
    write_json(project / "STATE.json", state)

    return {
        "status": "PASS",
        "project_dir": str(project),
        "project": project_name,
        "mode": mode,
        "profile": profile,
        "created": [
            "STATE.json",
            "CONTRACT.yaml",
            "ARTIFACT_MANIFEST.json",
            "DECISIONS.jsonl",
            "GATE_REPORTS/bootstrap.json",
        ],
    }


def print_text(report: dict) -> None:
    print("TraceGate Project Init")
    print(f"Project: {report['project_dir']}")
    print(f"Status: {report['status']}")
    print(f"Mode/Profile: {report['mode']} / {report['profile']}")
    print("\nCreated:")
    for item in report["created"]:
        print(f"- {item}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a minimal TraceGate project.")
    parser.add_argument("project_dir", help="Target project directory")
    parser.add_argument("--project", help="Project name. Defaults to directory name.")
    parser.add_argument("--mode", default="STAGING", choices=sorted(VALID_MODES))
    parser.add_argument("--profile", default="lite", choices=sorted(VALID_PROFILES))
    parser.add_argument("--force", action="store_true", help="Overwrite existing TraceGate files")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)

    project = Path(args.project_dir)
    name = args.project or slug(project.name)
    report = init_project(project, name, args.mode, args.profile, args.force)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
