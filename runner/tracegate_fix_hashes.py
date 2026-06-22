#!/usr/bin/env python3
"""Refresh TraceGate Research hash links for an existing project.

This script updates hashes that are already declared in STATE.json and
ARTIFACT_MANIFEST.json. It does not add missing artifacts or decide that a
changed file is valid evidence; it only makes an intentional file update
machine-consistent after the user has accepted that update.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"BLOCK: failed to read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"BLOCK: {path} must contain a JSON object")
    return data


def json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_bytes(json_bytes(data))


def rel(project: Path, maybe_path: str) -> Path:
    p = Path(maybe_path)
    return p if p.is_absolute() else project / p


def update_hash(target: dict[str, Any], key: str, actual: str, label: str, changes: list[str]) -> bool:
    old = target.get(key)
    if old != actual:
        target[key] = actual
        changes.append(f"{label}: {old!r} -> {actual}")
        return True
    return False


def refresh(project: Path, dry_run: bool = False) -> dict[str, Any]:
    project = project.resolve()
    state_path = project / "STATE.json"
    manifest_path = project / "ARTIFACT_MANIFEST.json"
    if not state_path.is_file():
        raise SystemExit("BLOCK: STATE.json is missing")
    if not manifest_path.is_file():
        raise SystemExit("BLOCK: ARTIFACT_MANIFEST.json is missing")

    state = load_json(state_path)
    manifest = load_json(manifest_path)
    changes: list[str] = []
    errors: list[str] = []
    manifest_dirty = False

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise SystemExit("BLOCK: ARTIFACT_MANIFEST.json must contain artifacts[]")

    for idx, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"artifact row {idx} is not an object")
            continue
        if artifact.get("status") == "external":
            continue
        path_value = artifact.get("path")
        artifact_id = artifact.get("artifact_id", f"row-{idx}")
        if not path_value:
            errors.append(f"{artifact_id} has no path")
            continue
        path = rel(project, str(path_value))
        if not path.is_file():
            errors.append(f"{artifact_id} path missing: {path_value}")
            continue
        if update_hash(artifact, "hash", sha256_file(path), f"manifest.{artifact_id}.hash", changes):
            manifest_dirty = True

    contract = state.get("contract", {})
    files = contract.get("files", {}) if isinstance(contract, dict) else {}
    if isinstance(files, dict):
        for name in list(files):
            path = rel(project, str(name))
            if not path.is_file():
                errors.append(f"contract file missing: {name}")
                continue
            actual = sha256_file(path)
            if files.get(name) != actual:
                old = files.get(name)
                files[name] = actual
                changes.append(f"STATE.contract.files.{name}: {old!r} -> {actual}")

    current = state.get("current_artifact")
    if isinstance(current, dict) and current.get("path"):
        current_path = rel(project, str(current["path"]))
        if current_path.is_file():
            update_hash(current, "hash", sha256_file(current_path), "STATE.current_artifact.hash", changes)
        else:
            errors.append(f"current artifact path missing: {current['path']}")

    if errors:
        return {"status": "BLOCK", "project_dir": str(project), "changes": changes, "errors": errors}

    manifest_hash_before = sha256_file(manifest_path)
    manifest_hash_after = sha256_bytes(json_bytes(manifest)) if manifest_dirty else manifest_hash_before
    if state.get("artifact_manifest_hash") != manifest_hash_after:
        old = state.get("artifact_manifest_hash")
        state["artifact_manifest_hash"] = manifest_hash_after
        changes.append(f"STATE.artifact_manifest_hash: {old!r} -> {manifest_hash_after}")

    if manifest_hash_before != manifest_hash_after and not any(c.startswith("STATE.artifact_manifest_hash") for c in changes):
        changes.append("ARTIFACT_MANIFEST.json content changed")

    if not dry_run:
        write_json(manifest_path, manifest)
        write_json(state_path, state)

    return {
        "status": "PASS",
        "project_dir": str(project),
        "dry_run": dry_run,
        "changes": changes,
        "errors": [],
    }


def print_text(report: dict[str, Any]) -> None:
    print("TraceGate Hash Refresh")
    print(f"Project: {report['project_dir']}")
    print(f"Status: {report['status']}")
    if report.get("dry_run"):
        print("Mode: dry-run")
    if report["changes"]:
        print("\nChanges:")
        for change in report["changes"]:
            print(f"- {change}")
    else:
        print("\nNo hash updates needed.")
    if report["errors"]:
        print("\nErrors:")
        for error in report["errors"]:
            print(f"- {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh declared TraceGate hashes.")
    parser.add_argument("project_dir", nargs="?", default=".", help="TraceGate project directory")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)

    report = refresh(Path(args.project_dir), dry_run=args.dry_run)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)
    return 2 if report["status"] == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
