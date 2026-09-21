"""Pure aggregation and formatting for the cross-run stats dashboard.

Everything here is a pure function: data in, data (or a rendered string) out. No
filesystem, no argparse, no path resolution. The ``run_phase`` CLI handlers do
the reading and writing, then hand the collected records to these functions.
Keeping the number-crunching separate from the I/O makes it trivial to test and
keeps the aggregation logic out of the CLI entrypoint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath
from statistics import median
from typing import Dict, Iterable, List, Optional

# How much a shipped feature changed downstream, in three coarse buckets. Kept
# small on purpose: a bucket someone will actually pick beats a scale nobody fills.
VALID_IMPACT = ("none", "minor", "major")


def parse_frontmatter(text: str) -> Dict[str, str]:
    """The ``key: value`` lines of a markdown document's leading ``---`` block.

    Only the *leading* block counts, so a document discussing a field in its prose —
    a spec explaining what ``status: shipped`` means, say — cannot accidentally declare
    one. Anything in that block that isn't ``key: value`` is skipped, and values come
    back stripped.

    This is the one reader of spec frontmatter. ``tests/test_spec_verification.py``
    calls it, and so does ``run_phase._shipped_spec_records``, which feeds the stats
    dashboard — so the gate that demands these lines and the dashboard that prints them
    can never disagree about what a spec says. It takes a string rather than a path to keep this module free of
    I/O — opening the file stays with the caller.
    """
    block = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    if not block:
        return {}
    fields: Dict[str, str] = {}
    for line in block.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip():
            fields[key.strip()] = value.strip()
    return fields


# A fence opens on a line whose first non-blank characters are three or more backticks, and
# closes on a run at least as long. Tracking the opener's length matters here: this repo writes
# spec templates inside four-backtick fences precisely so an inner three-backtick block does not
# close them early, and a stripper that assumed three would end the block in the wrong place.
_FENCE_LINE = re.compile(r"^\s*(`{3,})")

_BUILD_PLAN_HEADING = "## Build Plan"

# A markdown ATX heading, capturing its hashes so a section can be bounded by its own depth.
# Up to three leading spaces are allowed because three is markdown's own bound: `  ## Build Plan`
# renders as a level-2 heading and a reader sees nothing unusual about it, while four spaces make
# an indented code block — markdown's other way to quote a line, and the one `strip_fenced_blocks`
# cannot see. Anchoring this at column 0 instead put an indented heading outside every net here:
# the exact match misses it, so the spec has no plan, and rule 7 leaves a spec with no plan alone.
_HEADING_LINE = re.compile(r"^ {0,3}(#{1,6})\s")

# How a heading that opens a unit entry starts: an ordinal or a backticked id, either of them
# possibly wrapped in bold markers. Left unanchored here because its two users prefix it
# differently — `_section_from` allows the same leading indentation `_HEADING_LINE` does, and
# rule 7's `_INTENDED_UNIT_HEADING` in `tests/test_spec_verification.py` sits at column 0.
# Shared as one fragment so the bound that decides where a plan ends and the rule that reads
# the units inside it cannot disagree about what a unit heading looks like.
UNIT_HEADING_SHAPE = r"\**(?:\d+\.|`[^`\n]+`)"

# Level 3 exactly, the one depth a unit heading is ever written at. `#{2,}` here let
# `_section_from`'s continuation exception leak past a level-2 plan heading as well as the
# level-3 near miss it was written for: ``## `stats.py` — what changes`` and `## 1. Background`
# both match the shape, so neither ended a `## Build Plan` section and every section after the
# plan read as more plan. The exception is only ever needed when the plan heading itself sits at
# unit depth; at level 2 the units are a level down and the depth bound alone is enough.
_UNIT_HEADING = re.compile(r"^ {0,3}#{3}\s+" + UNIT_HEADING_SHAPE)


def _collapsed(line: str) -> str:
    """A heading line as a reader sees it rendered: casefolded, whitespace runs collapsed."""
    return " ".join(line.split()).casefold()


# A heading that means to be the Build Plan but is not the one the readers match. Compared
# against `_collapsed` output rather than the raw line, because the ways the exact match gets
# missed are not all visible on the page: `## Build plan` and `## BUILD PLAN` are typos, `##
# Build Plan` with two spaces renders identically to the real heading, and `### Build Plan` is
# the right words at the wrong level. Each one is as invisible to every reader as the
# deliberate rename `## Build Plan (revised after review)`, so they belong in the same net.
# The lookahead is what keeps `## Build Planning notes` out — a section about planning is not
# a near miss, it is a different heading.
#
# Level 2 is as shallow as this looks, and level 1 is left out on purpose rather than by
# oversight: a lone `#` is not reliably a heading in these files. A spec's frontmatter is YAML
# that carries its notes on `# ...` comment lines — every spec in `specs/` has several — and
# nothing here strips frontmatter, so `#{1,}` would read one of those as a heading and refuse a
# spec over a line no renderer ever shows. What that costs is a real `# Build Plan` going
# unseen, at the one level a spec's own title already occupies.
_NEAR_MISS_BUILD_PLAN_HEADING = re.compile(r"^#{2,}\s+build plan(?![a-z0-9])")

# The same words with nothing after them, at the levels the net above reads: what
# `indistinguishable_build_plan_headings` reports. Above that bound the level is deliberately
# not part of the test — the difference between that function and the near-miss net is whether
# the author appended something that says the section is not the plan, and `### Build Plan`
# appends nothing. Also compared against `_collapsed` output, so the single space here is every
# run of whitespace in the file.
_UNLABELLED_BUILD_PLAN_HEADING = re.compile(r"^#{2,} build plan$")


def strip_fenced_blocks(text: str) -> str:
    """The document with every fenced code block blanked out, line for line.

    Fenced lines come back as empty strings rather than being deleted, so line numbers still
    line up with the original file — a violation can say where it is and mean it.

    An unclosed fence swallows the rest of the document, which is what a markdown renderer
    does with one too.
    """
    kept = []
    open_fence = ""
    for line in text.splitlines():
        marker = _FENCE_LINE.match(line)
        if open_fence:
            if marker and len(marker.group(1)) >= len(open_fence):
                open_fence = ""
            kept.append("")
        elif marker:
            open_fence = marker.group(1)
            kept.append("")
        else:
            kept.append(line)
    return "\n".join(kept)


def build_plan_section(spec_text: str) -> str | None:
    """The ``## Build Plan`` section of a spec, or ``None`` when the spec has none.

    Fenced code blocks are removed first, then the **last** remaining Build Plan heading
    wins, then the section runs to the next ``## `` heading. The heading has to match
    exactly: last-wins plus a prefix match would hand the reader a section a human labelled
    as *not* the plan — ``## Build Plan (as originally proposed)`` written below the real one
    would win, and the real units would vanish with nothing said.

    Exactness cuts both ways, so it does not stand alone. A spec whose *only* plan heading is
    a near miss has no plan as far as this reader is concerned, and that silence would be as
    total as the one above; ``near_miss_build_plan_headings`` is what lets a caller say so
    instead of reading nothing.

    Both halves of that are load-bearing. A spec that documents the Build Plan format
    contains a *fenced* ``## Build Plan`` heading, and a line-anchored regex cannot see the
    fence, so the phantom heading would win on line order: ``specs/unit-acceptance-criteria.md``
    has one at line 77 and its real plan at line 415, and a first-match slice grabs 283 wrong
    lines and then reports a plan with no units against a spec whose plan is fine.

    One reader, shared, so the rule that polices Build Plans and the code that reads them can
    never disagree about where the Build Plan is.
    """
    lines = strip_fenced_blocks(spec_text).splitlines()
    headings = [
        index for index, line in enumerate(lines) if line.rstrip() == _BUILD_PLAN_HEADING
    ]
    if not headings:
        return None
    return _section_from(lines, headings[-1])


def _section_from(lines: List[str], start: int) -> str:
    """The heading at ``start`` and everything under it, up to the next section at its level.

    Bounded by the heading's own depth rather than by ``## ``, which is the same thing for the
    real heading and not for a near miss one level down: a ``### Build Plan`` section stopping
    only at the next ``## `` runs through every sibling level-3 section after it, so an
    ``### Appendix`` quoting ``### 2. `appendix_example` `` hands that id to whatever read the
    section — and a collision reported against it names a spec whose author cannot fix it.

    A unit heading at that same depth continues the plan instead of ending it, which is what
    stops the depth bound from cutting a ``### Build Plan`` section off before its own first
    unit: the plan heading and the units under it are both level 3 there, so depth alone cannot
    tell ``### 1. `real_unit` `` from ``### Appendix``, and only the second one is a new section.
    That exception is level 3 only. Tested at every depth it defeats the bound it is part of:
    under a level-2 plan heading the units sit a level down, so nothing there needs it, and
    ``## `stats.py` — what changes`` — a section heading that happens to open with a backticked
    filename — would go on reading as more plan, handing its ids to whatever read the section.
    """
    depth = len(_HEADING_LINE.match(lines[start]).group(1))
    section = [lines[start]]
    for line in lines[start + 1:]:
        heading = _HEADING_LINE.match(line)
        if heading and len(heading.group(1)) <= depth and not _UNIT_HEADING.match(line):
            break
        section.append(line)
    return "\n".join(section)


def _near_miss_headings(lines: List[str]) -> List[int]:
    """The indexes of the near-miss Build Plan headings, or nothing when the real one is here."""
    if any(line.rstrip() == _BUILD_PLAN_HEADING for line in lines):
        return []
    return [
        index
        for index, line in enumerate(lines)
        if _HEADING_LINE.match(line)
        and _NEAR_MISS_BUILD_PLAN_HEADING.match(_collapsed(line))
    ]


def near_miss_build_plan_headings(spec_text: str) -> List[str]:
    """The Build Plan headings a spec carries when none of them is *the* heading.

    Empty when ``build_plan_section`` found a real heading, because then a labelled one is
    doing its job: a superseded plan kept under ``## Build Plan (as originally proposed)`` is
    exactly what the exact match exists to skip past. It is only when nothing else is there
    that the near miss matters — an author who renamed the heading, or typed it at the wrong
    level or in the wrong case, has written the plan everyone reads as the plan, and every
    reader here returns nothing for it.

    Fences are stripped first, for the same reason ``build_plan_section`` strips them: a spec
    that quotes the plan format in an example is not carrying that heading.

    Only the trailing whitespace comes off each heading. Stripping the leading whitespace too
    would leave the indented case quoting a heading identical to the one it is being asked for,
    and a complaint that says a spec has no ``## Build Plan`` heading but does have
    ``## Build Plan`` tells its reader nothing about what to change.
    """
    lines = strip_fenced_blocks(spec_text).splitlines()
    return [lines[index].rstrip() for index in _near_miss_headings(lines)]


def indistinguishable_build_plan_headings(spec_text: str) -> List[str]:
    """The headings a spec carries that say ``Build Plan`` and nothing else, bar the real one.

    Reported whether or not the real heading is also present, which is the whole difference
    between this and ``near_miss_build_plan_headings``. The precedence there — a near miss
    matters only when nothing else matches — reads a labelled heading as its author saying it
    is not the plan, and that reading is right for ``## Build Plan (as originally proposed)``.
    A doubled space says nothing of the kind: ``##  Build Plan`` renders character for
    character like the real heading, so a spec carrying both shows its author two identical
    lines while every reader here takes the exact one and drops the other's units. Whichever
    of the two came later, the one that loses is invisible on the page.

    The label is the whole test, so the heading level is not part of it. ``### Build Plan``
    written beside the real one falls through everything else — the near-miss precedence is
    satisfied by the exact heading, and a comparison that counted the hashes would call a
    third ``#`` a difference. It says the same words with nothing appended, so its author has
    said nothing that makes it not the plan, and its units are read by nothing.
    """
    lines = strip_fenced_blocks(spec_text).splitlines()
    return [
        line.rstrip()
        for line in lines
        if line.rstrip() != _BUILD_PLAN_HEADING
        and _HEADING_LINE.match(line)
        and _UNLABELLED_BUILD_PLAN_HEADING.match(_collapsed(line))
    ]


def near_miss_build_plan_section(spec_text: str) -> str | None:
    """The section under a spec's near-miss Build Plan heading, or ``None`` when there is none.

    The plan its author wrote, read the way they meant it to be read. Nothing that *acts* on a
    plan may use this — ``build_plan_section`` is the one reader, and a heading nobody matches
    is the defect ``near_miss_build_plan_headings`` exists to report. It is for the checks that
    have to see ids they will not otherwise gate: a `draft` or `shipped` spec is exempt from
    rule 7, so its renamed heading is never complained about, and without this its planned ids
    are absent from the id-collision map as well — leaving an approved spec free to quietly
    reuse one.
    """
    lines = strip_fenced_blocks(spec_text).splitlines()
    headings = _near_miss_headings(lines)
    if not headings:
        return None
    return _section_from(lines, headings[-1])


# ---------------------------------------------------------------------------
# The completion ledger: what the specs planned, what git says was built
# ---------------------------------------------------------------------------

# How a Build Plan entry opens, read tolerantly: a level-3 heading carrying an ordinal, or a
# bare numbered list item, either of them free to wrap the id in bold markers. Rule 7 in
# `tests/test_spec_verification.py` holds new approved specs to the heading form alone; this
# reader has to read what is already on disk, and across the approved specs in the installs on
# this machine the strict shape finds nothing at all in 23 of 24 of them. Zero units is
# indistinguishable from "nothing is unfinished", which is the silence this ledger exists to end.
#
# The `snake_case` demand is not a style preference. It is what stops the reader handing a
# caller `/forge --spec doc-parity-tests --unit studio/tests/test_doc_parity.py` — a command
# that cannot run. An opener whose backticked token is not an id simply does not match, and the
# entry is skipped. The tail is captured so the title can be read off the same line.
UNIT_OPENER = re.compile(r"^(?:###\s+\d+\.|\d+\.)\s*\**\s*`([a-z][a-z0-9_]{2,})`(.*)$", re.M)

# Where one entry ends and the next thing begins: the next entry opener, or any heading down to
# level 3. Level 4 and deeper are sub-headings *inside* a unit, so a `#### What gets built`
# between the opener and the `Dropped:` line must not cut the entry short — the drop would be
# attributed to nothing and the unit would nag on with no hint why.
_ENTRY_BOUNDARY = re.compile(r"^ {0,3}#{1,3}\s")

# The one way to close a unit without building it: a date and a reason, both required. A bare
# "dropped" is a way to stop the nudge without deciding anything. The separator accepts an em
# dash, a double hyphen or a single one, because a hand-typed hyphen that silently failed to
# match would leave the unit nagging with no hint why.
#
# Shared with rule 7, which imports it, so the shape the suite tells an author to write and the
# shape the ledger reads can never drift apart. If they did, a spec could carry a drop line the
# suite accepts and the ledger cannot see, and the unit would be nagged about forever.
DROPPED_LINE = re.compile(
    r"^\s*-\s+\*\*Dropped:\*\*\s+(\d{4}-\d{2}-\d{2})\s+(?:—|--|-)\s+(\S.+)$", re.M
)

# A commit the implementation loop wrote: `writer: <unit_id>`, `editor: <unit_id>`, or the
# escalation `writer(stuck): <unit_id>`. Matched line by line over subjects *and* bodies, so a
# squash merge that kept the loop's subjects in its body still reads as built — including
# GitHub's default squash body, which is the commonest way a merged unit reaches a log and
# writes each subject as `* writer: <unit_id>`. One optional list bullet is all that buys it;
# the id shape after the colon is what keeps a prose line from reading as a build.
_LOOP_COMMIT = re.compile(
    r"^\s*(?:[*+-]\s+)?(writer|editor)(\(stuck\))?:\s+([a-z][a-z0-9_]{2,})\b", re.M
)

# An id as a spec mentions it in prose. Used for one question only — was this id ever planned
# anywhere? — so it reads every spec at every status, not just the approved ones.
_BACKTICKED_ID = re.compile(r"`([a-z][a-z0-9_]{2,})`")

# What separates an entry's id from its title, and the bold markers a list-form entry wraps the
# pair in. Stripped off so the title reads as the author wrote it.
_TITLE_LEAD = re.compile(r"^\**\s*(?:—|–|--|-)?\s*")


@dataclass(frozen=True)
class PlannedUnit:
    """One unit a spec's Build Plan planned, as written.

    ``dropped_on`` and ``dropped_reason`` are both empty for a live unit and both filled for
    one closed on purpose; a line carrying only one of them is not a drop (see
    :data:`DROPPED_LINE`). There is no ordinal field: document order is dependency order — the
    Build Plan template has said so since it was written — so order is list position, and a
    second place to record it is a second thing that can disagree.

    ``spec_file`` is the spec that planned the unit, and it is the only field that identifies
    that spec: rule 7 forbids a duplicate ``unit_id``, not a duplicate slug, so two approved
    specs can carry the same slug and counting distinct slugs would call them one spec. It has
    no default for that reason — a caller that omitted it would collapse every spec onto one
    empty string, which is the miscount this field exists to prevent, and it would do it
    silently. Missing it is a ``TypeError`` instead.
    """

    slug: str
    unit_id: str
    title: str
    dropped_on: str
    dropped_reason: str
    spec_file: str


@dataclass(frozen=True)
class UnitLedger:
    """Planned units and built ids, reconciled: the four states worth saying out loud.

    A planned unit that is built appears in none of these. That is the whole point — the ledger
    reports what is outstanding, and a finished unit is not.

    ``built_known`` is False when the built set could not be read at all, and then every tuple
    here is empty because nothing could be reconciled — not because nothing is outstanding. A
    reader that cannot tell those two apart prints "every unit is built" in exactly the repos
    the unknown built set was invented for.
    """

    unbuilt: tuple[PlannedUnit, ...]  # planned in an approved spec, not built, not dropped
    escalated: tuple[PlannedUnit, ...]  # a writer(stuck): commit and no writer:/editor: one
    dropped: tuple[PlannedUnit, ...]  # unbuilt and closed on purpose, with a date and a reason
    unplanned: tuple[str, ...]  # built ids no spec mentions anywhere, sorted
    built_known: bool = True  # False when git could not be read: every tuple above is silence


def _entry_title(tail: str) -> str:
    """The one-line outcome after a unit's id, without the separator or the bold wrapper."""
    return _TITLE_LEAD.sub("", tail.strip()).strip().strip("*").strip()


def parse_build_plan(spec_text: str, slug: str, spec_file: str) -> List[PlannedUnit]:
    """Every unit a spec's Build Plan plans, in document order.

    Empty for a spec with no ``## Build Plan`` section, which is the normal state of a document
    that has no units rather than a defect to report.

    An entry runs from its opener to the next opener or the next heading down to level 3,
    whichever comes first. That one boundary is what attributes a ``Dropped:`` line to the unit
    it belongs to, with no indentation arithmetic and no hazard from the nested lists a unit
    body is full of — and it bounds a list-form plan in a consuming repo exactly as it bounds a
    heading-form one here.
    """
    section = build_plan_section(spec_text)
    if section is None:
        return []

    lines = section.splitlines()
    openers = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := UNIT_OPENER.match(line))
    ]

    units: List[PlannedUnit] = []
    for position, (index, match) in enumerate(openers):
        limit = openers[position + 1][0] if position + 1 < len(openers) else len(lines)
        end = limit
        for offset in range(index + 1, limit):
            if _ENTRY_BOUNDARY.match(lines[offset]):
                end = offset
                break
        dropped = DROPPED_LINE.search("\n".join(lines[index + 1:end]))
        units.append(
            PlannedUnit(
                slug=slug,
                unit_id=match.group(1),
                title=_entry_title(match.group(2)),
                dropped_on=dropped.group(1) if dropped else "",
                dropped_reason=dropped.group(2).strip() if dropped else "",
                spec_file=spec_file,
            )
        )
    return units


def built_unit_ids(git_log_text: str) -> tuple[set[str], set[str]]:
    """The unit ids a commit log says were built, and the ones a writer escalated instead.

    Returns ``(built, escalated)``. ``writer(stuck): <id>`` is the commit the implementation
    loop tells a blocked writer to make, and it means the writer stopped on purpose rather than
    fake a finish — counting it as built would delete from the report the one case a fresh
    session most needs to be told about. It gets its own set.

    Built wins. A unit carrying both an escalation and a ``writer:`` or ``editor:`` commit is
    built, because the writer only commits a passing state. Neither set carries any order, so
    that is decided by membership and never by commit time.
    """
    built: set[str] = set()
    escalated: set[str] = set()
    for match in _LOOP_COMMIT.finditer(git_log_text):
        (escalated if match.group(2) else built).add(match.group(3))
    return built, escalated - built


def mentioned_unit_ids(spec_text: str) -> set[str]:
    """Every id-shaped token a spec quotes in backticks, at any status, anywhere in the text.

    This answers a different question from :func:`parse_build_plan` and so it needs a different
    reader. "Which approved spec still owes this unit?" reads Build Plans; "was this id ever
    planned anywhere?" reads the whole document of every spec, because a unit planned under a
    spec that has since shipped is finished work, not undisciplined work. Without it the
    built-but-never-planned count in this repository reads 41 against a truth near 20, and a
    count twice the truth is one people learn to ignore.
    """
    return set(_BACKTICKED_ID.findall(spec_text))


def reconcile_units(
    planned: List[PlannedUnit],
    built: set[str] | None,
    escalated: set[str],
    mentioned_ids: set[str],
) -> UnitLedger:
    """Reconcile planned units against built ids: what is outstanding, in both directions.

    ``planned`` arrives already filtered to approved specs, so the status policy lives with the
    caller that reads the directory rather than being re-decided here. Every planned unit lands
    in exactly one state: dropped, built (reported by nothing), escalated, or unbuilt.

    ``built`` is ``None`` when the built set could not be read at all — no git, no work tree, a
    shallow clone. Nothing is then reported as unbuilt, because with no built set every planned
    unit reads unbuilt and the ledger would nag about all of them. "I cannot see" and "nothing
    was built" are different answers, and silence beats a lie. The ledger says which answer it
    is carrying in ``built_known``, so a caller cannot read that silence as "everything is
    built". ``escalated`` is only ever read alongside a readable ``built``, so it is a set
    either way. Drops do not survive it either: a drop is only a drop on a unit git does not
    say was built, so with no built set there is nothing to say about them either.

    A drop line on a unit git says was built is not a drop — the unit was built, and built work
    is reported by nothing. Only an unbuilt unit can be closed on purpose.
    """
    if built is None:
        return UnitLedger(
            unbuilt=(), escalated=(), dropped=(), unplanned=(), built_known=False
        )

    dropped = tuple(unit for unit in planned if unit.dropped_on and unit.dropped_reason)
    open_units = [unit for unit in planned if not (unit.dropped_on and unit.dropped_reason)]
    return UnitLedger(
        unbuilt=tuple(
            unit for unit in open_units
            if unit.unit_id not in built and unit.unit_id not in escalated
        ),
        escalated=tuple(
            unit for unit in open_units
            if unit.unit_id not in built and unit.unit_id in escalated
        ),
        dropped=tuple(unit for unit in dropped if unit.unit_id not in built),
        unplanned=tuple(sorted(built - set(mentioned_ids))),
    )


def summarize_shipped_specs(records: List[Dict]) -> Dict:
    """Roll up shipped specs into an impact tally and the recent change lines.

    Each record is ``{"slug", "impact", "changed"}``, read from one spec's
    frontmatter by ``run_phase._shipped_spec_records``. An unrecognized or blank
    impact is counted by nothing — the spec-verification gate rejects those at the
    moment a spec claims it shipped, so anything odd reaching here is old data,
    not a case to invent a bucket for.

    Pure: data in, summary dict out.
    """
    impact = {k: 0 for k in VALID_IMPACT}
    recent_changed: List[Dict] = []

    for record in records:
        bucket = record.get("impact")
        if bucket in impact:
            impact[bucket] += 1
        changed = (record.get("changed") or "").strip()
        if changed:
            recent_changed.append({
                "slug": record.get("slug", "?"),
                "changed": changed,
            })

    return {
        "records": len(records),
        "impact": impact,
        "recent_changed": recent_changed[-8:],
    }


def _is_number(value) -> bool:
    """True for a real int/float. Excludes bool: it is an int subclass, but a
    flag is not a count, and treating it as one hides bad data instead of
    dropping it.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric(value) -> float:
    """Return the value if it is a real number, else 0.

    Session records come from disk and may carry nulls or missing fields, so
    every count is read through this guard before it enters a sum.
    """
    return value if _is_number(value) else 0


def _session_health_signals(records: List[Dict]) -> Dict:
    """Compute the three session-health signals over a list of session records.

    Split out from :func:`summarize_session_health` so the same math can run over
    the full history and over each half when we show a recent-vs-earlier trend.
    Each record is a ``session.json`` dict (see docs/SESSION_ANALYTICS_PLAN.md).
    Missing or partial fields are tolerated; an empty list yields all Nones.
    """
    count = len(records)

    # Assumed-P0 rate: blocking questions the session guessed on, over all the
    # blocking questions it surfaced. None when no P0 was ever surfaced.
    p0_surfaced = 0
    p0_assumed = 0
    for record in records:
        decisions = record.get("decisions") or {}
        surfaced = decisions.get("surfaced") or {}
        p0_surfaced += _numeric(surfaced.get("P0"))
        p0_assumed += _numeric(decisions.get("p0_assumed"))
    assumed_p0_rate = (p0_assumed / p0_surfaced) if p0_surfaced else None

    # Convergence: median iterations-to-verdict, and the fraction of sessions
    # that saw at least one rejection along the way.
    iteration_counts: List[float] = []
    sessions_with_rejection = 0
    for record in records:
        convergence = record.get("convergence") or {}
        iterations = convergence.get("iterations")
        if _is_number(iterations):
            iteration_counts.append(iterations)
        if _numeric(convergence.get("rejections")) > 0:
            sessions_with_rejection += 1
    median_iterations = median(iteration_counts) if iteration_counts else None
    rejection_rate = (sessions_with_rejection / count) if count else None

    # Clarity gain: mean of (after - before), only over records that have both.
    clarity_gains: List[float] = []
    for record in records:
        clarity = record.get("clarity") or {}
        before = clarity.get("mean_before")
        after = clarity.get("mean_after")
        if _is_number(before) and _is_number(after):
            clarity_gains.append(after - before)
    clarity_gain = (sum(clarity_gains) / len(clarity_gains)) if clarity_gains else None

    return {
        "records": count,
        "assumed_p0_rate": assumed_p0_rate,
        "convergence": {
            "median_iterations": median_iterations,
            "rejection_rate": rejection_rate,
        },
        "clarity_gain": clarity_gain,
    }


def summarize_session_health(session_records: List[Dict]) -> Dict:
    """Roll up ``session.json`` records into the three health signals over time.

    Each input is a ``session.json`` dict written automatically at finalize (see
    docs/SESSION_ANALYTICS_PLAN.md). These measure a run's *health*: did the
    debate converge, settle its blocking questions, and reduce uncertainty. They
    do not measure the quality of a plan not yet built.

    Records written before the volunteer-fed measurements were retired still
    carry ``cost`` and ``editor`` blocks. Nothing here reads them, so old and new
    records roll up side by side with no migration.

    Returns the all-time figures plus, once there are enough records (>= 6), a
    ``trend`` block that splits the list in half (caller passes them oldest
    first) so a reader can see whether the two most telling signals (assumed-P0
    rate and median iterations) are moving in the right direction. With fewer
    records ``trend`` is None. Never raises: missing fields and an empty list
    yield Nones and zeros.

    Pure: data in, summary dict out.
    """
    records = [r for r in session_records if isinstance(r, dict)]
    summary = _session_health_signals(records)

    # A recent-vs-earlier split only says something once each half has a few
    # sessions in it; below that it is noise, so we withhold it.
    if len(records) >= 6:
        midpoint = len(records) // 2
        summary["trend"] = {
            "earlier": _session_health_signals(records[:midpoint]),
            "recent": _session_health_signals(records[midpoint:]),
        }
    else:
        summary["trend"] = None

    return summary


def _parse_usage_log(text: str) -> Dict:
    """Summarize the prepare usage log (.studio/usage.log) into counts.

    Lines look like: ``ts | prepare | phase | mode | roles=... | scoped=true``.
    """
    by_phase: Dict[str, int] = {}
    by_mode: Dict[str, int] = {}
    scoped = {"true": 0, "false": 0}
    total = 0
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue
        _, _command, phase, mode, _roles, scoped_field = parts[:6]
        total += 1
        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_mode[mode] = by_mode.get(mode, 0) + 1
        val = scoped_field.split("=", 1)[1] if "=" in scoped_field else scoped_field
        if val in scoped:
            scoped[val] += 1
    return {"total": total, "by_phase": by_phase, "by_mode": by_mode, "scoped": scoped}


def aggregate_stats(runs: List[Dict]) -> Dict:
    """Aggregate cross-run signals into a stats summary.

    Pure over a list of enriched run dicts. Each run is a run.json dict that may
    additionally carry ``_decisions`` (list of DecisionPoint). Missing fields are
    tolerated.
    """
    by_phase: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    verdicts = {"APPROVED": 0, "REJECTED": 0, "UNKNOWN": 0}

    dec_priority = {"P0": 0, "P1": 0, "P2": 0}
    dec_total = 0
    dec_answered = 0

    for run in runs:
        phase = run.get("phase", "unknown")
        status = run.get("status", "UNKNOWN")
        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

        verdict = (run.get("verdict") or "").upper()
        if verdict in ("APPROVED", "REJECTED"):
            verdicts[verdict] += 1
        elif verdict:
            verdicts["UNKNOWN"] += 1

        for dp in run.get("_decisions", []):
            dec_total += 1
            pr = getattr(dp, "priority", "P2")
            if pr in dec_priority:
                dec_priority[pr] += 1
            if getattr(dp, "answer", None) is not None:
                dec_answered += 1

    verdict_total = verdicts["APPROVED"] + verdicts["REJECTED"]
    return {
        "total_runs": len(runs),
        "by_phase": by_phase,
        "by_status": by_status,
        "verdicts": verdicts,
        "approval_rate": (verdicts["APPROVED"] / verdict_total) if verdict_total else None,
        "decisions": {
            "total": dec_total,
            "by_priority": dec_priority,
            "answered": dec_answered,
            "answer_rate": (dec_answered / dec_total) if dec_total else None,
        },
    }


def _format_shipped_specs(shipped_specs: Dict) -> List[str]:
    """Render the shipped-features block: what actually landed, and what it changed.

    Read honestly, this block is a Studio-source-repo feature: a consuming repo
    sees the empty state until someone there flips a spec to ``status: shipped``.
    """
    lines = ["", "Shipped features (from specs/):"]
    if shipped_specs["records"] == 0:
        lines.append(
            "  No shipped features recorded yet — a spec gains a line here when "
            "its frontmatter says status: shipped."
        )
        return lines

    lines.append(f"  {shipped_specs['records']} spec(s) at status: shipped")

    impact = shipped_specs["impact"]
    lines.append(
        f"  Impact:  none={impact['none']} minor={impact['minor']} major={impact['major']}"
    )

    if shipped_specs["recent_changed"]:
        lines.append("  Recent changes:")
        for item in reversed(shipped_specs["recent_changed"]):
            changed = item["changed"]
            if len(changed) > 80:
                changed = changed[:77] + "..."
            lines.append(f"    [{item['slug']}] {changed}")
    return lines


def format_count(count: int, noun: str = "unit") -> str:
    """``1 unit`` / ``2 units`` — the plural the sentence around it needs."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _shared_slugs(units: Iterable[PlannedUnit]) -> set[str]:
    """Slugs that more than one spec file carries, among the units about to be printed."""
    files: Dict[str, set[str]] = {}
    for unit in units:
        files.setdefault(unit.slug, set()).add(unit.spec_file)
    return {slug for slug, paths in files.items() if len(paths) > 1}


def _unit_line(unit: PlannedUnit, shared_slugs: set[str]) -> str:
    """One planned unit on one line: which spec planned it, its id, and what it is for.

    The prefix is the slug, which is what someone types at ``/forge`` — except where two
    approved specs share one, and then it is the spec file's *stem*. A count that says
    "2 approved specs" over two identical ``[a-feature]`` prefixes tells the reader nothing
    about which file planned what.

    The stem rather than the whole file name, because the prefix should stay typeable:
    ``/forge --spec`` resolves a bare value as a slug against ``specs/<value>.md``, so
    ``a-feature`` opens the file while ``a-feature.md`` sends it looking for
    ``specs/a-feature.md.md``. Two specs cannot share a stem when one directory holds them
    all, so it separates them as well as the full name would.

    ``PurePath`` here is string work on a path, not a reading of one — this module still
    touches no filesystem.
    """
    title = unit.title if len(unit.title) <= 80 else unit.title[:77] + "..."
    label = unit.slug
    if unit.slug in shared_slugs:
        label = PurePath(unit.spec_file).stem or unit.slug
    return f"    [{label}] {unit.unit_id}" + (f" — {title}" if title else "")


def format_unit_ledger(ledger: UnitLedger) -> List[str]:
    """Render the completion ledger: planned work still owed, and built work no plan proposed.

    Silent states are left out rather than printed as zeroes, and a ledger with nothing in it
    gets one line saying so instead of a block of empty headings — a report that looks the same
    whether or not it has news is one people stop reading.

    A ledger whose built set is unknown gets no block at all. It has not reconciled anything,
    so every line it could print would be a claim it cannot support — and the emptiest of them,
    "nothing unfinished", is exactly the lie the unknown built set exists to prevent.
    """
    if not ledger.built_known:
        return []

    lines = ["", "Planned work (approved specs vs. git):"]

    if not (ledger.unbuilt or ledger.escalated or ledger.dropped or ledger.unplanned):
        lines.append(
            "  Nothing unfinished — every unit an approved spec plans is built or dropped."
        )
        return lines

    shared = _shared_slugs(ledger.unbuilt + ledger.escalated)

    if ledger.unbuilt:
        specs = len({unit.spec_file for unit in ledger.unbuilt})
        lines.append(
            f"  Planned and never built: {format_count(len(ledger.unbuilt))} "
            f"across {format_count(specs, 'approved spec')}"
        )
        lines.extend(_unit_line(unit, shared) for unit in ledger.unbuilt)

    if ledger.escalated:
        lines.append(
            f"  Started and escalated — a writer stopped on purpose: "
            f"{format_count(len(ledger.escalated))}"
        )
        lines.extend(_unit_line(unit, shared) for unit in ledger.escalated)

    if ledger.dropped:
        lines.append(f"  Dropped on purpose: {format_count(len(ledger.dropped))}")

    if ledger.unplanned:
        lines.append(
            f"  Built but never planned: {format_count(len(ledger.unplanned), 'id')} — a rough "
            "figure. Units built before /forge read a spec's plan are counted here too."
        )
    return lines


def _fmt_signal(value: Optional[float], *, pct: bool) -> str:
    """Format one session-health number, or "n/a" when it could not be computed."""
    if value is None:
        return "n/a"
    if pct:
        return f"{value*100:.0f}%"
    return f"{value:g}"


def _format_session_health(health: Dict) -> List[str]:
    """Render the session-health block: three signals auto-measured at finalize.

    Each line labels what the number means in a few words, because these are for
    a human reading the dashboard, not targets for an agent to chase.
    """
    lines = ["", "Session health (auto-measured at finalize):"]
    lines.append(f"  {health['records']} finalized session(s) on record")

    assumed = health["assumed_p0_rate"]
    if assumed is None:
        lines.append("  Assumed-P0 rate: n/a (no blocking questions surfaced)")
    else:
        lines.append(
            f"  Assumed-P0 rate: {assumed*100:.0f}% "
            "(blocking questions guessed instead of asked; want ~0%)"
        )

    convergence = health["convergence"]
    median_iterations = _fmt_signal(convergence["median_iterations"], pct=False)
    rejection_rate = _fmt_signal(convergence["rejection_rate"], pct=True)
    lines.append(
        f"  Convergence: median {median_iterations} iterations, "
        f"{rejection_rate} of sessions hit a rejection (both extremes are smells)"
    )

    gain = health["clarity_gain"]
    if gain is None:
        lines.append("  Clarity gain: n/a (no before/after snapshots)")
    else:
        lines.append(f"  Clarity gain: {gain:+.2f} mean per session (uncertainty reduced; higher is better)")

    trend = health.get("trend")
    if trend:
        earlier = trend["earlier"]
        recent = trend["recent"]
        lines.append(f"  Trend (recent {recent['records']} vs earlier {earlier['records']}):")
        lines.append(
            "    Assumed-P0 rate: "
            f"{_fmt_signal(earlier['assumed_p0_rate'], pct=True)} -> "
            f"{_fmt_signal(recent['assumed_p0_rate'], pct=True)}"
        )
        lines.append(
            "    Median iterations: "
            f"{_fmt_signal(earlier['convergence']['median_iterations'], pct=False)} -> "
            f"{_fmt_signal(recent['convergence']['median_iterations'], pct=False)}"
        )
    return lines


def format_stats(
    agg: Dict,
    usage: Optional[Dict] = None,
    clarity_note: Optional[str] = None,
    shipped_specs: Optional[Dict] = None,
    session_health: Optional[Dict] = None,
    unit_ledger: Optional[UnitLedger] = None,
) -> str:
    """Render an aggregate_stats() result as a terminal dashboard."""
    bar = "=" * 60
    lines: List[str] = [bar, "Studio Cross-Run Stats", bar]

    if agg["total_runs"] == 0:
        lines.append("No local runs found yet. Run a phase first.")
        # A repo can have shipped features before it has finalized runs — the state
        # right after /spec lands somewhere new — so the block renders here too,
        # empty state included: "nothing shipped yet" answers the same question, and
        # a reader who sees the line once knows where a feature would appear.
        if shipped_specs is not None:
            lines.extend(_format_shipped_specs(shipped_specs))
        if unit_ledger is not None:
            lines.extend(format_unit_ledger(unit_ledger))
        lines.append(bar)
        return "\n".join(lines)

    lines.append(f"Total runs: {agg['total_runs']}")
    lines.append("  By phase:  " + ", ".join(f"{k}={v}" for k, v in sorted(agg["by_phase"].items())))
    lines.append("  By status: " + ", ".join(f"{k}={v}" for k, v in sorted(agg["by_status"].items())))

    v = agg["verdicts"]
    lines.append("")
    lines.append("Verdicts (agent):")
    lines.append(f"  APPROVED={v['APPROVED']}  REJECTED={v['REJECTED']}  UNKNOWN={v['UNKNOWN']}")
    if agg["approval_rate"] is not None:
        lines.append(f"  Approval rate: {agg['approval_rate']*100:.0f}% (of decided runs)")

    if shipped_specs is not None:
        lines.extend(_format_shipped_specs(shipped_specs))

    if unit_ledger is not None:
        lines.extend(format_unit_ledger(unit_ledger))

    d = agg["decisions"]
    lines.append("")
    lines.append("Decision points:")
    if d["total"]:
        bp = d["by_priority"]
        lines.append(f"  {d['total']} total — P0={bp['P0']} P1={bp['P1']} P2={bp['P2']}")
        if d["answer_rate"] is not None:
            lines.append(f"  Answered: {d['answered']}/{d['total']} ({d['answer_rate']*100:.0f}%)")
    else:
        lines.append("  None recorded.")

    if session_health and session_health.get("records"):
        lines.extend(_format_session_health(session_health))

    if usage and usage["total"]:
        lines.append("")
        lines.append("Usage (prepare log):")
        lines.append(f"  {usage['total']} prepares — " + ", ".join(f"{k}={v}" for k, v in sorted(usage["by_phase"].items())))
        lines.append("  Modes: " + ", ".join(f"{k}={v}" for k, v in sorted(usage["by_mode"].items())))
        lines.append(f"  Scoped: {usage['scoped'].get('true', 0)} / Flat: {usage['scoped'].get('false', 0)}")

    if clarity_note:
        lines.append("")
        lines.append(f"Clarity: {clarity_note}")

    lines.append(bar)
    return "\n".join(lines)
