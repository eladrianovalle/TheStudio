#!/usr/bin/env python3
"""
Studio run instruction helper.

Prepares per-phase Cascade instructions, creates run directories, and keeps
output/index.md in sync so every Studio request can be executed agentically
through Cascade (no CLI round trips required).
"""
from __future__ import annotations

import argparse
import json
import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from cleanup import (
    cleanup_runs,
    format_bytes,
    load_cleanup_settings,
)
from run_phase_roles import (
    RoleConfigError,
    RoleDetails,
    build_role_details,
    collect_role_artifacts,
    default_role_pack_name,
    load_manifest,
    load_role_pack,
    normalize_role_filename,
    parse_iteration_from_filename,
    resolve_role_list,
)

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
                "Key algorithms/data-structure notes.",
                "Starter code fragment (e.g., HTML/JS or config snippet).",
            ],
        },
        "notes": "Don’t forget mobile/browser constraints and ops toil when approving.",
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

def get_studio_root() -> Path:
    env_override = os.environ.get("STUDIO_ROOT")
    if env_override:
        override_path = Path(env_override).expanduser()
        return override_path if override_path.is_absolute() else override_path.resolve()
    return Path(__file__).resolve().parent


def get_output_root() -> Path:
    return get_studio_root() / "output"


def get_knowledge_log_path() -> Path:
    return get_studio_root() / "knowledge" / "run_log.md"


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
                meta = load_json(meta_path)
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
                run_id=entry["run_id"],
                phase=entry["phase"],
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
        f"## {meta['run_id']} ({meta['phase']}) – {meta.get('status', 'PENDING')}",
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
    meta: Dict, run_dir: Path, studio_roles: Sequence[RoleDetails] | None = None
) -> str:
    phase = meta["phase"]
    info = PHASE_DETAILS[phase]
    rel_dir = run_dir.as_posix()
    base_section = [
        f"# Studio Cascade Instructions — {meta['run_id']}",
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

    roles_section = [
        "",
        "## Agent Roles",
        "",
        f"- **Advocate:** {info['advocate']}",
        f"- **Contrarian:** {info['contrarian']}",
    ]
    if phase != "studio":
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
        loop_section.append(
            "5. As soon as a contrarian returns `VERDICT: APPROVED`, move to the Implementer checklist."
        )
    else:
        loop_section.append(
            "5. Once the contrarian returns `VERDICT: APPROVED`, operate as the Integrator to merge inspiration + constraints into a roadmap (`integrator.md`)."
        )
    loop_section.append("")
    loop_section.append(f"**Notes:** {info['notes']}")

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

    integrator_duel_section: List[str] = []
    if phase == "studio":
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
        python run_phase.py finalize --phase {phase} --run-id {meta['run_id']} --status completed --verdict <APPROVED|REJECTED|N/A>
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
                + roles_section
                + loop_section
                + role_menu_section
                + integrator_duel_section
                + summary_section
            )
        ).strip()
        + "\n"
    )


def prepare_run(args: argparse.Namespace) -> str:
    phase = args.phase.lower()
    if phase not in PHASE_DETAILS:
        raise ValueError(f"Unsupported phase '{phase}'.")
    text = args.text.strip()
    if not text:
        raise ValueError("Input text cannot be empty.")

    skip_cleanup = getattr(args, "skip_cleanup", False) or _env_flag(CLEANUP_SKIP_ENV)
    cleanup_dry = getattr(args, "cleanup_dry_run", False) or _env_flag(CLEANUP_DRY_ENV)
    if not skip_cleanup:
        _maybe_run_cleanup(dry_run=cleanup_dry)

    now = utc_now()
    timestamp_slug = now.strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{phase}_{timestamp_slug}"
    run_dir = get_output_root() / phase / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    run_dir_abs = run_dir.resolve()

    studio_role_meta: Dict | None = None
    studio_role_details: List[RoleDetails] | None = None
    if phase == "studio":
        studio_root = get_studio_root()
        manifest = load_manifest(studio_root)
        try:
            pack_name = args.role_pack or default_role_pack_name(manifest)
            pack_data = load_role_pack(studio_root, pack_name)
            overrides = list(args.roles or [])
            invited_roles = resolve_role_list(manifest, pack_data, overrides)
            if not invited_roles:
                raise RoleConfigError(
                    "Studio role selection resolved to zero roles. Adjust the pack or overrides."
                )
            studio_role_details = build_role_details(manifest, invited_roles)
            studio_role_meta = {
                "pack": pack_name,
                "overrides": overrides,
                "invited": invited_roles,
            }
        except RoleConfigError as exc:
            raise RuntimeError(f"Studio role configuration error: {exc}") from exc

    meta = {
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
    }
    if studio_role_meta:
        meta["studio_roles"] = studio_role_meta

    instructions = build_instruction_doc(meta, run_dir, studio_role_details)
    instructions_path = run_dir / "instructions.md"
    instructions_path.write_text(instructions, encoding="utf-8")
    instructions_abs_path = instructions_path.resolve()

    write_json(run_dir / "run.json", meta)
    rebuild_index()

    print(f"Prepared {run_id} ({phase})")
    print(f"- Run directory: {run_dir_abs}")
    print(f"- Instructions: {instructions_abs_path}")
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

    write_json(meta_path, meta)
    rebuild_index()
    _append_run_log(meta)

    print(f"Finalized {run_id} ({phase}) → {meta['status']}")


def rebuild_index() -> None:
    base_output = get_output_root()
    entries = collect_runs(base_output)
    write_index(entries, base_output / "index.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Studio Cascade run helper.")
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
        nargs="*",
        default=None,
        help="Studio-only: role overrides like +qa or -marketing.",
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

    cleanup_parser = subparsers.add_parser(
        "cleanup", help="Manually enforce cleanup thresholds."
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without removing files.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "prepare":
        prepare_run(args)
    elif args.command == "finalize":
        finalize_run(args)
    elif args.command == "cleanup":
        dry_run = getattr(args, "dry_run", False)
        _maybe_run_cleanup(dry_run=dry_run or _env_flag(CLEANUP_DRY_ENV))
    else:
        parser.error("Unknown command")


if __name__ == "__main__":
    main()
