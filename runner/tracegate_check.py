#!/usr/bin/env python3
"""Minimal TraceGate Research runner.

This runner checks the file-grounded state closure that every TraceGate project
needs before an agent can safely continue:

- required authority files exist
- STATE.json has a valid minimal shape
- CONTRACT files listed in STATE.json exist and match their sha256 hashes
- ARTIFACT_MANIFEST.json matches STATE.artifact_manifest_hash
- manifest-listed local artifacts exist and match their hashes
- DECISIONS.jsonl has no malformed rows
- BASELINE mode has no open decisions

It is intentionally conservative. It does not prove scientific correctness and
does not execute domain gates. It catches the basic state, hash, and decision
failures that agents are most likely to hand-wave past.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


VALID_MODES = {"DISCOVERY", "STAGING", "VALIDATION", "BASELINE"}
VALID_PROFILES = {"lite", "full"}


@dataclass
class Check:
    status: str
    code: str
    message: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001 - report any parse/read failure
        return None, str(exc)


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return rows, [f"{path.name} does not exist"]
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                errors.append(f"line {line_no}: JSON value is not an object")
            else:
                rows.append(obj)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"line {line_no}: {exc}")
    return rows, errors


def rel(project: Path, maybe_path: str) -> Path:
    p = Path(maybe_path)
    return p if p.is_absolute() else project / p


class Runner:
    def __init__(self, project: Path):
        self.project = project.resolve()
        self.checks: list[Check] = []
        self.state: dict[str, Any] | None = None
        self.manifest: dict[str, Any] | None = None
        self.decisions: list[dict[str, Any]] = []

    def add(self, status: str, code: str, message: str) -> None:
        self.checks.append(Check(status, code, message))

    def require_file(self, name: str) -> Path:
        path = self.project / name
        if path.is_file():
            self.add("PASS", "file_exists", f"{name} exists")
        else:
            self.add("BLOCK", "missing_file", f"{name} is required but missing")
        return path

    def require_dir(self, name: str) -> Path:
        path = self.project / name
        if path.is_dir():
            self.add("PASS", "dir_exists", f"{name}/ exists")
        else:
            self.add("BLOCK", "missing_dir", f"{name}/ is required but missing")
        return path

    def check_required_files(self) -> None:
        self.require_file("STATE.json")
        self.require_file("CONTRACT.yaml")
        self.require_file("ARTIFACT_MANIFEST.json")
        self.require_file("DECISIONS.jsonl")
        self.require_dir("GATE_REPORTS")

    def check_state(self) -> None:
        path = self.project / "STATE.json"
        if not path.exists():
            return
        state, err = load_json(path)
        if err:
            self.add("BLOCK", "state_parse_error", f"STATE.json parse failed: {err}")
            return
        if not isinstance(state, dict):
            self.add("BLOCK", "state_type_error", "STATE.json must be a JSON object")
            return
        self.state = state
        required = ["project", "mode", "profile", "contract", "current_artifact", "artifact_manifest_hash", "open_decisions"]
        missing = [k for k in required if k not in state]
        if missing:
            self.add("BLOCK", "state_missing_fields", f"STATE.json missing fields: {', '.join(missing)}")
        else:
            self.add("PASS", "state_required_fields", "STATE.json required fields are present")
        mode = state.get("mode")
        profile = state.get("profile")
        if mode in VALID_MODES:
            self.add("PASS", "state_mode", f"mode={mode}")
        else:
            self.add("BLOCK", "state_mode_invalid", f"mode must be one of {sorted(VALID_MODES)}, got {mode!r}")
        if profile in VALID_PROFILES:
            self.add("PASS", "state_profile", f"profile={profile}")
        else:
            self.add("BLOCK", "state_profile_invalid", f"profile must be one of {sorted(VALID_PROFILES)}, got {profile!r}")

    def check_contract_hashes(self) -> None:
        if not self.state:
            return
        contract = self.state.get("contract", {})
        files = contract.get("files", {}) if isinstance(contract, dict) else {}
        if not isinstance(files, dict) or not files:
            self.add("BLOCK", "contract_files_missing", "STATE.contract.files must be a non-empty object")
            return
        for name, expected in files.items():
            path = rel(self.project, name)
            if not path.is_file():
                self.add("BLOCK", "contract_file_missing", f"contract file missing: {name}")
                continue
            actual = sha256_file(path)
            if actual == expected:
                self.add("PASS", "contract_hash", f"{name} hash matches")
            else:
                self.add("BLOCK", "contract_hash_mismatch", f"{name} hash mismatch: expected {expected}, actual {actual}")

    def check_artifact_manifest(self) -> None:
        path = self.project / "ARTIFACT_MANIFEST.json"
        if not path.exists():
            return
        manifest, err = load_json(path)
        if err:
            self.add("BLOCK", "manifest_parse_error", f"ARTIFACT_MANIFEST.json parse failed: {err}")
            return
        if not isinstance(manifest, dict):
            self.add("BLOCK", "manifest_type_error", "ARTIFACT_MANIFEST.json must be a JSON object")
            return
        self.manifest = manifest
        if "artifacts" not in manifest or not isinstance(manifest["artifacts"], list):
            self.add("BLOCK", "manifest_artifacts_missing", "ARTIFACT_MANIFEST.json must contain artifacts[]")
        else:
            self.add("PASS", "manifest_shape", "ARTIFACT_MANIFEST.json contains artifacts[]")
        if self.state:
            expected = self.state.get("artifact_manifest_hash")
            actual = sha256_file(path)
            if actual == expected:
                self.add("PASS", "artifact_manifest_hash", "ARTIFACT_MANIFEST.json hash matches STATE.artifact_manifest_hash")
            else:
                self.add("BLOCK", "artifact_manifest_hash_mismatch", f"artifact manifest hash mismatch: expected {expected}, actual {actual}")

    def check_manifest_artifacts(self) -> None:
        if not self.manifest:
            return
        artifacts = self.manifest.get("artifacts")
        if not isinstance(artifacts, list):
            return
        seen: set[str] = set()
        for idx, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                self.add("BLOCK", "manifest_artifact_type", f"artifact row {idx} is not an object")
                continue
            artifact_id = artifact.get("artifact_id")
            if not artifact_id:
                self.add("BLOCK", "manifest_artifact_id_missing", f"artifact row {idx} missing artifact_id")
            elif artifact_id in seen:
                self.add("BLOCK", "manifest_artifact_id_duplicate", f"duplicate artifact_id: {artifact_id}")
            else:
                seen.add(str(artifact_id))
            path_value = artifact.get("path")
            hash_value = artifact.get("hash")
            status = artifact.get("status", "unknown")
            if status == "external":
                self.add("PASS", "manifest_external_artifact", f"{artifact_id} is external")
                continue
            if not path_value:
                self.add("BLOCK", "manifest_path_missing", f"{artifact_id} missing path")
                continue
            path = rel(self.project, str(path_value))
            if not path.is_file():
                self.add("BLOCK", "manifest_artifact_missing", f"{artifact_id} path missing: {path_value}")
                continue
            if hash_value:
                actual = sha256_file(path)
                if actual == hash_value:
                    self.add("PASS", "manifest_artifact_hash", f"{artifact_id} hash matches")
                else:
                    self.add("BLOCK", "manifest_artifact_hash_mismatch", f"{artifact_id} hash mismatch: expected {hash_value}, actual {actual}")
            else:
                self.add("WARN", "manifest_artifact_hash_absent", f"{artifact_id} has no hash")

    def check_decisions(self) -> None:
        path = self.project / "DECISIONS.jsonl"
        rows, errors = read_jsonl(path)
        self.decisions = rows
        for err in errors:
            self.add("BLOCK", "decisions_parse_error", f"DECISIONS.jsonl {err}")
        if not errors:
            self.add("PASS", "decisions_parse", "DECISIONS.jsonl parses as JSONL")
        open_from_log = [r.get("decision_id", "<missing-id>") for r in rows if r.get("status") == "OPEN"]
        open_from_state = []
        if self.state and isinstance(self.state.get("open_decisions"), list):
            open_from_state = self.state.get("open_decisions", [])
        open_ids = sorted({str(x) for x in open_from_log + open_from_state})
        mode = self.state.get("mode") if self.state else None
        if mode == "BASELINE" and open_ids:
            self.add("BLOCK", "baseline_open_decisions", f"BASELINE cannot have open decisions: {', '.join(open_ids)}")
        elif open_ids:
            self.add("WARN", "open_decisions", f"open decisions present: {', '.join(open_ids)}")
        else:
            self.add("PASS", "open_decisions", "no open decisions")

    def check_current_artifact(self) -> None:
        if not self.state:
            return
        artifact = self.state.get("current_artifact")
        if not isinstance(artifact, dict):
            self.add("BLOCK", "current_artifact_missing", "STATE.current_artifact must be an object")
            return
        path_value = artifact.get("path")
        if not path_value:
            self.add("WARN", "current_artifact_path_missing", "STATE.current_artifact.path is absent")
            return
        path = rel(self.project, str(path_value))
        if not path.is_file():
            self.add("BLOCK", "current_artifact_missing_file", f"current artifact path missing: {path_value}")
            return
        expected = artifact.get("hash")
        if expected:
            actual = sha256_file(path)
            if actual == expected:
                self.add("PASS", "current_artifact_hash", "current artifact hash matches")
            else:
                self.add("BLOCK", "current_artifact_hash_mismatch", f"current artifact hash mismatch: expected {expected}, actual {actual}")
        else:
            self.add("WARN", "current_artifact_hash_absent", "current artifact has no hash")

    def check_last_checkpoint(self) -> None:
        if not self.state:
            return
        checkpoint = self.state.get("last_checkpoint")
        if not isinstance(checkpoint, dict):
            self.add("WARN", "last_checkpoint_absent", "STATE.last_checkpoint is absent or not an object")
            return
        report = checkpoint.get("gate_report")
        if report:
            report_path = rel(self.project, str(report))
            if report_path.is_file():
                self.add("PASS", "last_checkpoint_report", f"last checkpoint report exists: {report}")
            else:
                self.add("BLOCK", "last_checkpoint_report_missing", f"last checkpoint report missing: {report}")
        if checkpoint.get("all_required_gates_pass") is True:
            self.add("PASS", "last_checkpoint_pass", "last checkpoint declares all_required_gates_pass=true")
        else:
            self.add("WARN", "last_checkpoint_not_pass", "last checkpoint does not declare all_required_gates_pass=true")

    def run(self) -> dict[str, Any]:
        self.check_required_files()
        self.check_state()
        self.check_contract_hashes()
        self.check_artifact_manifest()
        self.check_manifest_artifacts()
        self.check_decisions()
        self.check_current_artifact()
        self.check_last_checkpoint()
        if any(c.status == "BLOCK" for c in self.checks):
            status = "BLOCK"
        elif any(c.status == "WARN" for c in self.checks):
            status = "WARN"
        else:
            status = "PASS"
        return {
            "project_dir": str(self.project),
            "status": status,
            "checks": [asdict(c) for c in self.checks],
        }


def print_text(report: dict[str, Any]) -> None:
    print("TraceGate Research Check")
    print(f"Project: {report['project_dir']}")
    print(f"Status: {report['status']}")
    print()
    for check in report["checks"]:
        print(f"{check['status']:<5} {check['code']:<34} {check['message']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run minimal TraceGate Research state checks.")
    parser.add_argument("project_dir", nargs="?", default=".", help="Project directory containing STATE.json")
    parser.add_argument("--json", action="store_true", help="Print JSON report instead of text")
    parser.add_argument("--report", help="Write JSON report to this file")
    args = parser.parse_args(argv)

    runner = Runner(Path(args.project_dir))
    report = runner.run()

    if args.report:
        out = rel(Path(args.project_dir).resolve(), args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)

    if report["status"] == "BLOCK":
        return 2
    if report["status"] == "WARN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
