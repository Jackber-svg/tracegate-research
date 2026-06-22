"""Shared utilities for TraceGate Research runners."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


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
    except Exception as exc:  # noqa: BLE001 - runners report all parse/read failures
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
            if isinstance(obj, dict):
                rows.append(obj)
            else:
                errors.append(f"line {line_no}: JSON value is not an object")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"line {line_no}: {exc}")
    return rows, errors


def rel(project: Path, maybe_path: str) -> Path:
    p = Path(maybe_path)
    return p if p.is_absolute() else project / p


def overall_status(checks: list[Check]) -> str:
    skip_statuses = {"SKIPPED_NOT_CONFIGURED", "SKIPPED_NOT_APPLICABLE"}
    if any(c.status == "BLOCK" for c in checks):
        return "BLOCK"
    if any(c.status == "WARN" for c in checks):
        return "WARN"
    if checks and all(c.status in skip_statuses for c in checks):
        if any(c.status == "SKIPPED_NOT_CONFIGURED" for c in checks):
            return "SKIPPED_NOT_CONFIGURED"
        return "SKIPPED_NOT_APPLICABLE"
    return "PASS"


def status_code(status: str) -> int:
    if status == "BLOCK":
        return 2
    if status == "WARN":
        return 1
    return 0


def make_report(project: Path, name: str, checks: list[Check]) -> dict[str, Any]:
    return {
        "runner": name,
        "project_dir": str(project.resolve()),
        "status": overall_status(checks),
        "checks": [asdict(c) for c in checks],
    }


def print_report(title: str, report: dict[str, Any]) -> None:
    print(title)
    print(f"Project: {report['project_dir']}")
    print(f"Status: {report['status']}")
    print()
    for check in report["checks"]:
        print(f"{check['status']:<24} {check['code']:<34} {check['message']}")


def is_text_file(path: Path, sample_size: int = 4096) -> bool:
    try:
        data = path.read_bytes()[:sample_size]
    except Exception:
        return False
    if b"\x00" in data:
        return False
    return True
