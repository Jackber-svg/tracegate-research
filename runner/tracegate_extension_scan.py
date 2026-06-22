#!/usr/bin/env python3
"""Scan runtime/source artifacts for forbidden residual extension tokens."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from tracegate_common import Check, is_text_file, load_json, make_report, print_report, rel, status_code


DEFAULT_TARGETS = ["MODEL_STATE.json", "runtime_expression_dump.json", "src"]


def parse_inline_list(value: str) -> list[str]:
    raw = value.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return []
    body = raw[1:-1].strip()
    if not body:
        return []
    return [part.strip().strip("'\"") for part in body.split(",") if part.strip()]


def contract_runtime_artifacts(project: Path) -> list[str]:
    path = project / "CONTRACT.yaml"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for idx, line in enumerate(lines):
        match = re.match(r"^(\s*)runtime_artifacts\s*:\s*(.*)$", line)
        if not match:
            continue
        base_indent = len(match.group(1))
        inline = parse_inline_list(match.group(2))
        if inline:
            return inline
        values: list[str] = []
        for child in lines[idx + 1 :]:
            child_indent = len(child) - len(child.lstrip(" "))
            stripped = child.strip()
            if not stripped:
                continue
            if child_indent <= base_indent:
                break
            item = re.match(r"^-\s*(.+)$", stripped)
            if item:
                values.append(item.group(1).strip().strip("'\""))
        return values
    return []


def iter_text_files(project: Path, target: str) -> tuple[list[Path], list[str]]:
    path = rel(project, target)
    errors: list[str] = []
    files: list[Path] = []
    if not path.exists():
        return files, errors
    if path.is_file():
        if is_text_file(path):
            files.append(path)
        return files, errors
    if path.is_dir():
        for item in path.rglob("*"):
            try:
                if item.is_symlink():
                    resolved = item.resolve()
                    if resolved.is_file() and is_text_file(resolved):
                        files.append(resolved)
                    continue
                if item.is_file() and is_text_file(item):
                    files.append(item)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{item}: {exc}")
    return files, errors


def line_allowed(line: str, allowed_contexts: list[str]) -> bool:
    if not allowed_contexts:
        return False
    return any(context and context in line for context in allowed_contexts)


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    checks: list[Check] = []
    manifest_path = project / "EXTENSION_KEYWORD_MANIFEST.json"
    if not manifest_path.exists():
        checks.append(Check("SKIPPED_NOT_CONFIGURED", "extension_scan_skipped", "EXTENSION_KEYWORD_MANIFEST.json is absent"))
        return make_report(project, "tracegate_extension_scan", checks)
    manifest, err = load_json(manifest_path)
    if err or not isinstance(manifest, dict):
        checks.append(Check("BLOCK", "extension_manifest_parse_error", f"EXTENSION_KEYWORD_MANIFEST.json parse failed: {err}"))
        return make_report(project, "tracegate_extension_scan", checks)
    targets = contract_runtime_artifacts(project) or manifest.get("runtime_artifacts") or manifest.get("scan_targets", DEFAULT_TARGETS)
    if not isinstance(targets, list):
        targets = DEFAULT_TARGETS
    files: list[Path] = []
    for target in targets:
        found, errors = iter_text_files(project, str(target))
        files.extend(found)
        for error in errors:
            checks.append(Check("WARN", "extension_scan_read_error", error))
    extensions = manifest.get("extensions")
    if not isinstance(extensions, list):
        checks.append(Check("BLOCK", "extension_manifest_shape", "EXTENSION_KEYWORD_MANIFEST.json must contain extensions[]"))
        return make_report(project, "tracegate_extension_scan", checks)
    if not files:
        checks.append(Check("WARN", "extension_scan_no_targets", "no readable runtime/source scan targets found"))
    for extension in extensions:
        if not isinstance(extension, dict):
            checks.append(Check("BLOCK", "extension_row_invalid", "extension row is not an object"))
            continue
        extension_id = str(extension.get("extension_id") or "<missing-id>")
        switch_value = extension.get("expected_switch_value")
        if switch_value is not False:
            checks.append(Check("SKIPPED_NOT_APPLICABLE", "extension_scan_not_core", f"{extension_id}: expected_switch_value is not false; scan not enforced"))
            continue
        forbidden_tokens = [str(t) for t in extension.get("forbidden_tokens", []) if str(t)]
        allowed_contexts = [str(c) for c in extension.get("allowed_contexts", []) if str(c)]
        if not forbidden_tokens:
            checks.append(Check("WARN", "extension_no_forbidden_tokens", f"{extension_id}: no forbidden_tokens declared"))
            continue
        hits: list[str] = []
        for file_path in files:
            try:
                for line_no, line in enumerate(file_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    for token in forbidden_tokens:
                        if token in line and not line_allowed(line, allowed_contexts):
                            hits.append(f"{file_path.relative_to(project)}:{line_no}:{token}")
            except Exception as exc:  # noqa: BLE001
                checks.append(Check("WARN", "extension_scan_read_error", f"{file_path}: {exc}"))
        if hits:
            checks.append(Check("BLOCK", "extension_forbidden_token", f"{extension_id}: forbidden token hits: {'; '.join(hits[:20])}"))
        else:
            checks.append(Check("PASS", "extension_forbidden_token", f"{extension_id}: forbidden tokens absent"))
    return make_report(project, "tracegate_extension_scan", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan TraceGate runtime artifacts for residual extension tokens.")
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(Path(args.project_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report("TraceGate Extension Scan", report)
    return status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
