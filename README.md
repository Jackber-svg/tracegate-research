# TraceGate Research

TraceGate Research is a file-grounded governance protocol for long-running research agent work. It is designed for tasks in which an AI agent must preserve hypotheses, constraints, source evidence, intermediate decisions, computational artifacts, and reproducible state across many turns, sessions, tools, and handoffs.

The motivation is a recurring failure mode in complex research workflows: as context grows, early constraints become diluted, missing evidence is replaced by plausible proxies, and partial results are promoted as if they were verified. This tendency is especially harmful in scientific modeling, computational simulation, research-code generation, data-analysis pipelines, and literature-derived parameterization, where a complete-looking answer can be worse than an explicit stop.

TraceGate Research treats agent-assisted research as an auditable state machine rather than a conversational stream. Contracts define what counts as acceptable evidence. Registries record where parameters and claims come from. Manifests bind artifacts to hashes. Decisions record human or external approvals. Gate reports determine whether the next action is allowed. A new agent should be able to recover the research state from files alone, without relying on chat memory.

The protocol is fail-closed by default. If a required source is incomplete, a unit conversion is unverified, an equation form has drifted, a disabled extension still appears in runtime artifacts, or an external audit reports unresolved findings, the project blocks until the issue is recorded and resolved. TraceGate Research does not claim that an output is true. It makes unsupported continuation harder than honest interruption.

TraceGate Research is not a model, solver, benchmark, or production engineering framework. It is a reusable control layer for research projects that need provenance, reproducibility, cold-start recovery, literature-aware parameter tracking, and defensible checkpoint promotion.

## Design Goals

- Preserve research authority in files instead of chat history.
- Make constraints, source evidence, decisions, and checkpoints machine-checkable.
- Prevent proxy laundering, evidence drift, equation-form drift, and self-audit leniency.
- Support cold-start handoff, where a new agent reconstructs state from the project directory.
- Keep failure visible by blocking unsafe continuation instead of silently repairing the story.

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
```

The runners are intentionally conservative. They do not prove scientific correctness or execute domain-specific gates. They verify the basic file-grounded closure that an agent must not hand-wave: required files, contract hashes, artifact manifest hash, manifest-listed artifact hashes, decision log parsing, open decisions, current artifact hash, and last checkpoint report.

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
```

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
runner/                  Minimal state/hash/manifest/source/equation runners
schemas/                 JSON schemas for core TraceGate files
examples/minimal_project Minimal passing project fixture
```

## Core Rule

Do not trust memory, summaries, or good-looking outputs. Trust only files, hashes, gates, manifests, decisions, and reproducible artifacts.
