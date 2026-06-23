# TraceGate Research

TraceGate Research is a runner-backed governance protocol for long-running research-agent workflows. It keeps hypotheses, constraints, source evidence, decisions, artifacts, and checkpoints in versioned files rather than chat memory, so a new agent can recover project state from the repository alone.

Requires only Python 3.11+. No dependencies.

The protocol addresses a recurring failure mode in agent-assisted research: as context grows, early constraints become diluted, missing evidence is replaced by plausible proxies, and partial outputs are promoted as verified. This risk is acute in computational modelling, simulation, literature-derived parameterization, and research-code generation, where a coherent answer can be less useful than a principled stop.

TraceGate treats the workflow as an auditable state machine. Contracts define acceptable evidence, manifests bind artifacts to hashes, decision logs record exceptions, and gate reports control continuation. Dependency-free runners check state closure, schemas, decisions, source locks, equation forms, extension residues, and baseline promotion.

The runner layer automates the routine checks that agents most often skip. It can initialize a minimal project, verify hashes and manifests, repair declared hash chains after intentional edits, audit decisions, compare registered parameters against source manifests, detect equation-form drift, scan disabled extensions for residual tokens, evaluate configured numeric KPI thresholds, and promote only passing states to `BASELINE`.

TraceGate is fail-closed by default. It does not prove that a result is true, but makes unsupported continuation visible and mechanically harder. The current release includes schemas, a passing fixture, regression tests, GitHub Actions CI, and line-ending controls that keep cloned fixtures hash-stable across platforms.

## Design Goals

- Preserve research authority in files instead of chat history.
- Make constraints, source evidence, decisions, and checkpoints machine-checkable.
- Prevent proxy laundering, evidence drift, equation-form drift, and self-audit leniency.
- Provide dependency-free runners for state closure, schema checks, decision audits, source locks, equation-form checks, extension residual scans, and baseline promotion.
- Support cold-start handoff, where a new agent reconstructs state from the project directory.
- Keep cloned fixtures hash-stable across platforms.
- Keep failure visible by blocking unsafe continuation instead of silently repairing the story.

## P0 Handoff Hardening Pattern

TraceGate projects often start as a wrapper around an existing long-running research effort. In that stage the goal is not full scientific automation yet; it is to prevent the next agent from continuing from the wrong root, wrong task boundary, or wrong interpretation of a non-passing state.

For this P0 stage, use four optional but recommended files:

```text
TASK_CONTRACT.yaml          Current task objective, non-goals, allowed actions, blocked actions.
ROOT_LOCK.json              Authoritative project root and forbidden mirror/stale roots.
LEGACY_GATE_BINDINGS.json   Machine-readable binding from legacy gates to claim/promotion effects.
GATE_REPORTS/expected_warn_staging.json
                            Explicit explanation of expected WARN states in STAGING.
```

This pattern is useful when a project has duplicate working directories, old CSV gate tables, diagnostic branches that must not be promoted, or an expected `WARN` state caused by open blockers. It turns "this warning is intentional" into a file-grounded startup fact instead of a chat-memory explanation.

## Install for Codex

Use this repository as a Codex skill. The repository root contains `SKILL.md`, so Codex can discover the skill directly after installation.

Manual local install:

```powershell
git clone https://github.com/Jackber-svg/tracegate-research.git "$env:USERPROFILE\.codex\skills\tracegate"
```

On macOS or Linux:

```bash
git clone https://github.com/Jackber-svg/tracegate-research.git ~/.codex/skills/tracegate
```

Then start a new Codex session and ask:

```text
Use $tracegate to audit this project and tell me whether it can safely promote a verified checkpoint.
```

## Runners

TraceGate Research includes small, dependency-free runners for the core file closure loop:

```bash
python runner/tracegate_check.py examples/minimal_project
```

Expected result:

```text
TraceGate Research Check
Status: PASS
```

Available runners:

```text
runner/tracegate_check.py       Check required files, hashes, manifest closure, decisions, and checkpoint state.
runner/tracegate_init.py        Create a minimal TraceGate project skeleton.
runner/tracegate_fix_hashes.py  Refresh declared hashes after an intentional file update.
runner/tracegate_promote.py     Promote a passing project state to BASELINE.
runner/tracegate_schema_check.py    Validate core file schemas.
runner/tracegate_decision_audit.py  Audit decision status, approvals, and STATE sync.
runner/tracegate_source_check.py    Check parameter/source manifest consistency.
runner/tracegate_equation_check.py  Check declared equation form against runtime expression dumps.
runner/tracegate_extension_scan.py  Scan for forbidden residual extension tokens.
runner/tracegate_kpi_check.py       Check configured numeric KPI thresholds from PHYSICAL_KPI_GATES.json.
```

The runners are intentionally conservative. The core runner does not execute domain-specific gates. Focused runners can check declared source locks, equation forms, extension residues, and generic numeric KPI thresholds, but they still do not prove scientific correctness. Project owners remain responsible for choosing scientifically meaningful KPIs and thresholds.

Typical workflow:

```bash
python runner/tracegate_init.py path/to/project --project my_project
python runner/tracegate_check.py path/to/project
python runner/tracegate_fix_hashes.py path/to/project
python runner/tracegate_promote.py path/to/project
python runner/tracegate_schema_check.py path/to/project
python runner/tracegate_decision_audit.py path/to/project
python runner/tracegate_source_check.py path/to/project
python runner/tracegate_equation_check.py path/to/project
python runner/tracegate_extension_scan.py path/to/project
python runner/tracegate_kpi_check.py path/to/project
```

## Scope and Limitations

TraceGate Research is a file-grounded governance layer for research workflows. It is not a solver, sandbox, security boundary, distributed scheduler, or replacement for institutional review.

The runners validate declared research state: required files, schemas, hashes, manifests, decisions, source locks, equation forms, extension residues, generic KPI thresholds, and checkpoint promotion. They do not guarantee that a scientific result is true, that a model is physically valid, or that a domain-specific gate is sufficient.

TraceGate does not intercept arbitrary shell commands, enforce CPU or memory limits, encrypt or cryptographically sign local logs, protect raw experimental data from deletion, or coordinate multi-machine execution. Use operating-system permissions, containers, CI policy, backups, external review, and domain-specific validation for those layers.

Project owners remain responsible for writing the scientific gates that matter for their field. TraceGate makes those gates harder to skip and easier to audit.

## Use with Other Agents

Agents that do not support Codex skills can still use TraceGate Research by reading:

```text
AGENTS.md
references/protocol.md
```

For Claude Code, keep `CLAUDE.md` in the project root or copy its instructions into the target project.

## Core Files

```text
SKILL.md                 Codex skill entry
AGENTS.md                Universal agent entry
CLAUDE.md                Claude Code style entry
references/protocol.md   Full TraceGate Research protocol
agents/openai.yaml       Codex UI metadata
runner/                  Minimal state/hash/manifest/source/equation/KPI runners
schemas/                 JSON schemas for core TraceGate files
examples/minimal_project Minimal passing project fixture
```

## Core Rule

Do not trust memory, summaries, or good-looking outputs. Trust only files, hashes, gates, manifests, decisions, and reproducible artifacts.
