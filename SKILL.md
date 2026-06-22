---
name: tracegate
description: Fail-closed evidence and checkpoint governance for long-running research agent projects. Use when Codex needs to set up, audit, repair, or follow a gate-driven workflow for scientific modeling, computational simulation, research-code generation, literature-derived parameter audits, source provenance checks, agent handoffs, cold-start recovery, reproducible research checkpoints, or any research project where contracts, sources, artifacts, decisions, and gate reports must be file-grounded rather than remembered from chat.
---

# TraceGate Research

Use TraceGate Research to keep long-running research agent work restartable, auditable, and fail-closed.

## Core Rule

Do not rely on chat memory for project authority. Load state, contracts, manifests, decisions, gate reports, and source records from files.

## Required First Step

For any setup, audit, repair, or handoff task, read `references/protocol.md` before changing project state. Use only the sections needed for the task, but always check:

- `Six Questions`
- `Modes and Gate Profiles`
- `Startup Protocol`
- `Checkpoint Rule`
- `Release Readiness Checklist`

## Workflow

1. Locate or create the TraceGate Research project files:
   - `STATE.json`
   - `CONTRACT.yaml`
   - `ARTIFACT_MANIFEST.json`
   - `DECISIONS.jsonl`
   - `GATE_REPORTS/`
2. Run the startup protocol from `references/protocol.md`.
3. Treat missing required files, hash mismatches, unresolved `BLOCK` or `CRITICAL` findings, and undeclared proxy/source gaps as blockers.
4. For parameterized or literature-derived projects, require `PARAMETER_REGISTRY.json` and use `SOURCE_MANIFEST.json` when source locking is declared.
5. For tool-backed models, require `ADAPTER.yaml` and adapter-exported `MODEL_STATE.json`.
6. For baseline promotion, require all mode/profile gates to pass and zero open decisions.

## Fail-Closed Conditions

Stop and report `BLOCK` when:

- `CONTRACT.yaml` or listed task-contract files cannot be read or hash-verified.
- `ARTIFACT_MANIFEST.json` does not match `STATE.json`.
- A required gate is declared but its manifest or input artifact is missing.
- A parameter has `SOURCE_INCOMPLETE` without an accepted decision.
- A source value, encoded value, unit conversion, or implementation value cannot be reconciled.
- An extension is disabled but active runtime artifacts still contain forbidden tokens.
- KPI/domain metrics pass but `equation_form_gate` fails.
- External audit has unresolved `BLOCK` or `CRITICAL` findings.

## Output Style

When reporting, separate:

- current mode/profile
- authority artifact and last checkpoint
- gates run and status
- open decisions
- blocked actions
- next allowed actions
- files changed or required

Do not promote a checkpoint from prose alone. A checkpoint is valid only when the checkpoint rule in `references/protocol.md` is satisfied.
