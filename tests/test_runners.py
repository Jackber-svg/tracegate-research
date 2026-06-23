from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "runner"
BASE = REPO / "examples" / "minimal_project"


def run_runner(script: str, project: Path) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(RUNNER / script), str(project), "--json"],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"{script} did not emit JSON\nstdout={proc.stdout}\nstderr={proc.stderr}") from exc
    return proc.returncode, payload


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class RunnerTests(unittest.TestCase):
    def make_project(self) -> Path:
        root = Path(self.tmp.name) / "project"
        shutil.copytree(BASE, root)
        return root

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tracegate-test-")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_minimal_project_passes_core_check(self) -> None:
        root = self.make_project()
        code, report = run_runner("tracegate_check.py", root)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS")

    def test_skipped_status_is_distinct(self) -> None:
        root = self.make_project()
        code, report = run_runner("tracegate_source_check.py", root)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "SKIPPED_NOT_CONFIGURED")
        self.assertEqual(report["checks"][0]["status"], "SKIPPED_NOT_CONFIGURED")

    def test_init_promote_and_fix_hashes(self) -> None:
        root = Path(self.tmp.name) / "fresh"
        subprocess.run([sys.executable, str(RUNNER / "tracegate_init.py"), str(root), "--project", "fresh"], cwd=REPO, check=True)
        code, report = run_runner("tracegate_check.py", root)
        self.assertEqual((code, report["status"]), (0, "PASS"))

        subprocess.run([sys.executable, str(RUNNER / "tracegate_promote.py"), str(root), "--checkpoint-id", "CHK-TEST"], cwd=REPO, check=True)
        state = json.loads((root / "STATE.json").read_text(encoding="utf-8"))
        self.assertEqual(state["mode"], "BASELINE")

        (root / "CONTRACT.yaml").write_text((root / "CONTRACT.yaml").read_text(encoding="utf-8") + "\n# test edit\n", encoding="utf-8")
        code, report = run_runner("tracegate_check.py", root)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "BLOCK")

        subprocess.run([sys.executable, str(RUNNER / "tracegate_fix_hashes.py"), str(root)], cwd=REPO, check=True)
        code, report = run_runner("tracegate_check.py", root)
        self.assertEqual((code, report["status"]), (0, "PASS"))

    def test_source_check_blocks_mismatch(self) -> None:
        root = self.make_project()
        write_json(
            root / "PARAMETER_REGISTRY.json",
            {
                "version": "1.0",
                "rows": [
                    {
                        "parameter": "D",
                        "value": {"type": "number", "data": 2.0, "unit": "m2/s"},
                        "baseline_allowed": True,
                        "source_status": "SOURCE_VERIFIED",
                        "source_anchor": {"source_id": "S1"},
                        "comparison": {"tolerance": 0.0},
                    }
                ],
            },
        )
        write_json(
            root / "SOURCE_MANIFEST.json",
            {
                "version": "1.0",
                "sources": [{"source_id": "S1"}],
                "values": [
                    {
                        "parameter": "D",
                        "encoded_value": {"type": "number", "data": 1.0, "unit": "m2/s"},
                        "original_value": {"type": "number", "data": 1.0, "unit": "m2/s"},
                    }
                ],
            },
        )
        code, report = run_runner("tracegate_source_check.py", root)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "BLOCK")

    def test_equation_check_blocks_forbidden_term(self) -> None:
        root = self.make_project()
        write_json(
            root / "EQUATION_MANIFEST.json",
            {
                "version": "1.0",
                "equations": [
                    {
                        "equation_id": "eq1",
                        "term_count": 1,
                        "variable_list": ["c"],
                        "nonlinearity_class": "linear",
                        "sign_vector": ["+"],
                        "required_terms": ["diffusion"],
                        "forbidden_terms": ["proxy"],
                    }
                ],
            },
        )
        write_json(
            root / "runtime_expression_dump.json",
            {
                "equations": [
                    {
                        "equation_id": "eq1",
                        "term_count": 1,
                        "variable_list": ["c"],
                        "nonlinearity_class": "linear",
                        "sign_vector": ["+"],
                        "terms": ["diffusion", "proxy"],
                        "expression": "diffusion + proxy",
                    }
                ]
            },
        )
        code, report = run_runner("tracegate_equation_check.py", root)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "BLOCK")

    def test_extension_scan_uses_contract_runtime_artifacts(self) -> None:
        root = self.make_project()
        (root / "custom_runtime.txt").write_text("active forbiddenToken here\n", encoding="utf-8")
        (root / "CONTRACT.yaml").write_text(
            (root / "CONTRACT.yaml").read_text(encoding="utf-8")
            + "\nparams:\n  runtime_artifacts:\n    - custom_runtime.txt\n",
            encoding="utf-8",
        )
        write_json(
            root / "EXTENSION_KEYWORD_MANIFEST.json",
            {
                "version": "1.0",
                "extensions": [
                    {
                        "extension_id": "ext",
                        "expected_switch_value": False,
                        "forbidden_tokens": ["forbiddenToken"],
                        "allowed_contexts": [],
                    }
                ],
            },
        )
        code, report = run_runner("tracegate_extension_scan.py", root)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "BLOCK")

    def test_schema_check_validates_p0_hardening_files(self) -> None:
        root = self.make_project()
        (root / "TASK_CONTRACT.yaml").write_text(
            "\n".join(
                [
                    'version: "1.0"',
                    'task_id: "P0_TEST"',
                    "objective:",
                    '  - "lock handoff"',
                    "non_goals:",
                    '  - "promote baseline"',
                    "allowed_actions:",
                    '  - "diagnostic_work"',
                    "blocked_actions:",
                    '  - "baseline_promotion"',
                    "expected_startup_status:",
                    '  status: "WARN"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        write_json(
            root / "ROOT_LOCK.json",
            {
                "version": "1.0",
                "authority_root": str(root),
                "project_root": str(root),
                "forbidden_authority_roots": [str(root.parent / "stale")],
                "path_policy": {"block_if_cwd_under_forbidden_root": True},
            },
        )
        write_json(
            root / "LEGACY_GATE_BINDINGS.json",
            {
                "version": "1.0",
                "bindings": [
                    {
                        "gate_id": "G001",
                        "status": "FAIL_CLOSED",
                        "machine_effect": {"blocks_baseline": True},
                    }
                ],
            },
        )
        code, report = run_runner("tracegate_schema_check.py", root)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS")
        messages = "\n".join(check["message"] for check in report["checks"])
        self.assertIn("ROOT_LOCK.json matches bundled schema", messages)
        self.assertIn("LEGACY_GATE_BINDINGS.json matches bundled schema", messages)
        self.assertIn("TASK_CONTRACT.yaml has minimal required task-boundary fields", messages)

    def test_core_check_does_not_execute_kpi_gates(self) -> None:
        root = self.make_project()
        write_json(
            root / "GATE_REPORTS" / "diagnostic_physical.json",
            {
                "full_window": True,
                "metrics": {"max_abs_current_residual": 0.2},
            },
        )
        write_json(
            root / "PHYSICAL_KPI_GATES.json",
            {
                "version": "1.0",
                "gates": [
                    {
                        "gate_id": "KPI001",
                        "input_file": "GATE_REPORTS/diagnostic_physical.json",
                        "requires_full_window": True,
                        "thresholds": [
                            {
                                "metric": "max_abs_current_residual",
                                "source": "metrics",
                                "op": "lt",
                                "value": 0.01,
                                "fail_status": "BLOCK_CURRENT_RESIDUAL_GT_0P01",
                            }
                        ],
                    }
                ],
            },
        )
        code, report = run_runner("tracegate_check.py", root)
        self.assertEqual((code, report["status"]), (0, "PASS"))

    def test_kpi_check_blocks_failed_metrics(self) -> None:
        root = self.make_project()
        write_json(
            root / "GATE_REPORTS" / "diagnostic_physical.json",
            {
                "window": {"coverage": "full"},
                "metrics": {"max_abs_current_residual": 0.2},
                "summary_rows": [{"metric": "cLi_CF_min_series", "value": "1.0"}],
            },
        )
        write_json(
            root / "PHYSICAL_KPI_GATES.json",
            {
                "version": "1.0",
                "gates": [
                    {
                        "gate_id": "KPI001",
                        "input_file": "GATE_REPORTS/diagnostic_physical.json",
                        "allowed_modes": ["STAGING"],
                        "requires_full_window": True,
                        "thresholds": [
                            {
                                "metric": "max_abs_current_residual",
                                "source": "metrics",
                                "op": "lt",
                                "value": 0.01,
                                "fail_status": "BLOCK_CURRENT_RESIDUAL_GT_0P01",
                            },
                            {
                                "metric": "cLi_CF_min_series",
                                "source": "summary_rows",
                                "op": "gt",
                                "value": 0.0,
                                "fail_status": "BLOCK_NEGATIVE_CLI_CF",
                            },
                        ],
                    }
                ],
            },
        )

        schema_code, schema_report = run_runner("tracegate_schema_check.py", root)
        self.assertEqual((schema_code, schema_report["status"]), (0, "PASS"))

        code, report = run_runner("tracegate_kpi_check.py", root)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "BLOCK")
        messages = "\n".join(check["message"] for check in report["checks"])
        self.assertIn("report declares full-window coverage", messages)
        self.assertIn("max_abs_current_residual=0.2 violates lt 0.01", messages)
        self.assertIn("cLi_CF_min_series=1 satisfies gt 0", messages)

    def test_kpi_check_requires_full_window_when_declared(self) -> None:
        root = self.make_project()
        write_json(root / "GATE_REPORTS" / "partial_physical.json", {"metrics": {"x": 1.0}})
        write_json(
            root / "PHYSICAL_KPI_GATES.json",
            {
                "version": "1.0",
                "gates": [
                    {
                        "gate_id": "KPI002",
                        "input_file": "GATE_REPORTS/partial_physical.json",
                        "requires_full_window": True,
                        "thresholds": [{"metric": "x", "op": "gt", "value": 0.0}],
                    }
                ],
            },
        )
        code, report = run_runner("tracegate_kpi_check.py", root)
        self.assertEqual((code, report["status"]), (2, "BLOCK"))
        messages = "\n".join(check["message"] for check in report["checks"])
        self.assertIn("requires full-window coverage metadata", messages)


if __name__ == "__main__":
    unittest.main()
