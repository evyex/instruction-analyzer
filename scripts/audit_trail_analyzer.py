#!/usr/bin/env python3
"""
Audit trail analyzer for instruction-analyzer skill.
Parses .claude/audit.log and checks that context resets, hooks, and session
boundaries are actually being enforced — not just configured.

Usage: python3 audit_trail_analyzer.py [--project-root /path] [--days 30]
Output: JSON report with session compliance, hook failure patterns, and flags.

Expected log format (pipe-delimited):
  2026-03-28T09:44:12Z|hook-name|PASS|session-num|detail text
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def parse_log_entry(line: str) -> dict | None:
    """Parse a single audit log line into structured fields."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split("|", 4)
    if len(parts) < 4:
        return None
    try:
        timestamp = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
    except ValueError:
        return None
    return {
        "timestamp": timestamp,
        "hook": parts[1].strip(),
        "result": parts[2].strip().upper(),
        "session": parts[3].strip(),
        "detail": parts[4].strip() if len(parts) > 4 else "",
    }


def load_log(log_path: str, days: int = 30) -> list[dict]:
    """Load and parse audit log entries within the date range."""
    if not os.path.isfile(log_path):
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            entry = parse_log_entry(line)
            if entry and entry["timestamp"] >= cutoff:
                entries.append(entry)
    return entries


def group_by_session(entries: list[dict]) -> dict[str, list[dict]]:
    """Group log entries by session number."""
    sessions = defaultdict(list)
    for e in entries:
        sessions[e["session"]].append(e)
    for s in sessions.values():
        s.sort(key=lambda e: e["timestamp"])
    return dict(sessions)


def analyze_session_resets(sessions: dict[str, list[dict]]) -> dict:
    """Check context reset compliance per session."""
    total = len(sessions)
    resets_triggered = 0
    resets_skipped = []
    handoff_read_at_start = 0
    handoff_read_missed = []
    validation_not_bypassed = 0
    validation_bypassed = []
    reset_timings = []

    for sid, entries in sessions.items():
        hooks_seen = [e["hook"] for e in entries]

        # Was a boundary check triggered?
        boundary_entries = [e for e in entries if e["hook"] == "session-boundary-check"]
        triggered = any(e["result"] == "TRIGGERED" for e in boundary_entries)
        if triggered:
            resets_triggered += 1
        else:
            commit_count = sum(1 for e in entries if e["hook"] == "pre-commit")
            if commit_count > 10:
                resets_skipped.append({
                    "session": sid, "commits": commit_count,
                    "detail": f"No boundary check over {commit_count} commits"
                })

        # Was handoff read at session start?
        if len(entries) >= 2:
            if entries[0]["hook"] == "session-start":
                if entries[1]["hook"] == "handoff-read":
                    handoff_read_at_start += 1
                else:
                    handoff_read_missed.append({
                        "session": sid,
                        "detail": f"First action after session-start was '{entries[1]['hook']}', not handoff-read"
                    })

        # Was handoff validation bypassed?
        validation_entries = [e for e in entries if e["hook"] == "handoff-validation"]
        session_end_entries = [e for e in entries if e["hook"] == "session-end"]
        if session_end_entries:
            last_end = session_end_entries[-1]
            # Check if there's a PASS validation before the session end
            valid_before_end = any(
                e["result"] == "PASS" and e["timestamp"] <= last_end["timestamp"]
                for e in validation_entries
            )
            fail_without_pass = any(
                e["result"] == "FAIL" for e in validation_entries
            ) and not valid_before_end
            if valid_before_end or not validation_entries:
                validation_not_bypassed += 1
            if fail_without_pass:
                validation_bypassed.append({
                    "session": sid,
                    "detail": "Validation failed but session ended without a subsequent PASS"
                })

        # Reset timing — time between session-start and boundary trigger
        start_entries = [e for e in entries if e["hook"] == "session-start"]
        if start_entries and triggered:
            first_trigger = next(e for e in boundary_entries if e["result"] == "TRIGGERED")
            delta = (first_trigger["timestamp"] - start_entries[0]["timestamp"]).total_seconds()
            reset_timings.append(delta)

    sessions_with_starts = sum(
        1 for entries in sessions.values()
        if any(e["hook"] == "session-start" for e in entries)
    )

    avg_timing = None
    if reset_timings:
        avg_seconds = sum(reset_timings) / len(reset_timings)
        hours = int(avg_seconds // 3600)
        minutes = int((avg_seconds % 3600) // 60)
        avg_timing = f"{hours}h {minutes}m"

    return {
        "sessions_audited": total,
        "resets_triggered": resets_triggered,
        "resets_skipped": resets_skipped,
        "handoff_read_at_start": {
            "count": handoff_read_at_start,
            "total": sessions_with_starts,
            "missed": handoff_read_missed,
        },
        "validation_not_bypassed": {
            "count": validation_not_bypassed,
            "total": sum(1 for entries in sessions.values() if any(e["hook"] == "session-end" for e in entries)),
            "bypassed": validation_bypassed,
        },
        "average_reset_timing": avg_timing,
    }


def analyze_hook_failures(entries: list[dict]) -> dict:
    """Analyze hook failure patterns across all entries."""
    hook_stats = defaultdict(lambda: {"pass": 0, "fail": 0})
    feature_attempts = defaultdict(lambda: {"fails": 0, "passes": 0})
    hooks_never_fired = set()

    for e in entries:
        hook = e["hook"]
        if e["result"] == "PASS":
            hook_stats[hook]["pass"] += 1
        elif e["result"] == "FAIL":
            hook_stats[hook]["fail"] += 1

        # Track per-feature commit attempts
        if hook == "pre-commit":
            # Extract feature from detail or commit message
            detail = e["detail"]
            feature_key = detail[:50] if detail else "unknown"
            if e["result"] == "FAIL":
                feature_attempts[feature_key]["fails"] += 1
            else:
                feature_attempts[feature_key]["passes"] += 1

    # Find most/least reliable features
    feature_reliability = {}
    for feat, counts in feature_attempts.items():
        total = counts["fails"] + counts["passes"]
        if total > 0:
            avg_attempts = (counts["fails"] + counts["passes"]) / max(counts["passes"], 1)
            feature_reliability[feat] = round(avg_attempts, 1)

    most_failed = max(feature_reliability.items(), key=lambda x: x[1]) if feature_reliability else None
    most_reliable = min(feature_reliability.items(), key=lambda x: x[1]) if feature_reliability else None

    return {
        "hook_stats": {k: dict(v) for k, v in hook_stats.items()},
        "most_failed_feature": {"feature": most_failed[0], "avg_attempts": most_failed[1]} if most_failed else None,
        "most_reliable_feature": {"feature": most_reliable[0], "avg_attempts": most_reliable[1]} if most_reliable else None,
    }


def generate_flags(session_analysis: dict, hook_analysis: dict) -> list[str]:
    """Generate actionable flags from the analysis."""
    flags = []

    for skip in session_analysis["resets_skipped"]:
        flags.append(f"Session {skip['session']}: {skip['detail']} — likely degraded output")

    for miss in session_analysis["handoff_read_at_start"]["missed"]:
        flags.append(f"Session {miss['session']}: handoff.md not read at start — agent may have duplicated work")

    for bypass in session_analysis["validation_not_bypassed"]["bypassed"]:
        flags.append(f"Session {bypass['session']}: {bypass['detail']}")

    if hook_analysis["most_failed_feature"]:
        feat = hook_analysis["most_failed_feature"]
        if feat["avg_attempts"] > 2.5:
            flags.append(f"High failure rate on '{feat['feature']}' (avg {feat['avg_attempts']} attempts) — unclear spec or missing edge cases")

    # Check for hooks that exist in stats but only pass (never fail = might not be checking)
    for hook, stats in hook_analysis["hook_stats"].items():
        if stats["fail"] == 0 and stats["pass"] > 10:
            flags.append(f"Hook '{hook}' has {stats['pass']} passes and 0 failures — verify it actually validates something")

    return flags


def analyze(project_root: str, days: int = 30) -> dict:
    """Run full audit trail analysis."""
    log_path = os.path.join(project_root, ".claude", "audit.log")

    if not os.path.isfile(log_path):
        return {
            "error": f"No audit log found at {log_path}",
            "recommendation": "Hook scripts must write structured entries to .claude/audit.log. See rules/skill-quality-rules.md RESET-07 for the expected format."
        }

    entries = load_log(log_path, days)
    if not entries:
        return {
            "error": f"No log entries found within the last {days} days",
            "log_path": log_path,
            "recommendation": "Audit log exists but has no recent entries. Verify hooks are appending to it."
        }

    sessions = group_by_session(entries)
    session_analysis = analyze_session_resets(sessions)
    hook_analysis = analyze_hook_failures(entries)
    flags = generate_flags(session_analysis, hook_analysis)

    return {
        "log_path": log_path,
        "period_days": days,
        "total_entries": len(entries),
        "session_reset_compliance": session_analysis,
        "hook_failure_patterns": hook_analysis,
        "flags": flags,
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    project_root = "."
    days = 30

    if "--project-root" in args:
        idx = args.index("--project-root")
        if idx + 1 < len(args):
            project_root = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            days = int(args[idx + 1])
            args = args[:idx] + args[idx + 2:]

    result = analyze(project_root, days)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
