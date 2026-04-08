#!/usr/bin/env python3
"""
Deterministic test suite for skill_quality_checker.py and audit_trail_analyzer.py.

Run:  python3 scripts/hook_test_quality_checker.py
Exit: 0 = all pass, 1 = failures

Creates temporary fixtures, runs all checks, asserts expected pass/fail for
each rule.  No external dependencies beyond the standard library.
"""
import json
import os
import shutil
import sys
import tempfile
import textwrap

# Ensure script dir is on path so we can import siblings
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import skill_quality_checker as qc
import audit_trail_analyzer as ata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestContext:
    """Manages a temp directory with .claude/ infrastructure."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="qa_test_")
        self.claude_dir = os.path.join(self.root, ".claude")
        self.hooks_dir = os.path.join(self.claude_dir, "hooks")
        self.templates_dir = os.path.join(self.claude_dir, "templates")
        os.makedirs(self.hooks_dir)
        os.makedirs(self.templates_dir)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel_path: str, content: str):
        path = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def write_settings(self, obj: dict):
        path = os.path.join(self.claude_dir, "settings.json")
        with open(path, "w") as f:
            json.dump(obj, f)
        return path

    def write_hook(self, name: str, content: str, executable: bool = True):
        path = os.path.join(self.hooks_dir, name)
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        if executable:
            os.chmod(path, 0o755)
        return path

    def write_handoff_template(self, content: str):
        path = os.path.join(self.templates_dir, "handoff.md")
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def write_audit_log(self, lines: list[str]):
        path = os.path.join(self.claude_dir, "audit.log")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return path


PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES = []


def assert_rule(results: list[dict], rule_id: str, expected_pass: bool, label: str = ""):
    """Assert a specific rule passed or failed."""
    global PASS_COUNT, FAIL_COUNT
    match = [r for r in results if r["rule"] == rule_id]
    if not match:
        FAIL_COUNT += 1
        FAILURES.append(f"MISSING {rule_id}: rule not found in results {label}")
        return
    actual = match[0]["passed"]
    if actual == expected_pass:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        status = "PASS" if actual else "FAIL"
        expected = "PASS" if expected_pass else "FAIL"
        FAILURES.append(
            f"WRONG  {rule_id}: got {status}, expected {expected} — {match[0]['detail']} {label}"
        )


def assert_eq(actual, expected, label: str):
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        FAILURES.append(f"ASSERT {label}: got {actual!r}, expected {expected!r}")


def assert_true(condition: bool, label: str):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        FAILURES.append(f"ASSERT {label}: condition is False")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_SKILL = """\
---
name: test-skill
description: "Use when the user asks to analyze API endpoints — returns a structured markdown report with endpoint inventory, auth requirements, and rate limit summary."
---

# Test Skill

## Why this matters

Understanding API surface area is critical because undocumented endpoints are security risks.

## Contract

INPUT: A repository path containing API route definitions
OUTPUT: A markdown report with sections for each endpoint group

## Done when

- All route files have been scanned
- Each endpoint has auth and rate-limit status
- The report contains no TBD sections

## Handoff

Output is consumed by the security-review skill as a JSON array.
Each item must have: path, method, auth_required, rate_limited.

## Review boundary

This skill generates the inventory. It does NOT self-review.
Pass output to the security-review skill for evaluation.

## Edge cases

- If a route file uses dynamic imports, flag it as "unresolvable" and skip
- If the auth middleware is missing on a public endpoint, flag as critical
- If rate limiting config is in a separate file, follow the import

## Session boundaries

Start a new session when ANY of:
- More than 6 route files have been processed
- A blocker requires human input

## Session start protocol

The FIRST action of every session (except session 1) is:
1. Read handoff.md
2. State: "Resuming from session [N]. Next task is [X]."

Write handoff.md when you have completed the current task but
BEFORE starting the next one, if any session boundary condition is met.

## Enforced via hook — do not rely on this file

Linting before commit is enforced by the pre-commit hook in .claude/hooks/.
See .claude/hooks/pre-commit.sh and .claude/hooks/pre-push.sh.
Do not duplicate these rules here — if the hooks and this file conflict,
the hooks win.

## Hook coverage matrix

| Rule                        | Enforced by      |
|-----------------------------|------------------|
| Tests pass before commit    | pre-commit hook  |
| Conventional commit format  | pre-commit hook  |
| No direct push to main      | pre-push hook    |
| Endpoint inventory format   | SKILL.md         |

## Workflow

1. **Propose** the endpoint list, then **Agree** on scope with the user
2. User confirms or adjusts the plan before continuing
3. **Build** — scan and produce the report
4. **STOP — verify all endpoints have auth status before continuing**
5. **Verify** — run the validation script

## Handoff artifact format

Write `handoff.json` with schema:
{ completed_steps: string[], modified_files: string[], next_step: string }

## Example output

**Input:** "Analyze the routes in src/api/"
**Output:**

```markdown
## GET /api/users
- Auth: required (JWT)
- Rate limit: 100/min
```

## Output format

Return a markdown document with exactly these sections:
- ## Summary (3 sentences max)
- ## Endpoints (one H3 per endpoint)
- ## Findings (bullet list)
"""

BAD_SKILL = """\
---
name: bad-skill
---

This skill helps with various tasks and assists with analysis.

- does stuff
- returns things

Build the feature, then test it.
Always run tests before committing.
"""

# Pad to over 150 lines
BAD_SKILL += "\n".join([f"# Filler line {i}" for i in range(160)]) + "\n"


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def test_description_rules():
    """Test DESC-01 through DESC-06."""
    print("  Description rules...")

    # --- Good file ---
    fm, valid = qc.parse_frontmatter(GOOD_SKILL)
    results = qc.check_description_rules(GOOD_SKILL, fm, valid)
    assert_rule(results, "DESC-01", True, "(good)")
    assert_rule(results, "DESC-02", True, "(good)")
    assert_rule(results, "DESC-03", True, "(good)")
    assert_rule(results, "DESC-04", True, "(good)")
    assert_rule(results, "DESC-05", True, "(good)")
    assert_rule(results, "DESC-06", True, "(good)")

    # --- Bad file ---
    fm, valid = qc.parse_frontmatter(BAD_SKILL)
    results = qc.check_description_rules(BAD_SKILL, fm, valid)
    assert_rule(results, "DESC-01", False, "(bad)")  # no description
    assert_rule(results, "DESC-02", False, "(bad)")  # skipped
    assert_rule(results, "DESC-03", False, "(bad)")  # skipped
    assert_rule(results, "DESC-04", False, "(bad)")  # skipped
    assert_rule(results, "DESC-05", False, "(bad)")  # skipped
    assert_rule(results, "DESC-06", False, "(bad)")  # skipped

    # --- Vague description ---
    vague = '---\nname: x\ndescription: "Helps with writing tasks and assists with document creation. Use when the user needs help. Returns a markdown report with all findings included."\n---\n'
    fm, valid = qc.parse_frontmatter(vague)
    results = qc.check_description_rules(vague, fm, valid)
    assert_rule(results, "DESC-01", True, "(vague)")
    assert_rule(results, "DESC-03", True, "(vague)")   # "Use when" present
    assert_rule(results, "DESC-04", False, "(vague)")   # "helps with" found
    assert_rule(results, "DESC-05", True, "(vague)")    # "markdown report"

    # --- Short description ---
    short = '---\nname: x\ndescription: "Use when writing tests."\n---\n'
    fm, valid = qc.parse_frontmatter(short)
    results = qc.check_description_rules(short, fm, valid)
    assert_rule(results, "DESC-06", False, "(short)")   # under 80 chars


def test_structure_rules():
    """Test STRUCT-01 through STRUCT-06."""
    print("  Structure rules...")

    results = qc.check_structure_rules(GOOD_SKILL)
    assert_rule(results, "STRUCT-01", True, "(good)")   # under 150 lines
    assert_rule(results, "STRUCT-02", True, "(good)")   # has reasoning
    assert_rule(results, "STRUCT-03", True, "(good)")   # has output format
    assert_rule(results, "STRUCT-05", True, "(good)")   # edge cases
    assert_rule(results, "STRUCT-06", True, "(good)")   # example present

    results = qc.check_structure_rules(BAD_SKILL)
    assert_rule(results, "STRUCT-01", False, "(bad)")   # over 150 lines
    assert_rule(results, "STRUCT-02", False, "(bad)")   # no reasoning
    assert_rule(results, "STRUCT-03", False, "(bad)")   # no output format
    assert_rule(results, "STRUCT-05", False, "(bad)")   # no edge cases
    assert_rule(results, "STRUCT-06", False, "(bad)")   # no example


def test_agent_readiness_rules():
    """Test AGENT-01 through AGENT-04."""
    print("  Agent readiness rules...")

    results = qc.check_agent_readiness_rules(GOOD_SKILL)
    assert_rule(results, "AGENT-01", True, "(good)")   # INPUT/OUTPUT
    assert_rule(results, "AGENT-02", True, "(good)")   # done when
    assert_rule(results, "AGENT-03", True, "(good)")   # handoff/consumed by
    assert_rule(results, "AGENT-04", True, "(good)")   # review boundary

    results = qc.check_agent_readiness_rules(BAD_SKILL)
    assert_rule(results, "AGENT-01", False, "(bad)")
    assert_rule(results, "AGENT-02", False, "(bad)")
    assert_rule(results, "AGENT-03", False, "(bad)")
    assert_rule(results, "AGENT-04", False, "(bad)")


def test_workflow_rules():
    """Test FLOW-01 through FLOW-05."""
    print("  Workflow rules...")

    results = qc.check_workflow_rules(GOOD_SKILL)
    assert_rule(results, "FLOW-01", True, "(good)")   # STOP checkpoint
    assert_rule(results, "FLOW-02", True, "(good)")   # session boundary
    assert_rule(results, "FLOW-03", True, "(good)")   # enforced by hook
    assert_rule(results, "FLOW-04", True, "(good)")   # propose/agree/build
    assert_rule(results, "FLOW-05", True, "(good)")   # handoff artifact

    results = qc.check_workflow_rules(BAD_SKILL)
    assert_rule(results, "FLOW-01", False, "(bad)")
    assert_rule(results, "FLOW-02", False, "(bad)")
    assert_rule(results, "FLOW-03", False, "(bad)")
    assert_rule(results, "FLOW-04", False, "(bad)")
    assert_rule(results, "FLOW-05", False, "(bad)")


def test_formatting_rules():
    """Test FMT-01 through FMT-05."""
    print("  Formatting rules...")

    results = qc.check_formatting_rules(GOOD_SKILL)
    assert_rule(results, "FMT-01", True, "(good)")   # valid frontmatter
    assert_rule(results, "FMT-02", True, "(good)")   # hierarchical headers
    assert_rule(results, "FMT-03", True, "(good)")   # code blocks tagged
    assert_rule(results, "FMT-05", True, "(good)")   # no inline HTML

    # Bad frontmatter
    no_fm = "# No frontmatter\nJust content.\n"
    results = qc.check_formatting_rules(no_fm)
    assert_rule(results, "FMT-01", False, "(no fm)")

    # Bad header hierarchy
    bad_headers = "---\nname: x\n---\n# H1\n### H3 directly\n"
    results = qc.check_formatting_rules(bad_headers)
    assert_rule(results, "FMT-02", False, "(bad headers)")

    # Untagged code block
    untagged = "---\nname: x\n---\n# H1\n## H2\n```\ncode\n```\n"
    results = qc.check_formatting_rules(untagged)
    assert_rule(results, "FMT-03", False, "(untagged)")

    # Inline HTML
    html = "---\nname: x\n---\n# H1\n## H2\n<div>bad</div>\n"
    results = qc.check_formatting_rules(html)
    assert_rule(results, "FMT-05", False, "(html)")


def test_hook_rules():
    """Test HOOK-01 through HOOK-07 with filesystem fixtures."""
    print("  Hook rules...")
    ctx = TestContext()
    try:
        # Set up valid hooks
        ctx.write_hook("pre-commit.sh", """\
            #!/bin/bash
            npm test
            if [ $? -ne 0 ]; then
              echo "Tests failed. Commit blocked."
              exit 1
            fi
            exit 0
        """)
        ctx.write_hook("pre-push.sh", """\
            #!/bin/bash
            COMMIT_MSG=$(git log -1 --pretty=%B)
            if ! echo "$COMMIT_MSG" | grep -qE "^(feat|fix|chore|docs):"; then
              echo "Bad commit message format. Push blocked."
              exit 1
            fi
            exit 0
        """)
        ctx.write_settings({
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": ".claude/hooks/pre-commit.sh"}]
                }]
            }
        })

        results = qc.check_hook_rules(GOOD_SKILL, ctx.root)
        assert_rule(results, "HOOK-01", True, "(hooks exist)")
        assert_rule(results, "HOOK-02", True, "(exits non-zero)")
        assert_rule(results, "HOOK-03", True, "(pre-push exists)")
        assert_rule(results, "HOOK-04", True, "(validates format)")
        assert_rule(results, "HOOK-05", True, "(registered)")
        assert_rule(results, "HOOK-06", True, "(defers)")
        assert_rule(results, "HOOK-07", True, "(matrix)")

        # Now test with NO hooks dir
        ctx2 = TestContext()
        shutil.rmtree(ctx2.hooks_dir)
        results = qc.check_hook_rules(BAD_SKILL, ctx2.root)
        assert_rule(results, "HOOK-01", False, "(no hooks dir)")
        assert_rule(results, "HOOK-02", False, "(no hook)")
        assert_rule(results, "HOOK-03", False, "(no hooks dir)")
        assert_rule(results, "HOOK-05", False, "(no settings)")
        ctx2.cleanup()

        # Hook that exits 0 only (no exit 1)
        ctx3 = TestContext()
        ctx3.write_hook("pre-commit.sh", """\
            #!/bin/bash
            npm test
            echo "Remember to check tests"
            exit 0
        """)
        results = qc.check_hook_rules(GOOD_SKILL, ctx3.root)
        assert_rule(results, "HOOK-02", False, "(exit 0 only)")
        ctx3.cleanup()
    finally:
        ctx.cleanup()


def test_reset_rules():
    """Test RESET-01 through RESET-07 with filesystem fixtures."""
    print("  Context reset rules...")
    ctx = TestContext()
    try:
        # Set up valid handoff template
        ctx.write_handoff_template("""\
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
        """)
        # Set up session-end hook with audit log
        ctx.write_hook("pre-session-end.sh", """\
            #!/bin/bash
            HANDOFF=".claude/templates/handoff.md"
            required_fields=("session-number" "completed-tasks" "next-task" "current-state" "do-not-redo")
            for field in "${required_fields[@]}"; do
              if ! grep -q "^${field}:" "$HANDOFF"; then
                echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)|session-end|FAIL|${SESSION}|missing ${field}" >> .claude/audit.log
                exit 1
              fi
            done
            echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)|session-end|PASS|${SESSION}|ok" >> .claude/audit.log
            exit 0
        """)

        results = qc.check_reset_rules(GOOD_SKILL, ctx.root)
        assert_rule(results, "RESET-01", True, "(template exists)")
        assert_rule(results, "RESET-02", True, "(fields present)")
        assert_rule(results, "RESET-03", True, "(boundary defined)")
        assert_rule(results, "RESET-04", True, "(start protocol)")
        assert_rule(results, "RESET-05", True, "(task-based trigger)")
        assert_rule(results, "RESET-06", True, "(session-end hook)")
        assert_rule(results, "RESET-07", True, "(audit log in hook)")

        # No template, no hooks
        ctx2 = TestContext()
        shutil.rmtree(ctx2.templates_dir)
        shutil.rmtree(ctx2.hooks_dir)
        results = qc.check_reset_rules(BAD_SKILL, ctx2.root)
        assert_rule(results, "RESET-01", False, "(no template)")
        assert_rule(results, "RESET-02", False, "(no template)")
        assert_rule(results, "RESET-03", False, "(no boundary)")
        assert_rule(results, "RESET-04", False, "(no protocol)")
        assert_rule(results, "RESET-06", False, "(no hook)")
        assert_rule(results, "RESET-07", False, "(no audit)")
        ctx2.cleanup()

        # Template with missing fields
        ctx3 = TestContext()
        ctx3.write_handoff_template("## Handoff\n- What we did\n- What's next\n")
        results = qc.check_reset_rules(GOOD_SKILL, ctx3.root)
        assert_rule(results, "RESET-01", True, "(template exists)")
        assert_rule(results, "RESET-02", False, "(missing fields)")
        ctx3.cleanup()
    finally:
        ctx.cleanup()


def test_scoring():
    """Test compute_scores produces correct weights and overall."""
    print("  Scoring...")
    ctx = TestContext()
    try:
        ctx.write_hook("pre-commit.sh", "#!/bin/bash\nexit 1\n")
        ctx.write_hook("pre-push.sh", "#!/bin/bash\nexit 1\n")
        ctx.write_settings({"hooks": {"PreToolUse": [{}]}})
        ctx.write_handoff_template(
            "session-number:\ncompleted-tasks:\nnext-task:\ncurrent-state:\ndo-not-redo:\n"
        )
        ctx.write_hook("pre-session-end.sh", "#!/bin/bash\necho audit.log\nexit 0\n")

        skill_path = ctx.write("test-skill.md", GOOD_SKILL)
        report = qc.audit_file(skill_path, ctx.root)

        assert_true("scores" in report, "report has scores")
        assert_true("overall" in report["scores"], "scores has overall")
        assert_true(report["scores"]["overall"] > 0, "overall > 0")
        assert_eq(report["scores"]["description"]["weight"], 0.20, "desc weight")
        assert_eq(report["scores"]["hooks"]["weight"], 0.20, "hooks weight")
        assert_eq(report["scores"]["formatting"]["weight"], 0.05, "fmt weight")
        assert_eq(report["total_rules"], 40, "total rules = 40")
    finally:
        ctx.cleanup()


def test_full_audit():
    """Test full audit_file end-to-end for good and bad files."""
    print("  Full audit (end-to-end)...")
    ctx = TestContext()
    try:
        ctx.write_hook("pre-commit.sh", "#!/bin/bash\nexit 1\n")
        ctx.write_hook("pre-push.sh", "#!/bin/bash\nexit 1\n")
        ctx.write_settings({"hooks": {"PreToolUse": [{}]}})
        ctx.write_handoff_template(
            "session-number:\ncompleted-tasks:\nnext-task:\ncurrent-state:\ndo-not-redo:\n"
        )
        ctx.write_hook("pre-session-end.sh", "#!/bin/bash\necho audit.log\nexit 0\n")

        # Good file should score high
        good_path = ctx.write("good.md", GOOD_SKILL)
        report = qc.audit_file(good_path, ctx.root)
        assert_true(report["scores"]["overall"] >= 70, f"good overall >= 70 (got {report['scores']['overall']})")
        assert_true(report["passed"] >= 30, f"good passed >= 30 (got {report['passed']})")

        # Bad file should score low
        bad_path = ctx.write("bad.md", BAD_SKILL)
        report = qc.audit_file(bad_path, ctx.root)
        assert_true(report["scores"]["overall"] < 40, f"bad overall < 40 (got {report['scores']['overall']})")
        assert_true(report["failed"] >= 25, f"bad failed >= 25 (got {report['failed']})")
    finally:
        ctx.cleanup()


def test_audit_trail_analyzer():
    """Test audit_trail_analyzer with synthetic log data."""
    print("  Audit trail analyzer...")
    ctx = TestContext()
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        fmt = "%Y-%m-%dT%H:%M:%SZ"

        def ts(delta_hours):
            return (now - timedelta(hours=delta_hours)).strftime(fmt)

        # Build a realistic audit log
        log_lines = [
            # Session 1 — good session
            f"{ts(48)}|session-start|PASS|1|started",
            f"{ts(48)}|handoff-read|PASS|1|read handoff.md",
            f"{ts(47)}|pre-commit|PASS|1|feat: add auth",
            f"{ts(46)}|pre-commit|PASS|1|feat: add users",
            f"{ts(45)}|session-boundary-check|TRIGGERED|1|6 features done",
            f"{ts(45)}|handoff-validation|PASS|1|all fields present",
            f"{ts(45)}|session-end|PASS|1|clean exit",
            # Session 2 — missed handoff read
            f"{ts(24)}|session-start|PASS|2|started",
            f"{ts(24)}|pre-commit|FAIL|2|tests failed: auth.test.ts",
            f"{ts(23)}|pre-commit|FAIL|2|tests failed: auth.test.ts",
            f"{ts(22)}|pre-commit|PASS|2|feat: fix auth",
            f"{ts(21)}|session-boundary-check|TRIGGERED|2|blocker hit",
            f"{ts(21)}|handoff-validation|PASS|2|ok",
            f"{ts(21)}|session-end|PASS|2|clean exit",
        ]
        ctx.write_audit_log(log_lines)

        result = ata.analyze(ctx.root, days=30)
        assert_true("error" not in result, "no error in result")
        assert_eq(result["total_entries"], 14, "14 log entries")

        compliance = result["session_reset_compliance"]
        assert_eq(compliance["sessions_audited"], 2, "2 sessions")
        assert_eq(compliance["resets_triggered"], 2, "2 resets triggered")
        assert_eq(compliance["handoff_read_at_start"]["count"], 1, "1 handoff read (session 2 missed)")
        assert_eq(len(compliance["handoff_read_at_start"]["missed"]), 1, "1 missed handoff")

        hooks = result["hook_failure_patterns"]
        assert_true("pre-commit" in hooks["hook_stats"], "pre-commit in stats")
        assert_eq(hooks["hook_stats"]["pre-commit"]["fail"], 2, "2 pre-commit failures")
        assert_eq(hooks["hook_stats"]["pre-commit"]["pass"], 3, "3 pre-commit passes")

        flags = result["flags"]
        assert_true(any("handoff" in f.lower() for f in flags), "flag about missed handoff")

        # Test with no log file
        ctx2 = TestContext()
        result = ata.analyze(ctx2.root, days=30)
        assert_true("error" in result, "error when no log file")
        ctx2.cleanup()

    finally:
        ctx.cleanup()


def test_audit_trail_empty_range():
    """Test analyzer with log entries outside the date range."""
    print("  Audit trail (empty range)...")
    ctx = TestContext()
    try:
        # Write entries from 60 days ago (outside 30-day window)
        log_lines = [
            "2020-01-01T00:00:00Z|pre-commit|PASS|1|old entry",
        ]
        ctx.write_audit_log(log_lines)
        result = ata.analyze(ctx.root, days=30)
        assert_true("error" in result, "error when no recent entries")
    finally:
        ctx.cleanup()


def test_parse_frontmatter():
    """Test frontmatter parser edge cases."""
    print("  Frontmatter parser...")

    # Valid
    fm, valid = qc.parse_frontmatter("---\nname: x\ndescription: y\n---\ncontent")
    assert_true(valid, "valid frontmatter")
    assert_eq(fm["name"], "x", "name field")
    assert_eq(fm["description"], "y", "description field")

    # Missing closing ---
    fm, valid = qc.parse_frontmatter("---\nname: x\ncontent")
    assert_true(not valid, "missing closing delimiter")

    # No frontmatter at all
    fm, valid = qc.parse_frontmatter("# Just a heading\ncontent")
    assert_true(not valid, "no frontmatter")

    # Quoted values
    fm, valid = qc.parse_frontmatter('---\nname: "quoted"\ndescription: \'single\'\n---\n')
    assert_true(valid, "quoted frontmatter")
    assert_eq(fm["name"], "quoted", "double-quoted value")
    assert_eq(fm["description"], "single", "single-quoted value")


def test_log_entry_parser():
    """Test audit log line parser edge cases."""
    print("  Log entry parser...")

    # Valid entry
    entry = ata.parse_log_entry("2026-03-28T09:44:12Z|pre-commit|PASS|4|feat: add auth")
    assert_true(entry is not None, "valid entry parsed")
    assert_eq(entry["hook"], "pre-commit", "hook name")
    assert_eq(entry["result"], "PASS", "result")
    assert_eq(entry["session"], "4", "session")
    assert_eq(entry["detail"], "feat: add auth", "detail")

    # Comment line
    entry = ata.parse_log_entry("# this is a comment")
    assert_true(entry is None, "comment ignored")

    # Empty line
    entry = ata.parse_log_entry("")
    assert_true(entry is None, "empty line ignored")

    # Too few fields
    entry = ata.parse_log_entry("2026-03-28T09:44:12Z|pre-commit|PASS")
    assert_true(entry is None, "too few fields")

    # Bad timestamp
    entry = ata.parse_log_entry("not-a-date|pre-commit|PASS|1|detail")
    assert_true(entry is None, "bad timestamp")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global PASS_COUNT, FAIL_COUNT, FAILURES

    print("Running quality checker tests...\n")

    tests = [
        test_parse_frontmatter,
        test_description_rules,
        test_structure_rules,
        test_agent_readiness_rules,
        test_workflow_rules,
        test_formatting_rules,
        test_hook_rules,
        test_reset_rules,
        test_scoring,
        test_full_audit,
        test_log_entry_parser,
        test_audit_trail_analyzer,
        test_audit_trail_empty_range,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            FAIL_COUNT += 1
            FAILURES.append(f"CRASH  {test.__name__}: {e}")

    print(f"\nResults: {PASS_COUNT} passed, {FAIL_COUNT} failed")

    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
