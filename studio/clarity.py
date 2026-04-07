"""
Per-topic Clarity Score tracking for Studio runs (mandatory, always active).

Topics are derived from DecisionPoint.unblocks fields, normalized to slugs.
Clarity scores control agent question density — low clarity means more
decision points, high clarity means treat prior decisions as constraints.

Pure function library — no side effects except explicit I/O functions
(save_clarity_json, load_clarity_json, etc.).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from decision_points import DecisionPoint


# --- Dataclasses ---


@dataclass
class TopicClarity:
    """Clarity score for a single topic."""

    topic: str              # Normalized slug (e.g., "core_loop_design")
    display_name: str       # Human-readable (e.g., "Core loop design")
    score: float            # 0.0 (unknown) to 1.0 (fully settled)
    answered_count: int     # Number of decisions answered for this topic
    total_count: int        # Total decisions surfaced for this topic
    challenged_count: int   # Times contrarians challenged assumptions
    user_override: float | None = None  # User-supplied override (None = use computed)

    @property
    def effective_score(self) -> float:
        """Return user override if set, otherwise the computed score."""
        return self.user_override if self.user_override is not None else self.score


@dataclass
class ClarityContext:
    """Scoping context for a clarity snapshot."""

    scope_label: str        # "broad" or "narrow"
    scope_description: str  # e.g., "the game" or "the inventory system"


@dataclass
class ClaritySnapshot:
    """Complete clarity state for a run or project."""

    topics: list[TopicClarity]
    context: ClarityContext
    created_iso: str
    run_id: str | None = None

    @property
    def mean_score(self) -> float:
        """Average effective score across all topics. 0.0 if no topics."""
        if not self.topics:
            return 0.0
        return sum(t.effective_score for t in self.topics) / len(self.topics)

    def get_topic(self, slug: str) -> TopicClarity | None:
        """Look up a topic by its normalized slug."""
        for t in self.topics:
            if t.topic == slug:
                return t
        return None


def empty_snapshot(input_text: str, run_id: str, created_iso: str) -> ClaritySnapshot:
    """Create an empty ClaritySnapshot for first-run bootstrap."""
    return ClaritySnapshot(
        topics=[],
        context=detect_context_scope(input_text),
        created_iso=created_iso,
        run_id=run_id,
    )


# --- Pure Functions ---


_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_EM_DASH_RE = re.compile(r"\s*[—–]\s*")

_NARROW_KEYWORDS = frozenset({
    "system", "feature", "screen", "module", "component",
    "flow", "menu", "mechanic", "ui", "inventory", "lobby",
})


def slugify_topic(unblocks: str) -> str:
    """Normalize an unblocks field to a topic slug.

    Takes text before the first em-dash (—) or en-dash (–) delimiter,
    strips punctuation, lowercases, and joins words with underscores.
    Empty or whitespace-only input returns ``"uncategorized"``.

    Examples::

        >>> slugify_topic("Core loop design — fundamentally different gameplay")
        'core_loop_design'
        >>> slugify_topic("")
        'uncategorized'
    """
    if not unblocks or not unblocks.strip():
        return "uncategorized"

    # Take text before first em-dash or en-dash
    before_dash = _EM_DASH_RE.split(unblocks, maxsplit=1)[0].strip()
    if not before_dash:
        return "uncategorized"

    # Strip punctuation, lowercase, collapse whitespace to underscores
    cleaned = _PUNCTUATION_RE.sub("", before_dash).strip().lower()
    slug = _WHITESPACE_RE.sub("_", cleaned)
    return slug or "uncategorized"


def display_name_from_unblocks(unblocks: str) -> str:
    """Extract a human-readable display name from an unblocks field.

    Takes text before the first em-dash (—) or en-dash (–) delimiter,
    stripped of leading/trailing whitespace. Preserves original case.

    Examples::

        >>> display_name_from_unblocks("Core loop design — fundamentally different")
        'Core loop design'
        >>> display_name_from_unblocks("")
        'Uncategorized'
    """
    if not unblocks or not unblocks.strip():
        return "Uncategorized"

    before_dash = _EM_DASH_RE.split(unblocks, maxsplit=1)[0].strip()
    return before_dash or "Uncategorized"


def compute_topic_clarity(
    topic_slug: str, decisions: list[DecisionPoint]
) -> TopicClarity:
    """Compute clarity for a single topic from its decision points.

    Filters *decisions* to those whose ``unblocks`` field maps to
    *topic_slug* via :func:`slugify_topic`.

    Score formula: ``answered / total - 0.1 * challenged``, clamped to
    ``[0.0, 1.0]``.  A decision counts as *challenged* when its
    ``source_file`` starts with ``"contrarian"``.

    Args:
        topic_slug: Normalized topic slug.
        decisions: Full list of decision points (will be filtered).

    Returns:
        TopicClarity with computed fields.
    """
    matching = [
        dp for dp in decisions if slugify_topic(dp.unblocks) == topic_slug
    ]

    total = len(matching)
    if total == 0:
        display = display_name_from_unblocks("")
        return TopicClarity(
            topic=topic_slug,
            display_name=display,
            score=0.0,
            answered_count=0,
            total_count=0,
            challenged_count=0,
        )

    # Derive display name from the first matching decision's unblocks
    display = display_name_from_unblocks(matching[0].unblocks)
    answered = sum(1 for dp in matching if dp.answer is not None)
    challenged = sum(
        1 for dp in matching
        if dp.source_file and dp.source_file.startswith("contrarian")
    )

    raw_score = (answered / total) - (0.1 * challenged)
    score = max(0.0, min(1.0, raw_score))

    return TopicClarity(
        topic=topic_slug,
        display_name=display,
        score=score,
        answered_count=answered,
        total_count=total,
        challenged_count=challenged,
    )


def compute_clarity_snapshot(
    decisions: list[DecisionPoint],
    context: ClarityContext,
    run_id: str | None = None,
    prior_snapshot: ClaritySnapshot | None = None,
) -> ClaritySnapshot:
    """Build a full clarity snapshot from a set of decision points.

    Groups decisions by topic slug (via :func:`slugify_topic` on each
    ``dp.unblocks``), computes per-topic clarity, and carries forward
    ``user_override`` values from *prior_snapshot* where topics match.

    Topics are sorted by effective score ascending (lowest clarity first).

    Args:
        decisions: All decision points for the run.
        context: Scoping context (broad/narrow).
        run_id: Optional run identifier.
        prior_snapshot: Previous snapshot to carry forward user overrides.

    Returns:
        New ClaritySnapshot.
    """
    # Collect unique topic slugs in insertion order
    slug_order: list[str] = []
    seen_slugs: set[str] = set()
    for dp in decisions:
        slug = slugify_topic(dp.unblocks)
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            slug_order.append(slug)

    topics: list[TopicClarity] = []
    for slug in slug_order:
        tc = compute_topic_clarity(slug, decisions)

        # Carry forward user override from prior snapshot
        if prior_snapshot is not None:
            prior_topic = prior_snapshot.get_topic(slug)
            if prior_topic is not None and prior_topic.user_override is not None:
                tc.user_override = prior_topic.user_override

        topics.append(tc)

    # Sort by effective score ascending (lowest clarity first)
    topics.sort(key=lambda t: t.effective_score)

    created_iso = datetime.now(timezone.utc).isoformat()
    return ClaritySnapshot(
        topics=topics,
        context=context,
        created_iso=created_iso,
        run_id=run_id,
    )


def detect_context_scope(input_text: str) -> ClarityContext:
    """Detect whether the input describes a broad or narrow scope.

    Uses keyword heuristics: if the text contains words like "system",
    "feature", "screen", "module", "component", "flow", "menu",
    "mechanic", "UI", "inventory", or "lobby", the scope is narrow.
    Otherwise broad.

    Args:
        input_text: The game/feature description provided by the user.

    Returns:
        ClarityContext with scope_label and scope_description.
    """
    words = set(re.findall(r"\w+", input_text.lower()))
    is_narrow = bool(words & _NARROW_KEYWORDS)

    if is_narrow:
        return ClarityContext(
            scope_label="narrow",
            scope_description=input_text.strip(),
        )
    return ClarityContext(
        scope_label="broad",
        scope_description=input_text.strip(),
    )


def question_density_for_scope(
    scope_name: str, topic_clarity: TopicClarity
) -> str:
    """Determine question density for a topic within a given scope.

    Returns ``"high"``, ``"medium"``, or ``"low"`` based on the scope
    and the topic's effective clarity score.

    Rules:
        - **alignment**: always ``"high"`` unless effective_score >= 0.8
        - **depth**: ``"high"`` if < 0.4, ``"medium"`` if < 0.7, ``"low"`` otherwise
        - **polish**: always ``"low"`` unless effective_score < 0.3

    Args:
        scope_name: Name of the scope (alignment, depth, polish).
        topic_clarity: The topic's clarity data.

    Returns:
        One of ``"high"``, ``"medium"``, ``"low"``.
    """
    score = topic_clarity.effective_score
    scope = scope_name.lower()

    if scope == "alignment":
        return "low" if score >= 0.8 else "high"
    elif scope == "depth":
        if score < 0.4:
            return "high"
        elif score < 0.7:
            return "medium"
        else:
            return "low"
    elif scope == "polish":
        return "high" if score < 0.3 else "low"
    else:
        # Unknown scope — fall back to depth rules
        if score < 0.4:
            return "high"
        elif score < 0.7:
            return "medium"
        return "low"


def format_clarity_summary(snapshot: ClaritySnapshot) -> str:
    """Render a clarity snapshot as a markdown summary.

    Produces a table with Topic, Score, Decisions (N/M answered), and
    Status (Settled / Settling / Needs work).  Appends mean clarity
    and context line.

    Args:
        snapshot: The clarity snapshot to format.

    Returns:
        Markdown string.
    """
    lines: list[str] = [
        "## Clarity Summary",
        "",
        f"**Context:** {snapshot.context.scope_label} — {snapshot.context.scope_description}",
        "",
        "| Topic | Score | Decisions | Status |",
        "|-------|-------|-----------|--------|",
    ]

    for t in snapshot.topics:
        score_str = f"{t.effective_score:.2f}"
        decisions_str = f"{t.answered_count}/{t.total_count} answered"
        if t.effective_score >= 0.7:
            status = "Settled"
        elif t.effective_score >= 0.4:
            status = "Settling"
        else:
            status = "Needs work"
        lines.append(f"| {t.display_name} | {score_str} | {decisions_str} | {status} |")

    lines.append("")
    lines.append(f"**Mean clarity:** {snapshot.mean_score:.2f}")
    lines.append("")

    return "\n".join(lines)


def generate_clarity_instructions(
    snapshot: ClaritySnapshot, scope_name: str
) -> str:
    """Generate markdown instructions for agent prompts based on clarity.

    Lists settled topics (treat as constraints) and unsettled topics
    (surface decision points).  Includes scope and density information.

    Args:
        snapshot: Current clarity snapshot.
        scope_name: Active scope name (alignment, depth, polish).

    Returns:
        Markdown string for inclusion in agent instructions.
    """
    lines: list[str] = [
        "## Clarity-Guided Focus",
        "",
        f"**Scope:** {scope_name}",
        f"**Context:** {snapshot.context.scope_label} — {snapshot.context.scope_description}",
        f"**Mean clarity:** {snapshot.mean_score:.2f}",
        "",
    ]

    settled: list[TopicClarity] = []
    unsettled: list[TopicClarity] = []
    for t in snapshot.topics:
        if t.effective_score >= 0.7:
            settled.append(t)
        else:
            unsettled.append(t)

    if settled:
        lines.append("### Settled Topics (treat as constraints)")
        lines.append("")
        for t in settled:
            density = question_density_for_scope(scope_name, t)
            lines.append(
                f"- **{t.display_name}** — score {t.effective_score:.2f}, "
                f"density: {density}"
            )
        lines.append("")

    if unsettled:
        lines.append("### Unsettled Topics (surface decision points)")
        lines.append("")
        for t in unsettled:
            density = question_density_for_scope(scope_name, t)
            lines.append(
                f"- **{t.display_name}** — score {t.effective_score:.2f}, "
                f"density: {density}"
            )
        lines.append("")

    if not settled and not unsettled:
        lines.append("_No topics tracked yet._")
        lines.append("")

    return "\n".join(lines)


def apply_user_overrides(
    snapshot: ClaritySnapshot, overrides: dict[str, float]
) -> ClaritySnapshot:
    """Return a new snapshot with user overrides applied.

    Does NOT mutate the input snapshot.  Validates that each override
    value is in ``[0.0, 1.0]``.

    Args:
        snapshot: The original snapshot.
        overrides: Mapping of topic slug to override score.

    Returns:
        New ClaritySnapshot with overrides applied.

    Raises:
        ValueError: If any override value is outside ``[0.0, 1.0]``.
    """
    for slug, value in overrides.items():
        if value is not None and not (0.0 <= value <= 1.0):
            raise ValueError(
                f"Override for '{slug}' must be in [0.0, 1.0], got {value}"
            )

    new_topics: list[TopicClarity] = []
    for t in snapshot.topics:
        if t.topic in overrides:
            # Explicit override (including None to reset)
            new_override = overrides[t.topic]
        else:
            new_override = t.user_override
        new_topics.append(TopicClarity(
            topic=t.topic,
            display_name=t.display_name,
            score=t.score,
            answered_count=t.answered_count,
            total_count=t.total_count,
            challenged_count=t.challenged_count,
            user_override=new_override,
        ))

    # Re-sort by effective score ascending
    new_topics.sort(key=lambda t: t.effective_score)

    return ClaritySnapshot(
        topics=new_topics,
        context=snapshot.context,
        created_iso=snapshot.created_iso,
        run_id=snapshot.run_id,
    )


# --- I/O Functions ---


_SCHEMA_VERSION = "1.0"


def _topic_to_dict(t: TopicClarity) -> dict:
    """Serialize a TopicClarity to a JSON-friendly dict."""
    return {
        "topic": t.topic,
        "display_name": t.display_name,
        "score": t.score,
        "answered_count": t.answered_count,
        "total_count": t.total_count,
        "challenged_count": t.challenged_count,
        "user_override": t.user_override,
    }


def _topic_from_dict(d: dict) -> TopicClarity:
    """Deserialize a TopicClarity from a dict."""
    return TopicClarity(
        topic=d["topic"],
        display_name=d["display_name"],
        score=d["score"],
        answered_count=d["answered_count"],
        total_count=d["total_count"],
        challenged_count=d["challenged_count"],
        user_override=d.get("user_override"),
    )


def save_clarity_json(path: Path, snapshot: ClaritySnapshot) -> Path:
    """Write a clarity snapshot to a JSON file.

    Includes ``schema_version`` key set to ``"1.0"``.

    Args:
        path: Destination file path.
        snapshot: The snapshot to persist.

    Returns:
        The path written to.
    """
    data = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": snapshot.run_id,
        "created_iso": snapshot.created_iso,
        "context": {
            "scope_label": snapshot.context.scope_label,
            "scope_description": snapshot.context.scope_description,
        },
        "topics": [_topic_to_dict(t) for t in snapshot.topics],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_clarity_json(path: Path) -> ClaritySnapshot | None:
    """Load a clarity snapshot from a JSON file.

    Returns ``None`` if the file does not exist.

    Args:
        path: Path to clarity.json.

    Returns:
        ClaritySnapshot or None.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    data = json.loads(raw)
    context = ClarityContext(
        scope_label=data["context"]["scope_label"],
        scope_description=data["context"]["scope_description"],
    )
    topics = [_topic_from_dict(d) for d in data.get("topics", [])]

    return ClaritySnapshot(
        topics=topics,
        context=context,
        created_iso=data.get("created_iso", ""),
        run_id=data.get("run_id"),
    )


def load_project_clarity(artifact_root: Path) -> ClaritySnapshot | None:
    """Load project-level clarity from ``{artifact_root}/.studio/clarity.json``.

    Args:
        artifact_root: Root of the project's artifact directory.

    Returns:
        ClaritySnapshot or None if file missing.
    """
    return load_clarity_json(artifact_root / ".studio" / "clarity.json")


def save_project_clarity(
    artifact_root: Path, snapshot: ClaritySnapshot
) -> Path:
    """Save project-level clarity to ``{artifact_root}/.studio/clarity.json``.

    Creates the ``.studio/`` directory if it does not exist.

    Args:
        artifact_root: Root of the project's artifact directory.
        snapshot: The snapshot to persist.

    Returns:
        Path written to.
    """
    return save_clarity_json(
        artifact_root / ".studio" / "clarity.json", snapshot
    )
