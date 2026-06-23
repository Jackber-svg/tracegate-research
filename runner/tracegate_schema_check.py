#!/usr/bin/env python3
"""Validate core TraceGate files against bundled schemas where possible."""

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

from tracegate_common import Check, load_json, make_report, print_report, rel, status_code


REPO_ROOT = RUNNER_DIR.parent
SCHEMA_MAP = {
    "STATE.json": REPO_ROOT / "schemas" / "STATE.schema.json",
    "ARTIFACT_MANIFEST.json": REPO_ROOT / "schemas" / "ARTIFACT_MANIFEST.schema.json",
}

OPTIONAL_JSON_SCHEMA_MAP = {
    "ROOT_LOCK.json": REPO_ROOT / "schemas" / "ROOT_LOCK.schema.json",
    "LEGACY_GATE_BINDINGS.json": REPO_ROOT / "schemas" / "LEGACY_GATE_BINDINGS.schema.json",
}


def type_matches(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(type_matches(value, item) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return True


def resolve_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        return None
    node: Any = root_schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node if isinstance(node, dict) else None


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$", root_schema: dict[str, Any] | None = None) -> list[str]:
    if root_schema is None:
        root_schema = schema
    errors: list[str] = []
    if "$ref" in schema:
        resolved = resolve_ref(root_schema, str(schema["$ref"]))
        if resolved is None:
            return [f"{path}: unsupported or unresolved $ref {schema['$ref']!r}"]
        return validate_schema(value, resolved, path, root_schema)

    if "allOf" in schema:
        for idx, sub_schema in enumerate(schema["allOf"]):
            if isinstance(sub_schema, dict):
                errors.extend(validate_schema(value, sub_schema, f"{path}.allOf[{idx}]", root_schema))

    if "anyOf" in schema:
        matches = []
        for sub_schema in schema["anyOf"]:
            if isinstance(sub_schema, dict):
                sub_errors = validate_schema(value, sub_schema, path, root_schema)
                matches.append(not sub_errors)
        if not any(matches):
            errors.append(f"{path}: does not match anyOf")

    if "oneOf" in schema:
        match_count = 0
        for sub_schema in schema["oneOf"]:
            if isinstance(sub_schema, dict):
                sub_errors = validate_schema(value, sub_schema, path, root_schema)
                if not sub_errors:
                    match_count += 1
        if match_count != 1:
            errors.append(f"{path}: matches {match_count} oneOf branches, expected exactly 1")

    expected_type = schema.get("type")
    if isinstance(expected_type, (str, list)) and not type_matches(value, expected_type):
        errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")
        return errors

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']!r}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.match(str(schema["pattern"]), value):
            errors.append(f"{path}: does not match pattern {schema['pattern']}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required field {key}")
        if "minProperties" in schema and len(value) < int(schema["minProperties"]):
            errors.append(f"{path}: fewer than minProperties {schema['minProperties']}")
        properties = schema.get("properties", {})
        for key, sub_schema in properties.items():
            if key in value and isinstance(sub_schema, dict):
                errors.extend(validate_schema(value[key], sub_schema, f"{path}.{key}", root_schema))
        additional = schema.get("additionalProperties", True)
        if isinstance(additional, dict):
            for key, item in value.items():
                if key not in properties:
                    errors.extend(validate_schema(item, additional, f"{path}.{key}", root_schema))

    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(validate_schema(item, item_schema, f"{path}[{idx}]", root_schema))

    return errors


def validate_contract_text(project: Path) -> list[Check]:
    path = project / "CONTRACT.yaml"
    checks: list[Check] = []
    if not path.is_file():
        return [Check("BLOCK", "contract_missing", "CONTRACT.yaml is missing")]
    text = path.read_text(encoding="utf-8", errors="replace")
    required_tokens = ["version:", "project:", "rules:", "id:", "category:", "check_type:", "fail_level:"]
    missing = [token for token in required_tokens if token not in text]
    if missing:
        checks.append(Check("BLOCK", "contract_schema_minimal", f"CONTRACT.yaml missing tokens: {', '.join(missing)}"))
    else:
        checks.append(Check("PASS", "contract_schema_minimal", "CONTRACT.yaml has minimal required rule fields"))
    return checks


def validate_task_contract_text(project: Path) -> list[Check]:
    path = project / "TASK_CONTRACT.yaml"
    checks: list[Check] = []
    if not path.is_file():
        checks.append(Check("SKIPPED_NOT_CONFIGURED", "task_contract_missing", "TASK_CONTRACT.yaml is not configured"))
        return checks
    text = path.read_text(encoding="utf-8", errors="replace")
    required_tokens = ["version:", "task_id:", "objective:", "non_goals:", "allowed_actions:", "blocked_actions:"]
    missing = [token for token in required_tokens if token not in text]
    if missing:
        checks.append(Check("BLOCK", "task_contract_schema_minimal", f"TASK_CONTRACT.yaml missing tokens: {', '.join(missing)}"))
    else:
        checks.append(Check("PASS", "task_contract_schema_minimal", "TASK_CONTRACT.yaml has minimal required task-boundary fields"))
    if "expected_startup_status:" in text and "status:" not in text:
        checks.append(Check("BLOCK", "task_contract_expected_status_missing", "expected_startup_status is declared without a status field"))
    return checks


def run(project: Path) -> dict[str, Any]:
    project = project.resolve()
    checks: list[Check] = []
    for file_name, schema_path in SCHEMA_MAP.items():
        file_path = project / file_name
        if not file_path.is_file():
            checks.append(Check("BLOCK", "schema_input_missing", f"{file_name} is missing"))
            continue
        data, err = load_json(file_path)
        if err or data is None:
            checks.append(Check("BLOCK", "schema_input_parse_error", f"{file_name} parse failed: {err}"))
            continue
        schema, schema_err = load_json(schema_path)
        if schema_err or not isinstance(schema, dict):
            checks.append(Check("BLOCK", "schema_file_error", f"schema read failed for {file_name}: {schema_err}"))
            continue
        errors = validate_schema(data, schema)
        if errors:
            for error in errors:
                checks.append(Check("BLOCK", "schema_validate", f"{file_name} {error}"))
        else:
            checks.append(Check("PASS", "schema_validate", f"{file_name} matches bundled schema"))
    for file_name, schema_path in OPTIONAL_JSON_SCHEMA_MAP.items():
        file_path = project / file_name
        if not file_path.is_file():
            checks.append(Check("SKIPPED_NOT_CONFIGURED", "schema_optional_missing", f"{file_name} is not configured"))
            continue
        data, err = load_json(file_path)
        if err or data is None:
            checks.append(Check("BLOCK", "schema_input_parse_error", f"{file_name} parse failed: {err}"))
            continue
        schema, schema_err = load_json(schema_path)
        if schema_err or not isinstance(schema, dict):
            checks.append(Check("BLOCK", "schema_file_error", f"schema read failed for {file_name}: {schema_err}"))
            continue
        errors = validate_schema(data, schema)
        if errors:
            for error in errors:
                checks.append(Check("BLOCK", "schema_validate", f"{file_name} {error}"))
        else:
            checks.append(Check("PASS", "schema_validate", f"{file_name} matches bundled schema"))
    checks.extend(validate_contract_text(project))
    checks.extend(validate_task_contract_text(project))
    return make_report(project, "tracegate_schema_check", checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate TraceGate core file schemas.")
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(Path(args.project_dir))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report("TraceGate Schema Check", report)
    return status_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
