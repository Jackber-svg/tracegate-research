# TraceGate

TraceGate is a file-grounded governance protocol for long-running agent work. It is designed for tasks in which an AI agent must preserve constraints, evidence, intermediate decisions, and reproducible state across many turns, sessions, tools, and handoffs.

The motivation is a recurring failure mode in complex agent workflows: as context grows, early constraints become diluted, missing evidence is replaced by plausible proxies, and partial results are promoted as if they were verified. This tendency is especially harmful in scientific modeling, simulation, code generation, data pipelines, and literature-derived parameterization, where a complete-looking answer can be worse than an explicit stop.

TraceGate treats agent work as an auditable state machine rather than a conversational stream. Contracts define what counts as correct. Registries record where parameters and claims come from. Manifests bind artifacts to hashes. Decisions record human or external approvals. Gate reports determine whether the next action is allowed. A new agent should be able to recover the project state from files alone, without relying on chat memory.

The protocol is fail-closed by default. If a required source is incomplete, a unit conversion is unverified, an equation form has drifted, a disabled extension still appears in runtime artifacts, or an external audit reports unresolved findings, the project blocks until the issue is recorded and resolved. TraceGate does not claim that an output is true. It makes unsupported continuation harder than honest interruption.

TraceGate is not a model, solver, or benchmark. It is a reusable control layer for agent-operated projects that need reproducibility, provenance, cold-start recovery, and defensible checkpoint promotion.

## Design Goals

- Preserve project authority in files instead of chat history.
- Make constraints, source evidence, decisions, and checkpoints machine-checkable.
- Prevent proxy laundering, evidence drift, equation-form drift, and self-audit leniency.
- Support cold-start handoff, where a new agent reconstructs state from the project directory.
- Keep failure visible by blocking unsafe continuation instead of silently repairing the story.

## Install for Codex

Use this repository as a Codex skill. The repository root contains `SKILL.md`, so Codex can discover the skill directly after installation.

Manual local install:

```powershell
git clone https://github.com/Jackber-svg/tracegate-skill.git "$env:USERPROFILE\.codex\skills\tracegate"
```

On macOS or Linux:

```bash
git clone https://github.com/Jackber-svg/tracegate-skill.git ~/.codex/skills/tracegate
```

Then start a new Codex session and ask:

```text
Use $tracegate to audit this project and tell me whether it can safely promote a verified checkpoint.
```

## Use with Other Agents

Agents that do not support Codex skills can still use TraceGate by reading:

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
references/protocol.md   Full TraceGate protocol
agents/openai.yaml       Codex UI metadata
```

## Core Rule

Do not trust memory, summaries, or good-looking outputs. Trust only files, hashes, gates, manifests, decisions, and reproducible artifacts.
