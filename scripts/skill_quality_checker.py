#!/usr/bin/env python3
"""
Quality checker for instruction files.
Usage: python3 skill_quality_checker.py [--project-root /path/to/project] file1.md file2.md ...
Output: JSON audit report with per-file rule results and scores.
The --project-root flag tells the checker where to look for .claude/hooks/ and .claude/settings.json.
Defaults to the current working directory.
"""
import json
import os
import re
import sys


def parse_frontmatter(content: str) -> tuple[dict | None, bool]:
    """Parse YAML frontmatter. Returns (fields_dict, is_valid)."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, False
    end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end == -1:
        return None, False
    fields = {}
    for line in lines[1:end]:
        match = re.match(r'^(\w[\w-]*):\s*(.+)', line)
        if match:
            key = match.group(1)
            val = match.group(2).strip().strip('"').strip("'")
            fields[key] = val
    return fields, True


def check_description_rules(content: str, fm: dict | None, fm_valid: bool) -> list[dict]:
    """Check all DESC-* rules."""
    results = []

    # DESC-01: description exists
    has_desc = fm is not None and "description" in fm
    results.append({
        "rule": "DESC-01", "name": "Description field exists",
        "severity": "critical", "passed": has_desc,
        "detail": "No description field in frontmatter" if not has_desc else "OK"
    })

    if not has_desc:
        # Can't check remaining description rules
        for rule_id, name, sev in [
            ("DESC-02", "Single line description", "critical"),
            ("DESC-03", "Trigger condition present", "critical"),
            ("DESC-04", "No vague language", "high"),
            ("DESC-05", "Names output artifact", "high"),
            ("DESC-06", "80+ characters", "high"),
        ]:
            results.append({
                "rule": rule_id, "name": name, "severity": sev,
                "passed": False, "detail": "Skipped — no description field"
            })
        return results

    desc = fm["description"]

    # DESC-02: single line
    lines = content.split("\n")
    desc_single = True
    for i, line in enumerate(lines):
        if re.match(r'^description:', line):
            # Check if next non-empty line is indented (continuation)
            for j in range(i + 1, min(i + 5, len(lines))):
                if lines[j].strip() == "" or lines[j].strip() == "---":
                    break
                if re.match(r'^[\s]+\S', lines[j]) and not re.match(r'^\w', lines[j]):
                    desc_single = False
                    break
            break
    results.append({
        "rule": "DESC-02", "name": "Single line description",
        "severity": "critical", "passed": desc_single,
        "detail": "Description spans multiple lines" if not desc_single else "OK"
    })

    # DESC-03: trigger condition
    trigger_patterns = [
        r'(?i)\buse when\b', r'(?i)\binvoke when\b', r'(?i)\btrigger when\b',
        r'(?i)\buse this when\b', r'(?i)\buse if\b',
    ]
    has_trigger = any(re.search(p, desc) for p in trigger_patterns)
    results.append({
        "rule": "DESC-03", "name": "Trigger condition present",
        "severity": "critical", "passed": has_trigger,
        "detail": "No trigger condition (e.g. 'Use when...') found" if not has_trigger else "OK"
    })

    # DESC-04: no vague language
    vague_patterns = [
        r'(?i)\bhelps with\b', r'(?i)\bassists with\b',
        r'(?i)\bhandles\b', r'(?i)\bdeals with\b',
    ]
    vague_found = [p for p in vague_patterns if re.search(p, desc)]
    results.append({
        "rule": "DESC-04", "name": "No vague language",
        "severity": "high", "passed": len(vague_found) == 0,
        "detail": f"Vague language found: {', '.join(re.search(p, desc).group() for p in vague_found)}" if vague_found else "OK"
    })

    # DESC-05: names output artifact
    artifact_patterns = [
        r'(?i)\b(markdown|json|yaml|csv|html|pdf|report|spec|document|file|array|object|table)\b',
        r'(?i)\breturns?\s+(a|an|the)\b',
    ]
    has_artifact = any(re.search(p, desc) for p in artifact_patterns)
    results.append({
        "rule": "DESC-05", "name": "Names output artifact",
        "severity": "high", "passed": has_artifact,
        "detail": "No output artifact type named in description" if not has_artifact else "OK"
    })

    # DESC-06: 80+ chars
    char_count = len(desc)
    results.append({
        "rule": "DESC-06", "name": "80+ characters",
        "severity": "high", "passed": char_count >= 80,
        "detail": f"Description is {char_count} chars (minimum 80)" if char_count < 80 else f"OK ({char_count} chars)"
    })

    return results


def check_structure_rules(content: str) -> list[dict]:
    """Check all STRUCT-* rules."""
    results = []
    lines = content.split("\n")

    # STRUCT-01: under 150 lines
    line_count = len(lines)
    results.append({
        "rule": "STRUCT-01", "name": "Under 150 lines",
        "severity": "high", "passed": line_count <= 150,
        "detail": f"File has {line_count} lines (max 150)" if line_count > 150 else f"OK ({line_count} lines)"
    })

    # STRUCT-02: contains reasoning
    reasoning_patterns = [
        r'(?i)\bwhy\b', r'(?i)\bbecause\b', r'(?i)\bthe goal is\b',
        r'(?i)\bthis matters\b', r'(?i)\bthe reason\b', r'(?i)\bthis ensures\b',
        r'(?i)\bpurpose\b', r'(?i)\bso that\b',
    ]
    # Only search outside code blocks
    in_code = False
    reasoning_lines = []
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            for p in reasoning_patterns:
                if re.search(p, line):
                    reasoning_lines.append(line.strip()[:60])
                    break
    has_reasoning = len(reasoning_lines) >= 1
    results.append({
        "rule": "STRUCT-02", "name": "Contains reasoning",
        "severity": "high", "passed": has_reasoning,
        "detail": "No reasoning/principles found (why, because, the goal is, etc.)" if not has_reasoning else f"OK ({len(reasoning_lines)} reasoning statements)"
    })

    # STRUCT-03: output format specified
    output_patterns = [
        r'(?i)##?\s*output\s*(format|structure|schema)',
        r'(?i)\breturn(s)?\s+(a|an|the)\s+\w+\s+(with|containing)',
        r'(?i)\bproduce\s+(a|an|the)\b',
        r'(?i)\buse this structure\b',
        r'(?i)\bformat\s*:\s*\w+',
    ]
    in_code = False
    has_output_format = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            if any(re.search(p, line) for p in output_patterns):
                has_output_format = True
                break
    results.append({
        "rule": "STRUCT-03", "name": "Output format specified",
        "severity": "high", "passed": has_output_format,
        "detail": "No explicit output format specification found" if not has_output_format else "OK"
    })

    # STRUCT-04: no competing instructions (heuristic — flag obvious contradictions)
    # Check for "always" + "never" or "omit" on same topic within 20 lines
    always_lines = []
    in_code = False
    competing = []
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if re.search(r'(?i)\balways\b', line):
            always_lines.append((i, line.strip()))
        if re.search(r'(?i)\b(never|do not|don\'t|omit|skip)\b', line):
            for ai, aline in always_lines:
                if abs(i - ai) <= 20:
                    # Check for topic overlap (shared nouns)
                    a_words = set(re.findall(r'\b\w{4,}\b', aline.lower()))
                    n_words = set(re.findall(r'\b\w{4,}\b', line.lower().strip()))
                    overlap = a_words & n_words - {"always", "never", "should", "must", "that", "this", "with", "from"}
                    if overlap:
                        competing.append(f"Lines {ai+1} and {i+1} may conflict on: {', '.join(overlap)}")
    results.append({
        "rule": "STRUCT-04", "name": "No competing instructions",
        "severity": "high", "passed": len(competing) == 0,
        "detail": "; ".join(competing) if competing else "OK (no obvious contradictions detected)"
    })

    # STRUCT-05: edge cases documented (>= 3 conditionals)
    conditional_patterns = [
        r'(?i)\bif\s+(the|a|an|input|user|output|file|data)\b',
        r'(?i)\bwhen\s+(the|a|an|no|there)\b',
        r'(?i)\bunless\b',
        r'(?i)\bin case\b',
    ]
    in_code = False
    conditional_count = 0
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            if any(re.search(p, line) for p in conditional_patterns):
                conditional_count += 1
    results.append({
        "rule": "STRUCT-05", "name": "Edge cases documented",
        "severity": "medium", "passed": conditional_count >= 3,
        "detail": f"Found {conditional_count} conditional statements (minimum 3)" if conditional_count < 3 else f"OK ({conditional_count} conditionals)"
    })

    # STRUCT-06: example present
    example_patterns = [
        r'(?i)##?\s*example',
        r'(?i)\bexample\s*(output|input|usage)\b',
        r'(?i)\bfor example\b',
        r'(?i)\be\.g\.\b',
    ]
    in_code = False
    has_example = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            if any(re.search(p, line) for p in example_patterns):
                has_example = True
                break
    results.append({
        "rule": "STRUCT-06", "name": "Example present",
        "severity": "medium", "passed": has_example,
        "detail": "No example found in file" if not has_example else "OK"
    })

    return results


def check_agent_readiness_rules(content: str) -> list[dict]:
    """Check all AGENT-* rules."""
    results = []
    lower = content.lower()

    # AGENT-01: contract framing (INPUT/OUTPUT sections)
    has_input = bool(re.search(r'(?i)\b(INPUT|input\s*:)', content))
    has_output = bool(re.search(r'(?i)\b(OUTPUT|output\s*:)', content))
    has_contract = has_input and has_output
    results.append({
        "rule": "AGENT-01", "name": "Contract framing",
        "severity": "high", "passed": has_contract,
        "detail": f"Missing {'INPUT' if not has_input else ''}{' and ' if not has_input and not has_output else ''}{'OUTPUT' if not has_output else ''} section" if not has_contract else "OK"
    })

    # AGENT-02: testable success criteria
    success_patterns = [
        r'(?i)\bdone when\b', r'(?i)\bcomplete when\b',
        r'(?i)\bverify\s+(that|it|the)\b', r'(?i)\bconfirm\s+(that|it|the)\b',
        r'(?i)\bsuccess\s+(criteria|when|if)\b',
        r'(?i)##?\s*(done|success|acceptance|verification)',
    ]
    has_criteria = any(re.search(p, content) for p in success_patterns)
    results.append({
        "rule": "AGENT-02", "name": "Testable success criteria",
        "severity": "high", "passed": has_criteria,
        "detail": "No testable success criteria found (done when, verify that, etc.)" if not has_criteria else "OK"
    })

    # AGENT-03: composability
    composability_patterns = [
        r'(?i)\bhandoff\b', r'(?i)\bdownstream\b', r'(?i)\breceiv(es?|ing)\b',
        r'(?i)\bconsumed by\b', r'(?i)\bpassed to\b', r'(?i)\bnext\s+(skill|agent|step)\b',
    ]
    has_composability = any(re.search(p, content) for p in composability_patterns)
    results.append({
        "rule": "AGENT-03", "name": "Composability documented",
        "severity": "medium", "passed": has_composability,
        "detail": "No composability/handoff documentation found" if not has_composability else "OK"
    })

    # AGENT-04: evaluator separation
    evaluator_patterns = [
        r'(?i)\breview\s+(boundary|separation|step)\b',
        r'(?i)\bdoes\s+not\s+self-review\b',
        r'(?i)\bevaluator\b', r'(?i)\bQA\s+(step|separation|review)\b',
    ]
    has_evaluator = any(re.search(p, content) for p in evaluator_patterns)
    results.append({
        "rule": "AGENT-04", "name": "Evaluator separation",
        "severity": "medium", "passed": has_evaluator,
        "detail": "No evaluator/QA separation acknowledged" if not has_evaluator else "OK"
    })

    return results


def check_workflow_rules(content: str) -> list[dict]:
    """Check all FLOW-* rules."""
    results = []
    lines = content.split("\n")

    # FLOW-01: checkpoints
    checkpoint_patterns = [
        r'(?i)\bSTOP\b', r'(?i)\bdo not proceed\b', r'(?i)\bbefore continuing\b',
        r'(?i)\bconfirm\s+(it|that|before|the)\b', r'(?i)\bwait\s+(for|until)\b',
        r'(?i)\bcheckpoint\b',
    ]
    in_code = False
    has_checkpoint = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and any(re.search(p, line) for p in checkpoint_patterns):
            has_checkpoint = True
            break
    results.append({
        "rule": "FLOW-01", "name": "Checkpoints defined",
        "severity": "medium", "passed": has_checkpoint,
        "detail": "No checkpoints or stopping conditions found" if not has_checkpoint else "OK"
    })

    # FLOW-02: context reset points
    reset_patterns = [
        r'(?i)\bsession\s*(boundary|break|end|split)\b',
        r'(?i)\bhandoff\.(md|json|yaml)\b',
        r'(?i)\bpick up\b', r'(?i)\bfresh agent\b',
        r'(?i)\bcontext reset\b',
    ]
    has_reset = any(re.search(p, content) for p in reset_patterns)
    results.append({
        "rule": "FLOW-02", "name": "Context reset points",
        "severity": "medium", "passed": has_reset,
        "detail": "No context reset or session boundary points identified" if not has_reset else "OK"
    })

    # FLOW-03: hardwired steps flagged
    hook_patterns = [
        r'(?i)\benforced\s+(via|by)\s+(hook|script|CI|pipeline)\b',
        r'(?i)\bpre-commit\s+hook\b', r'(?i)\bautomated\s+(by|via)\b',
        r'(?i)\bhook\s+(will|blocks?|runs?|enforces?)\b',
    ]
    has_hook_flag = any(re.search(p, content) for p in hook_patterns)
    results.append({
        "rule": "FLOW-03", "name": "Hardwired steps flagged",
        "severity": "medium", "passed": has_hook_flag,
        "detail": "No hardwired/hook-enforced steps identified" if not has_hook_flag else "OK"
    })

    # FLOW-04: sprint contract pattern
    sprint_patterns = [
        r'(?i)\bpropose\b.*\bagree\b', r'(?i)\bagree\b.*\bbuild\b',
        r'(?i)\bbuild\b.*\bverify\b', r'(?i)\bplan\b.*\bapproval\b',
        r'(?i)\bconfirm(s|ed)?\s+(before|the plan|or adjust)\b',
    ]
    has_sprint = any(re.search(p, content) for p in sprint_patterns)
    results.append({
        "rule": "FLOW-04", "name": "Sprint contract pattern",
        "severity": "low", "passed": has_sprint,
        "detail": "No propose/agree/build/verify pattern found" if not has_sprint else "OK"
    })

    # FLOW-05: handoff artifact format
    handoff_patterns = [
        r'(?i)\bhandoff\s+(artifact|file|format|schema)\b',
        r'(?i)\bwrite\s+.+\.(md|json|yaml)\s+with\b',
        r'(?i)\bschema\s*:\s*\{',
    ]
    has_handoff = any(re.search(p, content) for p in handoff_patterns)
    results.append({
        "rule": "FLOW-05", "name": "Handoff artifact format",
        "severity": "low", "passed": has_handoff,
        "detail": "No handoff artifact format documented" if not has_handoff else "OK"
    })

    return results


def check_hook_rules(content: str, project_root: str) -> list[dict]:
    """Check all HOOK-* rules. Inspects both file content and project filesystem."""
    results = []
    hooks_dir = os.path.join(project_root, ".claude", "hooks")
    settings_path = os.path.join(project_root, ".claude", "settings.json")

    # Find hook scripts by scanning for common names
    pre_commit_path = None
    pre_push_path = None
    if os.path.isdir(hooks_dir):
        for f in os.listdir(hooks_dir):
            lower = f.lower()
            if "pre-commit" in lower or "precommit" in lower:
                pre_commit_path = os.path.join(hooks_dir, f)
            if "pre-push" in lower or "prepush" in lower:
                pre_push_path = os.path.join(hooks_dir, f)

    # HOOK-01: pre-commit hook exists
    pre_commit_exists = pre_commit_path is not None and os.path.isfile(pre_commit_path)
    detail_01 = "OK"
    if not pre_commit_exists:
        if not os.path.isdir(hooks_dir):
            detail_01 = f".claude/hooks/ directory not found at {hooks_dir}"
        else:
            detail_01 = "No pre-commit hook script found in .claude/hooks/"
    results.append({
        "rule": "HOOK-01", "name": "Pre-commit hook exists",
        "severity": "critical", "passed": pre_commit_exists,
        "detail": detail_01
    })

    # HOOK-02: pre-commit hook blocks on failure (exits non-zero)
    pre_commit_blocks = False
    detail_02 = "Skipped — no pre-commit hook found"
    if pre_commit_exists:
        try:
            hook_content = open(pre_commit_path, encoding="utf-8").read()
            # Check for exit 1 / exit non-zero patterns
            has_nonzero_exit = bool(re.search(r'exit\s+[1-9]', hook_content))
            # Check it does NOT unconditionally exit 0 at the end
            lines = hook_content.strip().split("\n")
            last_lines = "\n".join(lines[-3:]) if len(lines) >= 3 else hook_content
            ends_exit_0 = bool(re.search(r'^\s*exit\s+0\s*$', last_lines, re.MULTILINE))
            # Passes if there's a non-zero exit AND it doesn't unconditionally exit 0 at the end
            # OR if there's conditional logic with non-zero exits
            pre_commit_blocks = has_nonzero_exit
            if pre_commit_blocks:
                detail_02 = "OK"
            else:
                detail_02 = "Pre-commit hook never exits non-zero — failures are not blocked"
        except Exception as e:
            detail_02 = f"Could not read pre-commit hook: {e}"
    results.append({
        "rule": "HOOK-02", "name": "Pre-commit blocks on failure",
        "severity": "critical", "passed": pre_commit_blocks,
        "detail": detail_02
    })

    # HOOK-03: pre-push hook exists
    pre_push_exists = pre_push_path is not None and os.path.isfile(pre_push_path)
    detail_03 = "OK"
    if not pre_push_exists:
        if not os.path.isdir(hooks_dir):
            detail_03 = ".claude/hooks/ directory not found"
        else:
            detail_03 = "No pre-push hook script found in .claude/hooks/"
    results.append({
        "rule": "HOOK-03", "name": "Pre-push hook exists",
        "severity": "critical", "passed": pre_push_exists,
        "detail": detail_03
    })

    # HOOK-04: pre-push hook validates commit format
    pre_push_validates = False
    detail_04 = "Skipped — no pre-push hook found"
    if pre_push_exists:
        try:
            hook_content = open(pre_push_path, encoding="utf-8").read()
            validation_patterns = [
                r'git\s+log.*--pretty', r'COMMIT_MSG', r'commit.*message',
                r'grep\s+.*-[qE]', r'branch.*nam', r'(?i)conventional',
                r'feat\|fix\|chore', r'exit\s+[1-9]',
            ]
            matches = sum(1 for p in validation_patterns if re.search(p, hook_content))
            pre_push_validates = matches >= 2
            if pre_push_validates:
                detail_04 = "OK"
            else:
                detail_04 = "Pre-push hook does not appear to validate commit format or branch rules"
        except Exception as e:
            detail_04 = f"Could not read pre-push hook: {e}"
    results.append({
        "rule": "HOOK-04", "name": "Pre-push validates format",
        "severity": "high", "passed": pre_push_validates,
        "detail": detail_04
    })

    # HOOK-05: hooks registered in .claude/settings.json
    hooks_registered = False
    detail_05 = "OK"
    if os.path.isfile(settings_path):
        try:
            settings = json.loads(open(settings_path, encoding="utf-8").read())
            hooks_key = settings.get("hooks", {})
            if hooks_key and any(hooks_key.values()):
                hooks_registered = True
            else:
                detail_05 = ".claude/settings.json exists but has no hooks configured"
        except Exception as e:
            detail_05 = f"Could not parse .claude/settings.json: {e}"
    else:
        detail_05 = f".claude/settings.json not found at {settings_path}"
    results.append({
        "rule": "HOOK-05", "name": "Hooks registered in settings",
        "severity": "critical", "passed": hooks_registered,
        "detail": detail_05
    })

    # HOOK-06: skill defers commit/push rules to hooks (checks instruction file content)
    defers_patterns = [
        r'(?i)enforced\s+(by|via)\s+hook', r'(?i)hook.*win',
        r'(?i)do not duplicate.*hook', r'(?i)see\s+\.claude/hooks/',
        r'(?i)not\s+(by|in)\s+this\s+file',
    ]
    has_deferral = any(re.search(p, content) for p in defers_patterns)
    # Also check for the anti-pattern: skill tries to enforce commit/push rules itself
    enforces_itself_patterns = [
        r'(?i)always\s+run\s+(tests?|lint)', r'(?i)never\s+push\s+directly',
        r'(?i)commit\s+messages?\s+must\s+follow',
    ]
    enforces_itself = any(re.search(p, content) for p in enforces_itself_patterns)
    hook_defers = has_deferral or (not enforces_itself and (pre_commit_exists or pre_push_exists))
    detail_06 = "OK"
    if enforces_itself and not has_deferral:
        detail_06 = "Skill enforces commit/push rules in plain text instead of deferring to hooks"
    elif not has_deferral and not pre_commit_exists and not pre_push_exists:
        detail_06 = "No hooks exist and skill does not mention hook enforcement"
    results.append({
        "rule": "HOOK-06", "name": "Skill defers to hooks",
        "severity": "high", "passed": hook_defers,
        "detail": detail_06
    })

    # HOOK-07: hook coverage matrix present
    matrix_patterns = [
        r'(?i)\|\s*rule\s*\|.*enforced\s*by\s*\|',
        r'(?i)\|\s*enforced\s*by\s*\|',
        r'(?i)hook\s+coverage\s+matrix',
        r'(?i)pre-commit\s+hook\s*\|',
    ]
    has_matrix = any(re.search(p, content) for p in matrix_patterns)
    results.append({
        "rule": "HOOK-07", "name": "Hook coverage matrix",
        "severity": "medium", "passed": has_matrix,
        "detail": "No hook coverage matrix documenting what hooks vs skill enforce" if not has_matrix else "OK"
    })

    return results


def check_reset_rules(content: str, project_root: str) -> list[dict]:
    """Check all RESET-* rules for context reset infrastructure."""
    results = []
    templates_dir = os.path.join(project_root, ".claude", "templates")
    handoff_template = os.path.join(templates_dir, "handoff.md")
    hooks_dir = os.path.join(project_root, ".claude", "hooks")
    audit_log = os.path.join(project_root, ".claude", "audit.log")

    # RESET-01: handoff template exists
    template_exists = os.path.isfile(handoff_template)
    results.append({
        "rule": "RESET-01", "name": "Handoff template exists",
        "severity": "critical", "passed": template_exists,
        "detail": f".claude/templates/handoff.md not found at {handoff_template}" if not template_exists else "OK"
    })

    # RESET-02: template has required fields
    required_fields = ["session-number", "completed-tasks", "next-task", "current-state", "do-not-redo"]
    template_valid = False
    detail_02 = "Skipped — no handoff template found"
    if template_exists:
        try:
            tmpl = open(handoff_template, encoding="utf-8").read().lower()
            missing = [f for f in required_fields if f not in tmpl]
            template_valid = len(missing) == 0
            if template_valid:
                detail_02 = "OK"
            else:
                detail_02 = f"Handoff template missing fields: {', '.join(missing)}"
        except Exception as e:
            detail_02 = f"Could not read handoff template: {e}"
    results.append({
        "rule": "RESET-02", "name": "Template has required fields",
        "severity": "critical", "passed": template_valid,
        "detail": detail_02
    })

    # RESET-03: session boundary trigger defined (in instruction file content)
    boundary_patterns = [
        r'(?i)session\s+boundar', r'(?i)start\s+a\s+new\s+session\s+when',
        r'(?i)context\s+(reset|window)\s+(trigger|warning)',
        r'(?i)reset\s+(required|when|if)',
    ]
    has_boundary = any(re.search(p, content) for p in boundary_patterns)
    results.append({
        "rule": "RESET-03", "name": "Session boundary trigger defined",
        "severity": "high", "passed": has_boundary,
        "detail": "No session boundary trigger conditions defined" if not has_boundary else "OK"
    })

    # RESET-04: session start protocol defined
    start_patterns = [
        r'(?i)session\s+start\s+protocol', r'(?i)first\s+action.*read\s+handoff',
        r'(?i)resuming\s+from\s+session', r'(?i)read\s+handoff\.md\s+(before|first)',
        r'(?i)begin\s+(by|with)\s+reading\s+handoff',
    ]
    has_start_protocol = any(re.search(p, content) for p in start_patterns)
    results.append({
        "rule": "RESET-04", "name": "Session start protocol defined",
        "severity": "high", "passed": has_start_protocol,
        "detail": "No session start protocol (read handoff first) defined" if not has_start_protocol else "OK"
    })

    # RESET-05: handoff written before context fills (task-completion based, not window-full)
    bad_trigger = bool(re.search(r'(?i)when\s+(the\s+)?context\s+(window\s+)?is\s+full', content))
    good_trigger = bool(re.search(r'(?i)(completed?\s+(the\s+)?current\s+task|before\s+starting\s+the\s+next)', content))
    reset_05_pass = good_trigger or (has_boundary and not bad_trigger)
    detail_05 = "OK"
    if bad_trigger:
        detail_05 = "Reset trigger is 'when context is full' — too late, quality already degraded"
    elif not good_trigger and not has_boundary:
        detail_05 = "No task-completion-based reset trigger found"
    results.append({
        "rule": "RESET-05", "name": "Handoff before context fills",
        "severity": "high", "passed": reset_05_pass,
        "detail": detail_05
    })

    # RESET-06: pre-session-end hook exists
    session_end_hook = None
    if os.path.isdir(hooks_dir):
        for f in os.listdir(hooks_dir):
            lower = f.lower()
            if "session-end" in lower or "sessionend" in lower or "handoff" in lower:
                candidate = os.path.join(hooks_dir, f)
                if os.path.isfile(candidate):
                    session_end_hook = candidate
                    break
    has_session_hook = session_end_hook is not None
    detail_06 = "OK"
    if not has_session_hook:
        if not os.path.isdir(hooks_dir):
            detail_06 = ".claude/hooks/ directory not found"
        else:
            detail_06 = "No session-end or handoff validation hook in .claude/hooks/"
    results.append({
        "rule": "RESET-06", "name": "Pre-session-end hook exists",
        "severity": "high", "passed": has_session_hook,
        "detail": detail_06
    })

    # RESET-07: audit log format defined
    # Check if hooks write to audit.log OR if content mentions audit log format
    audit_log_exists = os.path.isfile(audit_log)
    log_format_in_content = bool(re.search(r'(?i)audit\.log', content))
    log_format_in_hooks = False
    if os.path.isdir(hooks_dir):
        for f in os.listdir(hooks_dir):
            fpath = os.path.join(hooks_dir, f)
            if os.path.isfile(fpath):
                try:
                    hc = open(fpath, encoding="utf-8").read()
                    if "audit.log" in hc or "audit_log" in hc:
                        log_format_in_hooks = True
                        break
                except Exception:
                    pass
    has_audit_log = audit_log_exists or log_format_in_hooks or log_format_in_content
    detail_07 = "OK"
    if not has_audit_log:
        detail_07 = "No audit log (.claude/audit.log) and no hooks writing to one"
    results.append({
        "rule": "RESET-07", "name": "Audit log format defined",
        "severity": "medium", "passed": has_audit_log,
        "detail": detail_07
    })

    return results


def check_formatting_rules(content: str) -> list[dict]:
    """Check all FMT-* rules."""
    results = []
    lines = content.split("\n")

    # FMT-01: valid frontmatter
    _, fm_valid = parse_frontmatter(content)
    results.append({
        "rule": "FMT-01", "name": "Valid frontmatter",
        "severity": "required", "passed": fm_valid,
        "detail": "Missing or invalid frontmatter (--- delimiters)" if not fm_valid else "OK"
    })

    # FMT-02: hierarchical headers
    header_issues = []
    prev_level = 0
    in_code = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = re.match(r'^(#{1,6})\s', line)
        if match:
            level = len(match.group(1))
            if prev_level > 0 and level > prev_level + 1:
                header_issues.append(f"Line {i+1}: H{level} after H{prev_level} (skips H{prev_level+1})")
            prev_level = level
    results.append({
        "rule": "FMT-02", "name": "Hierarchical headers",
        "severity": "required", "passed": len(header_issues) == 0,
        "detail": "; ".join(header_issues) if header_issues else "OK"
    })

    # FMT-03: code blocks have language tags
    untagged = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            tag = stripped[3:].strip()
            # Opening block (not closing)
            if tag == "" and not in_code:
                untagged.append(f"Line {i+1}")
            in_code = not in_code
    results.append({
        "rule": "FMT-03", "name": "Code blocks have language tags",
        "severity": "required", "passed": len(untagged) == 0,
        "detail": f"Untagged code blocks at: {', '.join(untagged)}" if untagged else "OK"
    })

    # FMT-04: no orphaned bullets
    orphaned = []
    in_code = False
    prev_was_header = False
    prev_was_bullet = False
    in_bullet_group = False
    bullet_group_start = -1
    has_header_before_group = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            prev_was_header = False
            prev_was_bullet = False
            in_bullet_group = False
            continue
        if in_code:
            continue
        is_header = bool(re.match(r'^#{1,6}\s', stripped))
        is_bullet = bool(re.match(r'^[-*+]\s', stripped))
        is_empty = stripped == ""
        if is_header:
            prev_was_header = True
            in_bullet_group = False
        elif is_bullet:
            if not in_bullet_group:
                in_bullet_group = True
                bullet_group_start = i
                has_header_before_group = prev_was_header
            prev_was_header = False
        elif not is_empty:
            if in_bullet_group and not has_header_before_group:
                orphaned.append(f"Line {bullet_group_start + 1}")
            in_bullet_group = False
            prev_was_header = False
        # empty lines don't reset header flag for the purpose of bullet groups
    results.append({
        "rule": "FMT-04", "name": "No orphaned bullets",
        "severity": "required", "passed": len(orphaned) == 0,
        "detail": f"Orphaned bullet groups starting at: {', '.join(orphaned)}" if orphaned else "OK"
    })

    # FMT-05: no inline HTML
    html_lines = []
    in_code = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and re.search(r'<(?!--|!)/?[a-zA-Z][^>]*>', line):
            html_lines.append(f"Line {i+1}")
    results.append({
        "rule": "FMT-05", "name": "No inline HTML",
        "severity": "required", "passed": len(html_lines) == 0,
        "detail": f"Inline HTML found at: {', '.join(html_lines)}" if html_lines else "OK"
    })

    return results


def compute_scores(all_results: list[dict]) -> dict:
    """Compute category and overall scores."""
    categories = {
        "description": {"weight": 0.20, "rules": []},
        "structure": {"weight": 0.15, "rules": []},
        "agent_readiness": {"weight": 0.15, "rules": []},
        "hooks": {"weight": 0.20, "rules": []},
        "context_reset": {"weight": 0.15, "rules": []},
        "workflow": {"weight": 0.10, "rules": []},
        "formatting": {"weight": 0.05, "rules": []},
    }
    prefix_map = {
        "DESC": "description",
        "STRUCT": "structure",
        "AGENT": "agent_readiness",
        "HOOK": "hooks",
        "RESET": "context_reset",
        "FLOW": "workflow",
        "FMT": "formatting",
    }
    for r in all_results:
        prefix = r["rule"].split("-")[0]
        cat = prefix_map.get(prefix)
        if cat:
            categories[cat]["rules"].append(r)

    scores = {}
    overall = 0.0
    total_weight = 0.0
    for cat, data in categories.items():
        # Only count applicable rules in scoring
        applicable = [r for r in data["rules"] if r.get("applicable", True)]
        total = len(applicable)
        passed = sum(1 for r in applicable if r["passed"])
        na_count = len(data["rules"]) - len(applicable)
        pct = (passed / total * 100) if total > 0 else 100
        # If all rules in category are N/A, weight is 0
        effective_weight = data["weight"] if total > 0 else 0.0
        scores[cat] = {
            "passed": passed, "total": total,
            "score": round(pct, 1), "weight": data["weight"],
            "na_count": na_count,
        }
        overall += pct * effective_weight
        total_weight += effective_weight

    # Normalize overall score by actual weight used
    if total_weight > 0:
        overall = overall / total_weight * 1.0
    scores["overall"] = round(overall, 1)
    return scores


def detect_file_type(path: str, content: str) -> str:
    """Detect file type: 'skill', 'command', or 'config'.

    - skill: has YAML frontmatter with name/description, or filename is SKILL.md
    - command: lives under .claude/commands/ (plain markdown prompt file)
    - config: CLAUDE.md or similar project-level config
    """
    basename = os.path.basename(path).lower()
    normalized = path.replace("\\", "/")

    # Skills: SKILL.md or has valid frontmatter with description
    if basename == "skill.md":
        return "skill"
    fm, fm_valid = parse_frontmatter(content)
    if fm_valid and fm and "description" in fm:
        return "skill"

    # Commands: inside .claude/commands/ or a commands/ directory
    if "/.claude/commands/" in normalized or "/commands/" in normalized:
        return "command"

    # Config: CLAUDE.md, AGENTS.md, or similar root-level config
    if basename in ("claude.md", "agents.md", "copilot-instructions.md"):
        return "config"

    # Default: treat as command (most permissive — avoids false fails on unknown files)
    return "command"


def audit_file(path: str, project_root: str = ".") -> dict:
    """Run all quality checks on a single file."""
    try:
        content = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return {"file": path, "error": f"file not found: {path}"}
    except Exception as e:
        return {"file": path, "error": str(e)}

    fm, fm_valid = parse_frontmatter(content)
    file_type = detect_file_type(path, content)

    results = []

    # DESC rules: only applicable to skills (require frontmatter description)
    if file_type == "skill":
        results.extend(check_description_rules(content, fm, fm_valid))
    else:
        for rule_id, name, sev in [
            ("DESC-01", "Description field exists", "critical"),
            ("DESC-02", "Single line description", "critical"),
            ("DESC-03", "Trigger condition present", "critical"),
            ("DESC-04", "No vague language", "high"),
            ("DESC-05", "Names output artifact", "high"),
            ("DESC-06", "80+ characters", "high"),
        ]:
            results.append({
                "rule": rule_id, "name": name, "severity": sev,
                "passed": True, "applicable": False,
                "detail": f"N/A — {file_type} files do not use skill frontmatter"
            })

    results.extend(check_structure_rules(content))

    # AGENT rules: applicable to skills and commands, not config files
    if file_type in ("skill", "command"):
        results.extend(check_agent_readiness_rules(content))
    else:
        for rule_id, name, sev in [
            ("AGENT-01", "Contract framing", "high"),
            ("AGENT-02", "Testable success criteria", "high"),
            ("AGENT-03", "Composability documented", "medium"),
            ("AGENT-04", "Evaluator separation", "medium"),
        ]:
            results.append({
                "rule": rule_id, "name": name, "severity": sev,
                "passed": True, "applicable": False,
                "detail": f"N/A — {file_type} files are not single-purpose instructions"
            })

    results.extend(check_hook_rules(content, project_root))
    results.extend(check_reset_rules(content, project_root))
    results.extend(check_workflow_rules(content))

    # FMT rules: run all, but mark FMT-01 (frontmatter) as N/A for non-skills
    fmt_results = check_formatting_rules(content)
    if file_type != "skill":
        for r in fmt_results:
            if r["rule"] == "FMT-01":
                r["passed"] = True
                r["applicable"] = False
                r["detail"] = f"N/A — {file_type} files do not require frontmatter"
    results.extend(fmt_results)

    scores = compute_scores(results)

    failed = [r for r in results if not r["passed"]]
    passed = [r for r in results if r["passed"]]

    return {
        "file": path,
        "file_type": file_type,
        "scores": scores,
        "total_rules": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "results": results,
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

    if not args:
        print(json.dumps({"error": "no files provided"}))
        sys.exit(1)

    reports = []
    for path in args:
        reports.append(audit_file(path, project_root))

    print(json.dumps(reports, ensure_ascii=False, indent=2))
