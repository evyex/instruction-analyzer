# SDD Workflow Rules

Rules for evaluating whether a project follows the Spec-Driven Development five-layer model.
Unlike skill quality rules (which audit individual files), these audit the overall project workflow.

Based on the SDD article framework: specifications as source of truth, generation from specs,
validation against specs, drift detection, and feedback loops.

## Scoring Weights

| Layer | Weight |
|---|---|
| Specification | 25% |
| Generation | 20% |
| Validation | 25% |
| Drift Detection | 15% |
| Feedback Loop | 15% |

Layer score = (rules passed / total rules in layer) * 100.
Overall score = weighted average of layer scores.

---

## Layer 1: Specification

The authoritative definition of system behavior. Specs declare what the system is, not how it is implemented.

### SDD-SPEC-01: Spec directory exists (Critical)

Project must have a directory containing specification files.

```text
# FAIL
[no specs/, specifications/, or similar directory]
[specs exist but are scattered across the repo with no organizing structure]

# PASS
specs/
  NLSPEC_user_roles.md
  NLSPEC_billing.md
  NLSPEC_notifications.md
```

### SDD-SPEC-02: Specs follow consistent template (High)

Specs of the same type must share a common structure (3+ shared section headers).

```text
# FAIL — each spec has a different structure
NLSPEC_a.md: ## Overview, ## Steps, ## Notes
NLSPEC_b.md: ## Purpose, ## Implementation, ## Testing

# PASS — specs share a template
NLSPEC_a.md: ## Context, ## Architecture, ## Data Model, ## API Endpoints, ## Acceptance Criteria
NLSPEC_b.md: ## Context, ## Architecture, ## Data Model, ## API Endpoints, ## Acceptance Criteria
```

### SDD-SPEC-03: Specs are versioned (High)

At least half of spec files must contain a version marker (`Version:`, `v1.0`, etc.).

```markdown
# FAIL
# NLSpec: User Roles
[no version anywhere in the file]

# PASS
# NLSpec: User Roles
# Version: 1.0
# Date: 2026-03-15
```

### SDD-SPEC-04: Requirements traceability (Medium)

Upstream artifacts (interviews, requirements docs) must exist to trace how specs were derived.

```text
# FAIL
specs/
  NLSPEC_feature.md       ← no record of how decisions were made

# PASS
specs/
  INTERVIEW_feature.md    ← decisions captured here
  NLSPEC_feature.md       ← spec references interview as source
```

---

## Layer 2: Generation

Transforms declared intent into executable code. The spec governs what gets generated.

### SDD-GEN-01: Implementation process exists (Critical)

A defined process (command, workflow, or documented procedure) must exist that reads specs and produces code.

```text
# FAIL
[no implementation command, no workflow referencing specs]
[developers implement from ad-hoc descriptions in Slack]

# PASS
.claude/commands/implement.md exists and references specs/NLSPEC_*.md
```

### SDD-GEN-02: Generation reads spec first (High)

The implementation process must explicitly read the spec before writing any code.

```markdown
# FAIL — implementation command with no spec reference
## Steps
1. Create the files
2. Write the code
3. Run tests

# PASS
## Steps
1. Read the NLSpec completely — all sections — before writing any code
2. Read the exemplar files referenced in Section 6
3. Announce plan based on the spec
4. Implement in the order defined by the spec
```

### SDD-GEN-03: Generation is isolated (Medium)

Implementation must happen in an isolated environment (worktree, feature branch, sandbox) to prevent contaminating the main codebase.

```text
# FAIL
[implementation happens directly on main branch]

# PASS
All implementation work MUST happen in an isolated Git worktree.
The main working tree must stay clean at all times.
```

---

## Layer 3: Validation

Enforces alignment between declared intent (spec) and actual implementation (code).

### SDD-VAL-01: Review process exists (Critical)

A review process must exist that checks implementation against the spec — not just code review, but spec compliance review.

```text
# FAIL
[no review command, code review is general-purpose only]

# PASS
.claude/commands/review.md exists with NLSpec compliance checklist
```

### SDD-VAL-02: Review has pass/fail verdicts (High)

The review process must produce binary verdicts (PASS/FAIL, READY/REDO), not just advisory comments.

```markdown
# FAIL — advisory only
"Consider improving the error handling"
"This looks good overall"

# PASS — binary verdict
Verdict:
- READY — implementation matches spec and passes all checks
- NEEDS FIXES — list the specific changes needed
- REDO — fundamental issues require reimplementation
```

### SDD-VAL-03: Validation has automation (High)

Validation must have automated components — hooks, CI pipelines, or registered tool-use hooks. Manual-only review is insufficient.

```text
# FAIL
[review is manual only — someone runs /review when they remember]

# PASS — hooks enforce checks automatically
.claude/hooks/pre-commit.sh exists
.claude/settings.json registers hooks under PreToolUse
```

### SDD-VAL-04: Validation is continuous (Medium)

Automated validation must fire on events (commit, push, PR), not just when manually invoked.

```text
# FAIL
[hooks exist but are not registered — they only run when someone calls them]

# PASS
Hooks registered in settings.json fire automatically on every tool use.
CI pipeline runs validation on every push and PR.
```

---

## Layer 4: Drift Detection

Detects when implementation diverges from spec after the initial review. Without this, the system degrades silently.

### SDD-DRIFT-01: Post-review drift detection (High)

Something must check for divergence after the initial review — audit logs, scheduled re-reviews, CI checks, or runtime validation.

```text
# FAIL
[review happens once, then nothing — if someone changes the code later, nobody knows]

# PASS — audit log tracks enforcement over time
.claude/audit.log exists with structured entries
Hooks write pass/fail records for every commit
```

### SDD-DRIFT-02: Spec-to-code traceability (Medium)

A mechanism must exist to trace which spec produced which code — commit messages referencing specs, code comments, or structured logs.

```text
# FAIL
[commits say "add user roles" with no spec reference]
[no way to answer "which spec produced this code?"]

# PASS
Implementation command writes spec path in commit: "feat: add user roles (spec: NLSPEC_user_roles.md)"
Review command checks implementation against a specific spec file by path
```

---

## Layer 5: Feedback Loop

Findings from validation and production must feed back into specifications. Without this, the system is open-loop.

### SDD-LOOP-01: Spec update process defined (Medium)

A documented process must exist for updating specs when the review finds issues or requirements change.

```markdown
# FAIL
[no mention of updating specs — code gets patched directly]

# PASS
Rule 5: Update the spec when requirements change.
Don't patch code without updating the spec first.
```

### SDD-LOOP-02: Bug fixes reference specs (Low)

The bugfix workflow should read or update the original spec that produced the buggy code.

```text
# FAIL
[bugfix flow: find bug → fix code → deploy]

# PASS
[bugfix flow: find bug → read original NLSPEC → diagnose against spec → fix → update spec if needed]
```

### SDD-LOOP-03: Lessons learned exist (Low)

Retrospective artifacts (lessons learned, postmortems) must exist and be referenced in the implementation workflow.

```text
# FAIL
[no lessons learned files, same mistakes repeat across features]

# PASS
specs/LESSONS_LEARNED.md exists
Implementation command says: "Read specs/LESSONS_LEARNED.md — mandatory bug-pattern briefing"
```

### SDD-LOOP-04: Spec changes are governed (Medium)

Changes to specifications must have governance — breaking change classification, version bumps, or explicit approval.

```markdown
# FAIL
[anyone edits specs freely, no classification of change impact]

# PASS
Spec changes are classified:
- Additive: new section, new edge case → safe
- Compatible: reworded description → review recommended
- Breaking: output format changed, field removed → requires approval
```
