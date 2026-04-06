#!/usr/bin/env python3
"""
SDD workflow checker for instruction-analyzer skill.
Audits a project's adherence to the Spec-Driven Development five-layer model.
Unlike skill_quality_checker.py (which audits individual files), this checks
the overall project workflow: specs, generation, validation, drift detection,
and feedback loops.

Usage: python3 sdd_workflow_checker.py --project-root /path/to/project
Output: JSON report with per-layer scores and per-check results.
"""
import json
import os
import re
import sys
from glob import glob


def read_file_safe(path: str) -> str | None:
    """Read file content, returning None on any error."""
    try:
        return open(path, encoding="utf-8").read()
    except Exception:
        return None


def find_spec_dirs(project_root: str) -> list[str]:
    """Find directories likely containing specifications."""
    candidates = ["specs", "spec", "specifications", "design", "nlspecs"]
    found = []
    for name in candidates:
        d = os.path.join(project_root, name)
        if os.path.isdir(d):
            found.append(d)
    return found


def list_spec_files(spec_dirs: list[str]) -> list[str]:
    """List markdown/yaml spec files in spec directories."""
    files = []
    for d in spec_dirs:
        for ext in ("*.md", "*.yaml", "*.yml"):
            files.extend(glob(os.path.join(d, "**", ext), recursive=True))
    return files


def find_claude_commands(project_root: str) -> dict[str, str]:
    """Find .claude/commands/ files. Returns {filename: content}."""
    commands_dir = os.path.join(project_root, ".claude", "commands")
    result = {}
    if os.path.isdir(commands_dir):
        for f in os.listdir(commands_dir):
            fpath = os.path.join(commands_dir, f)
            if os.path.isfile(fpath):
                content = read_file_safe(fpath)
                if content:
                    result[f] = content
    return result


def find_workflow_docs(project_root: str) -> list[tuple[str, str]]:
    """Find workflow documentation files. Returns [(path, content)]."""
    candidates = ["CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md", "README.md",
                   ".claude/CLAUDE.md"]
    docs = []
    for name in candidates:
        path = os.path.join(project_root, name)
        content = read_file_safe(path)
        if content:
            docs.append((path, content))
    return docs


# --- Layer 1: Specification ---

def check_spec_layer(project_root: str) -> list[dict]:
    """Check SDD-SPEC-* rules for the Specification Layer."""
    results = []
    spec_dirs = find_spec_dirs(project_root)
    spec_files = list_spec_files(spec_dirs) if spec_dirs else []

    # Filter out interview/bugreport files — only count actual specs
    actual_specs = [f for f in spec_files
                    if not os.path.basename(f).upper().startswith(("INTERVIEW_", "BUGREPORT_", "LESSONS"))]

    # SDD-SPEC-01: Spec directory exists with spec files
    has_specs = len(actual_specs) > 0
    detail = "OK" if has_specs else "No spec directory or spec files found"
    if has_specs:
        detail = f"OK (found {len(actual_specs)} spec files in {', '.join(os.path.basename(d) for d in spec_dirs)})"
    results.append({
        "rule": "SDD-SPEC-01", "name": "Spec directory exists",
        "severity": "critical", "passed": has_specs, "detail": detail
    })

    # SDD-SPEC-02: Specs follow a consistent template
    # Group specs by type prefix (NLSPEC_, BUGREPORT_, PLAN_, etc.) and check
    # within groups — different spec types are expected to have different structures
    consistent = False
    detail = "Skipped — no specs found"
    if len(actual_specs) >= 2:
        groups: dict[str, list[str]] = {}
        for sf in actual_specs:
            basename = os.path.basename(sf).upper()
            prefix = basename.split("_")[0] if "_" in basename else "OTHER"
            groups.setdefault(prefix, []).append(sf)
        # Check the largest group with 2+ files
        best_group = ""
        best_common: set[str] = set()
        for prefix, files in groups.items():
            if len(files) < 2:
                continue
            header_sets = []
            for sf in files[:10]:  # sample up to 10
                content = read_file_safe(sf)
                if content:
                    headers = re.findall(r'^##?\s+(.+)', content, re.MULTILINE)
                    header_sets.append(set(h.strip() for h in headers))
            if len(header_sets) >= 2:
                common = header_sets[0]
                for hs in header_sets[1:]:
                    common = common & hs
                if len(common) > len(best_common):
                    best_common = common
                    best_group = prefix
        consistent = len(best_common) >= 3
        if consistent:
            detail = f"OK ({len(best_common)} common sections in {best_group} specs: {', '.join(sorted(list(best_common))[:5])})"
        else:
            detail = f"No spec group shares 3+ common sections (minimum 3 for template consistency)"
    elif len(actual_specs) == 1:
        detail = "Only 1 spec — cannot assess template consistency"
    results.append({
        "rule": "SDD-SPEC-02", "name": "Specs follow consistent template",
        "severity": "high", "passed": consistent, "detail": detail
    })

    # SDD-SPEC-03: Specs are versioned
    versioned_count = 0
    detail = "Skipped — no specs found"
    if actual_specs:
        for sf in actual_specs:
            content = read_file_safe(sf)
            if content and re.search(r'(?i)(^#\s*version|version\s*:\s*\d|v\d+\.\d+)', content, re.MULTILINE):
                versioned_count += 1
        ratio = versioned_count / len(actual_specs)
        versioned = ratio >= 0.5
        detail = f"{versioned_count}/{len(actual_specs)} specs have version markers"
        if versioned:
            detail = f"OK ({detail})"
    else:
        versioned = False
    results.append({
        "rule": "SDD-SPEC-03", "name": "Specs are versioned",
        "severity": "high", "passed": versioned, "detail": detail
    })

    # SDD-SPEC-04: Interview/requirements traceability
    interview_files = [f for f in spec_files
                       if os.path.basename(f).upper().startswith("INTERVIEW_")]
    # Also check for requirements directory
    req_dirs = [os.path.join(project_root, d) for d in ["requirements", "interviews"]
                if os.path.isdir(os.path.join(project_root, d))]
    has_traceability = len(interview_files) > 0 or len(req_dirs) > 0
    detail = "No interview or requirements files found — specs lack upstream traceability"
    if interview_files:
        detail = f"OK ({len(interview_files)} interview files found)"
    elif req_dirs:
        detail = f"OK (requirements directory found: {', '.join(os.path.basename(d) for d in req_dirs)})"
    results.append({
        "rule": "SDD-SPEC-04", "name": "Requirements traceability",
        "severity": "medium", "passed": has_traceability, "detail": detail
    })

    return results


# --- Layer 2: Generation ---

def check_generation_layer(project_root: str) -> list[dict]:
    """Check SDD-GEN-* rules for the Generation Layer."""
    results = []
    commands = find_claude_commands(project_root)
    workflow_docs = find_workflow_docs(project_root)
    all_content = "\n".join(c for _, c in workflow_docs) + "\n" + "\n".join(commands.values())

    # SDD-GEN-01: Implementation process exists that references specs
    impl_commands = {k: v for k, v in commands.items()
                     if re.search(r'(?i)implement', k)}
    impl_in_docs = bool(re.search(
        r'(?i)(implement.*spec|spec.*implement|build.*from.*spec|code.*from.*spec)',
        all_content
    ))
    has_impl = len(impl_commands) > 0 or impl_in_docs
    detail = "No implementation process found that references specs"
    if impl_commands:
        detail = f"OK (found implementation commands: {', '.join(impl_commands.keys())})"
    elif impl_in_docs:
        detail = "OK (implementation process references specs in workflow docs)"
    results.append({
        "rule": "SDD-GEN-01", "name": "Implementation process exists",
        "severity": "critical", "passed": has_impl, "detail": detail
    })

    # SDD-GEN-02: Implementation reads spec before writing code
    reads_spec = False
    detail = "Skipped — no implementation process found"
    if has_impl:
        read_patterns = [
            r'(?i)read\s+(the\s+)?(nlspec|spec|specification)',
            r'(?i)read.*NLSPEC',
            r'(?i)specs?/.*\.md',
            r'(?i)based\s+on\s+(the\s+)?spec',
            r'(?i)refer\s+to\s+(the\s+)?spec',
        ]
        impl_content = "\n".join(impl_commands.values()) if impl_commands else all_content
        reads_spec = any(re.search(p, impl_content) for p in read_patterns)
        if reads_spec:
            detail = "OK (implementation process explicitly reads specs)"
        else:
            detail = "Implementation process does not explicitly read specs before code generation"
    results.append({
        "rule": "SDD-GEN-02", "name": "Generation reads spec first",
        "severity": "high", "passed": reads_spec, "detail": detail
    })

    # SDD-GEN-03: Generation is isolated (worktree/branch)
    isolation_patterns = [
        r'(?i)\bworktree\b', r'(?i)\bisolat(ed|ion)\b',
        r'(?i)feature\s*(branch|/)', r'(?i)git\s+checkout\s+-b',
        r'(?i)sandbox',
    ]
    has_isolation = any(re.search(p, all_content) for p in isolation_patterns)
    detail = "No isolation mechanism (worktree, feature branch, sandbox) found"
    if has_isolation:
        detail = "OK (generation isolation documented)"
    results.append({
        "rule": "SDD-GEN-03", "name": "Generation is isolated",
        "severity": "medium", "passed": has_isolation, "detail": detail
    })

    return results


# --- Layer 3: Validation ---

def check_validation_layer(project_root: str) -> list[dict]:
    """Check SDD-VAL-* rules for the Validation Layer."""
    results = []
    commands = find_claude_commands(project_root)
    workflow_docs = find_workflow_docs(project_root)
    all_content = "\n".join(c for _, c in workflow_docs) + "\n" + "\n".join(commands.values())
    hooks_dir = os.path.join(project_root, ".claude", "hooks")
    settings_path = os.path.join(project_root, ".claude", "settings.json")

    # SDD-VAL-01: Review process exists that checks against specs
    review_commands = {k: v for k, v in commands.items()
                       if re.search(r'(?i)review', k)}
    review_in_docs = bool(re.search(
        r'(?i)(review.*spec|review.*implementation|spec\s+compliance|verify.*against.*spec)',
        all_content
    ))
    has_review = len(review_commands) > 0 or review_in_docs
    detail = "No review process found that checks implementation against specs"
    if review_commands:
        detail = f"OK (found review commands: {', '.join(review_commands.keys())})"
    elif review_in_docs:
        detail = "OK (review process references spec compliance in workflow docs)"
    results.append({
        "rule": "SDD-VAL-01", "name": "Review process exists",
        "severity": "critical", "passed": has_review, "detail": detail
    })

    # SDD-VAL-02: Review has pass/fail verdicts
    verdict_patterns = [
        r'(?i)\bPASS\b', r'(?i)\bFAIL\b', r'(?i)\bREADY\b', r'(?i)\bREDO\b',
        r'(?i)\bverdict\b', r'(?i)\bapprove[ds]?\b', r'(?i)\breject(ed)?\b',
        r'(?i)NEEDS\s+FIXES',
    ]
    review_content = "\n".join(review_commands.values()) if review_commands else ""
    has_verdicts = False
    detail = "Skipped — no review process found"
    if has_review:
        verdict_count = sum(1 for p in verdict_patterns if re.search(p, review_content or all_content))
        has_verdicts = verdict_count >= 2
        if has_verdicts:
            detail = "OK (review process includes pass/fail verdicts)"
        else:
            detail = "Review process is advisory only — no binary pass/fail verdicts"
    results.append({
        "rule": "SDD-VAL-02", "name": "Review has pass/fail verdicts",
        "severity": "high", "passed": has_verdicts, "detail": detail
    })

    # SDD-VAL-03: Validation has automation (hooks, CI)
    has_hooks = os.path.isdir(hooks_dir) and len(os.listdir(hooks_dir)) > 0
    ci_patterns = [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile",
                   ".circleci", "bitbucket-pipelines.yml"]
    has_ci = any(os.path.exists(os.path.join(project_root, p)) for p in ci_patterns)
    has_settings_hooks = False
    if os.path.isfile(settings_path):
        settings_content = read_file_safe(settings_path)
        if settings_content:
            try:
                settings = json.loads(settings_content)
                hooks_key = settings.get("hooks", {})
                has_settings_hooks = bool(hooks_key and any(hooks_key.values()))
            except Exception:
                pass
    has_automation = has_hooks or has_ci or has_settings_hooks
    detail_parts = []
    if has_hooks:
        detail_parts.append("hooks in .claude/hooks/")
    if has_ci:
        detail_parts.append("CI config found")
    if has_settings_hooks:
        detail_parts.append("hooks registered in settings.json")
    if has_automation:
        detail = f"OK ({', '.join(detail_parts)})"
    else:
        detail = "No automated validation found (no hooks, no CI config, no registered hooks in settings)"
    results.append({
        "rule": "SDD-VAL-03", "name": "Validation has automation",
        "severity": "high", "passed": has_automation, "detail": detail
    })

    # SDD-VAL-04: Validation is continuous, not one-shot
    continuous = False
    detail = "Validation appears to be manual/one-shot only"
    if has_settings_hooks:
        # Hooks registered in settings = they fire on every tool use
        continuous = True
        detail = "OK (hooks registered in settings.json fire automatically)"
    elif has_ci:
        continuous = True
        detail = "OK (CI pipeline runs validation on push/PR)"
    elif has_hooks:
        # Hooks exist but not registered — might not fire automatically
        detail = "Hooks exist but are not registered in settings.json — may not fire automatically"
    results.append({
        "rule": "SDD-VAL-04", "name": "Validation is continuous",
        "severity": "medium", "passed": continuous, "detail": detail
    })

    return results


# --- Layer 4: Drift Detection ---

def check_drift_layer(project_root: str) -> list[dict]:
    """Check SDD-DRIFT-* rules for Drift Detection."""
    results = []
    audit_log = os.path.join(project_root, ".claude", "audit.log")
    commands = find_claude_commands(project_root)
    workflow_docs = find_workflow_docs(project_root)
    all_content = "\n".join(c for _, c in workflow_docs) + "\n" + "\n".join(commands.values())

    # SDD-DRIFT-01: Post-review drift detection exists
    has_audit_log = os.path.isfile(audit_log)
    drift_patterns = [
        r'(?i)\bdrift\b', r'(?i)\bre-review\b', r'(?i)\bre-check\b',
        r'(?i)\bcontinuous\s+(check|validation|enforcement)\b',
        r'(?i)\bpost-deploy\s+(check|validation)\b',
    ]
    has_drift_docs = any(re.search(p, all_content) for p in drift_patterns)
    has_drift = has_audit_log or has_drift_docs
    detail = "No post-review drift detection (no audit log, no re-review process)"
    if has_audit_log and has_drift_docs:
        detail = "OK (audit log exists and drift detection documented)"
    elif has_audit_log:
        detail = "OK (audit log exists for tracking enforcement)"
    elif has_drift_docs:
        detail = "OK (drift detection process documented)"
    results.append({
        "rule": "SDD-DRIFT-01", "name": "Post-review drift detection",
        "severity": "high", "passed": has_drift, "detail": detail
    })

    # SDD-DRIFT-02: Spec-to-code traceability
    trace_patterns = [
        r'(?i)spec\s*:', r'(?i)refs?\s+spec', r'(?i)implements\s+spec',
        r'(?i)per\s+spec', r'(?i)NLSpec\s*:', r'(?i)source\s*:.*spec',
        r'(?i)referenc(e|ing)\s+(the\s+)?spec',
    ]
    # Check if implementation or review commands mention tracing back to spec
    impl_review = "\n".join(v for k, v in commands.items()
                            if re.search(r'(?i)(implement|review)', k))
    has_traceability = any(re.search(p, impl_review or all_content) for p in trace_patterns)
    # Also check for spec reference in commit hooks
    hooks_dir = os.path.join(project_root, ".claude", "hooks")
    if os.path.isdir(hooks_dir):
        for f in os.listdir(hooks_dir):
            content = read_file_safe(os.path.join(hooks_dir, f))
            if content and any(re.search(p, content) for p in trace_patterns):
                has_traceability = True
                break
    detail = "No spec-to-code traceability mechanism found"
    if has_traceability:
        detail = "OK (spec references found in workflow commands or hooks)"
    results.append({
        "rule": "SDD-DRIFT-02", "name": "Spec-to-code traceability",
        "severity": "medium", "passed": has_traceability, "detail": detail
    })

    return results


# --- Layer 5: Feedback Loop ---

def check_feedback_layer(project_root: str) -> list[dict]:
    """Check SDD-LOOP-* rules for the Feedback Loop."""
    results = []
    commands = find_claude_commands(project_root)
    workflow_docs = find_workflow_docs(project_root)
    all_content = "\n".join(c for _, c in workflow_docs) + "\n" + "\n".join(commands.values())
    spec_dirs = find_spec_dirs(project_root)

    # SDD-LOOP-01: Process for updating specs when review finds issues
    update_patterns = [
        r'(?i)update\s+(the\s+)?spec', r'(?i)spec\s+update',
        r'(?i)revise\s+(the\s+)?spec', r'(?i)modify\s+(the\s+)?spec',
        r'(?i)change.*requirements.*update.*spec',
        r'(?i)don.t\s+patch\s+code\s+without\s+updating\s+the\s+spec',
    ]
    has_update_process = any(re.search(p, all_content) for p in update_patterns)
    detail = "No process defined for updating specs when issues are found"
    if has_update_process:
        detail = "OK (spec update process documented)"
    results.append({
        "rule": "SDD-LOOP-01", "name": "Spec update process defined",
        "severity": "medium", "passed": has_update_process, "detail": detail
    })

    # SDD-LOOP-02: Bug fixes reference original specs
    bugfix_commands = {k: v for k, v in commands.items()
                       if re.search(r'(?i)bug', k)}
    bugfix_refs_spec = False
    detail = "No bugfix workflow found"
    if bugfix_commands:
        bugfix_content = "\n".join(bugfix_commands.values())
        spec_ref_patterns = [
            r'(?i)read.*spec', r'(?i)original\s+spec',
            r'(?i)NLSPEC', r'(?i)spec.*produced',
            r'(?i)update.*spec.*after.*fix',
        ]
        bugfix_refs_spec = any(re.search(p, bugfix_content) for p in spec_ref_patterns)
        if bugfix_refs_spec:
            detail = "OK (bugfix workflow references specs)"
        else:
            detail = "Bugfix workflow exists but does not reference or update original specs"
    results.append({
        "rule": "SDD-LOOP-02", "name": "Bug fixes reference specs",
        "severity": "low", "passed": bugfix_refs_spec, "detail": detail
    })

    # SDD-LOOP-03: Lessons learned feed back into process
    lessons_patterns = ["LESSONS_LEARNED", "lessons-learned", "retrospective",
                        "retro", "postmortem", "post-mortem"]
    lessons_files = []
    for d in spec_dirs:
        for f in glob(os.path.join(d, "**", "*"), recursive=True):
            if any(p.lower() in os.path.basename(f).lower() for p in lessons_patterns):
                lessons_files.append(f)
    # Also check project root
    for f in os.listdir(project_root):
        if any(p.lower() in f.lower() for p in lessons_patterns):
            lessons_files.append(os.path.join(project_root, f))
    # Check if lessons are referenced in implementation commands
    lessons_referenced = bool(re.search(r'(?i)lessons.learned', all_content))
    has_lessons = len(lessons_files) > 0 or lessons_referenced
    detail = "No lessons learned or retrospective files found"
    if lessons_files and lessons_referenced:
        detail = f"OK (found {len(lessons_files)} lessons file(s) and referenced in workflow)"
    elif lessons_files:
        detail = f"Found {len(lessons_files)} lessons file(s) but not referenced in implementation workflow"
    elif lessons_referenced:
        detail = "OK (lessons learned referenced in workflow)"
    results.append({
        "rule": "SDD-LOOP-03", "name": "Lessons learned exist",
        "severity": "low", "passed": has_lessons, "detail": detail
    })

    # SDD-LOOP-04: Spec changes are governed (versioning, breaking change classification)
    governance_patterns = [
        r'(?i)breaking\s+change', r'(?i)backward\s+compat',
        r'(?i)spec\s+version', r'(?i)migration\s+plan',
        r'(?i)deprecat', r'(?i)change\s+classif',
        r'(?i)additive\s+change', r'(?i)compatible\s+change',
    ]
    has_governance = any(re.search(p, all_content) for p in governance_patterns)
    detail = "No spec change governance (no breaking change classification, no versioning rules)"
    if has_governance:
        detail = "OK (spec change governance documented)"
    results.append({
        "rule": "SDD-LOOP-04", "name": "Spec changes are governed",
        "severity": "medium", "passed": has_governance, "detail": detail
    })

    return results


# --- Scoring ---

def compute_scores(all_results: list[dict]) -> dict:
    """Compute per-layer and overall scores."""
    categories = {
        "specification": {"weight": 0.25, "rules": []},
        "generation": {"weight": 0.20, "rules": []},
        "validation": {"weight": 0.25, "rules": []},
        "drift_detection": {"weight": 0.15, "rules": []},
        "feedback_loop": {"weight": 0.15, "rules": []},
    }
    prefix_map = {
        "SDD-SPEC": "specification",
        "SDD-GEN": "generation",
        "SDD-VAL": "validation",
        "SDD-DRIFT": "drift_detection",
        "SDD-LOOP": "feedback_loop",
    }
    for r in all_results:
        # Extract category prefix: SDD-SPEC-01 -> SDD-SPEC
        match = re.match(r'^(SDD-\w+)-\d+$', r["rule"])
        if match:
            prefix = match.group(1)
            cat = prefix_map.get(prefix)
            if cat:
                categories[cat]["rules"].append(r)

    scores = {}
    overall = 0.0
    for cat, data in categories.items():
        total = len(data["rules"])
        passed = sum(1 for r in data["rules"] if r["passed"])
        pct = (passed / total * 100) if total > 0 else 100
        scores[cat] = {
            "passed": passed, "total": total,
            "score": round(pct, 1), "weight": data["weight"]
        }
        overall += pct * data["weight"]

    scores["overall"] = round(overall, 1)
    return scores


# --- Main ---

def analyze(project_root: str) -> dict:
    """Run full SDD workflow audit on a project."""
    if not os.path.isdir(project_root):
        return {"error": f"Project root not found: {project_root}"}

    all_results = []
    all_results.extend(check_spec_layer(project_root))
    all_results.extend(check_generation_layer(project_root))
    all_results.extend(check_validation_layer(project_root))
    all_results.extend(check_drift_layer(project_root))
    all_results.extend(check_feedback_layer(project_root))

    scores = compute_scores(all_results)
    passed = [r for r in all_results if r["passed"]]
    failed = [r for r in all_results if not r["passed"]]

    return {
        "project_root": project_root,
        "scores": scores,
        "total_rules": len(all_results),
        "passed": len(passed),
        "failed": len(failed),
        "results": all_results,
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    project_root = "."

    if "--project-root" in args:
        idx = args.index("--project-root")
        if idx + 1 < len(args):
            project_root = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            print(json.dumps({"error": "--project-root requires a path argument"}))
            sys.exit(1)

    result = analyze(project_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
