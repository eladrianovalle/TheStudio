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
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

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
        "integrator": "Systems Integrator & Ops Lead — merge inspiration + constraints into a pragmatic upgrade plan.",
        "notes": (
            "Studio phase has no verdict loop—run Advocate ➜ Contrarian, then produce the Integrator roadmap. "
            "Still finish with summary + packaging."
        ),
    },
}

INDEX_HEADER = [
    "# Studio Run Index",
    "",
    "| Run ID | Phase | Created (UTC) | Status | Input | Summary |",
    "| --- | --- | --- | --- | --- | --- |",
]


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


def build_instruction_doc(meta: Dict, run_dir: Path) -> str:
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
    base_section.extend(
        [
            f"- **Created:** {meta['created_display']} (UTC)",
            "- **Artifacts:**",
            f"  - Advocate outputs → `{rel_dir}/advocate_<iteration>.md`",
            f"  - Contrarian outputs → `{rel_dir}/contrarian_<iteration>.md`",
        ]
    )
    if phase != "studio":
        base_section.append(f"  - Implementation → `{rel_dir}/implementation.md` (after approval)")
    else:
        base_section.append(f"  - Integrator/Roadmap → `{rel_dir}/integrator.md`")
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

    loop_section = [
        "",
        "## Iteration Loop",
        "",
        "1. Start at iteration 1.",
        "2. Run the Advocate prompt, save to `advocate_<n>.md`.",
        "3. Run the Contrarian prompt using that advocate file, save to `contrarian_<n>.md`.",
    ]
    if phase != "studio":
        loop_section.extend(
            [
                "4. If contrarian verdict is `VERDICT: REJECTED` and you still have iterations left, feed the rejection back into the Advocate and repeat.",
                "5. As soon as a contrarian returns `VERDICT: APPROVED`, move to the Implementer checklist.",
            ]
        )
    else:
        loop_section.extend(
            [
                "4. After the first Advocate/Contrarian pass, operate as the Integrator to merge inspiration + constraints into a roadmap (`integrator.md`).",
            ]
        )
    loop_section.append("")
    loop_section.append(f"**Notes:** {info['notes']}")

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

    return textwrap.dedent("\n".join(base_section + roles_section + loop_section + summary_section)).strip() + "\n"


def prepare_run(args: argparse.Namespace) -> str:
    phase = args.phase.lower()
    if phase not in PHASE_DETAILS:
        raise ValueError(f"Unsupported phase '{phase}'.")
    text = args.text.strip()
    if not text:
        raise ValueError("Input text cannot be empty.")

    now = utc_now()
    timestamp_slug = now.strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{phase}_{timestamp_slug}"
    run_dir = Path("output") / phase / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

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

    instructions = build_instruction_doc(meta, run_dir)
    instructions_path = run_dir / "instructions.md"
    instructions_path.write_text(instructions, encoding="utf-8")

    write_json(run_dir / "run.json", meta)
    rebuild_index()

    print(f"Prepared {run_id} ({phase})")
    print(f"- Run directory: {run_dir}")
    print(f"- Instructions: {instructions_path}")
    return run_id


def finalize_run(args: argparse.Namespace) -> None:
    phase = args.phase.lower()
    run_id = args.run_id
    run_dir = Path("output") / phase / run_id
    meta_path = run_dir / "run.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Could not find metadata for {run_id} at {meta_path}")

    meta = load_json(meta_path)
    meta["status"] = args.status.upper()
    if args.summary:
        meta["summary_path"] = args.summary
    elif not meta.get("summary_path"):
        meta["summary_path"] = (run_dir / "summary.md").as_posix()
    if args.verdict:
        meta["verdict"] = args.verdict.upper()
    if args.iterations_run is not None:
        meta["iterations_run"] = args.iterations_run
    meta["updated_iso"] = utc_now().isoformat(timespec="seconds")

    write_json(meta_path, meta)
    rebuild_index()

    print(f"Finalized {run_id} ({phase}) → {meta['status']}")


def rebuild_index() -> None:
    base_output = Path("output")
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "prepare":
        prepare_run(args)
    elif args.command == "finalize":
        finalize_run(args)
    else:
        parser.error("Unknown command")


if __name__ == "__main__":
    main()
