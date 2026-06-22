# TraceGate

TraceGate is a fail-closed evidence gate protocol for long-running agent work.

It helps agents keep contracts, sources, artifacts, decisions, gate reports, and checkpoints in files instead of fragile chat memory.

## Install for Codex

Use this repository as a Codex skill. The repository root contains `SKILL.md`, so Codex can discover the skill directly after installation.

Manual local install:

```powershell
git clone https://github.com/Jackber-svg/tracegate-skill.git C:\Users\Administrator\.codex\skills\tracegate
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
