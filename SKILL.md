---
name: instruction-analyzer
description: "Analyzes agent instruction files and project prompts across coding-agent environments. Use this skill to audit instruction quality, count tokens, detect duplication, find circular references, and analyze which instruction files are loaded for a specific task or command."
---

# Instruction Analyzer

Respond in the same language as the user.

## Step 0: Environment Check

Try to verify the local environment first:

```bash
python3 --version && python3 -c "import tiktoken; print('tiktoken ok')"
```

If Python 3 and `tiktoken` are available, use accurate token counting.

If Python 3 is missing, continue in estimation mode and explain that counts are approximate.

If `tiktoken` is missing, continue in estimation mode and explain that counts are approximate.

In estimation mode, use:

`estimated_tokens ~= len(text) / 4`

Mark estimated counts with `~`.

## Step 1: Decide Analysis Mode

Offer four modes in the user's language:

1. Full instruction audit.
2. Specific task or command load analysis.
3. Instruction quality audit (static — checks structure exists).
4. Audit trail analysis (dynamic — checks enforcement is happening).

## Mode 1: Full Instruction Audit

### 1.1 Use the Project's Standard Entry Point

Use the project's standard agent instruction entry point in the current workspace.

Then discover additional instruction files by scanning the workspace for likely instruction sources (for example files or directories with names containing `agent`, `instruction`, `prompt`, `policy`, `rule`, `guide`, or `command`), instead of relying on a fixed directory list.

### 1.2 Build the Reference Graph

Starting from the entry point, traverse referenced files and build a dependency graph.

Follow references from patterns such as:

- `@path/to/file`
- Markdown links: `[label](./relative/path.md)`
- Bare paths like `docs/rules.md` or `./prompts/system.md`
- Explicitly named `.md`, `.txt`, `.yaml`, `.yml`, `.json` instruction files

Track visited files to avoid infinite loops.

### 1.3 Count Tokens Per File

If Python + `tiktoken` are available, use `scripts/token_counter.py` from this skill directory.

Example:

```bash
python3 <skill_dir>/scripts/token_counter.py file1.md file2.md file3.md
```

Otherwise, estimate using `len(content) / 4` and mark as approximate.

### 1.4 Detect Circular References

Use DFS or equivalent graph traversal and detect cycles where a chain returns to an earlier file.

Report each cycle explicitly as a path.

### 1.5 Detect Duplication and Redundancy

Assess duplication across files:

- same rule repeated verbatim
- near-duplicate guidance with different wording
- repeated examples with equivalent meaning

Assess redundancy within files:

- verbose preambles before actionable instructions
- long caveats that do not change behavior
- low-signal text not useful for agent execution

Provide approximate percentages with a short justification.

### 1.6 Produce the Report

Use this structure (headers can be translated to the user's language):

## Documentation Analysis Report

Entry point: `path/to/entry-file`
Total files: N
Total tokens: N
Duplication: ~N%
Redundancy: ~N%
Circular references: N

### Circular References

List each cycle, or `None found`.

### File Statistics

| File | Purpose | Tokens |
|---|---|---|
| `path/to/file` | One-sentence summary | 1234 |

### Key Findings

Include 2-4 concise bullets with the most important issues.

## Mode 2: Specific Task or Command Load Analysis

### 2.1 Get the Target Task

Ask the user which task, prompt, or command to analyze.

### 2.2 Determine Loaded Instruction Files

Infer likely load order based on the runtime's instruction model:

1. Start from the detected entry point (auto-detected in 1.1).
2. Add files explicitly imported or referenced by it.
3. Add skill or command files that match the task intent.
4. Add project-level policy files that are always included by references.

Read files in encountered order and record load sequence.

### 2.3 Collect Per-File Efficiency Metrics

For each loaded file, report:

- Total tokens
- Useful tokens for this task (estimated)
- `% useful = useful / total`
- Repeated references to already loaded files

### 2.4 Assess Global Efficiency

Estimate:

- Duplication % across loaded set
- Redundancy % across loaded set

### 2.5 Produce the Report

Use this structure:

## Task Instruction Analysis

Task: "..."
Total tokens loaded: N
Files read: N
Duplication: ~N%
Redundancy: ~N%

### Instruction Load Order

| # | File | Total Tokens | Useful Tokens | % Useful | Refs to Earlier Files |
|---|---|---:|---:|---:|---|
| 1 | `AGENTS.md` | 2400 | 1800 | 75% | — |

### Key Findings

Include 2-4 concise bullets.

## Mode 3: Instruction Quality Audit

### 3.1 Collect Target Files

Ask the user which instruction files to audit, or default to all instruction files discovered in Step 1.1.

### 3.2 Run Automated Checks

Use `scripts/quality_checker.py` from this skill directory:

```bash
python3 <skill_dir>/scripts/quality_checker.py --project-root /path/to/project file1.md file2.md
```

The `--project-root` flag tells the checker where to find `.claude/hooks/` and `.claude/settings.json` for hook enforcement checks. Defaults to the current working directory.

This checks 40 rules across 7 categories against each file and returns JSON with per-rule results and scores.

### 3.3 Review Automated Results

Parse the JSON output. For each file, review the failed rules and verify whether the automated detection is accurate. Adjust findings if the checker produced false positives.

For rules that require semantic judgment (STRUCT-04 competing instructions, STRUCT-02 reasoning quality), read the file and apply human-level analysis on top of the automated result.

### 3.4 Produce the Report

Use this structure:

## Instruction Quality Report

Files audited: N
Overall score: N%

### Scores by Category

| Category | Score | Weight | Passed | Total |
|---|---|---|---|---|
| Description | 85% | 20% | 5/6 | 6 |
| Structure | 66% | 15% | 4/6 | 6 |
| Agent Readiness | 50% | 15% | 2/4 | 4 |
| Hook Enforcement | 57% | 20% | 4/7 | 7 |
| Context Reset | 42% | 15% | 3/7 | 7 |
| Workflow Enforcement | 40% | 10% | 2/5 | 5 |
| Formatting | 80% | 5% | 4/5 | 5 |

### Per-File Results

For each file, list:

| Rule | Severity | Status | Detail |
|---|---|---|---|
| DESC-01 | Critical | PASS | OK |
| STRUCT-01 | High | FAIL | File has 220 lines (max 150) |

### Key Findings

Include 3-5 concise bullets with the most impactful issues and suggested fixes.

### Rule Reference

Rules are defined in `rules/quality-rules.md` within this skill directory.

Scoring weights: Description (20%) → Structure (15%) → Agent Readiness (15%) → Hook Enforcement (20%) → Context Reset (15%) → Workflow Enforcement (10%) → Formatting (5%).

## Mode 4: Audit Trail Analysis

Dynamic analysis mode — reads `.claude/audit.log` to verify enforcement is actually happening, not just configured.

Requires hooks to have been running and writing structured log entries. If no log exists, report that and recommend setting up RESET-07.

### 4.1 Run the Analyzer

Use `scripts/audit_trail_analyzer.py` from this skill directory:

```bash
python3 <skill_dir>/scripts/audit_trail_analyzer.py --project-root /path/to/project --days 30
```

Returns JSON with session compliance, hook failure patterns, and flags.

### 4.2 Produce the Report

Use this structure:

## Audit Trail Analysis

Period: last N days
Sessions audited: N
Total log entries: N

### Session Reset Compliance

| Metric | Value | Status |
|---|---|---|
| Resets triggered | 11/12 | Warning |
| Handoff read at start | 10/11 | Warning |
| Validation not bypassed | 11/11 | OK |
| Average reset timing | 2h 14m | OK |

### Hook Failure Patterns

| Hook | Passes | Failures |
|---|---|---|
| pre-commit | 47 | 12 |
| pre-push | 38 | 2 |

Most failed feature: notifications (avg 3.8 attempts)
Most reliable feature: auth (avg 1.1 attempts)

### Flags

List all actionable flags from the analysis.

## Implementation Notes

Token counter script path is relative to this file:

`scripts/token_counter.py`

If needed, create a temporary fallback counter:

```python
import json
import sys
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")
result = {}
for path in sys.argv[1:]:
    try:
        text = open(path, encoding="utf-8").read()
        result[path] = len(enc.encode(text))
    except Exception as e:
        result[path] = f"error: {e}"
print(json.dumps(result))
```

For large projects, run token counting in batches of 10-20 files.

When estimating duplication or redundancy, prefer conservative ranges and explain uncertainty briefly.

All user-facing communication must stay in the user's language.
