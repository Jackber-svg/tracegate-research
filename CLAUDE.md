# TraceGate Research for Claude Code

This repository contains the TraceGate Research protocol for fail-closed, evidence-gated research agent work.

Before modifying a research project that claims to use TraceGate Research:

1. Read `references/protocol.md`.
2. Locate `STATE.json`, `CONTRACT.yaml`, `ARTIFACT_MANIFEST.json`, `DECISIONS.jsonl`, and `GATE_REPORTS/`.
3. Run `python runner/tracegate_check.py <project_dir>` if the runner is available.
4. Run the Startup Protocol from the protocol document.
5. Do not promote a checkpoint unless the Checkpoint Rule is satisfied.

For literature-derived parameter extraction or source-evidence audits, read `references/literature_extraction.md` and run the full R-1 to R5 workflow, including the R0.5 primary-source chain check, before strengthening `source_status` or treating a registry value as source-supported.

If required state, contract, manifest, source, adapter, or gate artifacts are missing, report `BLOCK` and state exactly which artifact is missing.

Never treat a passing KPI as sufficient if source locks, equation-form gates, extension-residual gates, or external audit gates are unresolved.
