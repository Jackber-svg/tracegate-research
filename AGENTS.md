# TraceGate Research Agent Instructions

Use TraceGate Research when working on a long-running research project that needs file-grounded state, source evidence, gate reports, decisions, or reproducible checkpoints.

## Required Reading

Before changing project state, read:

```text
references/protocol.md
```

For literature-derived parameter extraction or source-evidence audits, also read:

```text
references/literature_extraction.md
```

At minimum, inspect these sections:

- Six Questions
- Modes and Gate Profiles
- Startup Protocol
- Checkpoint Rule
- Release Readiness Checklist

For literature extraction, run the full R-1 to R5 workflow, including the R0.5 primary-source chain check, before strengthening any registry `source_status` or treating a parameter as source-supported.

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

## Minimal Runner

If `runner/tracegate_check.py` is available, run it before continuing:

```bash
python runner/tracegate_check.py <project_dir>
```

Treat runner `BLOCK` as authoritative. Treat runner `WARN` as unresolved unless the user or an external audit explicitly accepts it.

## Stop Conditions

Report `BLOCK` instead of continuing when:

- contract files are missing, unreadable, or hash-mismatched
- required manifests or gate inputs are missing
- artifact manifest hash does not match `STATE.json`
- source values, unit conversions, or implementation values cannot be reconciled
- a registry value cannot be found in the cited source evidence
- a baseline parameter relies on a relayed source without `primary_source_id` and a verified `provenance_chain`
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
