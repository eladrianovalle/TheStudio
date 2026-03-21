"""
Decision point parsing and formatting for Studio runs.

Agents flag inline decision points in their output using markdown blockquotes
with a distinctive header pattern. The format is readable by humans, AI agents,
and any assistant that handles standard markdown.

Example decision point in agent output::

    > **DECISION [P0]:** Should the mechanic be real-time or turn-based?
    > **Unblocks:** Core loop design — fundamentally different gameplay
    > **Options:** (a) Real-time (b) Turn-based

Pure function library — no side effects except extract_decisions_from_run
which reads files from a run directory.
"""
from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}

# Regex to count DECISION lines (used by validator for quick counting).
# Accepts both `**DECISION [P0]:**` and `**DECISION [P0]: ...**`
DECISION_LINE_RE = re.compile(
    r"^>\s*\*\*DECISION\s*\[P[012]\]:", re.MULTILINE | re.IGNORECASE
)

# Regex to capture a decision point blockquote.
# Matches lines starting with "> " where the first line has **DECISION [P0-2]:
# Handles two variants agents produce:
#   > **DECISION [P0]:** question text here     (canonical — colon outside bold)
#   > **DECISION [P0]: question text here**     (natural — question inside bold)
# and continues as long as lines start with "> ".
_BLOCK_RE = re.compile(
    r"^> \*\*DECISION \[(P[012])\]:\*\*\s*(.+)\n"
    r"((?:> .+\n?)*)",
    re.MULTILINE | re.IGNORECASE,
)
_BLOCK_RE_ALT = re.compile(
    r"^> \*\*DECISION \[(P[012])\]:\s*(.+?)\*\*\s*\n"
    r"((?:> .+\n?)*)",
    re.MULTILINE | re.IGNORECASE,
)

# Field extractors inside blockquote body lines (after stripping "> " prefix).
_UNBLOCKS_RE = re.compile(
    r"\*\*Unblocks:\*\*\s*(.+)", re.IGNORECASE
)
_OPTIONS_RE = re.compile(
    r"\*\*Options:\*\*\s*(.+)", re.IGNORECASE
)
_OPTION_ITEM_RE = re.compile(r"\([a-z]\)\s*([^()]+)")


@dataclass
class DecisionPoint:
    """A single decision point extracted from agent output."""

    priority: str  # P0, P1, or P2
    question: str
    unblocks: str
    options: Optional[List[str]] = field(default=None)
    source_file: Optional[str] = field(default=None)
    answer: Optional[str] = field(default=None)
    answered_by: Optional[str] = field(default=None)  # "user" or "assumption"


def parse_decision_points(
    text: str, source_file: str | None = None
) -> list[DecisionPoint]:
    """Parse all decision points from agent output text.

    Handles extra whitespace, missing Options field, and mixed-case tags.
    Returns list sorted by priority (P0 first).
    """
    results: list[DecisionPoint] = []
    seen_spans: set[tuple[int, int]] = set()

    for match in itertools.chain(_BLOCK_RE.finditer(text), _BLOCK_RE_ALT.finditer(text)):
        span = (match.start(), match.end())
        if span in seen_spans:
            continue
        seen_spans.add(span)
        priority = match.group(1).upper()
        question = match.group(2).strip()
        body_lines = match.group(3)

        # Strip "> " prefix from body lines
        body = "\n".join(
            line[2:] if line.startswith("> ") else line
            for line in body_lines.splitlines()
        )

        unblocks_m = _UNBLOCKS_RE.search(body)
        unblocks = unblocks_m.group(1).strip() if unblocks_m else ""

        options: Optional[List[str]] = None
        options_m = _OPTIONS_RE.search(body)
        if options_m:
            raw = options_m.group(1).strip()
            items = _OPTION_ITEM_RE.findall(raw)
            if items:
                options = [item.strip() for item in items]

        results.append(
            DecisionPoint(
                priority=priority,
                question=question,
                unblocks=unblocks,
                options=options,
                source_file=source_file,
            )
        )

    results.sort(key=lambda dp: _PRIORITY_ORDER.get(dp.priority, 99))
    return results


def format_decision_point(dp: DecisionPoint) -> str:
    """Render a DecisionPoint back to the standard blockquote format."""
    lines = [
        f"> **DECISION [{dp.priority}]:** {dp.question}",
        f"> **Unblocks:** {dp.unblocks}",
    ]
    if dp.options:
        opts = " ".join(
            f"({chr(97 + i)}) {opt}" for i, opt in enumerate(dp.options)
        )
        lines.append(f"> **Options:** {opts}")
    return "\n".join(lines)


def format_decisions_log(decisions: list[DecisionPoint]) -> str:
    """Format all decision points as a decisions.md file.

    Groups by priority, includes source file attribution.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections: list[str] = [f"# Decision Points\n\n_Generated {now}_\n"]

    grouped: dict[str, list[DecisionPoint]] = {"P0": [], "P1": [], "P2": []}
    for dp in decisions:
        if dp.priority in grouped:
            grouped[dp.priority].append(dp)

    labels = {"P0": "Blocking", "P1": "Important", "P2": "Nice-to-know"}

    for pri in ("P0", "P1", "P2"):
        items = grouped[pri]
        if not items:
            continue
        sections.append(f"## [{pri}] {labels.get(pri, pri)} ({len(items)})\n")
        for i, dp in enumerate(items, 1):
            source = f" _(from {dp.source_file})_" if dp.source_file else ""
            sections.append(f"{i}. **{dp.question}**{source}")
            sections.append(f"   *Unblocks:* {dp.unblocks}")
            if dp.options:
                opts = " ".join(
                    f"({chr(97 + j)}) {opt}"
                    for j, opt in enumerate(dp.options)
                )
                sections.append(f"   *Options:* {opts}")
            sections.append("")

    return "\n".join(sections)


def extract_decisions_from_run(run_dir: Path) -> list[DecisionPoint]:
    """Scan agent output files in a run directory for decision points.

    Reads advocate_*.md, contrarian_*.md and their studio variants
    (advocate--role--NN.md, advocate--role--S1-NN.md). Annotates each
    DecisionPoint with its source file name.

    Returns combined list sorted by priority (P0 first).
    """
    results: list[DecisionPoint] = []
    run_path = Path(run_dir)

    if not run_path.is_dir():
        return results

    for md_file in sorted(run_path.glob("*.md")):
        name = md_file.name
        # Match simple (advocate_1.md) and studio (advocate--role--01.md) names.
        is_advocate = name.startswith("advocate")
        is_contrarian = name.startswith("contrarian")
        if not (is_advocate or is_contrarian):
            continue

        text = md_file.read_text(encoding="utf-8")
        points = parse_decision_points(text, source_file=name)
        results.extend(points)

    results.sort(key=lambda dp: _PRIORITY_ORDER.get(dp.priority, 99))
    return results


def merge_decisions(
    existing: list[DecisionPoint], extracted: list[DecisionPoint]
) -> list[DecisionPoint]:
    """Merge extracted decisions into existing list, deduplicating by question.

    Existing decisions (typically from decisions.json) take precedence —
    extracted decisions are only added if their question text is new.
    Mutates and returns *existing*.
    """
    existing_qs = {dp.question for dp in existing}
    for dp in extracted:
        if dp.question not in existing_qs:
            existing.append(dp)
            existing_qs.add(dp.question)
    return existing


def format_settled_decisions(decisions: list[DecisionPoint]) -> str:
    """Format answered decision points as a settled-decisions markdown document.

    Only includes decisions that have an answer set. Produces a summary table
    followed by a details section with full metadata.
    """
    answered = [dp for dp in decisions if dp.answer is not None]

    if not answered:
        return "# Settled Decisions\n\n_No decisions have been answered yet._\n"

    lines: list[str] = [
        "# Settled Decisions",
        "",
        "_Treat these as hard constraints. Do not re-litigate._",
        "",
        "| # | Decision | Answer | Priority | Source |",
        "|---|----------|--------|----------|--------|",
    ]

    for i, dp in enumerate(answered, 1):
        source = dp.source_file or ""
        lines.append(f"| {i} | {dp.question} | {dp.answer} | {dp.priority} | {source} |")

    lines.append("")
    lines.append("## Details")
    lines.append("")

    for i, dp in enumerate(answered, 1):
        lines.append(f"### {i}. {dp.question} [{dp.priority}]")
        lines.append(f"- **Answer:** {dp.answer}")
        lines.append(f"- **Answered by:** {dp.answered_by or 'unknown'}")
        lines.append(f"- **Unblocks:** {dp.unblocks}")
        if dp.source_file:
            lines.append(f"- **Source:** {dp.source_file}")
        lines.append("")

    return "\n".join(lines)


def save_decisions_json(run_dir: Path, decisions: list[DecisionPoint]) -> Path:
    """Save decisions to decisions.json in the run directory. Returns the path."""
    data = [
        {
            "priority": dp.priority,
            "question": dp.question,
            "unblocks": dp.unblocks,
            "options": dp.options,
            "source_file": dp.source_file,
            "answer": dp.answer,
            "answered_by": dp.answered_by,
        }
        for dp in decisions
    ]
    path = run_dir / "decisions.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_decisions_json(run_dir: Path) -> list[DecisionPoint]:
    """Load decisions from decisions.json. Returns empty list if file missing."""
    path = run_dir / "decisions.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return [
        DecisionPoint(
            priority=d["priority"],
            question=d["question"],
            unblocks=d["unblocks"],
            options=d.get("options"),
            source_file=d.get("source_file"),
            answer=d.get("answer"),
            answered_by=d.get("answered_by"),
        )
        for d in data
    ]
