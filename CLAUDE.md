# TraceGate for Claude Code

This repository contains the TraceGate protocol for fail-closed, evidence-gated agent work.

Before modifying a project that claims to use TraceGate:

1. Read `references/protocol.md`.
2. Locate `STATE.json`, `CONTRACT.yaml`, `ARTIFACT_MANIFEST.json`, `DECISIONS.jsonl`, and `GATE_REPORTS/`.
3. Run the Startup Protocol from the protocol document.
4. Do not promote a checkpoint unless the Checkpoint Rule is satisfied.

If required state, contract, manifest, source, adapter, or gate artifacts are missing, report `BLOCK` and state exactly which artifact is missing.

Never treat a passing KPI as sufficient if source locks, equation-form gates, extension-residual gates, or external audit gates are unresolved.
