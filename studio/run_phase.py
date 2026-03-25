#!/usr/bin/env python3
"""
Studio run instruction helper.

Prepares per-phase instructions, creates run directories, and keeps
output/index.md in sync so every Studio request can be executed agentically
by any AI assistant (Claude Code, Windsurf/Cascade, etc.).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from cleanup import (
    cleanup_runs,
    format_bytes,
    load_cleanup_settings,
)
from validators.document_validator import DocumentValidator
from role_overrides import load_role_overrides
from run_phase_roles import (
    RoleConfigError,
    RoleDetails,
    build_role_details,
    collect_role_artifacts,
    default_role_pack_name,
    get_role_spec,
    parse_role_filename,
    load_manifest,
    load_role_pack,
    normalize_role_filename,
    parse_iteration_from_filename,
    resolve_role_list,
)
from scopes import (
    allocate_iterations,
    generate_scope_instructions,
    generate_scope_prompt,
    load_scopes_config,
)
from decision_points import (
    DecisionPoint,
    extract_decisions_from_run,
    format_decisions_log,
    format_settled_decisions,
    load_decisions_json,
    merge_decisions,
    parse_decision_points,
    save_decisions_json,
)
from question_mode import (
    generate_question_instructions,
    generate_question_integrator_instructions,
    is_question_mode,
)
from rerun import (
    detect_rerun_mode,
    generate_rerun_instructions,
    load_rejection_context,
)
from validators.code_validator import CodeValidator

# Clarity module — lazy-loaded to avoid hard dependency during cross-repo installs
_clarity = None
def _load_clarity():
    global _clarity
    if _clarity is None:
        try:
            import clarity as _mod
            _clarity = _mod
        except ImportError:
            pass
    return _clarity

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redefine]  # Python 3.10 fallback


def get_storage_stats() -> dict:
    """Get simple storage statistics for user awareness."""
    try:
        from cleanup import _collect_runs
        output_root = get_output_root()
        runs = _collect_runs(output_root)
        
        if not runs:
            return {
                "total_size_mb": 0,
                "file_count": 0,
                "oldest_artifact_days": 0,
                "cleanup_suggested": False
            }
        
        total_size_bytes = sum(run.size_bytes for run in runs)
        total_size_mb = total_size_bytes / (1024 * 1024)
        
        # Find oldest artifact
        now = datetime.now(timezone.utc)
        oldest_run = min(runs, key=lambda run: run.created_at)
        oldest_age_days = (now - oldest_run.created_at).days
        
        # Suggest cleanup if storage is getting large or old
        cleanup_suggested = (
            total_size_mb > 50 or  # More than 50MB
            oldest_age_days > 45   # Files older than 45 days
        )
        
        return {
            "total_size_mb": round(total_size_mb, 1),
            "file_count": len(runs),
            "oldest_artifact_days": oldest_age_days,
            "cleanup_suggested": cleanup_suggested
        }
    except Exception:
        # If anything goes wrong, return safe defaults
        return {
            "total_size_mb": 0,
            "file_count": 0,
            "oldest_artifact_days": 0,
            "cleanup_suggested": False
        }


PHASE_DETAILS = {
    "market": {
        "advocate": "Market Growth Strategist — steel-man the idea into a high-virality Steam hook.",
        "contrarian": "The Reality Check — hunt for fatal market flaws and issue VERDICT: APPROVED/REJECTED.",
        "implementer": {
            "title": "Market Research Analyst",
            "deliverables": [
                "Target audience profile with segments + motivations.",
                "Competitor analysis table (at least 3 comparables).",
                "Unique value proposition statement.",
                "Go-to-market plan focused on low-cost tactics.",
                "Success metrics/KPIs to watch.",
            ],
        },
        "notes": "Stop iterating once the contrarian returns VERDICT: APPROVED, then run implementation.",
    },
    "design": {
        "advocate": "Lead Systems Designer — craft the Minimum Viable Fun core loop.",
        "contrarian": "Scope-Creep Police — attack complexity, timeline, and missing UX safeguards.",
        "implementer": {
            "title": "Game Design Documenter",
            "deliverables": [
                "Annotated gameplay loop (bullets or diagram).",
                "Progression system outline.",
                "Key mechanics with rules/exceptions.",
                "UI/UX wireframe descriptions for critical screens.",
                "Technical/design constraints checklist.",
            ],
        },
        "notes": "Keep scope laser-focused on what can be shipped in weeks, not months.",
    },
    "tech": {
        "advocate": "Three.js Technical Architect — define performant WebGL architecture.",
        "contrarian": "Senior SRE — flag performance, compatibility, and ops risks.",
        "implementer": {
            "title": "Technical Architect & Code Generator",
            "deliverables": [
                "High-level architecture diagram or structured description.",
                "Technology stack with justifications + fallbacks.",
                "Suggested file/module structure.",
                "Test specifications (what will be tested, expected behaviors).",
                "Test code (unit tests, integration tests as appropriate).",
                "Implementation code (written to pass the tests).",
                "Key algorithms/data-structure notes.",
                "Instructions to run tests and verify the implementation.",
            ],
        },
        "notes": "Test-driven discipline: Define testable requirements, write tests first, then implement to pass tests. Don't forget mobile/browser constraints and ops toil when approving.",
    },
    "studio": {
        "advocate": "Studio Workflow Producer — articulate the inspiring yet actionable vision.",
        "contrarian": "Bootstrapped Reality Auditor — interrogate costs, scope, and maintenance burden.",
        "integrator": "Systems Integrator & Ops Lead — merge inspiration + constraints into a pragmatic upgrade plan after approval.",
        "notes": (
            "Iterate like every other phase until the Contrarian issues VERDICT: APPROVED. "
            "Then hand off to the Integrator for the roadmap before summarizing."
        ),
    },
}

INDEX_HEADER = [
    "# Studio Run Index",
    "",
    "| Run ID | Phase | Created (UTC) | Status | Input | Summary |",
    "| --- | --- | --- | --- | --- | --- |",
]

CLEANUP_SKIP_ENV = "STUDIO_SKIP_CLEANUP"
CLEANUP_DRY_ENV = "STUDIO_CLEANUP_DRY_RUN"
ARTIFACT_ROOT_ENV = "STUDIO_ARTIFACT_ROOT"

SUBCOMMANDS = {
    "prepare", "finalize", "cleanup", "validate",
    "record-decisions", "check-decisions",
    "extract-decisions", "inject-context",
    "init", "check-install", "update",
    "show-clarity", "set-clarity", "recompute-clarity",
}


def _resolve_env_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

def get_studio_root() -> Path:
    env_override = os.environ.get("STUDIO_ROOT")
    if env_override:
        return _resolve_env_path(env_override)
    return Path(__file__).resolve().parent


_artifact_root_override: Path | None = None


def set_artifact_root(path: Path | None) -> None:
    """Set an explicit artifact root (used by --artifact-root CLI flag)."""
    global _artifact_root_override
    _artifact_root_override = path


def get_artifact_root() -> Path:
    if _artifact_root_override is not None:
        return _artifact_root_override.resolve()

    env_override = os.environ.get(ARTIFACT_ROOT_ENV)
    if env_override:
        return _resolve_env_path(env_override)

    studio_root = get_studio_root().resolve()
    cwd = Path.cwd().resolve()
    if cwd == studio_root or _is_within(cwd, studio_root):
        return studio_root
    return cwd


def get_output_root() -> Path:
    artifact_root = get_artifact_root().resolve()
    studio_root = get_studio_root().resolve()
    if artifact_root == studio_root:
        return studio_root / "output"
    return artifact_root / ".studio" / "output"


def get_knowledge_log_path() -> Path:
    artifact_root = get_artifact_root().resolve()
    studio_root = get_studio_root().resolve()
    if artifact_root == studio_root:
        return studio_root / "knowledge" / "run_log.md"
    return artifact_root / ".studio" / "knowledge" / "run_log.md"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def write_json(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_runs(base_output: Path) -> List[Dict]:
    entries: List[Dict] = []
    if not base_output.exists():
        return entries

    for phase_dir in sorted(base_output.iterdir()):
        if not phase_dir.is_dir():
            continue
        for run_dir in sorted(phase_dir.glob("run_*")):
            meta_path = run_dir / "run.json"
            if meta_path.exists():
                try:
                    meta = load_json(meta_path)
                except (json.JSONDecodeError, OSError) as exc:
                    print(f"Warning: skipping {meta_path} (corrupt or unreadable: {exc})")
                    continue
                meta["run_dir"] = run_dir.as_posix()
                entries.append(meta)
    return entries


def write_index(entries: List[Dict], index_path: Path) -> None:
    lines = INDEX_HEADER.copy()
    entries_sorted = sorted(
        entries,
        key=lambda item: item.get("created_iso", ""),
        reverse=True,
    )
    for entry in entries_sorted:
        summary_cell = entry.get("summary_path") or "_pending_"
        if summary_cell not in ("", "_pending_"):
            summary_cell = f"[summary]({summary_cell})"
        elif summary_cell == "":
            summary_cell = "_pending_"

        lines.append(
            "| {run_id} | {phase} | {created} | {status} | {input} | {summary} |".format(
                run_id=entry.get("run_id", "unknown"),
                phase=entry.get("phase", "unknown"),
                created=entry.get("created_display", entry.get("created_iso", "")),
                status=entry.get("status", "PENDING"),
                input=sanitize_cell(entry.get("input", "")),
                summary=summary_cell,
            )
        )

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _log_cleanup_report(report) -> None:
    if report.total_runs == 0:
        print("Cleanup: no prior runs detected.")
        return

    print(
        f"Cleanup: scanned {report.total_runs} runs "
        f"({format_bytes(report.total_size_bytes)})"
    )
    if report.deletions:
        reason_counts = report.reasons_summary()
        reason_str = ", ".join(f"{k}={v}" for k, v in sorted(reason_counts.items()))
        verb = "Would remove" if report.dry_run else "Removed"
        print(
            f"- {verb} {len(report.deletions)} runs "
            f"({format_bytes(report.freed_bytes)}) [{reason_str}]"
        )
    else:
        print("- No deletions required.")
    if report.errors:
        for msg in report.errors:
            print(f"- Cleanup warning: {msg}")


def _maybe_run_cleanup(*, dry_run: bool = False) -> None:
    studio_root = get_studio_root()
    output_root = get_output_root()
    settings = load_cleanup_settings(studio_root)
    report = cleanup_runs(output_root, settings, dry_run=dry_run)
    _log_cleanup_report(report)


def _find_previous_run_dir(current_run_dir: Path) -> Path | None:
    """Find the most recent prior run directory in the same phase folder."""
    phase_dir = current_run_dir.parent
    prior_runs = sorted(
        [d for d in phase_dir.glob("run_*") if d.is_dir() and d != current_run_dir],
    )
    return prior_runs[-1] if prior_runs else None


def _ensure_summary_path(meta: Dict, run_dir: Path) -> Path:
    summary_path = meta.get("summary_path")
    if summary_path:
        return Path(summary_path)
    summary_file = run_dir / "summary.md"
    meta["summary_path"] = summary_file.as_posix()
    return summary_file


def _validate_artifacts(
    phase: str, run_dir: Path, summary_path: Path, meta: Dict | None = None
) -> Tuple[int, List[str], List[str], List[str]]:
    errors: List[str] = []
    completed_roles: List[str] = []
    missing_roles: List[str] = []

    if phase == "studio":
        studio_meta = (meta or {}).get("studio_roles") or {}
        invited_roles = studio_meta.get("invited") or []
        if not invited_roles:
            errors.append(
                "run.json is missing invited Studio roles. Re-run prepare after updating studio.manifest.json."
            )
        max_iteration = 0
        for role in invited_roles:
            advocate_files = collect_role_artifacts(run_dir, role, "advocate")
            contrarian_files = collect_role_artifacts(run_dir, role, "contrarian")
            if not advocate_files or not contrarian_files:
                missing_roles.append(role)
                continue
            completed_roles.append(role)
            role_iterations = max(
                [parse_iteration_from_filename(path.name) for path in contrarian_files],
                default=0,
            )
            max_iteration = max(max_iteration, role_iterations or len(contrarian_files))

        if not completed_roles:
            errors.append(
                "No Studio role produced both advocate and contrarian artifacts. "
                "Ensure at least one invited role completes the loop."
            )

        integrator_file = run_dir / "integrator.md"
        if not integrator_file.exists():
            errors.append("Missing integrator roadmap (integrator.md).")

        iterations_value = max_iteration or 0
    else:
        advocate_files = sorted(run_dir.glob("advocate_*.md"))
        if not advocate_files:
            errors.append("Missing advocate outputs (advocate_*.md).")

        contrarian_files = sorted(run_dir.glob("contrarian_*.md"))
        if not contrarian_files:
            errors.append("Missing contrarian outputs (contrarian_*.md).")

        iterations_value = len(advocate_files)

    if not summary_path.exists():
        errors.append(f"Missing summary file at {summary_path}.")

    if errors:
        raise FileNotFoundError(
            "Finalize aborted due to missing artifacts:\n- " + "\n- ".join(errors)
        )

    advocate_names = []
    if phase != "studio":
        advocate_names = [file.name for file in advocate_files]  # type: ignore[name-defined]

    # --- Quality checks (warnings only, never block finalize) ---
    quality_warnings: List[str] = []
    quality_errors: List[str] = []
    checks_run = 0
    doc_validator = DocumentValidator()

    all_advocate_paths: List[Path] = []
    all_contrarian_paths: List[Path] = []
    if phase == "studio":
        for role in completed_roles:
            all_advocate_paths.extend(collect_role_artifacts(run_dir, role, "advocate"))
            all_contrarian_paths.extend(collect_role_artifacts(run_dir, role, "contrarian"))
    else:
        all_advocate_paths = sorted(run_dir.glob("advocate_*.md"))
        all_contrarian_paths = sorted(run_dir.glob("contrarian_*.md"))

    all_artifact_paths = all_advocate_paths + all_contrarian_paths

    contrarian_set = set(all_contrarian_paths)
    scope_stats: Dict[str, Dict] = {}

    for fpath in all_artifact_paths:
        try:
            content = fpath.read_text(encoding="utf-8")
        except OSError:
            quality_warnings.append(f"{fpath.name}: could not read file")
            continue

        # 1. Verdict check (contrarian files only)
        if fpath in contrarian_set:
            checks_run += 1
            verdict_result = doc_validator.check_verdict(fpath)
            if not verdict_result.passed:
                quality_warnings.append(f"{fpath.name}: no VERDICT found")
            quality_warnings.extend(f"{fpath.name}: {w}" for w in verdict_result.warnings)

        # 2. Rubber-stamp detector
        checks_run += 1
        stripped_len = len(content.strip())
        if stripped_len < 200:
            quality_warnings.append(
                f"{fpath.name}: only {stripped_len} chars (possible rubber-stamp)"
            )

        # 3. Format check
        checks_run += 1
        fmt_result = doc_validator.check_format(fpath)
        quality_warnings.extend(f"{fpath.name}: {w}" for w in fmt_result.warnings)
        quality_errors.extend(f"{fpath.name}: {issue}" for issue in fmt_result.issues)

        # 4. Per-scope output stats
        _, _, scope, _ = parse_role_filename(fpath.name)
        scope_key = scope or "flat"
        if scope_key not in scope_stats:
            scope_stats[scope_key] = {"files": 0, "total_chars": 0, "total_words": 0}
        scope_stats[scope_key]["files"] += 1
        scope_stats[scope_key]["total_chars"] += len(content)
        scope_stats[scope_key]["total_words"] += len(content.split())

    if quality_warnings or quality_errors:
        print("Quality warnings:")
        for w in quality_warnings:
            print(f"  ⚠ {w}")
        for e in quality_errors:
            print(f"  ✗ {e}")

    if meta is not None:
        meta["quality"] = {
            "checks_run": checks_run,
            "warnings": quality_warnings,
            "errors": quality_errors,
        }

        for stats in scope_stats.values():
            stats["avg_words"] = round(stats["total_words"] / max(stats["files"], 1))
        meta["scope_stats"] = scope_stats

    return iterations_value, advocate_names, completed_roles, missing_roles


def _append_run_log(meta: Dict) -> None:
    log_path = get_knowledge_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("# Studio Run Log\n\n", encoding="utf-8")

    summary_path = meta.get("summary_path", "")
    summary_cell = (
        summary_path if not summary_path else f"[summary]({summary_path})"
    )
    lines = [
        f"## {meta.get('run_id', 'unknown')} ({meta.get('phase', 'unknown')}) – {meta.get('status', 'PENDING')}",
        f"- Created: {meta.get('created_display', meta.get('created_iso', ''))}",
        f"- Verdict: {meta.get('verdict', 'N/A')}",
        f"- Iterations: {meta.get('iterations_run', 'N/A')}",
        f"- Hours: {meta.get('hours', 'N/A')} | Cost: {meta.get('cost', 'N/A')}",
        f"- Summary: {summary_cell}",
        "",
    ]
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("\n".join(lines))


def build_instruction_doc(
    meta: Dict, run_dir: Path, studio_roles: List[RoleDetails] | None = None,
    scopes_config=None, scopes_allocations: Dict[str, int] | None = None,
    clarity_snapshot=None,
) -> str:
    phase = meta["phase"]
    info = PHASE_DETAILS[phase]
    rel_dir = run_dir.as_posix()
    base_section = [
        f"# Studio Instructions — {meta['run_id']}",
        "",
        f"- **Phase:** {phase.title()}",
        f"- **Run directory:** `{rel_dir}`",
        f"- **Max iterations:** {meta['max_iterations']}",
        f"- **Input:** {meta['input']}",
    ]
    if phase == "studio":
        base_section.append(f"- **Budget Cap:** {meta['budget_cap']}")
        studio_info = meta.get("studio_roles") or {}
        pack = studio_info.get("pack", "n/a")
        overrides = studio_info.get("overrides") or []
        overrides_display = ", ".join(overrides) if overrides else "none"
        base_section.append(f"- **Role pack:** {pack} (overrides: {overrides_display})")
    base_section.extend(
        [
            f"- **Created:** {meta['created_display']} (UTC)",
            "- **Artifacts:**",
        ]
    )
    if phase == "studio":
        base_section.append(
            "  - Advocate outputs → per-role files like "
            f"`{rel_dir}/advocate--marketing--<iteration>.md` (see Role Menu)"
        )
        base_section.append(
            "  - Contrarian outputs → per-role files like "
            f"`{rel_dir}/contrarian--marketing--<iteration>.md`"
        )
    else:
        base_section.append(f"  - Advocate outputs → `{rel_dir}/advocate_<iteration>.md`")
        base_section.append(f"  - Contrarian outputs → `{rel_dir}/contrarian_<iteration>.md`")
    if phase != "studio":
        base_section.append(f"  - Implementation → `{rel_dir}/implementation.md` (after approval)")
    else:
        base_section.append(
            "  - Integrator/Roadmap → "
            f"`{rel_dir}/integrator.md` (after approval; include integrator duel sections)"
        )
    base_section.append(f"  - Summary → `{rel_dir}/summary.md`")

    # Add scope instructions if scopes are configured
    scope_section: List[str] = []
    if scopes_config and scopes_allocations:
        scope_instructions = generate_scope_instructions(scopes_config, scopes_allocations)
        scope_section.append(scope_instructions)
        # Per-scope agent prompt templates for orchestrator use
        scope_section.extend([
            "",
            "### Per-Scope Agent Prompt Templates",
            "",
            "The orchestrator can generate scope-specific agent prompts using:",
            "",
            "```bash",
            f'python "{get_studio_root()}/run_phase.py" inject-context --run-dir {{run_dir}} --scope {{scope}} --role {{role}} --stance {{stance}}',
            "```",
            "",
            "Or extract decisions between agents with:",
            "",
            "```bash",
            f'python "{get_studio_root()}/run_phase.py" extract-decisions --run-dir {{run_dir}}',
            "```",
            "",
        ])
    
    # Add rerun context if previous rejections exist in prior runs.
    # Question mode bypasses rerun context — surfacing unknowns is not
    # a response to prior rejections.
    rerun_section: List[str] = []
    is_qmode = is_question_mode(meta.get("output_type"))
    prev_run_dir = _find_previous_run_dir(run_dir)
    if not is_qmode and prev_run_dir and detect_rerun_mode(prev_run_dir):
        rerun_instructions = generate_rerun_instructions(prev_run_dir)
        rerun_section.append(rerun_instructions)
        rerun_section.append("")

    # --- Question mode: override roles, loop, and integrator sections ---

    question_mode_section: List[str] = []
    if is_qmode:
        question_mode_section.extend([
            "",
            "## Output Mode: Question Surfacing",
            "",
            "> **This run surfaces open questions — NOT deliverables.**",
            "> Advocates produce prioritised question lists; contrarians challenge priorities",
            "> and surface missing questions. The integrator consolidates and deduplicates.",
            "",
        ])

    roles_section = [
        "",
        "## Agent Roles",
        "",
        f"- **Advocate:** {info['advocate']}",
        f"- **Contrarian:** {info['contrarian']}",
    ]
    if phase != "studio":
        if is_qmode:
            roles_section.extend([
                "",
                "### Question-Surfacing Instructions",
                "",
                "The advocate surfaces 5–15 prioritised questions (P0/P1/P2) that must be",
                "answered before deliverables can be produced. The contrarian challenges",
                "priorities, surfaces unstated assumptions, and identifies missing questions.",
                "",
                "**Do NOT produce deliverables, specs, or recommendations — only questions.**",
            ])
        else:
            impl = info["implementer"]
            roles_section.extend(
                [
                    f"- **Implementer:** {impl['title']} — generate the deliverables listed below once APPROVED.",
                    "",
                    "### Implementation Checklist",
                    "",
                ]
            )
            roles_section.extend([f"- {item}" for item in impl["deliverables"]])
    else:
        roles_section.append(f"- **Integrator:** {info['integrator']}")
        if is_qmode:
            roles_section.append(
                "- Integrator consolidates questions across roles into a single deduplicated set — NO roadmap."
            )
        else:
            roles_section.append(
                "- Integrator runs its own capped duel (Advocate vs. Contrarian) inside `integrator.md` once the pods approve."
            )

    loop_section = [
        "",
        "## Iteration Loop",
        "",
        "1. Start at iteration 1.",
        "2. Run the Advocate prompt, save to `advocate_<n>.md`.",
        "3. Run the Contrarian prompt using that advocate file, save to `contrarian_<n>.md`.",
    ]
    loop_section.extend(
        [
            "4. If the contrarian verdict is `VERDICT: REJECTED` and you still have iterations left, feed the rejection back into the Advocate and repeat.",
        ]
    )
    if phase != "studio":
        if is_qmode:
            loop_section.append(
                "5. As soon as a contrarian returns `VERDICT: APPROVED`, write `summary.md` with the consolidated question set."
            )
        else:
            loop_section.append(
                "5. As soon as a contrarian returns `VERDICT: APPROVED`, move to the Implementer checklist."
            )
    else:
        if is_qmode:
            loop_section.append(
                "5. Once all contrarians return `VERDICT: APPROVED`, the Integrator consolidates all questions into `integrator.md`."
            )
        else:
            loop_section.append(
                "5. Once the contrarian returns `VERDICT: APPROVED`, operate as the Integrator to merge inspiration + constraints into a roadmap (`integrator.md`)."
            )
    loop_section.append("")
    loop_section.append(f"**Notes:** {info['notes']}")

    # Decision Point Protocol — always included except in question mode
    decision_point_section: List[str] = []
    if not is_qmode:
        decision_point_section.extend([
            "",
            "## Decision Point Protocol",
            "",
            "When you encounter a gap, ambiguity, or fork that could meaningfully change your approach, flag it as a decision point. Do NOT silently assume — surface it.",
            "",
            "### Format",
            "",
            "Use a markdown blockquote with a bold DECISION header:",
            "",
            "```",
            "> **DECISION [P0]:** Should the social deduction mechanic be real-time or turn-based?",
            "> **Unblocks:** Core loop design — fundamentally different gameplay",
            "> **Options:** (a) Real-time (Among Us style) (b) Turn-based (Mafia style)",
            "```",
            "",
            "### Priority Levels",
            "",
            "- **P0 (Blocking):** Cannot proceed without an answer. The orchestrator will pause and ask the user.",
            "- **P1 (Important):** Shapes the approach significantly. State your assumption and continue, but flag it so the user can override.",
            "- **P2 (Context):** Nice-to-know. Log it for completeness but do not pause.",
            "",
            "### For Advocates",
            "You MUST surface at least 1 decision point (P0 or P1) per output. If nothing is genuinely unsettled, state that explicitly rather than omitting the section. Prefer fewer, high-quality P0/P1 flags over many P2s. Each decision point must name what it unblocks — if you can't articulate the impact, it's not worth flagging.",
            "",
            "### For Contrarians",
            "If the advocate assumed something that is actually unsettled, you MUST flag it as a decision point. Decision points are required output when assumptions are unsettled — do not let unexamined assumptions pass.",
        ])

    # Clarity-guided focus section — inject if clarity data exists
    clarity_section: List[str] = []
    _cl = _load_clarity()
    if _cl and clarity_snapshot is not None and not is_qmode:
        if scopes_config and scopes_config.scopes:
            # Generate clarity guidance for each scope so agents get scope-appropriate density
            for scope in scopes_config.scopes:
                clarity_section.append(_cl.generate_clarity_instructions(clarity_snapshot, scope.name))
        else:
            clarity_section.append(_cl.generate_clarity_instructions(clarity_snapshot, "depth"))

    role_menu_section: List[str] = []
    if phase == "studio" and studio_roles:
        role_menu_section.extend(
            [
                "",
                "## Role Menu",
                "",
                "| Role | Advocate focus | Contrarian focus | Deliverables | Files | Prompt |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for details in studio_roles:
            slug = details.name.replace(" ", "-")
            deliverables_text = "<br>".join(details.deliverables) or "-"
            files_text = "<br>".join(
                [
                    f"`{normalize_role_filename(details.name, 1, 'advocate')}`",
                    f"`{normalize_role_filename(details.name, 1, 'contrarian')}`",
                ]
            )
            prompt_link = details.prompt_doc or "-"
            if details.prompt_doc:
                prompt_link = f"[{slug}]({details.prompt_doc})"
            role_menu_section.append(
                f"| {details.title} | {details.advocate_focus} | {details.contrarian_focus} | "
                f"{deliverables_text} | {files_text} | {prompt_link} |"
            )

        if any(details.escalate_on for details in studio_roles):
            role_menu_section.extend(
                [
                    "",
                    "### Escalation cues",
                    "",
                ]
            )
            for details in studio_roles:
                if details.escalate_on:
                    cues = "; ".join(details.escalate_on)
                    role_menu_section.append(f"- **{details.title}:** {cues}")

        # Per-role question-surfacing instructions (studio + question mode)
        if is_qmode:
            role_menu_section.extend(["", "### Per-Role Question Instructions", ""])
            for details in studio_roles:
                role_data = {
                    "title": details.title,
                    "advocate_focus": details.advocate_focus,
                    "contrarian_focus": details.contrarian_focus,
                    "deliverables": details.deliverables,
                    "escalate_on": details.escalate_on or [],
                }
                adv_instr, con_instr = generate_question_instructions(role_data)
                role_menu_section.extend([
                    f"#### {details.title}",
                    "",
                    "**Advocate question prompt:**",
                    "",
                    adv_instr.strip(),
                    "",
                    "**Contrarian question prompt:**",
                    "",
                    con_instr.strip(),
                    "",
                ])

    integrator_duel_section: List[str] = []
    if phase == "studio":
        if is_qmode:
            integrator_duel_section.extend([
                "",
                "## Question Integrator (after approval)",
                "",
                generate_question_integrator_instructions().strip(),
                "",
                "Save the consolidated question set to `integrator.md`.",
            ])
        else:
            integrator_duel_section.extend(
                [
                    "",
                    "## Integrator Duel (after approval)",
                    "",
                    "1. Inside `integrator.md`, add `### Integrator Advocate` summarizing the fused plan.",
                    "2. Add `### Integrator Contrarian` critiquing feasibility, ops risk, and sequencing. End with `VERDICT: APPROVED/REJECTED`.",
                    "3. If REJECTED, adjust with one additional mini-iteration (max 2 total) before continuing.",
                    "4. Close with `### Integrated Plan` that synthesizes both perspectives and lists next steps.",
                ]
            )

    finalize_snippet = textwrap.dedent(
        f"""
        ```
        python "{get_studio_root()}/run_phase.py" finalize --phase {phase} --run-id {meta['run_id']} --status completed --verdict <APPROVED|REJECTED|N/A>
        ```
        """
    ).strip()

    summary_section = [
        "",
        "## Summary & Packaging",
        "",
        "- Summarize the entire run (inputs, iterations, verdict, key recommendations, next actions) in `summary.md`.",
        "- When finished, finalize the index entry:",
        finalize_snippet,
        "- `finalize` will update `output/index.md` so other projects can discover this run.",
    ]

    return (
        textwrap.dedent(
            "\n".join(
                base_section
                + question_mode_section
                + scope_section
                + rerun_section
                + roles_section
                + loop_section
                + decision_point_section
                + clarity_section
                + role_menu_section
                + integrator_duel_section
                + summary_section
            )
        ).strip()
        + "\n"
    )


def _resolve_studio_roles(args: argparse.Namespace) -> Tuple[Dict | None, List[RoleDetails] | None]:
    """Resolve studio-phase role configuration from CLI args.

    Returns (role_meta_dict, role_details_list) or (None, None) for non-studio phases.
    """
    if args.phase.lower() != "studio":
        return None, None

    studio_root = get_studio_root()
    artifact_root = get_artifact_root()
    manifest = load_manifest(studio_root)
    try:
        pack_name = args.role_pack or default_role_pack_name(manifest)
        pack_data = load_role_pack(studio_root, pack_name)
        cli_overrides = list(args.roles or [])
        invited_roles = resolve_role_list(manifest, pack_data, cli_overrides)
        if not invited_roles:
            raise RoleConfigError(
                "Studio role selection resolved to zero roles. Adjust the pack or overrides."
            )
        # Load project-local role overrides from .studio/roles/
        role_overrides = load_role_overrides(artifact_root)
        role_details = build_role_details(manifest, invited_roles, overrides=role_overrides)
        role_meta: Dict = {
            "pack": pack_name,
            "overrides": cli_overrides,
            "invited": invited_roles,
            "role_overrides_applied": list(role_overrides.keys()) if role_overrides else [],
        }
        return role_meta, role_details
    except RoleConfigError as exc:
        raise RuntimeError(f"Studio role configuration error: {exc}") from exc


def _resolve_scopes(args: argparse.Namespace):
    """Resolve scope-based iteration config from CLI args.

    Returns (scopes_config, scopes_allocations, scopes_meta) — all None if disabled.
    """
    if args.no_scopes:
        return None, None, None

    # Determine scopes path
    if args.scopes:
        scopes_path = Path(args.scopes)
        if not scopes_path.is_absolute():
            scopes_path = get_studio_root() / scopes_path
    else:
        default_scopes = get_studio_root() / ".studio" / "scopes.toml"
        scopes_path = default_scopes if default_scopes.exists() else None

    if not scopes_path:
        return None, None, None

    try:
        config = load_scopes_config(scopes_path)
        allocations = allocate_iterations(config, args.max_iterations)
        meta: Dict = {
            "config_path": scopes_path.as_posix(),
            "scopes": [
                {"name": s.name, "focus": s.focus, "allocated_iterations": allocations[s.name]}
                for s in config.scopes
            ],
            "total_iterations": sum(allocations.values()),
        }
        print(f"Loaded scopes config: {scopes_path}")
        print(f"- Total iteration budget: {meta['total_iterations']}")
        for scope_info in meta['scopes']:
            print(f"  - {scope_info['name']}: {scope_info['allocated_iterations']} iterations")
        return config, allocations, meta
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Scopes configuration file not found: {exc}\n\n"
            f"To fix:\n"
            f"1. Create .studio/scopes.toml with scope definitions, or\n"
            f"2. Use --no-scopes to disable scope-based iteration, or\n"
            f"3. See docs/SCOPES_GUIDE.md for examples"
        ) from exc
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid scopes configuration: {exc}\n\n"
            f"To fix:\n"
            f"1. Check TOML syntax in your scopes config\n"
            f"2. Ensure all scopes have 'focus' and 'max_iterations' fields\n"
            f"3. See docs/SCOPES_GUIDE.md for valid examples"
        ) from exc


def _build_run_meta(
    phase: str,
    text: str,
    now: datetime,
    run_id: str,
    args: argparse.Namespace,
    studio_role_meta: Dict | None,
    scopes_meta: Dict | None,
) -> Dict:
    """Build the run metadata dictionary."""
    meta: Dict = {
        "run_id": run_id,
        "phase": phase,
        "input": text,
        "budget_cap": args.budget if phase == "studio" else "",
        "max_iterations": args.max_iterations,
        "created_iso": now.isoformat(timespec="seconds"),
        "created_display": now.strftime("%Y-%m-%d %H:%M"),
        "status": "PENDING",
        "summary_path": "",
        "verdict": "",
        "iterations_run": None,
        "output_type": getattr(args, "mode", "deliverables"),
    }
    if studio_role_meta:
        meta["studio_roles"] = studio_role_meta
    if scopes_meta:
        meta["scopes"] = scopes_meta
    meta["storage"] = get_storage_stats()
    return meta


def _scaffold_external_repo(artifact_root: Path, studio_root: Path) -> None:
    """Create .studio/ structure and bridge doc in an external repo on first use."""
    studio_dir = artifact_root / ".studio"
    if studio_dir.exists():
        return

    studio_dir.mkdir(parents=True, exist_ok=True)
    (studio_dir / "output").mkdir(exist_ok=True)
    (studio_dir / "knowledge").mkdir(exist_ok=True)

    # Copy bridge template if no bridge doc exists
    bridge_candidates = [
        artifact_root / "docs" / "studio-bridge.md",
        artifact_root / "studio-bridge.md",
    ]
    if not any(c.exists() for c in bridge_candidates):
        template_path = studio_root / "docs" / "STUDIO_BRIDGE_TEMPLATE.md"
        if template_path.exists():
            dest = artifact_root / "docs" / "studio-bridge.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            template = template_path.read_text(encoding="utf-8")
            template = template.replace(
                'export STUDIO_ROOT="/path/to/studio"',
                f'export STUDIO_ROOT="{studio_root}"',
            )
            dest.write_text(template, encoding="utf-8")
            print(f"  Created bridge doc: {dest}")
            print(f"  Fill in the canon table and project summary.")

    print(f"  Initialized .studio/ in {artifact_root}")


def prepare_run(args: argparse.Namespace) -> str:
    phase = args.phase.lower()
    if phase not in PHASE_DETAILS:
        raise ValueError(f"Unsupported phase '{phase}'.")
    text = args.text.strip()
    if not text:
        raise ValueError("Input text cannot be empty.")

    # Auto-scaffold external repos on first use
    artifact_root = get_artifact_root()
    studio_root = get_studio_root()
    if artifact_root != studio_root:
        _scaffold_external_repo(artifact_root, studio_root)

    skip_cleanup = getattr(args, "skip_cleanup", False) or _env_flag(CLEANUP_SKIP_ENV)
    cleanup_dry = getattr(args, "cleanup_dry_run", False) or _env_flag(CLEANUP_DRY_ENV)
    if not skip_cleanup:
        _maybe_run_cleanup(dry_run=cleanup_dry)

    now = utc_now()
    timestamp_slug = now.strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{phase}_{timestamp_slug}"
    run_dir = get_output_root() / phase / run_id

    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise RuntimeError(
            f"Run directory {run_id} already exists. "
            f"This may be due to concurrent prepare commands or a timestamp collision. "
            f"Wait 1 second and retry, or use a different phase/text combination."
        )
    run_dir_abs = run_dir.resolve()

    studio_role_meta, studio_role_details = _resolve_studio_roles(args)
    scopes_config, scopes_allocations, scopes_meta = _resolve_scopes(args)
    meta = _build_run_meta(phase, text, now, run_id, args, studio_role_meta, scopes_meta)

    # Load project-level clarity for instruction injection
    project_clarity = None
    _cl = _load_clarity()
    if _cl:
        project_clarity = _cl.load_project_clarity(get_artifact_root())

    instructions = build_instruction_doc(
        meta, run_dir, studio_role_details, scopes_config, scopes_allocations,
        clarity_snapshot=project_clarity,
    )
    instructions_path = run_dir / "instructions.md"
    instructions_path.write_text(instructions, encoding="utf-8")
    instructions_abs_path = instructions_path.resolve()

    write_json(run_dir / "run.json", meta)
    rebuild_index()

    print(f"Prepared {run_id} ({phase})")
    print(f"- Run directory: {run_dir_abs}")
    print(f"- Instructions: {instructions_abs_path}")

    if scopes_meta:
        print(f"\n💡 Tip: Scopes are active. Work through {scopes_meta['scopes'][0]['name']} scope first.")
    else:
        print(f"\n💡 Tip: Want to optimize iteration budgets? Create .studio/scopes.toml")
        print(f"   See: docs/SCOPES_GUIDE.md")

    # Append to usage log (fail silently — don't break prepare over logging)
    try:
        mode = getattr(args, "mode", "deliverables")
        roles_str = ",".join(r.name for r in (studio_role_details or []))
        scoped = "true" if scopes_meta else "false"
        log_line = f"{now.isoformat(timespec='seconds')} | prepare | {phase} | {mode} | roles={roles_str} | scoped={scoped}\n"
        usage_log = artifact_root / ".studio" / "usage.log"
        usage_log.parent.mkdir(parents=True, exist_ok=True)
        with open(usage_log, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass  # Usage logging must never block prepare

    storage_stats = meta.get("storage", {})
    if storage_stats.get("cleanup_suggested", False):
        print(f"\n🧹 Storage Tip: You have {storage_stats['total_size_mb']}MB of Studio artifacts")
        print(f"   (oldest: {storage_stats['oldest_artifact_days']} days ago). Consider cleanup:")
        print(f"   python run_phase.py cleanup --dry-run  # Preview what would be deleted")
        print(f"   python run_phase.py cleanup           # Execute cleanup")

    return run_id


def finalize_run(args: argparse.Namespace) -> None:
    phase = args.phase.lower()
    run_id = args.run_id
    run_dir = get_output_root() / phase / run_id
    meta_path = run_dir / "run.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Could not find metadata for {run_id} at {meta_path}")

    meta = load_json(meta_path)
    meta["status"] = args.status.upper()
    if args.summary:
        meta["summary_path"] = args.summary
    summary_path = _ensure_summary_path(meta, run_dir)

    (
        iterations_count,
        advocate_files,
        completed_roles,
        missing_roles,
    ) = _validate_artifacts(phase, run_dir, summary_path, meta)

    if args.verdict:
        meta["verdict"] = args.verdict.upper()
    meta["iterations_run"] = args.iterations_run if args.iterations_run is not None else iterations_count
    if phase == "studio":
        studio_meta = meta.setdefault("studio_roles", {})
        studio_meta["completed"] = completed_roles
        studio_meta["missing"] = missing_roles
    if args.hours is not None:
        meta["hours"] = args.hours
    if args.cost is not None:
        meta["cost"] = args.cost
    meta["updated_iso"] = utc_now().isoformat(timespec="seconds")

    # Aggregate agent metrics into run.json before the single write
    metrics_entries = _load_metrics(run_dir)
    if metrics_entries:
        meta["metrics"] = _summarize_metrics(metrics_entries)

    write_json(meta_path, meta)
    rebuild_index()
    _append_run_log(meta)

    if metrics_entries:
        total_tokens = meta["metrics"]["total_tokens"]
        agent_count = meta["metrics"]["agents"]
        print(f"Agent metrics: {agent_count} agents, {total_tokens:,} total tokens")

    # Generate decisions.md — merge agent-surfaced decisions with any already-settled ones
    existing = load_decisions_json(run_dir)
    extracted = extract_decisions_from_run(run_dir)
    if existing or extracted:
        merge_decisions(existing, extracted)
        save_decisions_json(run_dir, existing)
        # Use settled format if any decisions have answers, otherwise use discovery log
        has_answers = any(dp.answer is not None for dp in existing)
        decisions_path = run_dir / "decisions.md"
        if has_answers:
            decisions_path.write_text(
                format_settled_decisions(existing), encoding="utf-8"
            )
        else:
            decisions_path.write_text(
                format_decisions_log(existing), encoding="utf-8"
            )
        print(f"Generated {decisions_path.name} with {len(existing)} decision point(s)")

        # Recompute clarity from merged decisions
        _cl = _load_clarity()
        if _cl:
            context = _cl.detect_context_scope(meta.get("input", ""))
            prior = _cl.load_project_clarity(get_artifact_root())
            snapshot = _cl.compute_clarity_snapshot(
                existing, context, run_id=run_id, prior_snapshot=prior
            )
            _cl.save_clarity_json(run_dir / "clarity.json", snapshot)
            _cl.save_project_clarity(get_artifact_root(), snapshot)
            print(f"Updated clarity scores ({len(snapshot.topics)} topic(s), mean: {snapshot.mean_score:.2f})")

    print(f"Finalized {run_id} ({phase}) → {meta['status']}")

    # Contextual hints for next steps
    if meta['status'] == 'COMPLETED' and meta.get('verdict') == 'APPROVED':
        print(f"\n💡 Next steps:")
        print(f"   1. Validate outputs: python run_phase.py validate --run-id {run_id}")
        print(f"   2. Review summary: {run_dir}/summary.md")
        if phase != 'studio':
            print(f"   3. Implement recommendations from the run")
    elif meta['status'] == 'COMPLETED' and meta.get('verdict') == 'REJECTED':
        print(f"\n💡 Run was rejected. Consider:")
        print(f"   1. Review rejection reasons in contrarian files")
        print(f"   2. Prepare a rerun with revised approach")
        print(f"   3. Rerun will automatically inject failure context")


def rebuild_index() -> None:
    base_output = get_output_root()
    entries = collect_runs(base_output)
    write_index(entries, base_output / "index.md")


def _normalize_prepare_roles_tokens(argv: Sequence[str]) -> List[str]:
    normalized: List[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]

        if token.startswith("--roles="):
            normalized.append(token)
            index += 1
            continue

        if token != "--roles":
            normalized.append(token)
            index += 1
            continue

        index += 1
        collected: List[str] = []
        while index < len(argv):
            candidate = argv[index]
            if candidate.startswith("--"):
                break
            if candidate in SUBCOMMANDS:
                break
            collected.append(candidate)
            index += 1

        for role in collected:
            normalized.append(f"--roles={role}")

    return normalized


def _normalize_cli_args(argv: Sequence[str]) -> List[str]:
    if not argv:
        return []
    if argv[0] != "prepare":
        return list(argv)
    return _normalize_prepare_roles_tokens(argv)


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    normalized_args = _normalize_cli_args(raw_args)
    return parser.parse_args(normalized_args)


def _add_artifact_root_arg(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Override where artifacts are written. Defaults to cwd (external repo) or Studio root.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Studio run helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Create a new run_id and instructions.")
    prepare_parser.add_argument(
        "--phase",
        required=True,
        choices=sorted(PHASE_DETAILS.keys()),
        help="Studio phase to run.",
    )
    prepare_parser.add_argument(
        "--text",
        required=True,
        help="Idea/objective text that seeds the run.",
    )
    prepare_parser.add_argument(
        "--budget",
        default="$0-20/mo",
        help="Budget cap (only used by studio phase).",
    )
    prepare_parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Iteration cap for Advocate/Contrarian loop.",
    )
    prepare_parser.add_argument(
        "--role-pack",
        help="Studio-only: role pack preset to load (defaults to manifest setting).",
    )
    prepare_parser.add_argument(
        "--roles",
        action="append",
        default=None,
        help=(
            "Studio-only: role overrides like +qa or -marketing. "
            "You can pass them as '--roles +qa -marketing' or repeated '--roles=+qa --roles=-marketing'."
        ),
    )
    prepare_parser.add_argument(
        "--mode",
        choices=["deliverables", "questions"],
        default="deliverables",
        help="Output mode: 'deliverables' (default) produces specs; 'questions' surfaces open questions.",
    )
    prepare_parser.add_argument(
        "--scopes",
        type=Path,
        default=None,
        help="Path to scopes TOML config (default: .studio/scopes.toml if exists).",
    )
    prepare_parser.add_argument(
        "--no-scopes",
        action="store_true",
        help="Disable scope-based iteration (skip default .studio/scopes.toml).",
    )
    prepare_parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip the automatic cleanup pass that enforces age/size budgets.",
    )
    prepare_parser.add_argument(
        "--cleanup-dry-run",
        action="store_true",
        help="Preview cleanup deletions without removing any files.",
    )
    _add_artifact_root_arg(prepare_parser)

    finalize_parser = subparsers.add_parser("finalize", help="Mark an existing run as completed and refresh index.")
    finalize_parser.add_argument(
        "--phase",
        required=True,
        choices=sorted(PHASE_DETAILS.keys()),
        help="Phase the run belongs to.",
    )
    finalize_parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier created via `prepare`.",
    )
    finalize_parser.add_argument(
        "--status",
        default="COMPLETED",
        help="Final status label (default: COMPLETED).",
    )
    finalize_parser.add_argument(
        "--summary",
        help="Override summary path recorded in the index.",
    )
    finalize_parser.add_argument(
        "--verdict",
        help="Final verdict (APPROVED/REJECTED/N/A).",
    )
    finalize_parser.add_argument(
        "--iterations-run",
        type=int,
        help="Number of iterations executed.",
    )
    finalize_parser.add_argument(
        "--hours",
        type=float,
        help="Optional hours spent on this run.",
    )
    finalize_parser.add_argument(
        "--cost",
        type=float,
        help="Optional cost (in USD) attributed to this run.",
    )
    _add_artifact_root_arg(finalize_parser)

    cleanup_parser = subparsers.add_parser(
        "cleanup", help="Manually enforce cleanup thresholds."
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without removing files.",
    )
    _add_artifact_root_arg(cleanup_parser)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate Studio run outputs (documents and/or code)."
    )
    validate_parser.add_argument(
        "--phase",
        required=True,
        choices=sorted(PHASE_DETAILS.keys()),
        help="Phase the run belongs to.",
    )
    validate_parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier to validate.",
    )
    validate_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to validation config TOML (default: .studio/validation.toml).",
    )
    _add_artifact_root_arg(validate_parser)

    record_parser = subparsers.add_parser(
        "record-decisions", help="Record an answered decision into a run's decisions.json."
    )
    record_parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to the run directory.",
    )
    record_parser.add_argument(
        "--question",
        default=None,
        help="The decision question text (required unless --decisions-file is used).",
    )
    record_parser.add_argument(
        "--answer",
        default=None,
        help="The answer to the decision (required unless --decisions-file is used).",
    )
    record_parser.add_argument(
        "--priority",
        default=None,
        choices=["P0", "P1", "P2"],
        help="Decision priority level (required unless --decisions-file is used).",
    )
    record_parser.add_argument(
        "--source",
        default=None,
        help="Source file the decision came from (optional).",
    )
    record_parser.add_argument(
        "--unblocks",
        default="",
        help="What this decision unblocks (optional).",
    )
    record_parser.add_argument(
        "--answered-by",
        default="user",
        help="Who answered: 'user' or 'assumption' (default: user).",
    )
    record_parser.add_argument(
        "--decisions-file",
        type=Path,
        default=None,
        help="Path to a JSON file with multiple decisions to record at once.",
    )

    check_parser = subparsers.add_parser(
        "check-decisions", help="Parse decision points from a single agent output file."
    )
    check_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to an agent output file to scan for decision points.",
    )

    # --- Mid-run orchestration commands ---
    extract_parser = subparsers.add_parser(
        "extract-decisions", help="Extract decision points from agent files in a run directory."
    )
    extract_parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to the run directory.",
    )
    extract_parser.add_argument(
        "--scope",
        default=None,
        help="Filter by scope (e.g., 'alignment', 'S1', 'depth', 'S2').",
    )

    inject_parser = subparsers.add_parser(
        "inject-context", help="Generate context block for the next agent in a scoped run."
    )
    inject_parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to the run directory.",
    )
    inject_parser.add_argument(
        "--scope",
        required=True,
        help="Current scope name (alignment, depth, polish).",
    )
    inject_parser.add_argument(
        "--role",
        required=True,
        help="Role name (e.g., marketing, engineering).",
    )
    inject_parser.add_argument(
        "--stance",
        required=True,
        choices=["advocate", "contrarian"],
        help="Agent stance.",
    )
    inject_parser.add_argument(
        "--artifact-root", type=Path, default=None,
        help="Override artifact root directory.",
    )

    # --- Cross-repo install commands ---
    init_parser = subparsers.add_parser(
        "init", help="Install Studio into a target project directory."
    )
    init_parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project directory.",
    )

    check_install_parser = subparsers.add_parser(
        "check-install", help="Check if installed Studio is up to date."
    )
    check_install_parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project directory.",
    )

    update_parser = subparsers.add_parser(
        "update", help="Update installed Studio from source."
    )
    update_parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project directory.",
    )

    # --- Clarity commands ---
    show_clarity_parser = subparsers.add_parser(
        "show-clarity", help="Display current project clarity scores."
    )
    show_clarity_parser.add_argument(
        "--artifact-root", type=Path, default=None,
        help="Override artifact root directory.",
    )

    set_clarity_parser = subparsers.add_parser(
        "set-clarity", help="Override a topic's clarity score."
    )
    set_clarity_parser.add_argument("--topic", required=True, help="Topic slug.")
    set_clarity_parser.add_argument("--score", type=float, default=None, help="Override score (0.0-1.0).")
    set_clarity_parser.add_argument("--reset", action="store_true", help="Remove user override.")
    set_clarity_parser.add_argument(
        "--artifact-root", type=Path, default=None,
        help="Override artifact root directory.",
    )

    recompute_clarity_parser = subparsers.add_parser(
        "recompute-clarity", help="Recompute clarity from a run's decisions."
    )
    recompute_clarity_parser.add_argument("--phase", required=True, choices=sorted(PHASE_DETAILS.keys()))
    recompute_clarity_parser.add_argument("--run-id", required=True)
    recompute_clarity_parser.add_argument(
        "--artifact-root", type=Path, default=None,
        help="Override artifact root directory.",
    )

    # --- Agent metrics ---

    record_metrics_parser = subparsers.add_parser(
        "record-metrics", help="Record token usage for a single agent invocation."
    )
    record_metrics_parser.add_argument("--run-dir", type=Path, required=True, help="Path to the run directory.")
    record_metrics_parser.add_argument("--agent", required=True, choices=["advocate", "contrarian", "integrator", "polish"], help="Agent type.")
    record_metrics_parser.add_argument("--total-tokens", type=int, required=True, help="Total tokens consumed.")
    record_metrics_parser.add_argument("--tool-uses", type=int, default=0, help="Number of tool uses.")
    record_metrics_parser.add_argument("--duration-ms", type=int, default=0, help="Duration in milliseconds.")
    record_metrics_parser.add_argument("--role", default=None, help="Role name (for studio phase).")
    record_metrics_parser.add_argument("--scope", default=None, choices=["alignment", "depth", "polish", "flat"], help="Scope name.")

    show_metrics_parser = subparsers.add_parser(
        "show-metrics", help="Display token usage summary for a run."
    )
    show_metrics_parser.add_argument("--run-dir", type=Path, required=True, help="Path to the run directory.")

    offload_parser = subparsers.add_parser(
        "offload", help="Analyze CLAUDE.md for offload opportunities."
    )
    offload_parser.add_argument("--target", type=Path, default=Path("."), help="Directory containing the CLAUDE.md to analyze.")
    offload_parser.add_argument("--apply", action="store_true", help="Apply changes after report.")
    offload_parser.add_argument("--rollback", action="store_true", help="Restore from most recent backup.")
    offload_parser.add_argument("--verify", action="store_true", help="Run canary verification.")

    return parser


def validate_run(args: argparse.Namespace) -> None:
    """Validate Studio run outputs."""
    phase = args.phase.lower()
    run_id = args.run_id
    run_dir = get_output_root() / phase / run_id
    
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    
    # Load validation config
    config_path = args.config
    if not config_path:
        config_path = get_studio_root() / ".studio" / "validation.toml"
    
    if not config_path.exists():
        print(f"Warning: Validation config not found at {config_path}")
        print("Using default validation rules.")
        config = {}
    else:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    
    # Validate discussion phase (documents)
    print(f"\n{'='*60}")
    print(f"Validating {run_id} ({phase} phase)")
    print(f"{'='*60}\n")
    
    doc_validator = DocumentValidator()
    
    # Get required sections from config
    discussion_key = f"{phase}_phase.discussion"
    required_sections = config.get(discussion_key, {}).get("required_sections", [])
    
    print("## Discussion Phase Validation\n")
    
    if required_sections:
        print(f"Checking for required sections: {', '.join(required_sections)}\n")
    
    # Validate all documents in run
    result = doc_validator.validate_run(run_dir, phase)
    
    if result.passed:
        print("✓ All document checks PASSED")
    else:
        print("✗ Document validation FAILED")
        print("\nIssues:")
        for issue in result.issues:
            print(f"  - {issue}")
    
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  ⚠ {warning}")
    
    # Check for implementation artifacts (code validation)
    impl_key = f"{phase}_phase.implementation"
    if impl_key in config:
        print("\n## Implementation Phase Validation\n")
        
        impl_config = config[impl_key]
        checks = impl_config.get("checks", [])
        timeout = impl_config.get("timeout", 60)
        
        if checks:
            code_validator = CodeValidator(timeout=timeout)
            
            # Look for implementation.md or integrator.md
            impl_file = run_dir / "implementation.md"
            integrator_file = run_dir / "integrator.md"
            
            if not impl_file.exists() and not integrator_file.exists():
                print("⚠ No implementation artifacts found (implementation.md or integrator.md)")
                print("  Skipping code validation.")
            else:
                print(f"Running code checks: {', '.join(checks)}\n")
                
                # Run checks on project directory (assume run_dir contains code)
                check_results = code_validator.validate_implementation(run_dir, checks)
                
                passed_count = sum(1 for r in check_results if r.passed)
                total_count = len(check_results)
                
                print(f"Results: {passed_count}/{total_count} checks passed\n")
                
                for check_result in check_results:
                    if check_result.passed:
                        print(f"  ✓ {check_result.check_name} - PASSED ({check_result.duration_seconds:.2f}s)")
                    else:
                        print(f"  ✗ {check_result.check_name} - FAILED ({check_result.duration_seconds:.2f}s)")
                        # Show first few lines of error
                        error_lines = check_result.output.split('\n')[:5]
                        for line in error_lines:
                            if line.strip():
                                print(f"      {line}")
    
    print(f"\n{'='*60}")
    print("Validation complete")
    print(f"{'='*60}\n")


def record_decisions(args: argparse.Namespace) -> None:
    """Record answered decisions into a run's decisions.json and regenerate decisions.md.

    Supports single decision via --question/--answer or batch via --decisions-file.
    """
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    decisions = load_decisions_json(run_dir)
    existing_qs = {dp.question for dp in decisions}

    def _append(dp: DecisionPoint) -> None:
        """Append decision, deduplicating by question text (update if exists)."""
        if dp.question in existing_qs:
            # Update existing decision with new answer
            for i, existing in enumerate(decisions):
                if existing.question == dp.question:
                    decisions[i] = dp
                    print(f"Updated [{dp.priority}] {dp.question} -> {dp.answer}")
                    return
        existing_qs.add(dp.question)
        decisions.append(dp)
        print(f"Recorded [{dp.priority}] {dp.question} -> {dp.answer}")

    if args.decisions_file:
        # Batch mode: read multiple decisions from a JSON file
        batch_data = json.loads(args.decisions_file.read_text(encoding="utf-8"))
        for d in batch_data:
            _append(DecisionPoint(
                priority=d["priority"],
                question=d["question"],
                unblocks=d.get("unblocks", ""),
                answer=d["answer"],
                answered_by=d.get("answered_by", "user"),
                source_file=d.get("source_file"),
            ))
    else:
        # Single decision mode — validate required args
        if args.question is None or args.answer is None or args.priority is None:
            raise ValueError(
                "Single-decision mode requires --question, --answer, and --priority. "
                "Use --decisions-file for batch mode."
            )
        _append(DecisionPoint(
            priority=args.priority,
            question=args.question,
            unblocks=args.unblocks,
            answer=args.answer,
            answered_by=args.answered_by,
            source_file=args.source,
        ))

    save_decisions_json(run_dir, decisions)

    # Regenerate decisions.md with settled decisions
    settled_md = format_settled_decisions(decisions)
    (run_dir / "decisions.md").write_text(settled_md, encoding="utf-8")

    print(f"  decisions.json: {run_dir / 'decisions.json'}")
    print(f"  decisions.md:   {run_dir / 'decisions.md'}")


def check_decisions(args: argparse.Namespace) -> None:
    """Parse decision points from a single agent output file and print as JSON."""
    file_path = Path(args.file)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    points = parse_decision_points(text, source_file=file_path.name)

    grouped: dict[str, list[dict]] = {"P0": [], "P1": [], "P2": []}
    for dp in points:
        entry = {
            "question": dp.question,
            "unblocks": dp.unblocks,
            "options": dp.options,
            "source_file": dp.source_file,
        }
        grouped[dp.priority].append(entry)

    print(json.dumps(grouped, indent=2))


def extract_decisions(args: argparse.Namespace) -> None:
    """Extract decision points from agent files in a run directory.

    Scans advocate/contrarian files (optionally filtered by scope) and
    outputs formatted decision points. Useful mid-run between agents.
    """
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    all_decisions = extract_decisions_from_run(run_dir)

    # Filter by scope if requested
    scope_filter = getattr(args, "scope", None)
    if scope_filter:
        scope_tag = f"S{scope_filter[-1]}" if scope_filter[0].isalpha() else scope_filter
        all_decisions = [
            dp for dp in all_decisions
            if dp.source_file and scope_tag in dp.source_file
        ]

    if not all_decisions:
        # Silent exit — no decisions found is normal
        return

    print(format_decisions_log(all_decisions))


# ---------------------------------------------------------------------------
# Agent metrics tracking
# ---------------------------------------------------------------------------

def _load_metrics(run_dir: Path) -> List[Dict]:
    """Load metrics.json from a run directory, returning [] if absent."""
    metrics_path = run_dir / "metrics.json"
    try:
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def _save_metrics(run_dir: Path, entries: List[Dict]) -> None:
    """Write metrics.json to a run directory."""
    write_json(run_dir / "metrics.json", entries)


def record_metrics(args: argparse.Namespace) -> None:
    """Record token usage for a single agent invocation."""
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    entries = _load_metrics(run_dir)
    entry: Dict = {
        "agent": args.agent,
        "total_tokens": args.total_tokens,
        "tool_uses": args.tool_uses or 0,
        "duration_ms": args.duration_ms or 0,
        "timestamp": utc_now().isoformat(timespec="seconds"),
    }
    if args.role:
        entry["role"] = args.role
    if args.scope:
        entry["scope"] = args.scope
    entries.append(entry)
    _save_metrics(run_dir, entries)


def _summarize_metrics(entries: List[Dict]) -> Dict:
    """Aggregate metrics entries into a summary."""
    total_tokens = sum(e.get("total_tokens", 0) for e in entries)
    total_duration = sum(e.get("duration_ms", 0) for e in entries)
    total_tool_uses = sum(e.get("tool_uses", 0) for e in entries)

    by_scope: Dict[str, Dict] = {}
    by_role: Dict[str, Dict] = {}

    for e in entries:
        scope = e.get("scope", "flat")
        role = e.get("role", "unknown")

        for group, key in [(by_scope, scope), (by_role, role)]:
            if key not in group:
                group[key] = {"agents": 0, "total_tokens": 0, "duration_ms": 0}
            group[key]["agents"] += 1
            group[key]["total_tokens"] += e.get("total_tokens", 0)
            group[key]["duration_ms"] += e.get("duration_ms", 0)

    return {
        "agents": len(entries),
        "total_tokens": total_tokens,
        "total_duration_ms": total_duration,
        "total_tool_uses": total_tool_uses,
        "by_scope": by_scope,
        "by_role": by_role,
    }


def show_metrics(args: argparse.Namespace) -> None:
    """Display metrics summary for a run."""
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    entries = _load_metrics(run_dir)
    if not entries:
        print("No metrics recorded for this run.")
        return

    summary = _summarize_metrics(entries)

    print(f"\n{'='*60}")
    print(f"Agent Metrics — {run_dir.name}")
    print(f"{'='*60}")
    print(f"  Agents spawned:  {summary['agents']}")
    print(f"  Total tokens:    {summary['total_tokens']:,}")
    print(f"  Total tool uses: {summary['total_tool_uses']:,}")
    total_sec = summary["total_duration_ms"] / 1000
    print(f"  Total duration:  {total_sec:.0f}s ({total_sec/60:.1f}m)")

    if summary["by_scope"]:
        print(f"\n  By scope:")
        for scope, stats in sorted(summary["by_scope"].items()):
            pct = (stats["total_tokens"] / summary["total_tokens"] * 100) if summary["total_tokens"] else 0
            print(f"    {scope:12s}  {stats['agents']} agents  {stats['total_tokens']:>8,} tokens ({pct:.0f}%)")

    if summary["by_role"]:
        print(f"\n  By role:")
        for role, stats in sorted(summary["by_role"].items()):
            pct = (stats["total_tokens"] / summary["total_tokens"] * 100) if summary["total_tokens"] else 0
            print(f"    {role:16s}  {stats['agents']} agents  {stats['total_tokens']:>8,} tokens ({pct:.0f}%)")

    # Per-agent detail
    print(f"\n  Agent detail:")
    for e in entries:
        role = e.get("role", "")
        scope = e.get("scope", "")
        label = e["agent"]
        if role:
            label = f"{label}--{role}"
        if scope:
            label = f"{label} ({scope})"
        print(f"    {label:40s}  {e.get('total_tokens', 0):>8,} tokens  {e.get('duration_ms', 0)/1000:.0f}s")

    print()


def inject_context(args: argparse.Namespace) -> None:
    """Generate the context block for the next agent in a scoped run.

    Combines settled decisions, clarity summary, prior-scope file lists,
    and scope-specific instructions into a single markdown block that
    the orchestrator appends to the agent prompt.
    """
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    scope_name = args.scope
    role = args.role
    stance = args.stance

    # Load run metadata
    meta_path = run_dir / "run.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"run.json not found in {run_dir}")
    meta = load_json(meta_path)
    user_text = meta.get("input", "")

    # Resolve scope config
    studio_root = get_studio_root()
    scopes_meta = meta.get("scopes")
    scopes_config = None
    scope = None
    scope_index = 0

    if scopes_meta:
        scopes_path = Path(scopes_meta.get("config_path", ""))
        if scopes_path.exists():
            scopes_config = load_scopes_config(scopes_path)
            scope = scopes_config.get_scope(scope_name)
            if scope:
                scope_index = next(
                    (i for i, s in enumerate(scopes_config.scopes) if s.name == scope_name),
                    0,
                )

    # Resolve role details from manifest via existing utility
    manifest = load_manifest(studio_root)
    try:
        role_detail = get_role_spec(manifest, role)
        advocate_focus = role_detail.advocate_focus
        contrarian_focus = role_detail.contrarian_focus
        deliverables = role_detail.deliverables
        role_title = role_detail.title
    except RoleConfigError:
        # Graceful fallback for unknown roles
        advocate_focus = ""
        contrarian_focus = ""
        deliverables = []
        role_title = role.title()

    # Check for prior-scope files
    decisions_md_exists = (run_dir / "decisions.md").exists()
    s2_brief_exists = (run_dir / "S2-brief.md").exists()

    s1_files: List[str] | None = None
    if scope_index >= 1:
        s1_files = [f.name for f in sorted(run_dir.glob(f"*--{role}--S1-*.md"))]
        if not s1_files:
            # Also include all S1 files if role-specific ones don't exist
            s1_files = [f.name for f in sorted(run_dir.glob("*--*--S1-*.md"))]

    output_parts: List[str] = []

    # 1. Scope-specific prompt (if scoped)
    if scope:
        output_parts.append(generate_scope_prompt(
            scope=scope,
            scope_index=scope_index,
            role_title=role_title,
            stance=stance,
            run_dir=str(run_dir),
            advocate_focus=advocate_focus,
            contrarian_focus=contrarian_focus,
            deliverables=deliverables,
            user_text=user_text,
            decisions_md_exists=decisions_md_exists,
            s1_files=s1_files,
            s2_brief_exists=s2_brief_exists,
        ))

    # 2. Settled decisions — only add if generate_scope_prompt didn't already cover it
    if decisions_md_exists and not scope:
        output_parts.extend([
            "## Settled Decisions",
            "",
            f"Read `{run_dir}/decisions.md` for settled constraints. Treat as hard constraints — do not re-litigate.",
            "",
        ])

    # 3. Clarity summary
    _cl = _load_clarity()
    if _cl:
        root = get_artifact_root()
        snapshot = _cl.load_project_clarity(root)
        if snapshot is not None:
            output_parts.append(_cl.generate_clarity_instructions(snapshot, scope_name))

    if output_parts:
        print("\n".join(output_parts))


def show_clarity(args: argparse.Namespace) -> None:
    """Display current project clarity scores."""
    _cl = _load_clarity()
    if not _cl:
        print("Clarity module not available.")
        return
    root = Path(args.artifact_root).resolve() if args.artifact_root else get_artifact_root()
    snapshot = _cl.load_project_clarity(root)
    if snapshot is None:
        print("No clarity data yet. Run a phase with decision points first.")
        return
    print(_cl.format_clarity_summary(snapshot))


def set_clarity(args: argparse.Namespace) -> None:
    """Override a topic's clarity score."""
    _cl = _load_clarity()
    if not _cl:
        print("Clarity module not available.")
        return
    root = Path(args.artifact_root).resolve() if args.artifact_root else get_artifact_root()
    snapshot = _cl.load_project_clarity(root)
    if snapshot is None:
        print("No clarity data yet. Run a phase with decision points first.")
        return
    if args.reset:
        snapshot = _cl.apply_user_overrides(snapshot, {args.topic: None})
    elif args.score is not None:
        snapshot = _cl.apply_user_overrides(snapshot, {args.topic: args.score})
    else:
        print("Provide --score VALUE or --reset")
        return
    _cl.save_project_clarity(root, snapshot)
    print(_cl.format_clarity_summary(snapshot))


def recompute_clarity(args: argparse.Namespace) -> None:
    """Recompute clarity from a run's decisions.

    Works with both finalized and in-progress runs. If decisions.json exists,
    uses it. Otherwise extracts decisions from agent output files directly,
    making this usable mid-run.
    """
    _cl = _load_clarity()
    if not _cl:
        print("Clarity module not available.")
        return
    root = Path(args.artifact_root).resolve() if args.artifact_root else get_artifact_root()
    phase = args.phase.lower()
    run_id = args.run_id
    run_dir = get_output_root() / phase / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    # Load existing decisions from JSON, then merge any new ones from agent files
    decisions = load_decisions_json(run_dir)
    extracted = extract_decisions_from_run(run_dir)
    merge_decisions(decisions, extracted)

    meta_path = run_dir / "run.json"
    input_text = ""
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        input_text = meta.get("input", "")
    context = _cl.detect_context_scope(input_text)
    prior = _cl.load_project_clarity(root)
    snapshot = _cl.compute_clarity_snapshot(decisions, context, run_id=run_id, prior_snapshot=prior)
    _cl.save_clarity_json(run_dir / "clarity.json", snapshot)
    _cl.save_project_clarity(root, snapshot)
    print(_cl.format_clarity_summary(snapshot))


def _do_init(args: argparse.Namespace) -> None:
    """Install Studio into a target project."""
    from install import install_studio  # lazy: install.py absent in cross-repo installs
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"Target directory not found: {target}")
    dot_studio = install_studio(target)
    print(f"Studio installed to {dot_studio}")
    print(f"  Slash commands: {target / '.claude' / 'commands'}")
    print(f"  Source: {dot_studio / 'source'}")
    print(f"\nRun /run-phase or /run-studio-phase from {target.name} — pause-and-ask included.")
    print(f"NOTE: Start a NEW Claude Code session (not just /clear) to discover the commands.")


def _do_check_install(args: argparse.Namespace) -> None:
    """Check if installed Studio is up to date."""
    from install import check_studio  # lazy: install.py absent in cross-repo installs
    target = Path(args.target).resolve()
    status = check_studio(target)
    if not status["installed"]:
        print(f"Studio is NOT installed at {target}")
        print("Run: python run_phase.py init --target " + str(target))
        return
    if status["up_to_date"]:
        print(f"Studio at {target} is up to date.")
    else:
        print(f"Studio at {target} needs updating:")
        if status["changed"]:
            print(f"  Changed: {', '.join(status['changed'])}")
        if status["missing"]:
            print(f"  Missing: {', '.join(status['missing'])}")
        print(f"\nRun: python run_phase.py update --target {target}")


def _do_update(args: argparse.Namespace) -> None:
    """Update installed Studio from source."""
    from install import update_studio  # lazy: install.py absent in cross-repo installs
    target = Path(args.target).resolve()
    result = update_studio(target)
    if result["updated"] == 0 and result["added"] == 0:
        print(f"Studio at {target} is already up to date.")
    else:
        print(f"Studio updated at {target}:")
        if result["updated"]:
            print(f"  Updated: {result['updated']} file(s)")
        if result["added"]:
            print(f"  Added: {result['added']} file(s)")


def do_offload(args: argparse.Namespace) -> None:
    """Analyze CLAUDE.md for offload opportunities."""
    import offload as _offload

    target = Path(args.target).resolve()
    claude_md = target / "CLAUDE.md"

    if args.rollback:
        backup_dir = target / ".studio" / "offload-backup"
        if not backup_dir.is_dir():
            print("No backup directory found.")
            return
        # Find most recent backup
        backups = sorted(backup_dir.iterdir(), reverse=True)
        if not backups:
            print("No backups found.")
            return
        restored = _offload.restore_backup(str(backups[0]))
        print(f"Restored {len(restored)} file(s) from {backups[0].name}")
    elif args.verify:
        if not claude_md.exists():
            print(f"No CLAUDE.md found at {target}")
            return
        content = claude_md.read_text(encoding="utf-8")
        sections = _offload.classify_sections(content)
        canaries = {
            s["name"]: _offload.generate_canary_token(s["name"])
            for s in sections if s["tier"] != _offload.TIER_ALWAYS_INLINE
        }
        leaked = _offload.verify_canary_isolation(content, list(canaries.values()))
        if leaked:
            print(f"WARNING: {len(leaked)} canary token(s) found in CLAUDE.md")
        else:
            print("Canary isolation verified — no tokens in CLAUDE.md")
    else:
        if not claude_md.exists():
            print(f"No CLAUDE.md found at {target}")
            return
        content = claude_md.read_text(encoding="utf-8")
        sections = _offload.classify_sections(content)
        constraints = _offload.detect_embedded_constraints(sections)
        context = _offload.detect_cross_repo_context()
        companion_root = context.get("companion_root", ".")
        existing = _offload.scan_existing_docs(companion_root)
        reconciliation = _offload.reconcile_with_existing(sections, existing)
        pointers = [
            _offload.generate_pointer_stub(s, r.get("target", ""))
            for s, r in zip(
                [s for s in sections if s["tier"] != _offload.TIER_ALWAYS_INLINE],
                reconciliation,
            )
        ]
        canaries = {
            s["name"]: _offload.generate_canary_token(s["name"])
            for s in sections if s["tier"] != _offload.TIER_ALWAYS_INLINE
        }
        report = _offload.generate_report(
            sections, constraints, pointers, canaries, reconciliation,
        )
        print(report)


def main() -> None:
    args = parse_cli_args()

    # Apply --artifact-root override before any command runs
    artifact_root = getattr(args, "artifact_root", None)
    if artifact_root is not None:
        set_artifact_root(artifact_root)

    if args.command == "prepare":
        prepare_run(args)
    elif args.command == "finalize":
        finalize_run(args)
    elif args.command == "cleanup":
        dry_run = getattr(args, "dry_run", False)
        _maybe_run_cleanup(dry_run=dry_run or _env_flag(CLEANUP_DRY_ENV))
    elif args.command == "validate":
        validate_run(args)
    elif args.command == "record-decisions":
        record_decisions(args)
    elif args.command == "check-decisions":
        check_decisions(args)
    elif args.command == "extract-decisions":
        extract_decisions(args)
    elif args.command == "inject-context":
        inject_context(args)
    elif args.command == "init":
        _do_init(args)
    elif args.command == "check-install":
        _do_check_install(args)
    elif args.command == "update":
        _do_update(args)
    elif args.command == "show-clarity":
        show_clarity(args)
    elif args.command == "set-clarity":
        set_clarity(args)
    elif args.command == "recompute-clarity":
        recompute_clarity(args)
    elif args.command == "record-metrics":
        record_metrics(args)
    elif args.command == "show-metrics":
        show_metrics(args)
    elif args.command == "offload":
        do_offload(args)
    else:
        raise ValueError("Unknown command")


if __name__ == "__main__":
    main()
