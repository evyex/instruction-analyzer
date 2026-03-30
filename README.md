# Instruction Analyzer Skill

This skill analyzes agent instruction systems in a project.

## What it does

- Finds the project's standard agent instruction entry point.
- Traverses referenced instruction files.
- Counts tokens per file (exact with `tiktoken`, or estimated fallback).
- Detects circular references.
- Estimates duplication and redundancy.
- Produces reports for full audits and task-specific instruction loads.

## Modes

| Mode | Purpose | Output |
|---|---|---|
| Full instruction audit | Scans instruction files from the project entry point and builds a dependency graph. | Token totals, cycles, duplication, redundancy, per-file stats. |
| Task-specific load analysis | Analyzes one concrete user task or command and inferred load chain. | File load order, useful-token estimates, efficiency findings. |

## Output Example

```text
Documentation Analysis Report
Entry point: AGENTS.md
Total files: 7
Total tokens: 9,840
Duplication: ~18%
Redundancy: ~12%
Circular references: 1

Circular References
- AGENTS.md -> docs/policies.md -> docs/shared.md -> AGENTS.md

File Statistics
|        File       |              Purpose              | Tokens |
|-------------------|-----------------------------------|--------|
| AGENTS.md         | Global routing and priority rules | 2,430  |
| docs/policies.md  | Repository-wide constraints       | 1,950  |
| prompts/review.md | Review task workflow              | 1,120  |

Key Findings
- Two policy files repeat the same commit rules with minor wording changes.
- One cycle is present in the shared reference chain.
- Task-specific prompts are concise and mostly high-signal.
```

## Files

- `SKILL.md` - skill behavior and workflow.
- `scripts/token_counter.py` - exact token counting helper.
- `instruction-analyzer.skill` - packaged artifact.

## Tips from authors
- Don't use one large file for all instructions.
- Keep individual files focused on specific topics or tasks.
- Use yaml format for metadata and instruction index.
