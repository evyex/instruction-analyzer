# Quality Audit Rules

Rules for evaluating instruction file quality. Each rule has a severity, check logic, and pass/fail examples.

## File Types

The checker auto-detects three file types and adjusts which rules apply:

| File type | Detection | Skipped rules |
|---|---|---|
| **skill** | Has YAML frontmatter with `description`, or filename is `SKILL.md` | None — all 40 rules apply |
| **command** | Lives under `.claude/commands/` or a `commands/` directory | DESC-01–06, FMT-01 (no frontmatter) |
| **config** | `CLAUDE.md`, `AGENTS.md`, or similar root-level config | DESC-01–06, AGENT-01–04, FMT-01 |

Skipped rules are marked N/A and excluded from scoring. The overall score is renormalized to the applicable weight.

## Scoring Weights

| Category | Weight |
|---|---|
| Description | 20% |
| Structure | 15% |
| Agent Readiness | 15% |
| Hook Enforcement | 20% |
| Context Reset | 15% |
| Workflow Enforcement | 10% |
| Formatting | 5% |

Category score = (rules passed / total rules in category) * 100.
Overall score = weighted average of category scores.

---

## Description Rules

### DESC-01: Description field exists (Critical)

Frontmatter must contain a `description` field.

```yaml
# FAIL
---
name: my-skill
---

# PASS
---
name: my-skill
description: "Use when the user needs X — returns Y."
---
```

### DESC-02: Description is a single line (Critical)

Multi-line descriptions break agent routing silently.

```yaml
# FAIL
description: "Use when the user wants to analyze competitors.
  Returns a markdown report with sections for each competitor."

# PASS
description: "Use when the user wants to analyze competitors. Returns a markdown report with sections for each competitor."
```

### DESC-03: Trigger condition present (Critical)

Description must contain an explicit trigger condition like "Use when...", "Invoke when...", or "Trigger when...".

```yaml
# FAIL
description: "Competitive analysis skill for market research."

# PASS
description: "Use when asked to analyze competitors, map a market, or answer 'who are the players in X' — returns a structured markdown competitive analysis."
```

### DESC-04: No vague language (High)

Description must not contain: "helps with", "assists with", "handles", "deals with".

```yaml
# FAIL
description: "Helps with writing tasks and assists with document creation."

# PASS
description: "Use when drafting a client-facing proposal — takes a brief and returns a formatted PDF-ready proposal with exec summary, scope, and pricing sections."
```

### DESC-05: Names the output artifact (High)

Description must name the output type (markdown, JSON, report, spec, etc.).

```yaml
# FAIL
description: "Use when the user needs a summary of a meeting."

# PASS
description: "Use when the user needs a summary of a meeting — returns a markdown file with sections: decisions, action items (owner + deadline), and open questions."
```

### DESC-06: 80+ characters (High)

Description must be at least 80 characters to function as a routing signal.

```yaml
# FAIL — 42 chars
description: "Use when writing tests for new features."

# PASS — 96 chars
description: "Use when writing tests for a new feature or bug fix — enforces TDD: test file first, then implementation."
```

---

## Structure Rules

### STRUCT-01: Under 150 lines (High)

File must stay under 150 lines. Move examples to a subfolder if needed.

```
# FAIL
[file with 220 lines of instructions, examples, edge cases all in one]

# PASS
[core SKILL.md is 95 lines — examples live in /examples/example-output.md]
```

### STRUCT-02: Contains reasoning (High)

File must contain reasoning or principles, not just procedural steps. Look for "why", "because", "the goal is", "this matters", "the reason".

```markdown
# FAIL
## Steps
1. Read the input
2. Write the tests
3. Run the tests
4. Write the implementation

# PASS
## Why this order matters
Tests are written first because they define the contract, not verify it.
Writing implementation first produces tests that mirror code rather than
specify behavior. If you're tempted to skip — that's a signal the
requirement is unclear. Stop and clarify before continuing.

## Steps
1. Read the input
2. Write the tests
...
```

### STRUCT-03: Output format specified (High)

Output format must be explicitly defined — not just "produce a summary".

```markdown
# FAIL
Produce a summary of the findings.

# PASS
## Output format
Return a markdown document with exactly these sections:
- ## Summary (3 sentences max)
- ## Findings (bullet list, one finding per bullet)
- ## Recommended actions (numbered list with owner and deadline)
Do not add additional sections.
```

### STRUCT-04: No competing instructions (High)

No contradictory instructions within the same file.

```markdown
# FAIL
Always include a confidence score with every claim.
...
Keep responses concise — omit scores and metadata unless asked.

# PASS
Include a confidence score with every claim.
If the user asks for a concise response, move scores to a collapsed
footnote section rather than omitting them.
```

### STRUCT-05: Edge cases documented (Medium)

At least 3 conditional statements covering edge cases (if/when/unless patterns).

```markdown
# FAIL
Analyze the provided data and return insights.

# PASS
## Edge cases
- If the input CSV has no header row, stop and ask the user to confirm column names
- If a data column is more than 30% null, flag it as unreliable
- If the user provides more than one file, process them independently and note conflicts
- Never infer currency — if units are ambiguous, ask
```

### STRUCT-06: Example present (Medium)

File must contain at least one example for pattern matching, either inline or in an examples subfolder.

```markdown
# FAIL
[SKILL.md with instructions only, no examples]

# PASS
## Example output
**Input:** "Analyze the CRM market for a mid-market buyer"
**Output:**
## Salesforce
- Market position: dominant, 23% share
- Weakness: pricing, complexity for teams under 50
```

---

## Agent Readiness Rules

### AGENT-01: Contract framing (High)

Output must be framed as a contract with explicit INPUT and OUTPUT sections.

```markdown
# FAIL
This skill helps you write PRDs from a feature request.

# PASS
## Contract
INPUT: A feature request in plain English (1 sentence to 1 paragraph)
OUTPUT: A markdown PRD with sections — Problem, Goals, Non-goals, User stories, Success metrics
PRECONDITION: Input must describe a user-facing feature, not an infrastructure task
INVARIANT: Never include implementation details — spec the what, not the how
```

### AGENT-02: Testable success criteria (High)

Success criteria must be testable and verifiable — "done when X", "verify Y returns Z".

```markdown
# FAIL
The skill is complete when the PRD looks good.

# PASS
## Done when
- All five sections are present and non-empty
- Each user story follows "As a [role], I want [action], so that [outcome]"
- At least one success metric is measurable (contains a number or percentage)
- No section says "TBD" or "to be determined"
```

### AGENT-03: Composability documented (Medium)

Must state what receives the output downstream and in what format.

```markdown
# FAIL
Returns a list of GitHub issues.

# PASS
## Handoff
Output is a JSON array consumed by the github-issue-creator skill.
Each item must have: title (string), body (string), labels (array), milestone (string or null).
Do not include markdown formatting inside the body field — the next skill handles that.
```

### AGENT-04: Evaluator separation (Medium)

If the skill produces reviewed output, evaluator/QA separation must be acknowledged.

```markdown
# FAIL
[Skill that generates and self-reviews code with no separation]

# PASS
## Review boundary
This skill generates the draft. It does NOT self-review.
Pass the output to the code-review skill for evaluation.
If no reviewer is available, flag the output as "unreviewed draft".
```

---

## Workflow Enforcement Rules

### FLOW-01: Checkpoints defined (Medium)

Must define stopping conditions — "do not proceed until X".

```markdown
# FAIL
Write the tests, then the implementation, then commit.

# PASS
1. Write the test file
2. **STOP — run `npm test` and confirm it fails before continuing**
3. Write the implementation
4. **STOP — run `npm test` and confirm it passes. Do not proceed to commit.**
5. Commit with message format: `feat: [description] (test-first)`
```

### FLOW-02: Context reset points (Medium)

Long workflows must identify where a fresh agent can pick up.

```markdown
# FAIL
[15-step workflow with no break points]

# PASS
## Session boundary
This workflow is split into two sessions. End session 1 after step 6.
Before ending, write handoff.md with:
- Completed steps and their outcomes
- Current file states that were modified
- Exact next step for session 2 to begin from
- Any blockers or open questions
```

### FLOW-03: Hardwired steps flagged (Medium)

Steps enforced by hooks or scripts must say so, not rely on plain English.

```markdown
# FAIL
Always run the linter before committing.

# PASS
## Enforced via hook — do not rely on this file
Linting before commit is enforced by the pre-commit hook in .claude/hooks/.
This skill does not need to instruct the agent to lint — the hook will block
the commit if lint fails regardless of what the agent intends.
```

### FLOW-04: Sprint contract pattern (Low)

Multi-step builds should follow propose → agree → build → verify.

```markdown
# FAIL
Build the feature, then test it.

# PASS
## Workflow
1. **Propose** — draft a plan and present for approval
2. **Agree** — user confirms or adjusts the plan
3. **Build** — implement per the agreed plan
4. **Verify** — run tests and confirm acceptance criteria
Do not skip the agree step.
```

### FLOW-05: Handoff artifact format (Low)

If passing state between agents, document the handoff artifact format.

```markdown
# FAIL
Pass the results to the next agent.

# PASS
## Handoff artifact
Write `handoff.json` with schema:
{ completed_steps: string[], modified_files: string[],
  next_step: string, blockers: string[] }
The receiving agent reads this file before taking any action.
```

---

## Hook Enforcement Rules

The audit checks three things in combination, not independently:
1. Does `.claude/hooks/` contain at least a pre-commit and pre-push script?
2. Do those scripts exit non-zero on failure (not just warn)?
3. Does `.claude/settings.json` register them under `PreToolUse`?

If any one of the three is missing, flag as critical — a hook file that is not registered does nothing, and a hook that exits 0 on failure is just a log statement.

### HOOK-01: Pre-commit hook exists (Critical)

`.claude/hooks/` must contain a pre-commit script that is executable.

```text
# FAIL
[.claude/hooks/ directory does not exist or is empty]

# FAIL
SKILL.md says "always run tests before committing" — relies on agent compliance

# PASS
[.claude/hooks/pre-commit.sh exists and is executable]
[SKILL.md references it: "enforced by pre-commit hook, not by this file"]
```

### HOOK-02: Pre-commit hook blocks on failure (Critical)

The pre-commit script must exit non-zero when checks fail.

```bash
# FAIL — warns but does not block
#!/bin/bash
npm test
echo "Remember to check tests before committing"
exit 0

# PASS — non-zero exit blocks the commit
#!/bin/bash
npm test
if [ $? -ne 0 ]; then
  echo "Tests failed. Commit blocked."
  exit 1
fi
exit 0
```

### HOOK-03: Pre-push hook exists (Critical)

`.claude/hooks/` must contain a pre-push script for remote enforcement.

```text
# FAIL
[only a pre-commit hook exists — nothing stops a forced push or skipped commit hook]

# PASS
[.claude/hooks/pre-push.sh exists]
```

### HOOK-04: Pre-push hook validates commit format (High)

The pre-push script must validate commit message format or branch rules.

```bash
# FAIL — no validation on push
#!/bin/bash
exit 0

# PASS — enforces commit message format before remote accepts it
#!/bin/bash
COMMIT_MSG=$(git log -1 --pretty=%B)
if ! echo "$COMMIT_MSG" | grep -qE "^(feat|fix|chore|docs)\:"; then
  echo "Commit message must start with feat:|fix:|chore:|docs: — push blocked."
  exit 1
fi
exit 0
```

### HOOK-05: Hooks registered in settings (Critical)

Hook files must be wired in `.claude/settings.json` under the `hooks` key — a file that exists but is not registered does nothing.

```json
// FAIL — hook file exists but is not wired in
// .claude/settings.json has no hooks key

// PASS
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{ "type": "command", "command": ".claude/hooks/pre-commit.sh" }]
    }]
  }
}
```

### HOOK-06: Skill defers to hooks (High)

Instruction files must not duplicate rules that hooks enforce. The skill should explicitly defer.

```markdown
# FAIL — skill is trying to enforce this itself
Always run `npm test` before committing.
Never push directly to main.
Commit messages must follow conventional commits format.

# PASS — skill acknowledges hooks own this
## Commit and push rules
These are enforced by hooks, not by this file.
See .claude/hooks/pre-commit.sh and .claude/hooks/pre-push.sh.
Do not duplicate these rules here — if the hooks and this file conflict,
the hooks win.
```

### HOOK-07: Hook coverage matrix present (Medium)

A table must document what is enforced by hooks versus what is enforced by the skill.

```markdown
# FAIL
[no documentation of what hooks cover vs what the skill covers]

# PASS
| Rule                        | Enforced by      |
|-----------------------------|------------------|
| Tests pass before commit    | pre-commit hook  |
| Conventional commit format  | pre-commit hook  |
| No direct push to main      | pre-push hook    |
| Branch naming convention    | pre-push hook    |
| Linting                     | pre-commit hook  |
| Feature scope per sprint    | SKILL.md         |
| Output format               | SKILL.md         |
```

---

## Context Reset Rules

Context resets prevent agent degradation in long workflows. The agent is most degraded when the reset should happen — if it depends on the agent remembering, it will not happen. Hooks make it real.

### RESET-01: Handoff template exists (Critical)

`.claude/templates/handoff.md` must exist with a structured format.

```text
# FAIL
[no handoff.md template anywhere in the repo]
[CLAUDE.md says "summarize progress" with no structure]

# PASS
[.claude/templates/handoff.md exists with required fields]
```

### RESET-02: Template has required fields (Critical)

The handoff template must contain all required fields for a fresh agent to resume cold.

```markdown
# FAIL — too vague to be useful
## Handoff
- What we did
- What's next

# PASS — a fresh agent can pick this up cold
## Session handoff
session-number:
completed-tasks:
  - task:
    outcome:
    files-modified: []
current-state:
next-task:
blockers: []
do-not-redo: []
open-questions: []
```

Required fields: `session-number`, `completed-tasks`, `next-task`, `current-state`, `do-not-redo`.

### RESET-03: Session boundary trigger defined (High)

The skill or CLAUDE.md must define concrete conditions for when to start a new session.

```markdown
# FAIL — no guidance on when to reset
[SKILL.md runs a 20-step workflow with no break points]

# FAIL — vague
"Start a new session when things get complicated"

# PASS — concrete trigger conditions
## Session boundaries
Start a new session when ANY of the following are true:
- More than 6 features have been completed in this session
- The context window warning appears
- A blocker requires human input before continuing
- A hook has failed more than twice on the same commit
```

### RESET-04: Session start protocol defined (High)

Instructions must define what the first action of a new session is.

```markdown
# FAIL
[no instruction on how to start a session]

# PASS
## Session start protocol
The FIRST action of every session (except session 1) is:
1. Read handoff.md
2. State: "Resuming from session [N]. Next task is [X]."
3. Confirm do-not-redo list before touching any files
Only then begin work.
```

### RESET-05: Handoff written before context fills (High)

The reset trigger must be task-completion based, not "when context is full".

```markdown
# FAIL
"When the context window is full, write a handoff and start fresh"

# PASS
Write handoff.md when you have completed the current task but
BEFORE starting the next one, if any session boundary condition is met.
A handoff written mid-task is invalid — complete or explicitly park
the current task first.
```

### RESET-06: Pre-session-end hook exists (High)

A hook must validate the handoff artifact before the session can end.

```bash
# FAIL — no hook, relies on agent remembering
[.claude/hooks/ has no session-end or handoff validation hook]

# PASS
# .claude/hooks/pre-session-end.sh
required_fields=("session-number" "completed-tasks" "next-task" "current-state" "do-not-redo")
for field in "${required_fields[@]}"; do
  if ! grep -q "^${field}:" "$HANDOFF"; then
    echo "Handoff missing required field: ${field}. Session end blocked."
    exit 1
  fi
done
exit 0
```

### RESET-07: Audit log format defined (Medium)

Hooks must write structured entries to `.claude/audit.log` for dynamic analysis.

```bash
# FAIL — no logging, no trail
[hooks run but produce no persistent record]

# PASS — structured, parseable log entries
# in each hook:
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)|${HOOK_NAME}|${RESULT}|${SESSION}|${DETAIL}" >> .claude/audit.log

# produces:
2026-03-28T09:44:12Z|pre-commit|FAIL|4|Tests failed: auth.test.ts
2026-03-28T09:51:33Z|pre-commit|PASS|4|feat: add auth middleware
```

---

## Formatting Rules

### FMT-01: Valid frontmatter (Required)

File must have a frontmatter block with `---` delimiters.

```yaml
# FAIL — no closing delimiter
---
name: my-skill
description: "Use when..."

# FAIL — wrong delimiter
==
name: my-skill
==

# PASS
---
name: my-skill
description: "Use when the user needs X — returns Y."
---
```

### FMT-02: Hierarchical headers (Required)

Headers must be hierarchical — no H3 before H2, no H4 before H3.

```markdown
# FAIL — jumps from H1 to H3
# My Skill
### Steps

# PASS
# My Skill
## Steps
### Step 1 detail
```

### FMT-03: Code blocks have language tags (Required)

Every code block must specify a language.

````markdown
# FAIL
```
const x = 1;
```

# PASS
```javascript
const x = 1;
```
````

### FMT-04: No orphaned bullets (Required)

Bullet lists must have a parent header — no floating bullets in prose.

```markdown
# FAIL — bullets floating in prose
This skill handles analysis tasks.
- reads input
- returns output
The format is markdown.

# PASS
## What it does
- Reads the input file
- Returns a markdown analysis
```

### FMT-05: No inline HTML (Required)

No inline HTML that would break plain-text agent parsing.

```markdown
# FAIL
<div class="note">Important: do this first</div>

# PASS
> **Note:** Important: do this first
```
