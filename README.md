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
| Instruction quality audit | Experimental, Claude-only. Checks instruction files against 40 rules across 7 categories. | Per-rule pass/fail, category scores, weighted overall score. |
| Audit trail analysis | Experimental, Claude-only. Parses `.claude/audit.log` to verify enforcement is happening. | Session reset compliance, hook failure patterns, actionable flags. |
| SDD workflow audit | Experimental, Claude-only. Checks project-level compliance with the five-layer SDD model. | Per-layer scores, per-check pass/fail, overall workflow score. |

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
- `scripts/skill_quality_checker.py` - automated quality rule checker (static).
- `scripts/audit_trail_analyzer.py` - audit log analyzer (dynamic).
- `scripts/sdd_workflow_checker.py` - SDD five-layer workflow checker (project-level).
- `rules/skill-quality-rules.md` - quality rule definitions with pass/fail examples.
- `rules/sdd-workflow-rules.md` - SDD workflow rule definitions with pass/fail examples.
- `instruction-analyzer.skill` - packaged artifact.

## Tips from authors
- Don't use one large file for all instructions.
- Keep individual files focused on specific topics or tasks.
- Use yaml format for metadata and instruction index.
