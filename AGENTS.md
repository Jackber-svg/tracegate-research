# TraceGate Agent Instructions

Use TraceGate when working on a long-running project that needs file-grounded state, evidence, gate reports, decisions, or reproducible checkpoints.

## Required Reading

Before changing project state, read:

```text
references/protocol.md
```

At minimum, inspect these sections:

- Six Questions
- Modes and Gate Profiles
- Startup Protocol
- Checkpoint Rule
- Release Readiness Checklist

## Operating Rule

Do not rely on chat history as project authority. Load authority from files:

```text
STATE.json
CONTRACT.yaml
TASK_CONTRACT.yaml
ARTIFACT_MANIFEST.json
DECISIONS.jsonl
GATE_REPORTS/
PARAMETER_REGISTRY.json
SOURCE_MANIFEST.json
```

## Stop Conditions

Report `BLOCK` instead of continuing when:

- contract files are missing, unreadable, or hash-mismatched
- required manifests or gate inputs are missing
- artifact manifest hash does not match `STATE.json`
- source values, unit conversions, or implementation values cannot be reconciled
- `SOURCE_INCOMPLETE` lacks an accepted decision
- an extension is disabled but active runtime artifacts still contain forbidden tokens
- KPI/domain gates pass but equation-form gates fail
- external audit has unresolved `BLOCK` or `CRITICAL` findings

## Reporting Format

When reporting status, include:

```text
mode/profile
authority artifact
last checkpoint
gates run
open decisions
blocked actions
next allowed actions
files changed or required
```
