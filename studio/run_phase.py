#!/usr/bin/env python3
"""
Studio CLI entrypoint.

The single command surface for Studio. Beyond preparing per-phase instructions
and run directories, it finalizes and validates runs, manages decisions and
clarity, records agent metrics and human ratings, prints the cross-run stats
dashboard and maintains the outcomes ledger, writes session-health records,
sends run digests, and installs/updates Studio into other repos. Runs are
executed by an AI assistant (Claude Code is the supported path); this script
does the mechanics around them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from cleanup import (
    cleanup_runs,
    format_bytes,
    load_cleanup_settings,
)
from validators.document_validator import DocumentValidator
from role_overrides import load_role_overrides
from persona_overrides import load_persona_overrides, apply_persona_overrides
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
from design_mandate import DESIGN_CRITIQUE_GUIDE
from scopes import (
    CONTRARIAN_MANDATE,
    allocate_iterations,
    generate_scope_instructions,
    generate_scope_prompt,
    load_scopes_config,
)
from decision_points import (
    DECISION_BLOCK_EXAMPLE,
    DecisionPoint,
    extract_decisions_from_run,
    filter_unsettled,
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
)
from validators.code_validator import CodeValidator

import clarity
from verdict import extract_verdict
from session import build_session_record
from integrations.slack_digest import (
    INTEGRATIONS_FILENAME,
    load_integrations_config,
    notify_run,
)

from config_loading import tomllib
from stats import (
    VALID_IMPACT,
    VALID_SHIPPED,
    _parse_usage_log,
    _summarize_metrics,
    aggregate_stats,
    detect_trend_alerts,
    format_stats,
    summarize_outcomes,
    summarize_session_health,
)


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
        "advocate": "Market Growth Strategist — steel-man the idea into a high-virality launch hook for its target platform.",
        "contrarian": "The Reality Check & Editor — cut the pitch to its essential hook, kill fatal market flaws, and issue VERDICT: APPROVED/REJECTED.",
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
        "contrarian": "Scope-Creep Police & Editor — cut the loop to its essence; attack complexity, timeline, and missing UX safeguards.",
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
        "advocate": "Technical Architect — define a performant, idiomatic architecture for the project's stack.",
        "contrarian": "Senior SRE & Editor — delete needless moving parts; flag performance, compatibility, and ops risks.",
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
        "notes": "Test-driven discipline: Define testable requirements, write tests first, then implement to pass tests. Account for the target platform's runtime, performance, and ops constraints when approving.",
    },
    "studio": {
        "advocate": "Studio Workflow Producer — articulate the inspiring yet actionable vision.",
        "contrarian": "Bootstrapped Reality Auditor & Editor — cut scope to the essential; interrogate costs, scope, and maintenance burden.",
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
    "init", "check-install", "check-updates", "update",
    "show-clarity", "set-clarity", "recompute-clarity",
    "record-metrics", "show-metrics", "offload", "setup",
    "rate", "stats", "notify",
    "export-outcomes", "import-outcomes",
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


def _entrypoint() -> str:
    """How to invoke this CLI in next-step hints. Echoes the path as actually called,
    so hints copy-paste correctly in both the source repo (``studio/run_phase.py``) and
    installed repos (``.studio/source/run_phase.py``) instead of a bare ``run_phase.py``.
    """
    argv0 = sys.argv[0] if sys.argv and sys.argv[0] else "run_phase.py"
    return f"python {argv0}"


def _phase_from_run_id(run_id: str) -> str:
    """Derive the phase from a run_id (format ``run_<phase>_<timestamp>``).

    Lets run-scoped commands (finalize/validate/recompute-clarity) make ``--phase``
    optional, since it's redundant with ``--run-id``, which already encodes it.
    """
    parts = run_id.split("_")
    if len(parts) >= 3 and parts[0] == "run" and parts[1] in PHASE_DETAILS:
        return parts[1]
    raise ValueError(
        f"Cannot derive phase from run_id '{run_id}' — pass --phase explicitly."
    )


_artifact_root_override: Path | None = None
_artifact_root_warned: bool = False


def set_artifact_root(path: Path | None) -> None:
    """Set an explicit artifact root (used by --artifact-root CLI flag)."""
    global _artifact_root_override
    _artifact_root_override = path


def _installed_repo_root(studio_root: Path) -> Path | None:
    """Return the consuming repo root when studio_root is an installed snapshot.

    Installed layout places the source at ``<repo>/.studio/source``; the artifact
    root is then ``<repo>``, not the snapshot dir.
    """
    if studio_root.name == "source" and studio_root.parent.name == ".studio":
        return studio_root.parent.parent
    return None


def _find_installed_root_upwards(start: Path) -> Path | None:
    """Walk up from ``start`` for an installed repo root (has ``.studio/VERSION``).

    Lets a CLI call from a monorepo subdirectory resolve to the real repo root
    instead of scaffolding a fresh, unconfigured ``.studio/`` in the subdir.
    """
    for d in [start, *start.parents]:
        if (d / ".studio" / "VERSION").is_file():
            return d
    return None


def get_artifact_root() -> Path:
    if _artifact_root_override is not None:
        return _artifact_root_override.resolve()

    env_override = os.environ.get(ARTIFACT_ROOT_ENV)
    if env_override:
        return _resolve_env_path(env_override)

    studio_root = get_studio_root().resolve()
    cwd = Path.cwd().resolve()

    if cwd == studio_root or _is_within(cwd, studio_root):
        # Running from the source tree (or from inside an installed snapshot).
        # In the source repo the artifact root IS the studio dir; in an installed
        # snapshot it's the consuming repo root, never the snapshot itself.
        installed_root = _installed_repo_root(studio_root)
        return installed_root if installed_root is not None else studio_root

    # The next two branches are distinct on purpose: an init'd repo is marked by
    # .studio/VERSION (walk UP for it, which handles monorepo subdirs), whereas a merely
    # scaffolded repo has a bare .studio/ and no VERSION (check cwd ONLY). Don't merge.
    found = _find_installed_root_upwards(cwd)
    if found is not None:
        return found
    if (cwd / ".studio").is_dir():
        return cwd

    # Genuine first run in a fresh external repo with no .studio/: default to cwd, warn once.
    global _artifact_root_warned
    if not _artifact_root_warned:
        print(
            f"Warning: artifact root defaulting to current directory ({cwd}). "
            f"Set STUDIO_ARTIFACT_ROOT or use --artifact-root to override.",
            file=sys.stderr,
        )
        _artifact_root_warned = True
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


def _project_name() -> str:
    """Short name for the repo a run belongs to; tags outcome records.

    In a consuming repo the artifact root IS the repo root, so its directory name
    is the project name. In this tool repo the artifact root is the ``studio/``
    dir, so use its parent (the repo root) rather than the literal "studio".
    """
    artifact_root = get_artifact_root().resolve()
    studio_root = get_studio_root().resolve()
    if artifact_root == studio_root:
        return studio_root.parent.name
    return artifact_root.name


def get_outcomes_ledger_path() -> Path:
    """Central append-only ledger of run outcomes (mirrors get_knowledge_log_path).

    This is where cross-repo outcome records land via ``import-outcomes`` so that
    ``stats`` in the tool repo can see results from every project, not only runs
    done here. Lives under ``knowledge/`` (gitignored). It can name unshipped
    work, so it stays local unless you deliberately commit a redacted copy.
    """
    artifact_root = get_artifact_root().resolve()
    studio_root = get_studio_root().resolve()
    if artifact_root == studio_root:
        return studio_root / "knowledge" / "outcomes.jsonl"
    return artifact_root / ".studio" / "knowledge" / "outcomes.jsonl"


def get_configured_ledger_path() -> Optional[Path]:
    """Local ledger path for auto-appending outcome records at finalize.

    Reads an optional ``[outcomes] ledger_path`` from
    ``<artifact_root>/.studio/integrations.toml``, the same file that holds the
    Slack/n8n webhook config. This is a single-user simplification: the "central
    ledger" is just a fixed local file (typically the tool repo's
    ``knowledge/outcomes.jsonl``), so finalize can append there directly instead
    of making you run export-outcomes then import-outcomes by hand.

    Returns the resolved path when configured, or None when the config file, the
    ``[outcomes]`` table, or the ``ledger_path`` key is absent or unreadable. The
    ledger file itself need not exist yet; the first append creates it. Never
    raises: a broken config must not break finalize.
    """
    config_path = get_artifact_root() / ".studio" / INTEGRATIONS_FILENAME
    try:
        if not config_path.is_file():
            return None
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
        raw = (data.get("outcomes") or {}).get("ledger_path")
        if not isinstance(raw, str) or not raw.strip():
            return None
        return Path(raw).expanduser().resolve()
    except Exception:
        return None


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


def _is_same_objective(prev_run_dir: Path, current_input: str) -> bool:
    """Check if the previous run targeted the same objective as the current one.

    Returns True if the previous run's input text matches the current input
    (case-insensitive, whitespace-normalized). This distinguishes genuine reruns
    (same objective, new iteration) from fresh runs (different objective).
    """
    meta_path = prev_run_dir / "run.json"
    if not meta_path.is_file():
        return False
    try:
        meta = load_json(meta_path)
        prev_input = meta.get("input", "")
    except Exception:
        return False
    def _norm(s: str) -> str:
        return " ".join(s.strip().lower().split())
    normed_prev, normed_cur = _norm(prev_input), _norm(current_input)
    return bool(normed_prev and normed_cur and normed_prev == normed_cur)


def _norm_objective(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _objective_changed(
    project_clarity: "clarity.ClaritySnapshot | None",
    prev_run_dir: Path | None,
    current_input: str,
) -> bool:
    """Decide whether the current objective differs from the prior one.

    Prefers the objective stored in the project-level clarity.json
    (``context.scope_description``), which is shared across phases, so a
    prior run under a different phase still counts. Falls back to the
    same-phase previous run's input when no clarity snapshot exists.
    Returns False when there is no prior context to compare against.
    """
    normed_cur = _norm_objective(current_input)
    if project_clarity is not None:
        prev = _norm_objective(project_clarity.context.scope_description)
        return bool(prev and normed_cur and prev != normed_cur)
    if prev_run_dir is not None:
        return not _is_same_objective(prev_run_dir, current_input)
    return False


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
    same_objective: bool | None = None,
    phase_details: Dict | None = None,
) -> str:
    phase = meta["phase"]
    info = (phase_details or PHASE_DETAILS)[phase]
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
            "The orchestrator **must** generate scope-specific agent context before spawning each agent:",
            "",
            "```bash",
            f'python "{get_studio_root()}/run_phase.py" inject-context --run-dir {{run_dir}} --scope {{scope}} --role {{role}} --stance {{stance}}',
            "```",
            "",
            "This writes `context--<role>--<scope>--<stance>.md` into the run directory. Read that file and prepend its contents to the agent prompt.",
            "",
            "Or extract decisions between agents with:",
            "",
            "```bash",
            f'python "{get_studio_root()}/run_phase.py" extract-decisions --run-dir {{run_dir}}',
            "```",
            "",
        ])
    
    # Rerun context: only inject if same objective and previous run was rejected.
    # Question mode and fresh runs (different objective) skip rerun context.
    rerun_section: List[str] = []
    is_qmode = is_question_mode(meta.get("output_type"))
    if same_objective is None:
        prev_run_dir = _find_previous_run_dir(run_dir)
        same_objective = prev_run_dir is not None and _is_same_objective(
            prev_run_dir, meta.get("input", "")
        )
    elif same_objective:
        prev_run_dir = _find_previous_run_dir(run_dir)
        # The incoming same_objective may be a project-wide (clarity-based,
        # cross-phase) decision. Rerun context must be phase-local: only
        # inject from this phase's previous run if it targeted this objective.
        if prev_run_dir is not None and not _is_same_objective(
            prev_run_dir, meta.get("input", "")
        ):
            prev_run_dir = None
    else:
        prev_run_dir = None
    if not is_qmode and prev_run_dir and same_objective and detect_rerun_mode(prev_run_dir):
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
    # Editor mandate is always on for deliverable runs; in question-surfacing mode
    # the contrarian judges question relevance instead and must not cut questions.
    if not is_qmode:
        roles_section.append("")
        roles_section.extend(CONTRARIAN_MANDATE)
        roles_section.append("")
        # The anti-slop blacklist, embarrassment gate, and Goodwill Reservoir are
        # design-phase only: they judge game UI/menus/store pages, not market or
        # tech work, so they stay out of those phases' instructions.
        if phase == "design":
            roles_section.extend(DESIGN_CRITIQUE_GUIDE)
            roles_section.append("")
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

    # Open-Questions Pre-Flight: every deliverable run opens by surfacing what is
    # genuinely unsettled before anyone dives in. Reuses the decision/clarity machinery
    # so answers raise the clarity score and later passes only re-ask what is still open.
    preflight_section: List[str] = []
    if not is_qmode:
        preflight_section.extend([
            "",
            "## Step 0: Open-Questions Pre-Flight (required before the loop)",
            "",
            "Before anyone produces deliverables, run a fast reconnaissance pass to surface what is genuinely unsettled. The point is to stop building on silent assumptions — not to gate progress. Keep it lean.",
            "",
            "1. Across the participating role(s), surface the **open questions** that must be answered to build the *simplest system that actually solves the problem*. Tag each P0/P1/P2 using the Decision Point format (defined under **Decision Point Protocol** below).",
            "2. **Pause on every P0** and ask the user — batch all P0s into a single message. For P1s, state your assumption and proceed but flag it for override. Log P2s only.",
            "3. Record the answers so every later pass treats them as settled:",
            "",
            "```bash",
            f'python "{get_studio_root()}/run_phase.py" record-decisions --run-dir {rel_dir} --decisions-file <answers.json>',
            "```",
            "",
            "4. If nothing is genuinely open, say so in one line and proceed. Then begin the Iteration Loop.",
            "",
            "In scoped studio runs, fold this into the start of the **Alignment** scope (S1). This pre-flight front-loads the obvious questions; it does **not** replace ongoing flagging — every later pass must keep raising new questions as they surface.",
        ])

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

    # Decision Point Protocol: always included except in question mode
    decision_point_section: List[str] = []
    if not is_qmode:
        decision_point_section.extend([
            "",
            "## Decision Point Protocol",
            "",
            "When you encounter a gap, ambiguity, or fork that could meaningfully change your approach, flag it as a decision point. Do NOT silently assume — surface it. This applies to **every pass** — the pre-flight front-loads the obvious questions, but each later pass must keep raising new ones as they surface.",
            "",
            "> **Known failure mode — do not repeat.** An earlier version let agents hold their decisions and present them in a batch at the end (or leave them for the integrator). By then the run had already built on top of the unasked question, so the answer arrived too late to matter. Surface each decision the moment you hit it, per agent, inline — never collect them into a closing section and never defer them downstream.",
            "",
            "### Format",
            "",
            "Use a markdown blockquote with a bold DECISION header:",
            "",
            "```",
            *DECISION_BLOCK_EXAMPLE.splitlines(),
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
            "### Think-First Checkpoint (Advocates)",
            "Before producing any analysis, state in 2-3 sentences: (1) what you understand the objective to be, (2) what constraints you are treating as fixed, and (3) what you are unsure about. This goes at the top of your output before any deliverable content.",
            "",
            "### For Contrarians",
            "If the advocate assumed something that is actually unsettled, you MUST flag it as a decision point. Decision points are required output when assumptions are unsettled — do not let unexamined assumptions pass.",
            "",
            "If the advocate's stated understanding of the objective differs from yours, flag that FIRST — it outranks any deliverable critique. A correct analysis of the wrong problem is worse than an imperfect analysis of the right one.",
        ])

    # Clarity-guided focus section (skipped in question mode)
    clarity_section: List[str] = []
    if clarity_snapshot is not None and not is_qmode:
        if scopes_config and scopes_config.scopes:
            # Generate clarity guidance for each scope so agents get scope-appropriate density
            for scope in scopes_config.scopes:
                clarity_section.append(clarity.generate_clarity_instructions(clarity_snapshot, scope.name))
        else:
            clarity_section.append(clarity.generate_clarity_instructions(clarity_snapshot, "depth"))

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
                    "   **Lone-critical override:** a single serious finding from one role's contrarian must not be dropped just because it wasn't the consensus or another role disagreed. Carry it into the plan — either resolved, or explicitly logged as an accepted risk with the reason. Synthesis reconciles findings; it never quietly buries the inconvenient one.",
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
                + preflight_section
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

    Returns (scopes_config, scopes_allocations, scopes_meta); all None if disabled.
    """
    if args.no_scopes:
        return None, None, None

    # Determine scopes path. Project-local config lives at the artifact root
    # (<repo>/.studio/), like roles/personas/clarity/integrations, NOT the source
    # snapshot. The shipped default stays under the source dir.
    if args.scopes:
        scopes_path = Path(args.scopes)
        if not scopes_path.is_absolute():
            scopes_path = get_artifact_root() / scopes_path
    else:
        default_scopes = get_artifact_root() / ".studio" / "scopes.toml"
        if default_scopes.exists():
            scopes_path = default_scopes
        else:
            # Fall back to the shipped default config
            shipped_scopes = get_studio_root() / "config" / "scopes.toml"
            scopes_path = shipped_scopes if shipped_scopes.exists() else None

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
            f"3. See .studio/source/docs/SCOPES_GUIDE.md for examples"
        ) from exc
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid scopes configuration: {exc}\n\n"
            f"To fix:\n"
            f"1. Check TOML syntax in your scopes config\n"
            f"2. Ensure all scopes have 'focus' and 'max_iterations' fields\n"
            f"3. See .studio/source/docs/SCOPES_GUIDE.md for valid examples"
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


def _ensure_bridge_doc(artifact_root: Path, studio_root: Path) -> None:
    """Create the project bridge doc if none exists yet.

    Kept separate from the .studio/ scaffold guard: an ``init``-installed repo already
    has .studio/ (so the scaffold short-circuits), but still needs its bridge doc, so
    this runs regardless of whether .studio/ pre-existed.
    """
    bridge_candidates = [
        artifact_root / "docs" / "studio-bridge.md",
        artifact_root / "studio-bridge.md",
    ]
    if any(c.exists() for c in bridge_candidates):
        return
    template_path = studio_root / "docs" / "STUDIO_BRIDGE_TEMPLATE.md"
    if not template_path.exists():
        return
    dest = artifact_root / "docs" / "studio-bridge.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    template = template_path.read_text(encoding="utf-8")
    template = template.replace(
        'export STUDIO_ROOT="/path/to/studio"',
        f'export STUDIO_ROOT="{studio_root}"',
    )
    dest.write_text(template, encoding="utf-8")
    print(f"  Created bridge doc: {dest}")
    print("  Fill in the canon table and project summary.")


def _scaffold_external_repo(artifact_root: Path, studio_root: Path) -> None:
    """Ensure .studio/ structure and the bridge doc exist in an external repo."""
    studio_dir = artifact_root / ".studio"
    fresh = not studio_dir.exists()

    studio_dir.mkdir(parents=True, exist_ok=True)
    (studio_dir / "output").mkdir(exist_ok=True)
    (studio_dir / "knowledge").mkdir(exist_ok=True)

    # Bridge doc is ensured even for init'd repos (where .studio/ already existed).
    _ensure_bridge_doc(artifact_root, studio_root)

    if fresh:
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
    effective_details = apply_persona_overrides(
        PHASE_DETAILS, load_persona_overrides(artifact_root)
    )
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

    # Reset clarity when the objective changes so stale topic scores don't
    # bleed in (rebuilt via recompute-clarity). The objective is compared
    # against the one stored in the project-level clarity.json, which is
    # phase-independent, so a prior run under a different phase still counts.
    project_clarity = clarity.load_project_clarity(artifact_root)
    prev_run = _find_previous_run_dir(run_dir)
    had_prior = project_clarity is not None or prev_run is not None
    objective_changed = _objective_changed(project_clarity, prev_run, text)
    if objective_changed or project_clarity is None:
        (artifact_root / ".studio" / "clarity.json").unlink(missing_ok=True)
        project_clarity = clarity.empty_snapshot(text, run_id, now)

    instructions = build_instruction_doc(
        meta, run_dir, studio_role_details, scopes_config, scopes_allocations,
        clarity_snapshot=project_clarity,
        same_objective=(not objective_changed) if had_prior else None,
        phase_details=effective_details,
    )
    instructions_path = run_dir / "instructions.md"
    instructions_path.write_text(instructions, encoding="utf-8")
    instructions_abs_path = instructions_path.resolve()

    write_json(run_dir / "run.json", meta)
    rebuild_index()

    emit_json = getattr(args, "json", False)
    if emit_json:
        print(json.dumps({
            "run_id": run_id,
            "phase": phase,
            "run_dir": str(run_dir_abs),
            "instructions": str(instructions_abs_path),
            "scoped": bool(scopes_meta),
            "objective_changed": bool(objective_changed),
        }))
    else:
        print(f"Prepared {run_id} ({phase})")
        print(f"- Run directory: {run_dir_abs}")
        print(f"- Instructions: {instructions_abs_path}")
        if objective_changed:
            print("- Fresh run: cleared stale clarity from previous objective")

        if scopes_meta:
            print(f"\n💡 Tip: Scopes are active. Work through {scopes_meta['scopes'][0]['name']} scope first.")
        else:
            print("\n💡 Tip: Want to optimize iteration budgets? Create .studio/scopes.toml")
            print("   See: .studio/source/docs/SCOPES_GUIDE.md")

    # Append to usage log (fail silently so logging can't break prepare)
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
    if storage_stats.get("cleanup_suggested", False) and not emit_json:
        print(f"\n🧹 Storage Tip: You have {storage_stats['total_size_mb']}MB of Studio artifacts")
        print(f"   (oldest: {storage_stats['oldest_artifact_days']} days ago). Consider cleanup:")
        print(f"   {_entrypoint()} cleanup --dry-run  # Preview what would be deleted")
        print(f"   {_entrypoint()} cleanup           # Execute cleanup")

    return run_id


def _ordered_agent_files(run_dir: Path, phase: str, kind: str) -> List[Path]:
    """Agent output files (``kind`` is 'advocate' or 'contrarian') in write order.

    Chronological so "first draft vs final" and "rejections before the last one"
    are meaningful: simple runs sort by iteration number; studio runs sort by
    scope then iteration.
    """
    if phase == "studio":
        paths = list(run_dir.glob(f"{kind}--*--*.md"))

        def studio_key(path: Path) -> Tuple[str, int, str]:
            _, role, scope, iteration = parse_role_filename(path.name)
            return (scope or "", iteration, role)

        paths.sort(key=studio_key)
    else:
        paths = list(run_dir.glob(f"{kind}_*.md"))

        def simple_key(path: Path) -> int:
            suffix = path.stem.split("_")[-1]
            return int(suffix) if suffix.isdigit() else 0

        paths.sort(key=simple_key)
    return paths


def _count_rejections(run_dir: Path, phase: str) -> int:
    """Count contrarian REJECTED verdicts before the final one.

    Each contrarian file carries a VERDICT line. A debate that took two
    rejections to reach APPROVED did real work; one that approved on the first
    pass may be a rubber stamp. We count REJECTED verdicts across every
    contrarian file except the last, so the terminal verdict itself isn't
    counted as a rejection-along-the-way.
    """
    paths = _ordered_agent_files(run_dir, phase, "contrarian")
    rejections = 0
    for path in paths[:-1]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if extract_verdict(text) == "REJECTED":
            rejections += 1
    return rejections


def _ordered_advocate_word_counts(run_dir: Path, phase: str) -> List[int]:
    """Word count of each advocate document, first draft first, final last."""
    counts: List[int] = []
    for path in _ordered_agent_files(run_dir, phase, "advocate"):
        try:
            counts.append(len(path.read_text(encoding="utf-8").split()))
        except OSError:
            continue
    return counts


def _write_session_record(
    run_dir: Path,
    meta: Dict,
    phase: str,
    run_id: str,
    metrics_entries: List[Dict],
    clarity_mean_before: Optional[float],
    clarity_mean_after: Optional[float],
    clarity_topics_touched: int,
) -> None:
    """Write the automatic session.json health record for a finalized run.

    Additive and soft-fail: session.json augments finalize, it never gates it.
    Anything that goes wrong while deriving the record is logged and skipped so
    a finalize that already did its real work still succeeds. See
    docs/SESSION_ANALYTICS_PLAN.md and session.build_session_record.
    """
    try:
        record = build_session_record(
            run_id=run_id,
            repo=_project_name(),
            phase=phase,
            mode=meta.get("output_type", "deliverables"),
            finalized_iso=meta.get("updated_iso")
            or utc_now().isoformat(timespec="seconds"),
            verdict=meta.get("verdict", ""),
            iterations=meta.get("iterations_run") or 0,
            max_iterations=meta.get("max_iterations") or 0,
            rejections=_count_rejections(run_dir, phase),
            decisions=load_decisions_json(run_dir),
            clarity_mean_before=clarity_mean_before,
            clarity_mean_after=clarity_mean_after,
            clarity_topics_touched=clarity_topics_touched,
            metrics_entries=metrics_entries,
            advocate_word_counts=_ordered_advocate_word_counts(run_dir, phase),
        )
        write_json(run_dir / "session.json", record)
    except Exception as exc:  # never let the health record break finalize
        print(f"Session record skipped: {exc}", file=sys.stderr)


def finalize_run(args: argparse.Namespace) -> None:
    run_id = args.run_id
    phase = (args.phase or _phase_from_run_id(run_id)).lower()
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
    _maybe_notify(run_dir)
    _maybe_append_to_ledger(run_dir, meta)

    if metrics_entries:
        total_tokens = meta["metrics"]["total_tokens"]
        agent_count = meta["metrics"]["agents"]
        print(f"Agent metrics: {agent_count} agents, {total_tokens:,} total tokens")

    # Clarity delta for the session record: the "before" is captured below only
    # when there are decisions to recompute clarity from; otherwise it stays null.
    clarity_mean_before: Optional[float] = None
    clarity_mean_after: Optional[float] = None
    clarity_topics_touched = 0

    # Generate decisions.md: merge agent-surfaced decisions with any already-settled ones
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
        art_root = get_artifact_root()
        context = clarity.detect_context_scope(meta.get("input", ""))
        prior = clarity.load_project_clarity(art_root)
        snapshot = clarity.compute_clarity_snapshot(
            existing, context, run_id=run_id, prior_snapshot=prior
        )
        clarity.save_clarity_json(run_dir / "clarity.json", snapshot)
        clarity.save_project_clarity(art_root, snapshot)
        print(f"Updated clarity scores ({len(snapshot.topics)} topic(s), mean: {snapshot.mean_score:.2f})")

        clarity_mean_before = prior.mean_score if prior is not None else None
        clarity_mean_after = snapshot.mean_score
        clarity_topics_touched = len(snapshot.topics)

    # Auto-write the judgment-free session health record (additive, soft-fail).
    _write_session_record(
        run_dir,
        meta,
        phase,
        run_id,
        metrics_entries,
        clarity_mean_before,
        clarity_mean_after,
        clarity_topics_touched,
    )

    print(f"Finalized {run_id} ({phase}) → {meta['status']}")

    # Contextual hints for next steps
    if meta['status'] == 'COMPLETED' and meta.get('verdict') == 'APPROVED':
        print("\n💡 Next steps:")
        print(f"   1. Validate outputs: {_entrypoint()} validate --phase {phase} --run-id {run_id}")
        print(f"   2. Review summary: {run_dir}/summary.md")
        if phase != 'studio':
            print("   3. Implement recommendations from the run")
    elif meta['status'] == 'COMPLETED' and meta.get('verdict') == 'REJECTED':
        print("\n💡 Run was rejected. Consider:")
        print("   1. Review rejection reasons in contrarian files")
        print("   2. Prepare a rerun with revised approach")
        print("   3. Rerun will automatically inject failure context")

    # Invite a human quality rating to close the feedback loop (skippable).
    if meta['status'] == 'COMPLETED' and not getattr(args, 'no_rate_prompt', False):
        _prompt_for_rating(run_dir)


def _maybe_notify(run_dir: Path) -> None:
    """Auto-fire the run digest on finalize if a webhook target is enabled.

    Default-disabled: no-op unless ``.studio/integrations.toml`` enables a
    target. Soft-fail: any error is reported but never breaks finalize.
    """
    try:
        config = load_integrations_config(get_artifact_root())
    except Exception as exc:  # malformed config shouldn't break finalize
        print(f"Notify skipped (config error): {exc}", file=sys.stderr)
        return
    if not any(config.get(t, {}).get("enabled") for t in ("slack", "n8n")):
        return
    try:
        for line in notify_run(run_dir, config):
            print(f"Notify: {line}")
    except Exception as exc:
        print(f"Notify failed: {exc}", file=sys.stderr)


def _maybe_append_to_ledger(run_dir: Path, meta: Dict) -> None:
    """Append this run's outcome record to the configured local ledger.

    Collapses the manual export-outcomes → import-outcomes two-step into one
    finalize side effect: when ``[outcomes] ledger_path`` is set in
    ``.studio/integrations.toml``, the finalized run (rated or not) is appended to
    that ledger, deduped by (repo, run_id) so re-finalizing refreshes the record
    instead of duplicating it. Default-off and soft-fail: on any error we warn,
    print the manual import fallback, and never break finalize. Mirrors
    _maybe_notify.
    """
    ledger_path = get_configured_ledger_path()
    if ledger_path is None:
        return
    try:
        run = dict(meta)
        run["_rating"] = _load_rating(run_dir)
        record = _outcome_record_from_run(run, _project_name())
        existing = _read_ledger(ledger_path)
        merged = _merge_outcomes(existing, [record])
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        _write_ledger(ledger_path, merged)
        print(f"Appended outcome record to ledger: {ledger_path}")
    except Exception as exc:
        print(f"Ledger append failed ({exc}); record NOT added to {ledger_path}", file=sys.stderr)
        print(
            f"   Fallback: {_entrypoint()} export-outcomes --out out.jsonl && "
            f"{_entrypoint()} import-outcomes --from out.jsonl",
            file=sys.stderr,
        )


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
    prepare_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON object {run_id, run_dir, instructions, phase, ...} "
             "as the final line of stdout (instead of the prose summary + tips).",
    )
    _add_artifact_root_arg(prepare_parser)

    finalize_parser = subparsers.add_parser("finalize", help="Mark a run completed: refresh index, write session.json, append to the outcomes ledger.")
    finalize_parser.add_argument(
        "--phase",
        required=False,
        default=None,
        choices=sorted(PHASE_DETAILS.keys()),
        help="Phase the run belongs to (optional — derived from --run-id when omitted).",
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
    finalize_parser.add_argument(
        "--no-rate-prompt",
        action="store_true",
        help="Suppress the end-of-run quality-rating prompt/nudge.",
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
        required=False,
        default=None,
        choices=sorted(PHASE_DETAILS.keys()),
        help="Phase the run belongs to (optional — derived from --run-id when omitted).",
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
    extract_parser.add_argument(
        "--all",
        action="store_true",
        dest="show_all",
        help="Show all decisions including already-settled ones (default: only unsettled).",
    )
    extract_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON {count, decisions:[...]} instead of markdown (gate on count, not empty stdout).",
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
    init_parser.add_argument(
        "--no-hook",
        action="store_true",
        help="Do not install the SessionStart update-check hook.",
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
    check_install_parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip the network fetch of the Studio source's remote; compare "
             "against cached refs only (for offline use).",
    )

    check_updates_parser = subparsers.add_parser(
        "check-updates",
        help="Print a one-line update nudge if the installed Studio snapshot is "
             "behind upstream. Silent when current. Invoked by the SessionStart hook.",
    )
    check_updates_parser.add_argument(
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
    update_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite even locally-modified snapshot files (default: refuse and list them).",
    )
    update_parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip the network fetch of the Studio source's remote; compare "
             "against cached refs only (for offline use).",
    )
    update_parser.add_argument(
        "--no-hook",
        action="store_true",
        help="Do not install the SessionStart update-check hook.",
    )
    update_parser.add_argument(
        "--pull-source",
        action="store_true",
        help="Fast-forward your own Studio SOURCE checkout to origin before "
             "installing, when it is cleanly behind (overrides the source config).",
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
    recompute_clarity_parser.add_argument(
        "--phase", required=False, default=None, choices=sorted(PHASE_DETAILS.keys()),
        help="Phase the run belongs to (optional — derived from --run-id when omitted).",
    )
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
    record_metrics_parser.add_argument("--agent", required=True, choices=["advocate", "contrarian", "integrator", "implementer"], help="Agent type.")
    record_metrics_parser.add_argument("--total-tokens", type=int, required=True, help="Total tokens consumed.")
    record_metrics_parser.add_argument("--tool-uses", type=int, default=0, help="Number of tool uses.")
    record_metrics_parser.add_argument("--duration-ms", type=int, default=0, help="Duration in milliseconds.")
    record_metrics_parser.add_argument("--role", default=None, help="Role name (for studio phase).")
    record_metrics_parser.add_argument("--scope", default=None, choices=["alignment", "depth", "polish", "flat"], help="Scope name.")

    show_metrics_parser = subparsers.add_parser(
        "show-metrics", help="Display token usage summary for a run."
    )
    show_metrics_parser.add_argument("--run-dir", type=Path, required=True, help="Path to the run directory.")

    # --- Human quality ratings & cross-run stats ---

    rate_parser = subparsers.add_parser(
        "rate", help="Record a human quality rating (1-5) for a completed run."
    )
    rate_parser.add_argument("--run-dir", type=Path, required=True, help="Path to the run directory.")
    rate_parser.add_argument(
        "--score", type=int, required=True, choices=[1, 2, 3, 4, 5],
        help="Quality score: 1 (poor) to 5 (excellent).",
    )
    rate_parser.add_argument("--note", default=None, help="Optional note on what was good or bad.")
    rate_parser.add_argument(
        "--shipped", default=None, choices=list(VALID_SHIPPED),
        help="Outcome: did this run's result actually ship? (yes/no/partial)",
    )
    rate_parser.add_argument(
        "--impact", default=None, choices=list(VALID_IMPACT),
        help="Outcome: how much did it change downstream? (none/minor/major)",
    )
    rate_parser.add_argument(
        "--changed", default=None,
        help="Outcome: one line on what this run actually changed.",
    )

    export_outcomes_parser = subparsers.add_parser(
        "export-outcomes",
        help="Export this repo's runs as portable JSONL outcome records (rated or not).",
    )
    export_outcomes_parser.add_argument(
        "--out", default=None, help="Write JSONL here (default: stdout)."
    )
    export_outcomes_parser.add_argument(
        "--repo", default=None, help="Project name to tag records with (default: repo dir name)."
    )
    _add_artifact_root_arg(export_outcomes_parser)

    import_outcomes_parser = subparsers.add_parser(
        "import-outcomes",
        help="Merge JSONL outcome records into the central ledger (dedup by repo+run_id).",
    )
    import_outcomes_parser.add_argument(
        "--from", dest="from_file", required=True, help="Path to a JSONL outcomes export."
    )
    _add_artifact_root_arg(import_outcomes_parser)

    stats_parser = subparsers.add_parser(
        "stats", help="Cross-run diagnostics: outcomes, ratings, efficiency, decisions, usage."
    )
    stats_parser.add_argument(
        "--phase", default=None, choices=sorted(PHASE_DETAILS.keys()),
        help="Filter to a single phase.",
    )
    stats_parser.add_argument("--json", action="store_true", help="Emit aggregated stats as JSON.")
    stats_parser.add_argument(
        "--artifact-root", type=Path, default=None,
        help="Override artifact root directory.",
    )

    # --- Outbound notification (Slack / n8n run digest) ---
    notify_parser = subparsers.add_parser(
        "notify", help="Post a run digest to configured Slack/n8n webhooks."
    )
    notify_parser.add_argument("--run-dir", type=Path, required=True, help="Path to the run directory.")
    notify_parser.add_argument("--dry-run", action="store_true", help="Build and print payloads without posting.")
    notify_parser.add_argument(
        "--artifact-root", type=Path, default=None,
        help="Override artifact root directory (where .studio/integrations.toml lives).",
    )

    offload_parser = subparsers.add_parser(
        "offload", help="Analyze CLAUDE.md for offload opportunities."
    )
    offload_parser.add_argument("--target", type=Path, default=Path("."), help="Directory containing the CLAUDE.md to analyze.")
    offload_parser.add_argument("--apply", action="store_true", help="Apply changes after report.")
    offload_parser.add_argument("--rollback", action="store_true", help="Restore from most recent backup.")
    offload_parser.add_argument("--verify", action="store_true", help="Run canary verification.")

    # --- Setup wizard ---
    setup_parser = subparsers.add_parser(
        "setup", help="Configure Studio for a project (roles, personas, scopes, cleanup, unstale)."
    )
    setup_parser.add_argument(
        "--target", type=Path, default=Path("."),
        help="Path to the target project directory.",
    )
    setup_parser.add_argument(
        "--status", action="store_true",
        help="Show current setup configuration status.",
    )
    setup_parser.add_argument(
        "--defaults", action="store_true",
        help="Apply all default configuration non-interactively.",
    )
    setup_parser.add_argument(
        "--answers", type=Path, default=None,
        help="Apply configuration from a JSON answers file.",
    )
    setup_parser.add_argument(
        "--role-pack", type=str, default=None,
        help="Set role pack (shorthand for role_pack step).",
    )
    setup_parser.add_argument(
        "--roles", nargs="*", default=None,
        help="Role overrides (+role to add, -role to remove). Use with --role-pack.",
    )

    return parser


def validate_run(args: argparse.Namespace) -> None:
    """Validate Studio run outputs."""
    run_id = args.run_id
    phase = (args.phase or _phase_from_run_id(run_id)).lower()
    run_dir = get_output_root() / phase / run_id
    
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    
    # Load validation config (project-local lives at the artifact root, not the snapshot)
    config_path = args.config
    if not config_path:
        config_path = get_artifact_root() / ".studio" / "validation.toml"
    
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
        # Single decision mode: validate required args
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


def _decision_to_dict(dp) -> dict:
    """Serialize a DecisionPoint. Single source of truth for the machine-readable
    shape shared by `check-decisions` and `extract-decisions --json`."""
    return {
        "priority": dp.priority,
        "question": dp.question,
        "unblocks": dp.unblocks,
        "options": dp.options,
        "source_file": dp.source_file,
    }


def check_decisions(args: argparse.Namespace) -> None:
    """Parse decision points from a single agent output file and print as JSON."""
    file_path = Path(args.file)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    points = parse_decision_points(text, source_file=file_path.name)

    grouped: dict[str, list[dict]] = {"P0": [], "P1": [], "P2": []}
    for dp in points:
        entry = _decision_to_dict(dp)
        grouped[entry.pop("priority")].append(entry)  # grouped by priority → drop it from the entry

    print(json.dumps(grouped, indent=2))


def extract_decisions(args: argparse.Namespace) -> None:
    """Extract decision points from agent files in a run directory.

    Scans advocate/contrarian files (optionally filtered by scope) and
    outputs formatted decision points. Filters out already-settled
    decisions by default; use --all to include them. Useful mid-run
    between agents.
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

    if not getattr(args, "show_all", False):
        settled = load_decisions_json(run_dir)
        all_decisions = filter_unsettled(all_decisions, settled)

    if getattr(args, "json", False):
        # Machine-readable: always emit (count lets callers gate on a number, not empty stdout).
        decisions = [_decision_to_dict(dp) for dp in all_decisions]
        print(json.dumps({"count": len(decisions), "decisions": decisions}, indent=2))
        return

    if not all_decisions:
        # Silent exit: no decisions found is normal
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
        print("\n  By scope:")
        for scope, stats in sorted(summary["by_scope"].items()):
            pct = (stats["total_tokens"] / summary["total_tokens"] * 100) if summary["total_tokens"] else 0
            print(f"    {scope:12s}  {stats['agents']} agents  {stats['total_tokens']:>8,} tokens ({pct:.0f}%)")

    if summary["by_role"]:
        print("\n  By role:")
        for role, stats in sorted(summary["by_role"].items()):
            pct = (stats["total_tokens"] / summary["total_tokens"] * 100) if summary["total_tokens"] else 0
            print(f"    {role:16s}  {stats['agents']} agents  {stats['total_tokens']:>8,} tokens ({pct:.0f}%)")

    # Per-agent detail
    print("\n  Agent detail:")
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


# ---------------------------------------------------------------------------
# Human quality ratings & cross-run stats
# ---------------------------------------------------------------------------

def _load_rating(run_dir: Path) -> Optional[Dict]:
    """Load rating.json from a run directory, returning None if absent/unreadable."""
    try:
        return json.loads((run_dir / "rating.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _load_session(run_dir: Path) -> Optional[Dict]:
    """Load session.json from a run directory, returning None if absent/unreadable.

    session.json is the automatic health record finalize writes; a run finalized
    before that feature (or a broken file) simply has none.
    """
    try:
        return json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _write_rating(
    run_dir: Path,
    score: int,
    note: str,
    shipped: Optional[str] = None,
    impact: Optional[str] = None,
    changed: Optional[str] = None,
) -> Dict:
    """Write rating.json (the human counterpart to the agent verdict).

    The optional shipped/impact/changed fields are the *outcome* of the run
    (what it led to downstream), stored under an ``outcome`` block. They answer
    "did this actually change anything, and what," which is the signal a run's
    verdict and quality score can't capture on their own.
    """
    rating = {
        "score": score,
        "note": (note or "").strip(),
        "rated_iso": utc_now().isoformat(timespec="seconds"),
    }
    outcome = {}
    if shipped:
        outcome["shipped"] = shipped
    if impact:
        outcome["impact"] = impact
    if changed and changed.strip():
        outcome["changed"] = changed.strip()
    if outcome:
        rating["outcome"] = outcome
    write_json(run_dir / "rating.json", rating)
    return rating


def record_rating(args: argparse.Namespace) -> None:
    """Record a human quality rating (1-5), plus optional outcome, for a run.

    Stored as rating.json alongside metrics.json, the human counterpart to the
    agent-emitted verdict. The score says how good the run was; the optional
    ``--shipped/--impact/--changed`` outcome says what it actually led to. This
    is the signal `stats` uses to gauge how well the system is doing and which
    runs to learn from.
    """
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    rating = _write_rating(
        run_dir,
        args.score,
        args.note,
        shipped=getattr(args, "shipped", None),
        impact=getattr(args, "impact", None),
        changed=getattr(args, "changed", None),
    )
    suffix = f' — "{rating["note"]}"' if rating["note"] else ""
    print(f"Recorded rating {rating['score']}/5 for {run_dir.name}{suffix}")
    outcome = rating.get("outcome")
    if outcome:
        print("  Outcome: " + ", ".join(f"{k}={v}" for k, v in outcome.items()))


def _prompt_for_rating(run_dir: Path) -> None:
    """Invite a human quality rating at the end of finalize.

    Interactive when attached to a TTY (a human running ``finalize`` directly);
    otherwise prints a copy-paste nudge so automation (and the assistant driving
    finalize via a non-interactive shell) never blocks on stdin.
    """
    nudge = (
        f"   {_entrypoint()} rate --run-dir {run_dir} "
        f"--score <1-5> --note \"...\""
    )
    if not sys.stdin.isatty():
        print("\n📊 Rate this run (feeds `stats` + tuning over time):")
        print(nudge)
        return

    try:
        raw = input("\n📊 Rate this run 1-5 (Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not raw:
        return
    try:
        score = int(raw)
    except ValueError:
        print(f"   Not a number — skipped. Rate later with:\n{nudge}")
        return
    if not 1 <= score <= 5:
        print("   Score must be 1-5 — skipped.")
        return
    try:
        note = input("   Note (optional, Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        note = ""
        print()
    _write_rating(run_dir, score, note)
    print(f"   Recorded {score}/5.")


def _outcome_record_from_run(run: Dict, repo: str) -> Dict:
    """Build a portable outcome record from an enriched run dict.

    Every run yields a record, including unrated ones; an unrated run is still a
    session the ledger and stats should see. A rating, when present, fills in
    score/shipped/impact/changed/rated_iso; without one those stay null while
    repo, run_id, phase, verdict, status, and token cost are still recorded.
    """
    rating = run.get("_rating") or {}
    outcome = rating.get("outcome") or {}
    return {
        "repo": repo,
        "run_id": run.get("run_id", Path(run.get("run_dir", "?")).name),
        "phase": run.get("phase"),
        "verdict": run.get("verdict"),
        "status": run.get("status"),
        "score": rating.get("score"),
        "shipped": outcome.get("shipped"),
        "impact": outcome.get("impact"),
        "changed": outcome.get("changed"),
        "total_tokens": (run.get("metrics") or {}).get("total_tokens"),
        "rated_iso": rating.get("rated_iso"),
    }


def _read_ledger(path: Path) -> List[Dict]:
    """Read a JSONL outcomes file, skipping blank or unparseable lines."""
    if not path.exists():
        return []
    records: List[Dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _write_ledger(path: Path, records: List[Dict]) -> None:
    """Write outcome records as JSONL (one compact object per line)."""
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _collect_local_outcomes(runs: List[Dict], repo: str) -> List[Dict]:
    """Outcome records for this repo's runs (runs already carry _rating).

    Includes unrated runs; every run yields a record, so stats and the ledger
    see every session rather than only the ones a human bothered to rate.
    """
    return [_outcome_record_from_run(run, repo) for run in runs]


def _merge_outcomes(ledger: List[Dict], local: List[Dict]) -> List[Dict]:
    """Combine cross-repo ledger records with this repo's fresh local records.

    Dedup by (repo, run_id); local wins, since it's read straight from the run
    directories and the ledger may hold an older export of the same run.
    """
    by_key = {(r.get("repo"), r.get("run_id")): r for r in ledger}
    for rec in local:
        by_key[(rec.get("repo"), rec.get("run_id"))] = rec
    return list(by_key.values())


def export_outcomes(args: argparse.Namespace) -> None:
    """Collect this repo's runs into a portable JSONL of outcome records.

    Includes unrated runs; every session is a record. Writes to --out (default:
    stdout). Feed the file to ``import-outcomes`` in the tool repo so a consuming
    repo's results become visible to ``stats`` there. This is the bridge that lets
    evidence reach the main repo when a repo lives on another machine.
    """
    repo = getattr(args, "repo", None) or _project_name()
    runs = collect_runs(get_output_root())
    for run in runs:
        run["_rating"] = _load_rating(Path(run["run_dir"]))
    records = _collect_local_outcomes(runs, repo)

    payload = "".join(json.dumps(r) + "\n" for r in records)
    out = getattr(args, "out", None)
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"Exported {len(records)} outcome record(s) from '{repo}' to {out_path}")
    else:
        if payload:
            print(payload, end="")
        print(f"# {len(records)} outcome record(s) from '{repo}'", file=sys.stderr)


def import_outcomes(args: argparse.Namespace) -> None:
    """Merge outcome records from a JSONL file into the central ledger.

    Dedup by (repo, run_id): re-importing an updated export refreshes existing
    records instead of duplicating them. This is how outcomes from other repos
    reach ``stats`` in this repo.
    """
    src = Path(args.from_file)
    if not src.is_file():
        raise FileNotFoundError(f"Outcomes file not found: {src}")
    incoming = _read_ledger(src)

    ledger_path = get_outcomes_ledger_path()
    existing = _read_ledger(ledger_path)
    keys_before = {(r.get("repo"), r.get("run_id")) for r in existing}
    merged = _merge_outcomes(existing, incoming)

    added = sum(1 for r in incoming if (r.get("repo"), r.get("run_id")) not in keys_before)
    updated = len(incoming) - added

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    _write_ledger(ledger_path, merged)
    print(
        f"Imported {len(incoming)} record(s) into {ledger_path} "
        f"(+{added} new, {updated} updated; {len(merged)} total)"
    )


def show_stats(args: argparse.Namespace) -> None:
    """Display cross-run diagnostics: outcomes, ratings, efficiency, decisions, usage."""
    root = Path(args.artifact_root).resolve() if getattr(args, "artifact_root", None) else get_artifact_root()
    runs = collect_runs(get_output_root())

    phase_filter = getattr(args, "phase", None)
    if phase_filter:
        runs = [r for r in runs if r.get("phase") == phase_filter]

    for run in runs:
        run_dir = Path(run["run_dir"])
        run["_rating"] = _load_rating(run_dir)
        run["_session"] = _load_session(run_dir)
        try:
            run["_decisions"] = load_decisions_json(run_dir)
        except Exception:
            run["_decisions"] = []

    agg = aggregate_stats(runs)

    # Trend alerts: run-over-run regressions that persist across 2+ consecutive
    # runs (rating falling, tokens/cost climbing). detect_trend_alerts orders by
    # created_iso itself, so the raw run list is fine to hand over.
    trend_alerts = detect_trend_alerts(runs)

    # Session health: the automatic finalize records, oldest first so the
    # recent-vs-earlier trend split is chronological. The --phase filter above
    # already narrowed `runs`, so this respects it.
    session_records = [run["_session"] for run in runs if run.get("_session")]
    session_records.sort(key=lambda record: record.get("finalized_iso") or "")
    session_health = summarize_session_health(session_records)

    # Outcomes: this repo's rated runs plus the cross-repo ledger (imported from
    # other projects). Local records win on conflict since they're the fresher read.
    local_outcomes = _collect_local_outcomes(runs, _project_name())
    ledger_outcomes = _read_ledger(get_outcomes_ledger_path())
    outcome_records = _merge_outcomes(ledger_outcomes, local_outcomes)
    if phase_filter:
        outcome_records = [r for r in outcome_records if r.get("phase") == phase_filter]
    outcomes = summarize_outcomes(outcome_records)

    if getattr(args, "json", False):
        print(json.dumps(
            {**agg, "outcomes": outcomes, "session_health": session_health, "trend_alerts": trend_alerts},
            indent=2,
        ))
        return

    usage = None
    usage_path = root / ".studio" / "usage.log"
    if usage_path.exists():
        try:
            usage = _parse_usage_log(usage_path.read_text(encoding="utf-8"))
        except OSError:
            usage = None

    clarity_note = None
    snapshot = clarity.load_project_clarity(root)
    if snapshot is not None and snapshot.topics:
        clarity_note = f"{len(snapshot.topics)} topics tracked (run 'show-clarity' for the table)"

    print(format_stats(
        agg, usage=usage, clarity_note=clarity_note, outcomes=outcomes,
        session_health=session_health, trend_alerts=trend_alerts,
    ))


def inject_context(args: argparse.Namespace) -> None:
    """Generate context for the next agent in a scoped run.

    Combines settled decisions, clarity summary, prior-scope file lists,
    and scope-specific instructions into a markdown file written to
    ``context--<role>--<scope>--<stance>.md`` in the run directory.
    Resolves custom scope names via canonical positional aliases.
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
    qmode = is_question_mode(meta.get("output_type"))

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
                    (i for i, s in enumerate(scopes_config.scopes) if s.name == scope.name),
                    0,
                )
        else:
            # The run recorded a scopes config that no longer resolves (e.g. moved, or a
            # path from another machine). Don't silently drop scope guidance; say so.
            print(
                f"Warning: scopes config {scopes_path} (from run.json) not found; "
                "emitting context without scope guidance.",
                file=sys.stderr,
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
            question_mode=qmode,
        ))

    # 2. Settled decisions: only add if generate_scope_prompt didn't already cover it
    if decisions_md_exists and not scope:
        output_parts.extend([
            "## Settled Decisions",
            "",
            f"Read `{run_dir}/decisions.md` for settled constraints. Treat as hard constraints — do not re-litigate.",
            "",
        ])

    # 3. Clarity summary
    root = get_artifact_root()
    snapshot = clarity.load_project_clarity(root)
    if snapshot is not None:
        output_parts.append(clarity.generate_clarity_instructions(snapshot, scope_name))

    if output_parts:
        context_text = "\n".join(output_parts)
        context_file = run_dir / f"context--{role}--{scope_name}--{stance}.md"
        context_file.write_text(context_text, encoding="utf-8")
        print(context_file)
    else:
        print(f"No prior context for {scope_name} {role} {stance} — starting fresh.", file=sys.stderr)


def notify(args: argparse.Namespace) -> None:
    """Post a run digest to configured Slack/n8n webhooks."""
    root = Path(args.artifact_root).resolve() if args.artifact_root else get_artifact_root()
    config = load_integrations_config(root)
    for line in notify_run(args.run_dir, config, dry_run=args.dry_run):
        print(line)


def show_clarity(args: argparse.Namespace) -> None:
    """Display current project clarity scores."""
    root = Path(args.artifact_root).resolve() if args.artifact_root else get_artifact_root()
    snapshot = clarity.load_project_clarity(root)
    if snapshot is None:
        print("No clarity data yet. Run a phase with decision points first.")
        return
    print(clarity.format_clarity_summary(snapshot))


def set_clarity(args: argparse.Namespace) -> None:
    """Override a topic's clarity score."""
    root = Path(args.artifact_root).resolve() if args.artifact_root else get_artifact_root()
    snapshot = clarity.load_project_clarity(root)
    if snapshot is None:
        print("No clarity data yet. Run a phase with decision points first.")
        return
    if args.reset:
        snapshot = clarity.apply_user_overrides(snapshot, {args.topic: None})
    elif args.score is not None:
        snapshot = clarity.apply_user_overrides(snapshot, {args.topic: args.score})
    else:
        print("Provide --score VALUE or --reset")
        return
    clarity.save_project_clarity(root, snapshot)
    print(clarity.format_clarity_summary(snapshot))


def recompute_clarity(args: argparse.Namespace) -> None:
    """Recompute clarity from a run's decisions.

    Works with both finalized and in-progress runs. If decisions.json exists,
    uses it. Otherwise extracts decisions from agent output files directly,
    making this usable mid-run.
    """
    root = Path(args.artifact_root).resolve() if args.artifact_root else get_artifact_root()
    run_id = args.run_id
    phase = (args.phase or _phase_from_run_id(run_id)).lower()
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
    context = clarity.detect_context_scope(input_text)
    prior = clarity.load_project_clarity(root)
    snapshot = clarity.compute_clarity_snapshot(decisions, context, run_id=run_id, prior_snapshot=prior)
    clarity.save_clarity_json(run_dir / "clarity.json", snapshot)
    clarity.save_project_clarity(root, snapshot)
    print(clarity.format_clarity_summary(snapshot))


def _do_init(args: argparse.Namespace) -> None:
    """Install Studio into a target project."""
    from install import install_studio
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"Target directory not found: {target}")
    dot_studio = install_studio(target, install_hook=not args.no_hook)
    print(f"Studio installed to {dot_studio}")
    print(f"  Slash commands: {target / '.claude' / 'commands'}")
    print(f"  Source: {dot_studio / 'source'}")
    print("\nRun /studio-setup to configure roles, personas, scopes, cleanup, and unstale audit.")
    print("Then use /run-phase or /run-studio-phase — pause-and-ask included.")
    print("NOTE: Start a NEW Claude Code session (not just /clear) to discover the commands.")


def _print_local_edits_preview(locally_modified: list) -> None:
    """Print the clobber preview: installed files the user edited that an update
    would overwrite. No-op when there are none. Shared so the preview shows in
    both the normal report and the stale-source path (which exits early)."""
    if not locally_modified:
        return
    print(f"\n⚠️  {len(locally_modified)} installed file(s) have LOCAL EDITS that update would overwrite:")
    for rel in locally_modified:
        print(f"   - .studio/source/{rel}")
    print("   If any is project config, move it to <repo>/.studio/<name>.toml (update never")
    print("   touches that). update will refuse to clobber these unless run with --force.")


def _do_check_install(args: argparse.Namespace) -> None:
    """Check if installed Studio is up to date."""
    from install import check_studio, _resolve_source_dir
    target = Path(args.target).resolve()
    status = check_studio(target, fetch=not args.no_fetch)
    if not status["installed"]:
        print(f"Studio is NOT installed at {target}")
        print(f"Run: {_entrypoint()} init --target {target}")
        return
    if status.get("warning"):
        print(f"WARNING: {status['warning']}\n")
    if status.get("source_note"):
        print(f"Note: {status['source_note']}.")

    # A stale source (its own local main behind origin) makes any "up to date"
    # false: the installed files match a source that is itself out of date. Refuse
    # the green verdict — show the honest diff against origin, name the one command
    # that catches the source up, and exit non-zero so nothing prints "up to date".
    staleness = status.get("staleness")
    if staleness and staleness["is_stale"]:
        source_dir, _ = _resolve_source_dir(target, None)
        print(
            f"Studio source is {staleness['behind']} commit(s) behind "
            f"{staleness['remote_ref']}; comparing against {staleness['remote_ref']} "
            f"instead of the stale local copy."
        )
        if status["changed"]:
            print(f"  Changed: {', '.join(status['changed'])}")
        if status["missing"]:
            print(f"  Missing: {', '.join(status['missing'])}")
        if status.get("retired"):
            print(f"  Retired (update will delete): {', '.join(status['retired'])}")
        if status.get("claude_md_stale"):
            print("  CLAUDE.md: coding-principles block is behind the current template")
        print(f"\nCatch your source up first:  git -C {source_dir} pull")
        print(f"Then:  {_entrypoint()} update --target {target}")
        # Surface the clobber preview too, so a user with local edits over a stale
        # source learns about it now, not only when a later update refuses.
        _print_local_edits_preview(status["locally_modified"])
        sys.exit(1)

    if status["up_to_date"]:
        print(f"Studio at {target} is up to date.")
    else:
        print(f"Studio at {target} needs updating:")
        if status["changed"]:
            print(f"  Changed: {', '.join(status['changed'])}")
        if status["missing"]:
            print(f"  Missing: {', '.join(status['missing'])}")
        if status.get("retired"):
            print(f"  Retired (update will delete): {', '.join(status['retired'])}")
        if status.get("claude_md_stale"):
            print("  CLAUDE.md: coding-principles block is behind the current template")
        print(f"\nRun: {_entrypoint()} update --target {target}")

    _print_local_edits_preview(status["locally_modified"])


def _do_check_updates(args: argparse.Namespace) -> None:
    """Print a one-line SessionStart nudge when the installed snapshot is behind.

    Invoked by the SessionStart hook, so it must NEVER fail the session: every
    path is wrapped and the process always exits 0. Silent when current, offline,
    or anything at all goes wrong.
    """
    try:
        import install
        result = install.compute_update_check(Path(args.target).resolve())
        if result.should_notify:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": install.UPDATE_ADDITIONAL_CONTEXT,
                }
            }))
    except Exception:
        pass


def _do_update(args: argparse.Namespace) -> None:
    """Update installed Studio from source."""
    from install import update_studio, _resolve_source_dir
    target = Path(args.target).resolve()
    result = update_studio(
        target,
        force=getattr(args, "force", False),
        fetch=not getattr(args, "no_fetch", False),
        install_hook=not getattr(args, "no_hook", False),
        pull_source=getattr(args, "pull_source", False),
    )
    if result.get("warning"):
        print(f"WARNING: {result['warning']}\n")
    if result.get("source_note"):
        print(f"Note: {result['source_note']}.")

    # A stale source (its own local main behind origin) would falsely no-op; the
    # update instead read and re-installed from origin/main. When the user opted
    # into the fast-forward and it happened, say the source is now current. When it
    # didn't (or they never opted in), fall back to naming the one command that
    # catches their own source checkout up — plus, if an opted-in pull was skipped,
    # why we couldn't do it.
    source_pull = result.get("source_pull")
    staleness = result.get("staleness")
    if source_pull and source_pull["pulled"]:
        print(
            f"Fast-forwarded your Studio source to {source_pull['new_head']}; "
            "your local checkout is now current."
        )
    else:
        if source_pull and source_pull["reason"]:
            print(
                "Wanted to fast-forward your Studio source but couldn't: "
                f"{source_pull['reason']}."
            )
        if staleness and staleness["is_stale"]:
            source_dir, _ = _resolve_source_dir(target, None)
            print(
                f"Studio source was {staleness['behind']} commit(s) behind "
                f"{staleness['remote_ref']}; installed from {staleness['remote_ref']} "
                f"instead of the stale local copy."
            )
            print(f"Catch your source up:  git -C {source_dir} pull")

    if result.get("blocked"):
        mods = result["locally_modified"]
        print(f"Update BLOCKED: {len(mods)} installed file(s) have local edits that would be overwritten:")
        for rel in mods:
            print(f"   - .studio/source/{rel}")
        print("\nThese are edits to the Studio snapshot (it gets replaced on update). If any is")
        print("project config, move it to <repo>/.studio/<name>.toml — the project-override location")
        print(f"update never touches. To overwrite anyway: {_entrypoint()} update --target {target} --force")
        return
    if (
        result["updated"] == 0
        and result["added"] == 0
        and result.get("removed", 0) == 0
        and not result.get("claude_md_refreshed")
    ):
        print(f"Studio at {target} is already up to date.")
    else:
        print(f"Studio updated at {target}:")
        if result["updated"]:
            print(f"  Updated: {result['updated']} file(s)")
        if result["added"]:
            print(f"  Added: {result['added']} file(s)")
        if result.get("removed"):
            print(f"  Removed: {result['removed']} file(s) Studio no longer ships — "
                  f"{', '.join(result.get('retired', []))}")
        if result.get("claude_md_refreshed"):
            print("  CLAUDE.md: refreshed the coding-principles block (your own notes left untouched)")
        # Check for new setup steps
        try:
            import setup as _setup
            state = _setup.load_setup_state(target)
            pend = _setup.pending_steps(state)
            if pend:
                labels = ", ".join(s["label"] for s in pend)
                print(f"\n  New features available: {labels}")
                print("  Run /studio-setup to configure.")
        except ImportError:
            pass


def _do_setup(args: argparse.Namespace) -> None:
    """Configure Studio for a project."""
    import setup as _setup

    target = Path(args.target).resolve()

    if args.status:
        print(_setup.show_status(target))
    elif args.defaults:
        state = _setup.apply_defaults(target)
        pend = _setup.pending_steps(state)
        print(f"Applied default configuration ({len(state['completed_steps'])} steps).")
        if pend:
            print(f"  Pending: {', '.join(s['label'] for s in pend)}")
    elif args.answers:
        answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        _setup.apply_from_answers(target, answers)
        print(f"Applied configuration from {args.answers}.")
    elif args.role_pack:
        _setup.apply_role_pack(target, args.role_pack, args.roles or [])
        print(f"Role pack set to '{args.role_pack}'.")
        if args.roles:
            print(f"  Overrides: {' '.join(args.roles)}")
    else:
        print(_setup.show_status(target))


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


def _dispatch(args: argparse.Namespace) -> None:
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
    elif args.command == "check-updates":
        _do_check_updates(args)
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
    elif args.command == "rate":
        record_rating(args)
    elif args.command == "stats":
        show_stats(args)
    elif args.command == "export-outcomes":
        export_outcomes(args)
    elif args.command == "import-outcomes":
        import_outcomes(args)
    elif args.command == "notify":
        notify(args)
    elif args.command == "offload":
        do_offload(args)
    elif args.command == "setup":
        _do_setup(args)
    else:
        raise ValueError("Unknown command")


def main() -> None:
    args = parse_cli_args()

    # Apply --artifact-root override before any command runs
    artifact_root = getattr(args, "artifact_root", None)
    if artifact_root is not None:
        set_artifact_root(artifact_root)

    try:
        _dispatch(args)
    except Exception as exc:  # operational failure: surface an actionable message, not a traceback
        if os.environ.get("STUDIO_DEBUG"):
            raise
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
