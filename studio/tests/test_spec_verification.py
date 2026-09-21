"""The spec-verification convention, enforced (see specs/prompt-feature-verification.md).

Some features are prose — a mandate, a blacklist, a passage giving a stuck writer
permission to stop. No pytest can tell you those broke, so their specs carry a
``## Verification`` section: a pass criterion written before the build, and a results
file beside the spec that has to be filled in before anyone says the feature works.

This file is what makes that claim cost evidence. Flip a spec to ``status: shipped``
while its results file still says ``FILL_ME`` and the suite goes red. So does dropping one
of the pre-written headings, or clearing a placeholder and leaving the skeleton's own
question sitting there with no answer under it.

It is a separate file from ``test_doc_parity.py`` on purpose: that one asserts every
name the code defines is documented, while this one compares two documents to each
other. Same spirit, different contract.

Be straight about the limit: this enforces that a *claim* of verification is backed,
not that verification happened. Typing ``shipped`` is one trigger; the calendar is the
other. Approving a spec that promised evidence means writing down the date you expect to
have it, and once that date passes the suite goes red until you either record what you
found and flip the status, or move the date — so a finished feature can no longer sit at
``approved`` with nobody noticing.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import pytest

from stats import (
    DROPPED_LINE,
    UNIT_HEADING_SHAPE,
    VALID_IMPACT,
    build_plan_section,
    indistinguishable_build_plan_headings,
    near_miss_build_plan_headings,
    near_miss_build_plan_section,
    parse_frontmatter,
    strip_fenced_blocks,
)

# CI runs pytest with `working-directory: studio`, so relative paths are out.
# parents[2] is the repo root — the same idiom test_claude_code.py uses.
REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "specs"
SPEC_COMMAND = REPO_ROOT / ".claude" / "commands" / "spec.md"
FORGE_COMMAND = REPO_ROOT / ".claude" / "commands" / "forge.md"

_STATUSES = {"draft", "approved", "shipped"}
_RESULTS_SUFFIX = "-eval-results.md"
_FILL = "FILL_ME"

# The frontmatter field naming the day the evidence is due. Rule 6 below is the only reader.
_DUE_FIELD = "verification_due"

# The four headings an evidence file is born with, stated once. /spec's skeleton prints these
# and rule 4 below requires them; `test_the_skeleton_prints_exactly_the_required_headings`
# holds the two lists to each other so neither side can drift out from under the other.
_REQUIRED_HEADINGS = (
    "## Pass criterion (written before the build)",
    "## What happened",
    "## What this doesn't prove",
    "## Verdict",
)

# The line the evidence skeleton opens with inside spec.md. Extraction has to be scoped to
# this block: spec.md also carries the *spec* template, whose headings are a different list.
_SKELETON_TITLE = "# <Feature> — Verification Results"

# The two places in spec.md that teach the field rule 6 reads: the frontmatter template a spec
# is born from, and the approval bullet that creates the evidence file. Nothing else writes it.
_TEMPLATE_FIRST_LINE = "feature: <human title>"
_APPROVAL_EVIDENCE_STEP = "**If the spec carries a `## Verification` section**"

# Rule 7's vocabulary — the Build Plan writing standard.
#
# The canonical entry is a level-3 heading carrying an ordinal, a backticked id, an em dash
# and a one-line outcome:
#
#     ### 1. `unit_id` — one-line usable outcome
#
# `_ENTRY_OPENER` is deliberately looser than that, because a rule that could only see the
# shape it wants would be unable to say anything about an entry written the old way — and
# "this entry is in the wrong shape" is the whole point of the rule. It matches either opener
# in use (`### 1.` or a bare `1.`, with or without the bold markers the list form wraps its id
# in) and captures whatever sat in the backticks, canonical or not. The checks below then say
# which part is wrong.
_ENTRY_OPENER = re.compile(r"^(###\s+\d+\.|\d+\.)\s*\**\s*`([^`\n]+)`(.*)$")

# A level-3 heading somebody meant as a unit, whether or not `_ENTRY_OPENER` can read it.
# Not every `###` in a Build Plan opens a unit — `writer-escalation-channel.md` has a
# `### Tests` — so a blanket refusal would be wrong. But a heading that *opens* with an
# ordinal or with a backticked id is a unit, and one that `_ENTRY_OPENER` cannot match (the
# number forgotten, the backticks forgotten) is dropped by every reader in silence. That is the
# same defect this rule exists to close, so the heading gets the sentence instead.
#
# Both alternatives are anchored at the start of the heading text. An unanchored one would
# match a backticked token anywhere in the line, and `### Tests for `stats.py`` — prose that
# happens to quote a filename — would be refused as a malformed unit.
#
# The bold markers sit out in front of the pair rather than on the backtick branch, because a
# heading bolded whole — `### **2. `bold_x`** — outcome` — wraps the ordinal too, and guarding
# only the backticks left that one matching neither this nor `_ENTRY_OPENER`: dropped by every
# reader with the suite green, which is the hole this regex exists to close.
#
# The shape is `stats.py`'s, anchored here at level 3. That module needs the same one to tell a
# unit heading continuing a plan from the sibling heading that ends it, and two copies of it
# could drift into disagreeing about what a unit heading is.
_INTENDED_UNIT_HEADING = re.compile(r"^###\s+" + UNIT_HEADING_SHAPE)

# The id pattern, bound for bound the same as the one the reconciler will use. An id this rule
# accepted but a reader could not see would be silently dropped from the ledger instead of
# rejected here, which is the failure this rule exists to prevent.
_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]{2,}$")

# What has to follow the id on the opener line: an em dash and something after it. Leading
# asterisks are stripped first so a list-form entry's closing `**` does not read as a missing
# title — that entry already has an opener complaint, and one complaint per problem is enough.
_TITLE_AFTER_ID = re.compile(r"^—\s*\S")

# Where an entry ends: the next level-3 heading, whether or not it opens a unit. Level 4 and
# deeper are sub-headings *inside* a unit, so a `#### What gets built` sitting between the
# opener and the criteria must not cut the entry short — the unit would read as having no
# criteria and the complaint would point at the wrong thing entirely.
_THIRD_LEVEL_HEADING = re.compile(r"^###\s")

# One acceptance criterion, at any indentation. Both indentations in this repo's approved specs
# are in use — flush-left under a `**Acceptance criteria:**` line, and two spaces in under a
# `- **Acceptance criteria:**` bullet — and the heading already bounds the entry, so there is
# nothing to gain by demanding one of them.
_CRITERION = re.compile(r"^\s*-\s+\[[ xX]\]\s*\S", re.M)

# The sentence `spec.md` used to teach, which said an id only had to be unique inside its own
# spec. Git commit subjects carry no slug, so two specs planning the same id cannot be told
# apart by anything reading them. Quoting the retired sentence while correcting it is fine;
# stating it as a rule is what `test_no_doc_states_the_retired_uniqueness_rule` refuses.
_RETIRED_UNIQUENESS = "unique within this spec"


class _UnitEntry(NamedTuple):
    """One Build Plan entry, as written rather than as it should have been written."""

    opener: str    # the `### 1.` or `1.` that opened it
    unit_id: str   # whatever sat in the backticks, canonical or not
    tail: str      # the rest of the opener line, where the title should be
    body: str      # everything up to the next entry or the next level-3 heading


def _unit_entries(build_plan: str) -> list[_UnitEntry]:
    """Every unit entry in a Build Plan section, in document order.

    An entry runs from its opener to the next opener or the next level-3 heading, whichever
    comes first. That one boundary is what attaches an acceptance criterion or a `Dropped:`
    line to the unit it belongs to, with no indentation arithmetic and no hazard from the
    nested lists a unit body is full of.
    """
    lines = build_plan.splitlines()
    openers = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := _ENTRY_OPENER.match(line))
    ]
    entries = []
    for position, (index, match) in enumerate(openers):
        limit = openers[position + 1][0] if position + 1 < len(openers) else len(lines)
        end = limit
        for offset in range(index + 1, limit):
            if _THIRD_LEVEL_HEADING.match(lines[offset]):
                end = offset
                break
        entries.append(
            _UnitEntry(
                opener=match.group(1),
                unit_id=match.group(2),
                tail=match.group(3),
                body="\n".join(lines[index + 1:end]),
            )
        )
    return entries


def _unreadable_unit_headings(build_plan: str) -> list[str]:
    """Every level-3 heading in the plan that means to open a unit but cannot be read as one.

    `_unit_entries` can only report what it matched, so a malformed heading leaves no trace at
    all: its id never reaches the ledger, never reaches `_duplicate_unit_ids`, and the moment
    the plan holds one valid entry the "nothing in it opens a unit" complaint stops firing too.
    """
    return [
        line.strip()
        for line in build_plan.splitlines()
        if _INTENDED_UNIT_HEADING.match(line) and not _ENTRY_OPENER.match(line)
    ]


def _build_plan_problems(spec_name: str, spec_text: str) -> list[str]:
    """Rule 7, for one spec: every way its Build Plan departs from the canonical shape.

    Callers gate this on `status: approved`. A spec with no `## Build Plan` section at all is
    left alone — not every document has units, and several older specs have no plan. A spec
    whose only plan heading is a near miss is not that case: it has a plan, and the exact
    match the reader needs is the one thing standing between those units and everything that
    reads them.

    A heading that differs from the real one in case or spacing alone is reported even with the
    real heading present, and before any unit is read: which of two indistinguishable headings
    the reader took decides which units the rest of this function is looking at, so that is the
    thing to fix first, and complaining about the wrong plan's units would point at lines the
    author is not looking at.
    """
    build_plan = build_plan_section(spec_text)
    if build_plan is None:
        return [
            f"specs/{spec_name} has no `## Build Plan` heading, but it does have "
            f"`{heading}`. The heading has to read exactly `## Build Plan` — the readers "
            "match it exactly so a superseded plan kept under a label cannot be mistaken for "
            "the plan in force, which means a renamed heading is not found at all and every "
            "unit under it is invisible. Write the heading exactly as above — same case, one "
            "space, no indentation — and put whatever a suffix said in a line beneath it."
            for heading in near_miss_build_plan_headings(spec_text)
        ]

    twins = indistinguishable_build_plan_headings(spec_text)
    if twins:
        return [
            f"specs/{spec_name} has a second heading that reads as `## Build Plan` but is not "
            f"it: `{heading}`. It says the same words with nothing appended — the difference "
            "is only the case, the spacing or the heading level — so nothing about it says "
            "this section is not the plan, while the readers match the exact heading and every "
            "unit under this one is invisible. Make it the exact heading and fold the two "
            "plans into one, or, if this one is superseded, label it so it says so."
            for heading in twins
        ]

    entries = _unit_entries(build_plan)
    unreadable = _unreadable_unit_headings(build_plan)
    if not entries and not unreadable:
        return [
            f"specs/{spec_name} is marked `status: approved` and has a `## Build Plan` "
            "section, but nothing in it opens a unit. Every unit starts with a heading like "
            "``### 1. `some_unit_id` — one-line usable outcome``; the /spec Build Plan "
            "template shows the whole shape. A plan with no readable units is a plan nothing "
            "can follow up on."
        ]

    problems: list[str] = [
        f"specs/{spec_name} has a Build Plan heading that reads as a unit but cannot be "
        f"parsed as one: `{heading}`. Write it as ``### N. `some_unit_id` — one-line usable "
        "outcome``: the ordinal and the backticks around the id are both required, and a "
        "heading missing either is invisible to everything that reads the plan — the ledger, "
        "`/forge --unit`, and the id-collision check alike."
        for heading in unreadable
    ]
    for entry in entries:
        if not entry.opener.startswith("###"):
            problems.append(
                f"specs/{spec_name} opens the `{entry.unit_id}` unit with "
                f"`{entry.opener}` instead of a heading. Write it as "
                f"``### N. `{entry.unit_id}` — one-line usable outcome``: a heading bounds the "
                "entry at the next `###`, so a nested list inside a unit can never be read as "
                "another unit."
            )
        if not _SNAKE_CASE.match(entry.unit_id):
            problems.append(
                f"specs/{spec_name} plans a unit whose id is `{entry.unit_id}`, which is not "
                "snake_case (lower-case letters, digits and underscores, starting with a "
                "letter, at least three characters). The id is what `/forge --spec <slug> "
                "--unit <id>` takes and what the commit subject records, so an id outside that "
                "shape cannot be matched back to the work."
            )
        if not _TITLE_AFTER_ID.match(entry.tail.lstrip("*").strip()):
            problems.append(
                f"specs/{spec_name}'s `{entry.unit_id}` unit has no `— <one-line outcome>` "
                "after its id. Write an em dash — not a hyphen and not an en dash — and then "
                "what someone can do once this is built, straight after the backticked id: "
                "that sentence is what a session brief prints when it names the unit, and an "
                "id on its own says nothing to whoever reads it next."
            )
        if not _CRITERION.search(entry.body) and not DROPPED_LINE.search(entry.body):
            problems.append(
                f"specs/{spec_name}'s `{entry.unit_id}` unit has no `- [ ]` acceptance "
                "criteria. Either write the checkable statements the /forge editor grades the "
                "built unit against, or, if the unit was dropped on purpose, close it with "
                "`- **Dropped:** YYYY-MM-DD — <reason>` inside the entry. Both the date and "
                "the reason are required; a bare 'dropped' stops the nag without deciding "
                "anything."
            )
    return problems


def _duplicate_unit_ids(specs: list[tuple[str, str]]) -> list[str]:
    """Every `unit_id` two or more of these specs plan, when one of them is approved.

    Takes `(name, text)` pairs rather than reading the directory itself, so the collision it
    reports can be observed on a fabricated pair instead of only asserted against a tree that
    happens to be clean today.

    Ids are collected at every status, because the built set is flat: a shipped spec's id
    silences an approved spec's just as well. The complaint is raised only when at least one
    of the colliding specs is `approved`, which lets a draft reuse an id while the argument is
    still running and catches it at the commit that approves it.

    Every id is collected, snake_case or not. Rule 7 is what refuses an id outside the pattern
    in an approved spec; filtering here as well would mean a non-conforming id in an exempt
    spec — `doc-parity-tests.md` plans `studio/tests/test_doc_parity.py` — was invisible to the
    collision check too, which is a silent drop rather than a second complaint.

    A single spec planning one id twice is caught as well: `/forge --spec <slug> --unit <id>`
    is a direct lookup and cannot tell two entries with the same id apart.

    A plan under a near-miss heading counts too. Rule 7 makes that heading an approved spec's
    problem before anything else, but a `draft` or `shipped` spec is exempt from rule 7 — so
    reading only the exact heading here would leave its ids out of the map entirely and let an
    approved spec quietly reuse one, which is the ledger collision this check exists to stop.
    """
    planned: dict[str, list[str]] = {}
    approved: set[str] = set()
    for name, spec_text in specs:
        if parse_frontmatter(spec_text).get("status") == "approved":
            approved.add(name)
        build_plan = build_plan_section(spec_text) or near_miss_build_plan_section(spec_text)
        if build_plan is None:
            continue
        for entry in _unit_entries(build_plan):
            planned.setdefault(entry.unit_id, []).append(name)

    problems = []
    for unit_id, names in sorted(planned.items()):
        owners = sorted(set(names))
        if not approved.intersection(owners):
            continue
        if len(owners) > 1:
            problems.append(
                f"`{unit_id}` is planned by more than one spec: "
                f"{', '.join(f'specs/{name}' for name in owners)}. A commit subject carries no "
                "slug, so building it once would read as building both. Rename it in whichever "
                "spec has not been built against yet."
            )
        elif len(names) > 1:
            problems.append(
                f"`{unit_id}` is planned {len(names)} times inside specs/{owners[0]}. "
                "`/forge --spec <slug> --unit <id>` is a direct lookup on the id and cannot "
                "tell the two entries apart, so one of them would be built twice and the other "
                "never. Rename one."
            )
    return problems


def _spec_files(specs_dir: Path) -> list[Path]:
    """Every spec in the directory, excluding the results files that sit beside them."""
    return sorted(
        path for path in specs_dir.glob("*.md") if not path.name.endswith(_RESULTS_SUFFIX)
    )


def _approved_specs() -> list[Path]:
    """The specs rule 7 actually gates — the only ones whose Build Plan shape is enforced."""
    return [
        spec
        for spec in _spec_files(SPECS_DIR)
        if parse_frontmatter(spec.read_text(encoding="utf-8")).get("status") == "approved"
    ]


def _as_a_list_item(spec_text: str) -> str:
    """The spec with its first unit heading rewritten as the numbered-bold list item.

    This is the shape most of this repo's older specs use, and the one rule 7 exists to stop
    a new approved spec from picking up. Used to watch the rule fail on a real spec without
    touching the file on disk.
    """
    lines = spec_text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = re.match(r"^###\s+(\d+)\.\s+(`[^`\n]+`)\s+(—.*?)\s*$", line)
        if match:
            ordinal, backticked_id, title = match.groups()
            lines[index] = f"{ordinal}. **{backticked_id} {title}**\n"
            break
    return "".join(lines)


def _spec_template(command_text: str) -> str:
    """The whole spec skeleton /spec tells an author to write, out of its four-backtick fence.

    The template is fenced, so `build_plan_section` — which strips fences before it looks —
    cannot see anything inside it. Lifting the block out first is what lets the same reader
    check the template that checks the specs written from it.
    """
    opener = "````markdown"
    if opener not in command_text:
        return ""
    inside = command_text.split(opener, 1)[1]
    return inside.split("\n````", 1)[0]


def _has_verification_section(spec_text: str) -> bool:
    """Whether the spec carries a ``## Verification`` section.

    Matched by prefix, not by line equality, so a heading someone widened to
    ``## Verification & Evidence`` is still gated. For a gate, the forgiving reading
    is the correct one.
    """
    return any(line.startswith("## Verification") for line in spec_text.splitlines())


def _parse_due(raw_value: str) -> date | None:
    """The date a ``verification_due`` value names, or ``None`` if there isn't a readable one.

    The frontmatter template writes trailing comments after a value — ``status: draft
    # draft → approved → shipped`` — and the reader strips whitespace but not comments, so
    this can arrive as ``2026-09-30   # 30 days from approval``. Everything from the first
    ``#`` on is a note to the reader, not part of the date.

    Malformed reads the same as missing on purpose: rule 6a says so, and a date nothing can
    parse holds no deadline no matter how it got that way.
    """
    date_token = raw_value.split("#", 1)[0].strip()
    try:
        return date.fromisoformat(date_token)
    except ValueError:
        return None


def _section_of_first_fill(results_text: str) -> str:
    """The nearest heading above the first ``FILL_ME``, to point the failure somewhere."""
    heading = "(no heading)"
    for line in results_text.splitlines():
        if line.startswith("##"):
            heading = line.strip()
        if _FILL in line:
            return heading
    return heading


def _skeleton_block(command_text: str) -> list[str]:
    """The evidence skeleton /spec prints, lifted out of .claude/commands/spec.md.

    Scoped to the fenced block that opens with the results title and stopping at that
    fence's close, because spec.md also carries the spec template. Lines come back
    stripped: the skeleton sits two spaces indented inside a bullet, and that same
    normalization is what makes them comparable to an evidence file's own lines.
    """
    lines = [line.strip() for line in command_text.splitlines()]
    if _SKELETON_TITLE not in lines:
        return []
    block: list[str] = []
    for line in lines[lines.index(_SKELETON_TITLE):]:
        if line.startswith("```"):
            break
        block.append(line)
    return block


def _printed_lines(skeleton_lines: list[str]) -> frozenset[str]:
    """Every non-blank, non-heading line /spec's evidence skeleton prints under a heading.

    These are the lines an evidence file is born with — the questions, the guidance, the empty
    table, the placeholders. Not one of them is somebody's finding. Takes the block
    ``_skeleton_block`` already found, so the fence scoping happens in exactly one place.
    """
    printed: set[str] = set()
    in_section = False
    for line in skeleton_lines:
        if line.startswith("#"):
            # The title, and the preamble under it, sit outside every section.
            in_section = line.startswith("## ")
            continue
        if in_section and line:
            printed.add(line)
    return frozenset(printed)


def _preamble_rules(skeleton_lines: list[str]) -> str:
    """The paragraph stating the rules, from the top matter above the first section.

    Everything above the first `## ` is preamble; its last paragraph is the one that tells
    the reader what filling this file in requires. Taken structurally rather than by its
    opening words, so a reword still lands in the same place.
    """
    preamble: list[str] = []
    for line in skeleton_lines[1:]:
        if line.startswith("## "):
            break
        preamble.append(line)
    paragraphs = "\n".join(preamble).strip().split("\n\n")
    return paragraphs[-1].strip() if paragraphs else ""


def _section_body(results_text: str, heading: str) -> str | None:
    """Everything under `heading` up to the next heading, or None if the heading isn't there."""
    lines = results_text.splitlines()
    stripped = [line.strip() for line in lines]
    if heading not in stripped:
        return None
    body: list[str] = []
    for line in lines[stripped.index(heading) + 1:]:
        if line.strip().startswith("#"):
            break
        body.append(line)
    return "\n".join(body)


def _own_words(body: str, printed: frozenset[str]) -> bool:
    """Whether anything under this heading was written by the reporter.

    A line the skeleton printed is not a report; neither is a blank one. Whatever survives
    that, someone typed on purpose.
    """
    return any(line.strip() and line.strip() not in printed for line in body.splitlines())


def _frontmatter_template(command_text: str) -> list[str]:
    """The frontmatter block /spec tells an author to write, out of .claude/commands/spec.md.

    Scoped from the template's first line to the ``---`` that closes it. The command names
    ``verification_due`` in its approval step as well, and a field explained there but missing
    from the template is a field an author copying the template never writes.
    """
    lines = command_text.splitlines()
    if _TEMPLATE_FIRST_LINE not in lines:
        return []
    block: list[str] = []
    for line in lines[lines.index(_TEMPLATE_FIRST_LINE):]:
        if line.strip() == "---":
            break
        block.append(line)
    return block


def _approval_step(command_text: str) -> str:
    """The approval bullet that creates the evidence file, up to the skeleton it prints."""
    if _APPROVAL_EVIDENCE_STEP not in command_text:
        return ""
    after_marker = command_text.split(_APPROVAL_EVIDENCE_STEP, 1)[1]
    return after_marker.split("```markdown", 1)[0]


_SKELETON_LINES = _skeleton_block(SPEC_COMMAND.read_text(encoding="utf-8"))
_PRINTED_LINES = _printed_lines(_SKELETON_LINES)
_PREAMBLE_RULES = _preamble_rules(_SKELETON_LINES)


def _violations(
    spec_name: str,
    spec_text: str,
    results_name: str,
    results_text: str | None,
) -> list[str]:
    """Every way this spec breaks the convention, in plain sentences.

    ``results_text`` is ``None`` when the results file does not exist. Seven rules, and rules
    2 to 4 and rule 6 stay quiet unless the spec actually has a Verification section — that
    tolerance is what leaves a spec with no prose-shaped behavior alone. Rules 5 and 7 have no
    such tolerance; see their comments.

    Frontmatter comes from ``stats.parse_frontmatter``, the one reader of it.
    """
    problems: list[str] = []
    frontmatter = parse_frontmatter(spec_text)
    status = frontmatter.get("status", "")
    promised_evidence = _has_verification_section(spec_text)

    # Rule 1: known status. Every rule below branches on it, so a typo (`Shipped`,
    # `ship`, `done`) would otherwise switch the rest of this convention off forever
    # while the suite stayed green.
    if status not in _STATUSES:
        problems.append(
            f"specs/{spec_name} has `status: {status or '(missing)'}`, which is not one of "
            f"{', '.join(sorted(_STATUSES))}. An unrecognized status silently switches off "
            "the rest of this convention, so use one of the three."
        )

    # Rule 2: evidence has a home. Existence only — a skeleton full of FILL_ME counts.
    # That is the approved-but-not-built tolerance, and it is the pre-registration this
    # whole convention rests on: the headings go in before the data does.
    if promised_evidence and status in {"approved", "shipped"} and results_text is None:
        problems.append(
            f"specs/{spec_name} has a `## Verification` section and is marked "
            f"`status: {status}`, but {results_name} does not exist. Create it from the "
            "skeleton in /spec's approval step — empty, with the criterion copied over — so "
            "the shape of the answer is committed before the answer is known."
        )

    # Rule 3: a claim costs evidence.
    if promised_evidence and status == "shipped" and results_text is not None:
        remaining = results_text.count(_FILL)
        if remaining:
            problems.append(
                f"specs/{spec_name} is marked `status: shipped`, but {results_name} still has "
                f"{remaining} {_FILL} placeholders — the first under "
                f"'{_section_of_first_fill(results_text)}'. A results file still at {_FILL} is "
                "not evidence. Either fill it in with what you actually observed, or set this "
                "spec back to `status: approved` and stop describing the feature as working."
            )

    # Rule 4: a claim costs the whole shape. Every required heading must still be there, and
    # each must carry at least one line the reporter wrote rather than one the skeleton printed.
    # An independent `if`, not an `elif` after rule 3: this function returns a list precisely so
    # one CI run tells you everything that is wrong. `approved` stays untouched — a hollow
    # skeleton there is the pre-registration the whole convention rests on.
    if promised_evidence and status == "shipped" and results_text is not None:
        for heading in _REQUIRED_HEADINGS:
            body = _section_body(results_text, heading)
            if body is None:
                problems.append(
                    f"specs/{spec_name} is marked `status: shipped`, but {results_name} no longer "
                    f"has '{heading}'. These headings were written before the data existed so they "
                    "could not be dropped once the data turned out inconvenient. Either put the "
                    "section back and answer it, or set this spec back to `status: approved`."
                )
            elif not _own_words(body, _PRINTED_LINES):
                problems.append(
                    f"specs/{spec_name} is marked `status: shipped`, but nothing under '{heading}' "
                    f"in {results_name} was written by you — every line there is one /spec's "
                    "skeleton printed, so the section is still asking its question with no answer "
                    "under it. Either write what you actually found, or set this spec back to "
                    "`status: approved`."
                )

    # Rule 5: a shipped claim costs an outcome. Not gated on `promised_evidence`: every
    # feature that shipped changed something, prompt-shaped or not, and this line is the
    # only record of what. It is also the whole reason `stats` has anything to show.
    if status == "shipped":
        # Already stripped by the reader, so a whitespace-only value arrives here as "".
        impact = frontmatter.get("shipped_impact", "")
        changed = frontmatter.get("shipped_changed", "")
        if not impact or not changed:
            fields = (("shipped_impact", impact), ("shipped_changed", changed))
            missing = " and ".join(name for name, value in fields if not value)
            problems.append(
                f"specs/{spec_name} is marked `status: shipped`, but its frontmatter has no "
                f"{missing}. Shipping is the claim that this feature landed; those two lines "
                "are the only record of what landing bought, and they are what `stats` reads. "
                "Fill them in — impact is one of none, minor, major, and changed is one line "
                "on what actually changed — or set this spec back to `status: approved`."
            )
        elif impact not in VALID_IMPACT:
            problems.append(
                f"specs/{spec_name} has `shipped_impact: {impact}`, which is not one of "
                f"{', '.join(VALID_IMPACT)}. An unrecognized value is counted by nothing and "
                "read by no one, so pick the bucket that fits."
            )

    # Rule 6: the wait for evidence has a deadline. A spec that promised evidence is allowed
    # to sit at `approved` holding a blank results file — that blank file is the whole
    # pre-registration — but not forever. Without a clock, a feature can be built, merged and
    # in daily use while its spec quietly stays `approved` with nothing recorded, because
    # rules 3 and 4 only fire on a spec that *claims* to be done.
    if promised_evidence and status == "approved":
        due = _parse_due(frontmatter.get(_DUE_FIELD, ""))
        # 6a: no readable date means no deadline, and optional means off. Rule 1 exists for
        # the same reason — a missing value must not silently switch the check below off.
        if due is None:
            problems.append(
                f"specs/{spec_name} has a `## Verification` section and is marked "
                f"`status: approved`, but its frontmatter has no readable `{_DUE_FIELD}` "
                "date (write it as YYYY-MM-DD; 30 days out is the convention). Approving a "
                "spec that promised evidence means saying when you expect to have it. With "
                "no date there is no deadline, and this spec can sit here forever holding an "
                "empty results file while the feature is already in daily use."
            )
        # 6b: the deadline passed. Deliberately not gated on FILL_ME still being present —
        # a past-due spec with a filled-in results file is a feature that did the work and
        # forgot to flip its status, which is the same stale-status bug.
        elif date.today() > due:
            problems.append(
                f"specs/{spec_name} is marked `status: approved` with "
                f"`{_DUE_FIELD}: {due.isoformat()}`, and that date has passed. Two honest "
                f"ways out: fill in {results_name} with what you actually observed and flip "
                "this spec to `status: shipped`, or move the date to when you now expect the "
                "evidence. Moving the date is allowed and sometimes correct — the point is "
                "that it becomes a visible edit somebody can question, rather than silence "
                "nobody notices."
            )

    # Rule 7: an approved spec's Build Plan has one shape. Approval is the moment a plan stops
    # being an argument and starts being work somebody is expected to pick up, so it is the
    # right moment to demand a shape something can read. Gated on `approved` alone: extending
    # it to `shipped` would force eleven historical specs to be rewritten and eighteen ids to
    # be invented after the fact, for units whose commits carry no `writer:` subject and could
    # never match anyway.
    if status == "approved":
        problems += _build_plan_problems(spec_name, spec_text)

    return problems


# A deadline comfortably ahead of any run of this suite, so the cases that predate rule 6
# keep proving what they were written to prove instead of tripping over a missing date.
_FUTURE_DUE = (date.today() + timedelta(days=30)).isoformat()


# A Build Plan in the canonical shape, so every `approved` case below keeps proving what its
# name says instead of tripping over rule 7. The rule-7 cases pass their own.
_CANONICAL_BUILD_PLAN = """## Build Plan

One unit.

### 1. `synthetic_unit` — the synthetic thing becomes usable

**Acceptance criteria:**
- [ ] The synthetic thing happens.
"""


def _synthetic_spec(
    status: str,
    *,
    verification: bool,
    heading: str = "## Verification",
    impact: str | None = "minor",
    changed: str | None = "The synthetic feature started doing the synthetic thing.",
    due: str | None = _FUTURE_DUE,
    build_plan: str | None = _CANONICAL_BUILD_PLAN,
) -> str:
    """A minimal spec body for the synthetic cases below.

    `heading` exists so one case can widen it and prove the prefix match is doing real work.

    `impact` and `changed` carry values by default so that every `shipped` case here keeps
    proving what its name says instead of tripping over rule 5. `due` carries a future date
    by default for the same reason, one rule along: without it every `approved` case would
    fail rule 6a. Pass `None` to any of the three to leave that line out of the frontmatter
    entirely — that is how the missing-field cases are built.

    `build_plan` is the same idea for rule 7: a canonical plan by default, a plan of your own
    to test the rule, and `None` for a spec with no Build Plan section at all.
    """
    lines = ["---", "feature: Synthetic", "slug: synthetic", f"status: {status}"]
    if due is not None:
        lines.append(f"{_DUE_FIELD}: {due}")
    if impact is not None:
        lines.append(f"shipped_impact: {impact}")
    if changed is not None:
        lines.append(f"shipped_changed: {changed}")
    lines += ["---", ""]
    lines += ["# Synthetic — Architecture Spec", ""]
    if verification:
        lines += [
            heading,
            "",
            "- **Pass criterion.** This works if and only if something observable happens.",
            "",
        ]
    if build_plan is not None:
        lines += build_plan.splitlines() + [""]
    return "\n".join(lines)


_SKELETON = (
    "# Synthetic — Verification Results\n\n"
    "## Pass criterion (written before the build)\n\n"
    "This works if and only if something observable happens.\n\n"
    "## What happened\n\n"
    "| Condition | What was run | Criterion met |\n"
    "|---|---|---|\n"
    f"| Baseline (feature off) | {_FILL} | {_FILL} |\n"
    f"| With the feature | {_FILL} | {_FILL} |\n\n"
    "## What this doesn't prove\n\n"
    f"{_FILL}\n\n"
    "## Verdict\n\n"
    f"{_FILL}\n"
)

# Pulled out so the fixtures below can swap one section at a time and stay readable.
_FILLED_CRITERION = "This works if and only if something observable happens.\n"
_FILLED_LIMITS = "Three runs is a small sample, and the same author read all six outputs.\n"

_FILLED = (
    "# Synthetic — Verification Results\n\n"
    "## Pass criterion (written before the build)\n\n"
    f"{_FILLED_CRITERION}\n"
    "## What happened\n\n"
    "| Condition | What was run | Criterion met |\n"
    "|---|---|---|\n"
    "| Baseline (feature off) | three runs, feature off | no |\n"
    "| With the feature | three runs, feature on | yes |\n\n"
    "## What this doesn't prove\n\n"
    f"{_FILLED_LIMITS}\n"
    "## Verdict\n\n"
    "Criterion met — the effect held in all three runs.\n"
)

# The skeleton's own guidance under "What this doesn't prove", with the placeholder cleared and
# nothing written in its place. That is the easiest route to a green suite with nothing reported,
# and the one rule 4 exists to close. Taken from the real skeleton rather than retyped, so the
# hollow case below cannot quietly drift into a paraphrase that proves nothing.
_SKELETON_TEXT = "\n".join(_SKELETON_LINES)
_UNANSWERED = "".join(
    f"{line}\n"
    for line in (_section_body(_SKELETON_TEXT, "## What this doesn't prove") or "").splitlines()
    if line.strip() and _FILL not in line
)

# Each of these differs from `_FILLED` in exactly one section, so the case it proves is obvious.
_HOLLOW = _FILLED.replace(_FILLED_LIMITS, _UNANSWERED)
_MISSING_HEADING = _FILLED.replace(f"## What this doesn't prove\n\n{_FILLED_LIMITS}\n", "")
_ANSWER_AS_BLOCKQUOTE = _FILLED.replace(_FILLED_LIMITS, f"> {_FILLED_LIMITS}")
_CRITERION_AS_BLOCKQUOTE = _FILLED.replace(_FILLED_CRITERION, f"> {_FILLED_CRITERION}")


class TestFrontmatterReader:
    """`stats.parse_frontmatter` — the one thing that decides what a spec says.

    Every case in this file leans on it, and each way it can go wrong is silent: a
    reader that comes back empty switches every rule below off while the suite stays
    green. So the edges are pinned here directly rather than only through the rules.
    """

    def test_reads_the_key_value_lines(self):
        fields = parse_frontmatter("---\nslug: thing\nstatus: shipped\n---\n\n# Thing\n")
        assert fields == {"slug": "thing", "status": "shipped"}

    def test_a_document_with_no_frontmatter_reads_as_empty(self):
        assert parse_frontmatter("# Thing\n\nstatus: shipped\n") == {}

    def test_a_block_further_down_the_page_is_not_frontmatter(self):
        """Specs quote each other's headers. Only a block at the very top declares anything."""
        assert parse_frontmatter("# Thing\n\nA header looks like:\n\n---\nstatus: shipped\n---\n") == {}

    def test_only_the_leading_block_counts(self):
        """A spec explaining what `status: shipped` means must not thereby claim it."""
        text = (
            "---\nstatus: approved\n---\n\n"
            "# Thing\n\nSet `status: shipped` once the evidence is in.\n\n"
            "---\nstatus: shipped\n---\n"
        )
        assert parse_frontmatter(text)["status"] == "approved"

    def test_values_are_stripped_and_may_hold_a_colon(self):
        """`shipped_changed` is a line of freetext, so the first colon ends the key and
        every colon after it belongs to the sentence."""
        text = "---\nshipped_changed:   it stopped lying: about being current  \n---\n"
        assert parse_frontmatter(text)["shipped_changed"] == "it stopped lying: about being current"

    def test_lines_that_are_not_key_value_are_skipped(self):
        assert parse_frontmatter("---\nstatus: draft\nnot a field\n\n---\n") == {"status": "draft"}


class TestRealSpecs:
    """The convention, against the specs actually in this repo."""

    def test_specs_dir_is_not_empty(self):
        """If specs/ were renamed, every other check here would pass while guarding nothing."""
        specs = _spec_files(SPECS_DIR)
        assert specs, f"no specs found in {SPECS_DIR} — has the directory moved?"

    def test_every_spec_satisfies_the_convention(self):
        problems: list[str] = []
        for spec in _spec_files(SPECS_DIR):
            results = SPECS_DIR / f"{spec.stem}{_RESULTS_SUFFIX}"
            problems += _violations(
                spec.name,
                spec.read_text(encoding="utf-8"),
                results.name,
                results.read_text(encoding="utf-8") if results.exists() else None,
            )
        assert not problems, "\n\n".join(problems)

    def test_specs_without_a_verification_section_are_left_alone(self):
        """No evidence is demanded where none was promised — even with no results file."""
        for spec in _spec_files(SPECS_DIR):
            text = spec.read_text(encoding="utf-8")
            if _has_verification_section(text):
                continue
            assert _violations(spec.name, text, f"{spec.stem}{_RESULTS_SUFFIX}", None) == [], (
                f"specs/{spec.name} has no `## Verification` section, so the evidence rules "
                "must not fire on it"
            )

    def test_the_skeleton_block_is_findable_and_prints_body_lines(self):
        """Rule 4 leans on finding this block, and both ways of losing it are silent.

        If extraction came back empty, every line in every evidence file would count as the
        reporter's own words and rule 4 would stop firing while the suite stayed green. So
        moving or renaming that fence has to turn the tree red instead.
        """
        assert _SKELETON_LINES, (
            f"{_SKELETON_TITLE!r} is no longer in {SPEC_COMMAND.name} — has the evidence "
            "skeleton moved or been retitled? Rule 4 cannot tell boilerplate from a report "
            "without it, and would pass everything."
        )
        assert _PRINTED_LINES, (
            f"the skeleton in {SPEC_COMMAND.name} was found but prints no lines under any of "
            "its headings, so rule 4 would read every line of an evidence file as a finding."
        )
        assert _UNANSWERED.strip(), (
            "the skeleton prints no guidance under \"What this doesn't prove\", so the "
            "unanswered-section case below has nothing to be unanswered with."
        )

    def test_every_copy_of_the_skeleton_preamble_matches_the_live_one(self):
        """The preamble lives by hand in more than one file, and nothing synced them.

        `.claude/commands/spec.md` is the one the tests read and the one `/spec` prints, so it
        is the source. Every evidence file quotes the same paragraph, and the spec that defines
        the convention transcribes the whole skeleton. Reword the source and those copies go on
        stating a rule that no longer exists, with the suite green — which is how the spec's own
        transcription came to describe the honour system rule 4 replaced with a test.
        """
        assert _PREAMBLE_RULES, (
            f"no rules paragraph found above the first section of the skeleton in "
            f"{SPEC_COMMAND.name}; the copies below cannot be checked against anything."
        )
        assert "status: shipped" in _PREAMBLE_RULES, (
            f"the skeleton's rules paragraph in {SPEC_COMMAND.name} no longer mentions "
            "`status: shipped`, so it has stopped naming when these rules bite. Either the "
            "wording drifted or the preamble's last paragraph is no longer the rules."
        )

        transcribers = [
            path
            for path in sorted(SPECS_DIR.glob("*.md"))
            if _SKELETON_TITLE in path.read_text(encoding="utf-8")
        ]
        for path in transcribers:
            assert _PREAMBLE_RULES in path.read_text(encoding="utf-8"), (
                f"specs/{path.name} transcribes the evidence skeleton but its rules paragraph "
                f"no longer matches {SPEC_COMMAND.name}. Update the copy, or stop copying it."
            )

        for results in sorted(SPECS_DIR.glob(f"*{_RESULTS_SUFFIX}")):
            assert _PREAMBLE_RULES in results.read_text(encoding="utf-8"), (
                f"specs/{results.name} states different rules than the skeleton in "
                f"{SPEC_COMMAND.name} prints. An evidence file that quotes a rule the skeleton "
                "no longer states tells its reporter the wrong thing about what filling it in "
                "requires."
            )

    def test_the_skeleton_prints_exactly_the_required_headings(self):
        """The heading list, agreed both ways — two documents that must match.

        A heading required here but no longer printed means every new evidence file is born
        failing. A heading printed but not required here can be deleted for free at `shipped`.
        """
        printed_headings = [line for line in _SKELETON_LINES if line.startswith("## ")]
        assert printed_headings == list(_REQUIRED_HEADINGS), (
            f"the skeleton in {SPEC_COMMAND.name} prints {printed_headings}, but rule 4 "
            f"requires {list(_REQUIRED_HEADINGS)}. Change both or neither."
        )

    def test_the_frontmatter_template_offers_the_due_date_field(self):
        """Rule 6a and /spec's template, agreed both ways.

        The only writer of `verification_due` is an author following that template. Drop the
        field from it and every prompt-shaped spec written afterwards is born failing rule 6a,
        with nothing on the page to say where the date was supposed to come from.
        """
        template = _frontmatter_template(SPEC_COMMAND.read_text(encoding="utf-8"))
        assert template, (
            f"{_TEMPLATE_FIRST_LINE!r} is no longer in {SPEC_COMMAND.name}, so the frontmatter "
            "template cannot be found — has it moved or been reworded?"
        )
        assert any(line.strip().startswith(f"{_DUE_FIELD}:") for line in template), (
            f"{SPEC_COMMAND.name}'s frontmatter template no longer carries a `{_DUE_FIELD}:` "
            "line, but rule 6a still demands one at `approved`. Put it back, or drop the rule."
        )
        assert "## Verification" in "\n".join(template), (
            f"the template offers `{_DUE_FIELD}` without saying it is required only of a spec "
            "carrying a `## Verification` section, which is how rule 6 is gated. An author "
            "reading it cannot tell whether their spec needs a date at all."
        )

    def test_the_approval_step_sets_the_due_date_where_it_creates_the_evidence_file(self):
        """The deadline gets written at the one moment rule 6 starts watching: approval.

        Approval is already where the blank evidence file is created, and the date is what
        bounds how long that file may stay blank. Said anywhere else it is guidance sitting
        beside the step rather than part of it — and the step is what an agent follows.
        """
        step = _approval_step(SPEC_COMMAND.read_text(encoding="utf-8"))
        assert step, (
            f"{SPEC_COMMAND.name} no longer has the approval bullet that creates the evidence "
            f"file ({_APPROVAL_EVIDENCE_STEP!r}), so there is nowhere for the deadline to be set."
        )
        assert _DUE_FIELD in step, (
            f"the approval step in {SPEC_COMMAND.name} creates the evidence file but never sets "
            f"`{_DUE_FIELD}`, so a spec approved by following it fails rule 6a the moment it "
            "lands."
        )
        assert "30 days" in step, (
            f"the approval step in {SPEC_COMMAND.name} no longer says how far out the date goes, "
            "and rule 6a's own failure message tells an author 30 days is the convention."
        )

    def test_unfilled_sections_are_regenerable_from_the_skeleton(self):
        """A section still holding a placeholder has not been reported in, so every other line
        in it came from the template. One that didn't means this file was built from a skeleton
        that has since changed — and rule 4 would read that stale line as somebody's finding.
        """
        for results in sorted(SPECS_DIR.glob(f"*{_RESULTS_SUFFIX}")):
            text = results.read_text(encoding="utf-8")
            for heading in _REQUIRED_HEADINGS:
                body = _section_body(text, heading)
                if body is None or _FILL not in body:
                    continue
                for line in body.splitlines():
                    stray = line.strip()
                    if not stray or stray in _PRINTED_LINES:
                        continue
                    pytest.fail(
                        f"{results.name} still has {_FILL} under '{heading}', so nothing there "
                        f"has been reported yet — but {stray!r} is not a line the skeleton in "
                        f"{SPEC_COMMAND.name} prints. Rebuild that section from the skeleton as "
                        "it stands now, or put the guidance line back the way it prints."
                    )


class TestBuildPlanShape:
    """Rule 7 and the uniqueness check, against the specs actually in this repo.

    `TestRealSpecs.test_every_spec_satisfies_the_convention` already runs rule 7 over the whole
    directory. What is here is the part that directory cannot show: the rule refusing a real
    spec once somebody writes it the other way, and the section reader stepping over a fenced
    example to find the plan underneath.
    """

    def test_there_are_approved_specs_to_check(self):
        """Rule 7 is gated on `approved`. With none in the tree the cases below would pass
        while checking nothing, so say so out loud rather than go quietly green."""
        assert _approved_specs(), (
            f"no `status: approved` spec found in {SPECS_DIR}. Rule 7 only fires on those, so "
            "every case below would be vacuous."
        )

    def test_rewriting_one_entry_as_a_list_item_turns_the_suite_red(self):
        """The rule, observed failing on a real spec instead of only on a fabricated one.

        Nothing on disk is touched — the rewrite happens in the string, which is exactly what
        `test_every_spec_satisfies_the_convention` reads.
        """
        spec = _approved_specs()[0]
        original = spec.read_text(encoding="utf-8")
        assert _violations(spec.name, original, "unused.md", None) == []

        rewritten = _as_a_list_item(original)
        assert rewritten != original, (
            f"specs/{spec.name} has no `### N. `id` — title` entry to rewrite, so this case "
            "cannot show the rule firing."
        )
        problems = _violations(spec.name, rewritten, "unused.md", None)
        assert problems, f"rewriting an entry of specs/{spec.name} as a list item was accepted"
        assert all(f"specs/{spec.name}" in problem for problem in problems)
        assert any("instead of a heading" in problem for problem in problems)

    def test_a_fenced_build_plan_does_not_hide_the_real_one(self):
        """`specs/unit-acceptance-criteria.md` carries two `## Build Plan` lines — one inside a
        fenced template near the top of the file, the real one some 340 lines below it (77 and
        415 as this was written). A first-match slice takes the fenced one and then reports a
        plan with no units against a spec whose plan is fine.
        """
        spec = SPECS_DIR / "unit-acceptance-criteria.md"
        raw = spec.read_text(encoding="utf-8")
        headings = [line for line in raw.splitlines() if line.startswith("## Build Plan")]
        assert len(headings) == 2, (
            f"{spec.name} no longer has both a fenced and a real `## Build Plan` heading, so it "
            "has stopped being the case this reader was written for. Point this at another "
            "spec that has one, or drop it."
        )
        assert len(strip_fenced_blocks(raw).splitlines()) == len(raw.splitlines()), (
            "stripping fences changed the line count, so a violation's line numbers would no "
            "longer match the file"
        )

        build_plan = build_plan_section(raw)
        assert build_plan is not None
        planned = [entry.unit_id for entry in _unit_entries(build_plan)]
        assert planned == ["loop_grades_criteria", "criteria_contract"], planned
        assert "<unit_id>" not in build_plan, (
            "the section reader landed on the fenced template rather than the real plan"
        )

    def test_no_two_specs_plan_the_same_unit_id(self):
        problems = _duplicate_unit_ids(
            [(spec.name, spec.read_text(encoding="utf-8")) for spec in _spec_files(SPECS_DIR)]
        )
        assert not problems, "\n\n".join(problems)

    def test_two_specs_planning_the_same_id_is_caught(self):
        """The collision, observed. Run only against a directory that happens to be clean, the
        test above would pass with the comparison inverted."""
        shared = _synthetic_spec("approved", verification=False)
        problems = _duplicate_unit_ids([("one.md", shared), ("two.md", shared)])
        assert len(problems) == 1
        assert "`synthetic_unit`" in problems[0]
        assert "specs/one.md" in problems[0] and "specs/two.md" in problems[0]

    def test_one_spec_planning_the_same_id_twice_is_caught(self):
        """`/forge --spec x --unit dupe` is a direct lookup on the id, so two entries sharing
        one inside a single spec are no more distinguishable than two specs sharing one."""
        problems = _duplicate_unit_ids([("one.md", _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] It happens.\n\n"
                "### 2. `synthetic_unit` — it becomes usable again\n\n"
                "- [ ] It happens twice.\n"
            ),
        ))])
        assert len(problems) == 1
        assert "`synthetic_unit` is planned 2 times inside specs/one.md" in problems[0]

    def test_an_id_outside_snake_case_still_collides(self):
        """Rule 7 refuses a non-conforming id in an approved spec. Dropping it from the
        collision check as well would make the same id invisible in the specs rule 7 exempts —
        and `doc-parity-tests.md` already plans a path as an id."""
        odd = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `studio/tests/test_thing.py` — the tests exist\n\n"
                "- [ ] They do.\n"
            ),
        )
        problems = _duplicate_unit_ids([("one.md", odd), ("two.md", odd)])
        assert len(problems) == 1
        assert "`studio/tests/test_thing.py`" in problems[0]

    def test_a_collision_between_drafts_is_left_alone(self):
        """A draft is an argument in progress, and two arguments may reach for the same handle.
        The commit that approves one of them is where it has to be settled."""
        draft = _synthetic_spec("draft", verification=False)
        assert _duplicate_unit_ids([("one.md", draft), ("two.md", draft)]) == []

    def test_a_collision_with_a_shipped_spec_is_caught(self):
        """The built set is flat, so a shipped spec's id silences an approved spec's just as
        well as another approved spec's would."""
        problems = _duplicate_unit_ids([
            ("shipped.md", _synthetic_spec("shipped", verification=False)),
            ("approved.md", _synthetic_spec("approved", verification=False)),
        ])
        assert len(problems) == 1
        assert "`synthetic_unit`" in problems[0]

    def test_the_build_plan_template_teaches_the_canonical_entry(self):
        """The template and the rule, agreed both ways.

        The template is the only thing an author writing a new spec reads. Leave it showing the
        list form and every spec written from it is born failing rule 7, with nothing on the
        page to say what the right shape was.
        """
        template = _spec_template(SPEC_COMMAND.read_text(encoding="utf-8"))
        assert template, (
            f"the spec template block in {SPEC_COMMAND.name} could not be found — has the "
            "four-backtick fence around it moved or changed width?"
        )
        build_plan = build_plan_section(template)
        assert build_plan is not None, (
            f"{SPEC_COMMAND.name}'s template no longer shows a `## Build Plan` section, so an "
            "author following it has nothing to copy."
        )
        entries = _unit_entries(build_plan)
        assert entries, (
            f"{SPEC_COMMAND.name}'s Build Plan template shows no unit entry at all."
        )
        for entry in entries:
            assert entry.opener.startswith("###"), (
                f"{SPEC_COMMAND.name}'s Build Plan template opens a unit with "
                f"`{entry.opener}`, which rule 7 refuses in an approved spec. Change both or "
                "neither."
            )
            assert _TITLE_AFTER_ID.match(entry.tail.lstrip("*").strip()), (
                f"{SPEC_COMMAND.name}'s Build Plan template shows no one-line outcome after "
                f"`{entry.unit_id}`, which rule 7 demands."
            )
            # Per entry, not over the whole plan: rule 7 asks each unit for its own criteria,
            # and a plan-wide search lets the template show a second unit with none — a spec
            # copied from it and approved would then fail on a unit the template said was fine.
            assert _CRITERION.search(entry.body), (
                f"{SPEC_COMMAND.name}'s Build Plan template shows no `- [ ]` acceptance "
                f"criteria under `{entry.unit_id}`, which rule 7 demands of every unit."
            )
        assert "unique repo-wide" in build_plan, (
            f"{SPEC_COMMAND.name}'s Build Plan template no longer says a `unit_id` is unique "
            "repo-wide, but `_duplicate_unit_ids` enforces exactly that across the directory."
        )

    def test_forge_points_at_the_template_rather_than_restating_it(self):
        """Two documents describing one format in different words is how they drift apart.

        `forge.md` used to say the Build Plan "is a numbered list of units" — a sentence that
        was already wrong about most of this repo's specs and is now wrong about the template
        as well. It needs to know where to look, not to carry its own copy of the shape.
        """
        forge = FORGE_COMMAND.read_text(encoding="utf-8")
        assert "numbered list of\nunits" not in forge and "numbered list of units" not in forge, (
            f"{FORGE_COMMAND.name} still describes the Build Plan as a numbered list of units. "
            f"Point at the shape {SPEC_COMMAND.name}'s template defines instead of restating a "
            "format in its own words."
        )
        assert SPEC_COMMAND.name in forge, (
            f"{FORGE_COMMAND.name} no longer names {SPEC_COMMAND.name} as where the Build Plan "
            "entry shape is defined, so a reader following it has nowhere to look it up."
        )

    def test_no_doc_states_the_retired_uniqueness_rule(self):
        """A `unit_id` unique only inside its own spec is not unique enough to be read back.

        A document may still *quote* the retired sentence while correcting it — the spec that
        made this change does, three times — so an occurrence in double quotes is allowed and a
        bare one is not.
        """
        docs = sorted(
            [*SPECS_DIR.glob("*.md"), *(REPO_ROOT / ".claude" / "commands").glob("*.md"),
             *(REPO_ROOT / "studio" / "docs").glob("*.md"),
             REPO_ROOT / "README.md", REPO_ROOT / "CLAUDE.md"]
        )
        for doc in docs:
            stated = doc.read_text(encoding="utf-8").replace(
                f'"{_RETIRED_UNIQUENESS}"', ""
            )
            assert _RETIRED_UNIQUENESS not in stated, (
                f"{doc.relative_to(REPO_ROOT)} still states that a `unit_id` is "
                f"{_RETIRED_UNIQUENESS}. Ids have to be unique repo-wide: a commit subject "
                "carries no slug, so two specs planning the same id cannot be told apart."
            )


class TestSyntheticSpecs:
    """Each rule fires, and each rule stays quiet when it should.

    Run only against the real directory, this file would be a green checkmark: it passes
    today and would keep passing with the logic inverted. These cases are where the rules
    are actually observed failing.
    """

    def test_shipped_with_placeholders_fails(self):
        problems = _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _SKELETON,
        )
        # Rule 4 also has plenty to say about an untouched skeleton at `shipped`, so pick out
        # the placeholder complaint rather than asserting it is the only one.
        placeholders = [problem for problem in problems if _FILL in problem]
        assert len(placeholders) == 1
        # Two honest exits, so nobody is cornered into deleting this test to get green.
        assert "fill it in" in placeholders[0]
        assert "`status: approved`" in placeholders[0]

    def test_approved_with_missing_results_file_fails(self):
        problems = _violations(
            "synthetic.md", _synthetic_spec("approved", verification=True),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "does not exist" in problems[0]

    def test_a_widened_verification_heading_is_still_gated(self):
        # The prefix match, observed instead of asserted. Under line equality this heading would
        # switch rules 2 and 3 off silently — a spec could promise evidence, ship none, and pass.
        # The writer named the prefix match load-bearing while nothing tested it; this is the test.
        problems = _violations(
            "synthetic.md",
            _synthetic_spec("approved", verification=True, heading="## Verification & Evidence"),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "does not exist" in problems[0]

    def test_unknown_status_fails(self):
        problems = _violations(
            "synthetic.md", _synthetic_spec("Shipped", verification=True),
            "synthetic-eval-results.md", _SKELETON,
        )
        assert len(problems) == 1
        assert "`status: Shipped`" in problems[0]

    def test_approved_with_placeholders_passes(self):
        """The tolerance: a spec approved but not yet built has a skeleton, not results."""
        assert _violations(
            "synthetic.md", _synthetic_spec("approved", verification=True),
            "synthetic-eval-results.md", _SKELETON,
        ) == []

    @pytest.mark.parametrize("status", sorted(_STATUSES))
    def test_spec_without_a_verification_section_is_ignored(self, status):
        """Not every feature is prompt-shaped; most specs promise no evidence at all."""
        assert _violations(
            "synthetic.md", _synthetic_spec(status, verification=False),
            "synthetic-eval-results.md", None,
        ) == []

    def test_shipped_and_filled_in_passes(self):
        assert _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _FILLED,
        ) == []

    def test_shipped_with_a_required_heading_deleted_fails(self):
        """Deleting a section is the cheapest route past a rule that only counts placeholders."""
        problems = _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _MISSING_HEADING,
        )
        assert len(problems) == 1
        assert "no longer has '## What this doesn't prove'" in problems[0]
        # The same two honest exits rule 3 offers.
        assert "put the section back and answer it" in problems[0]
        assert "`status: approved`" in problems[0]

    def test_shipped_with_an_unanswered_section_fails(self):
        """The easier route: clear the placeholder, leave the skeleton's question, write nothing.

        There is not a single placeholder left in this file, so rule 3 has nothing to say — the
        heading is present and the section still looks full.
        """
        assert _FILL not in _HOLLOW
        problems = _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _HOLLOW,
        )
        assert len(problems) == 1
        assert "nothing under '## What this doesn't prove'" in problems[0]
        assert "was written by you" in problems[0]
        assert "write what you actually found" in problems[0]
        assert "`status: approved`" in problems[0]

    def test_an_answer_written_as_a_blockquote_passes(self):
        """Excluding blockquotes was designed and rejected: reporters are allowed the shape."""
        assert _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _ANSWER_AS_BLOCKQUOTE,
        ) == []

    def test_a_copied_criterion_written_as_a_blockquote_passes(self):
        """The one real evidence file quotes its criterion, so the rule meant to protect it
        must not fail it — the reason the blockquote exclusion was thrown out."""
        assert _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _CRITERION_AS_BLOCKQUOTE,
        ) == []

    @pytest.mark.parametrize(
        "impact, changed, named",
        [
            (None, None, "shipped_impact and shipped_changed"),
            (None, "It got faster.", "shipped_impact"),
            ("minor", None, "shipped_changed"),
        ],
    )
    def test_shipped_without_an_outcome_line_fails(self, impact, changed, named):
        """Rule 5, the one rule that fires on every shipped spec rather than only the
        prompt-shaped ones. The evidence file here is fully filled in, so rules 3 and 4
        have nothing to say and the single complaint has to be this one."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec("shipped", verification=True, impact=impact, changed=changed),
            "synthetic-eval-results.md", _FILLED,
        )
        assert len(problems) == 1
        assert f"has no {named}." in problems[0]
        # The same two honest exits rules 3 and 4 offer.
        assert "Fill them in" in problems[0]
        assert "`status: approved`" in problems[0]

    def test_shipped_with_an_impact_outside_the_vocabulary_fails(self):
        """A bucket nothing counts is worse than a blank: the dashboard would drop it
        silently while the spec looked complete."""
        problems = _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True, impact="huge"),
            "synthetic-eval-results.md", _FILLED,
        )
        assert len(problems) == 1
        assert "`shipped_impact: huge`" in problems[0]
        assert "none, minor, major" in problems[0]

    @pytest.mark.parametrize("status", ["draft", "approved"])
    @pytest.mark.parametrize(
        "impact, changed", [(None, None), ("huge", "It got faster.")],
    )
    def test_the_outcome_lines_are_not_demanded_before_shipped(self, status, impact, changed):
        """You do not know what a feature changed until it has changed something.
        Demanding the answer at `draft` is how you get an invented one."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(status, verification=True, impact=impact, changed=changed),
            "synthetic-eval-results.md", _SKELETON,
        ) == []

    def test_approved_without_a_due_date_fails(self):
        """Rule 6a. Optional would mean off: with no date, 6b can never fire and the spec
        sits at `approved` with an empty results file for as long as nobody looks."""
        problems = _violations(
            "synthetic.md", _synthetic_spec("approved", verification=True, due=None),
            "synthetic-eval-results.md", _SKELETON,
        )
        assert len(problems) == 1
        assert f"no readable `{_DUE_FIELD}`" in problems[0]

    def test_a_due_date_nothing_can_parse_counts_as_missing(self):
        """A date the rule cannot read holds no deadline, however it got that way."""
        problems = _violations(
            "synthetic.md", _synthetic_spec("approved", verification=True, due="next quarter"),
            "synthetic-eval-results.md", _SKELETON,
        )
        assert len(problems) == 1
        assert f"no readable `{_DUE_FIELD}`" in problems[0]

    def test_a_due_date_written_only_in_the_prose_does_not_satisfy_the_rule(self):
        """The field is read from the leading `---` block and nowhere else.

        Specs quote each other's frontmatter, and this convention's own specs quote this
        very field. A spec that merely *mentions* a deadline has not set one.
        """
        spec_naming_the_field_in_its_body = (
            _synthetic_spec("approved", verification=True, due=None)
            + f"\n## Notes\n\nWhen you approve one of these, set `{_DUE_FIELD}: {_FUTURE_DUE}`:\n"
            + f"\n```\n---\nstatus: approved\n{_DUE_FIELD}: {_FUTURE_DUE}\n---\n```\n"
        )
        problems = _violations(
            "synthetic.md", spec_naming_the_field_in_its_body,
            "synthetic-eval-results.md", _SKELETON,
        )
        assert len(problems) == 1
        assert f"no readable `{_DUE_FIELD}`" in problems[0]

    def test_a_due_date_with_a_trailing_comment_still_reads_as_a_date(self):
        """The frontmatter template writes notes after a value, and the reader strips
        whitespace but not comments. A gate that rejected the form the template teaches
        would fire on every spec written the way it was told to write them."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=True, due=f"{_FUTURE_DUE}   # 30 days from approval",
            ),
            "synthetic-eval-results.md", _SKELETON,
        ) == []

    def test_approved_past_its_due_date_fails(self):
        """Rule 6b, the deadline itself."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        problems = _violations(
            "synthetic.md", _synthetic_spec("approved", verification=True, due=yesterday),
            "synthetic-eval-results.md", _SKELETON,
        )
        assert len(problems) == 1
        assert f"`{_DUE_FIELD}: {yesterday}`" in problems[0]
        # Two honest exits, so nobody is cornered into deleting this test to get green.
        assert "fill in synthetic-eval-results.md" in problems[0]
        assert "move the date" in problems[0]

    def test_the_deadline_fires_even_when_the_evidence_is_filled_in(self):
        """No `FILL_ME` clause on 6b, on purpose. A past-due spec whose results file is
        complete is a feature that did the work and forgot to flip its status — the same
        stale-status bug, and one rules 3 and 4 never see, because they need `shipped`."""
        assert _FILL not in _FILLED
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        problems = _violations(
            "synthetic.md", _synthetic_spec("approved", verification=True, due=yesterday),
            "synthetic-eval-results.md", _FILLED,
        )
        assert len(problems) == 1
        assert f"`{_DUE_FIELD}: {yesterday}`" in problems[0]

    def test_a_spec_promising_no_evidence_needs_no_deadline(self):
        """Most specs are not prompt-shaped. Rule 6 keeps rules 2 to 4's tolerance."""
        assert _violations(
            "synthetic.md", _synthetic_spec("approved", verification=False, due=None),
            "synthetic-eval-results.md", None,
        ) == []

    @pytest.mark.parametrize("status", ["draft", "shipped"])
    def test_the_deadline_is_demanded_only_at_approved(self, status):
        """A draft is legitimately open-ended, and a shipped spec is past this rule —
        rules 3 and 4 have it from there."""
        assert _violations(
            "synthetic.md", _synthetic_spec(status, verification=True, due=None),
            "synthetic-eval-results.md", _FILLED,
        ) == []

    def test_approved_with_a_build_plan_holding_no_units_fails(self):
        """Rule 7's first check. A plan nothing can read a unit out of is a plan no session,
        no `/forge` invocation and no reconciliation can follow up on."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan="## Build Plan\n\nWe will build it in roughly three goes.\n",
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "specs/synthetic.md" in problems[0]
        assert "nothing in it opens a unit" in problems[0]

    @pytest.mark.parametrize("heading", [
        "### `ghost_unit` — the number was forgotten",
        "### 2. ghost_unit — the backticks were forgotten",
        "### **2. `ghost_unit`** — the whole heading was bolded",
        "### **`ghost_unit`** — bolded whole, and the number forgotten",
    ])
    def test_approved_with_a_malformed_unit_heading_beside_a_good_one_fails(self, heading):
        """A heading no reader can match is worse than a plan with no units at all.

        The zero-entries complaint only fires when *nothing* matches, so one valid entry is
        enough to silence every malformed sibling: the unit reads as planned by whoever wrote
        it and as nonexistent to the ledger, `/forge --unit` and the collision check. That
        gap is the exact silence rule 7 was added to end.

        The bolded pair is why `_INTENDED_UNIT_HEADING` guards the ordinal and the backticks
        together rather than the backticks alone. A heading bolded whole wraps its ordinal in
        the asterisks too, so `_ENTRY_OPENER` — which only tolerates them *after* the ordinal —
        cannot read it either, and it fell through both patterns into the same silence.
        """
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "### 1. `synthetic_unit` — it becomes usable\n\n"
                    "- [ ] The synthetic thing happens.\n\n"
                    f"{heading}\n\n"
                    "- [ ] The ghost happens.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "specs/synthetic.md" in problems[0]
        assert heading in problems[0]
        assert "cannot be parsed as one" in problems[0]

    def test_a_plan_whose_only_unit_is_malformed_names_the_heading(self):
        """Not the generic "nothing opens a unit" sentence. The author wrote something they
        meant as a unit, and the complaint that helps them is the one quoting it back."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "### `ghost_unit` — the number was forgotten\n\n"
                    "- [ ] The ghost happens.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "cannot be parsed as one" in problems[0]
        assert "nothing in it opens a unit" not in problems[0]

    def test_a_third_level_heading_that_is_not_a_unit_stays_legal(self):
        """`writer-escalation-channel.md` closes its plan with a `### Tests` section. A
        heading carrying neither an ordinal nor a backticked id is prose, and refusing it
        would make the rule unusable on plans that are already fine."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "### 1. `synthetic_unit` — it becomes usable\n\n"
                    "- [ ] The synthetic thing happens.\n\n"
                    "### Tests\n\n"
                    "Run the suite.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        ) == []

    def test_a_third_level_heading_quoting_a_filename_stays_legal(self):
        """The narrower half of the same tolerance. `### Tests for `stats.py`` is prose that
        happens to quote a filename; a pattern that looked for backticks anywhere in the line
        would refuse it as a malformed unit, and a rule that false-reds on a plan written
        properly is a rule someone deletes."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "### 1. `synthetic_unit` — it becomes usable\n\n"
                    "- [ ] The synthetic thing happens.\n\n"
                    "### Tests for `stats.py`\n\n"
                    "Run the suite.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        ) == []

    def test_approved_with_a_unit_written_as_a_list_item_fails(self):
        """The shape most older specs use. It is not wrong markdown; it is a boundary a
        reader has to guess at, which is why the heading replaced it."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "1. **`synthetic_unit` — the synthetic thing becomes usable.** What gets "
                    "built.\n"
                    "   - **Acceptance criteria:**\n"
                    "     - [ ] The synthetic thing happens.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "specs/synthetic.md" in problems[0]
        assert "instead of a heading" in problems[0]

    @pytest.mark.parametrize("unit_id", ["Synthetic_Unit", "synthetic-unit", "ui", "3_units"])
    def test_approved_with_an_id_outside_snake_case_fails(self, unit_id):
        """The id is what `/forge` takes and what the commit subject records. An id the
        reader's own pattern cannot match would be dropped from the ledger in silence — the
        failure this rule is here to turn into a sentence."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    f"## Build Plan\n\n### 1. `{unit_id}` — it becomes usable\n\n"
                    "- [ ] It happens.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert f"`{unit_id}`" in problems[0]
        assert "snake_case" in problems[0]

    def test_approved_with_a_unit_carrying_no_outcome_fails(self):
        """An id on its own is what the session brief would have to print. `— what you can do
        once this is built` is the only part of the entry a reader who has not opened the spec
        can act on."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan="## Build Plan\n\n### 1. `synthetic_unit`\n\n- [ ] It happens.\n",
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "`— <one-line outcome>`" in problems[0]

    @pytest.mark.parametrize("separator", ["-", "–"])
    def test_a_unit_titled_after_the_wrong_dash_is_told_which_dash(self, separator):
        """`DROPPED_LINE` accepts three dashes and this rule accepts one, which is a defensible
        split — a dropped line that silently failed to match would leave the unit nagging with
        no hint, while this one does complain. What it must not do is complain about the wrong
        thing: the outcome is right there, and "has no outcome" sends the author hunting."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    f"## Build Plan\n\n### 1. `synthetic_unit` {separator} it becomes usable\n\n"
                    "- [ ] It happens.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "em dash" in problems[0]

    def test_approved_with_a_unit_holding_no_criteria_fails(self):
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n### 1. `synthetic_unit` — it becomes usable\n\n"
                    "What gets built: the files, the behavior, the tests.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "no `- [ ]` acceptance" in problems[0]
        # Both honest ways out, so nobody is cornered into deleting this rule to get green.
        assert "write the checkable statements" in problems[0]
        assert "**Dropped:**" in problems[0]

    def test_a_unit_dropped_on_purpose_needs_no_criteria(self):
        """The escape. A unit withdrawn with a date and a reason is closed, not unfinished —
        and the line lives next to the plan, in a commit somebody reviews."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n### 1. `synthetic_unit` — it becomes usable\n\n"
                    "- **Dropped:** 2026-09-16 — superseded by `other_unit`.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        ) == []

    @pytest.mark.parametrize(
        "dropped_line, why",
        [
            ("- **Dropped:** superseded by `other_unit`.", "no date"),
            ("- **Dropped:** 2026-09-16", "no reason"),
            ("- **Dropped:** 2026-09-16 —", "an empty reason"),
        ],
    )
    def test_a_dropped_line_missing_a_date_or_a_reason_is_not_a_drop(self, dropped_line, why):
        """Both halves are required. A bare "dropped" is a way to stop the nag without
        deciding anything, which is the one thing this escape must not become."""
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n### 1. `synthetic_unit` — it becomes usable\n\n"
                    f"{dropped_line}\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1, f"a Dropped line with {why} was accepted as a drop"
        assert "no `- [ ]` acceptance" in problems[0]

    @pytest.mark.parametrize(
        "criteria",
        [
            "**Acceptance criteria:**\n- [ ] The synthetic thing happens.",
            "- **Acceptance criteria:**\n  - [ ] The synthetic thing happens.",
        ],
        ids=["flush-left", "indented"],
    )
    def test_both_acceptance_criteria_indentations_pass(self, criteria):
        """Both are in this repo's approved specs today. The heading already bounds the entry,
        so there is nothing to buy by demanding one of them and a migration to pay for it."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    f"## Build Plan\n\n### 1. `synthetic_unit` — it becomes usable\n\n"
                    f"{criteria}\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        ) == []

    def test_a_spec_with_no_build_plan_at_all_is_left_alone(self):
        """Not every document has units, and several older specs have no plan section."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec("approved", verification=False, build_plan=None),
            "synthetic-eval-results.md", None,
        ) == []

    @pytest.mark.parametrize("status", ["draft", "shipped"])
    def test_the_build_plan_shape_is_demanded_only_at_approved(self, status):
        """A draft is still an argument, and a shipped spec is a record of what was built.
        Demanding the shape of either would have forced eleven rewrites and eighteen invented
        ids for units whose commits could never match them."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(
                status, verification=False,
                build_plan="## Build Plan\n\n1. Build it.\n",
            ),
            "synthetic-eval-results.md", None,
        ) == []

    def test_a_fenced_example_before_the_real_plan_is_not_the_plan(self):
        """A spec that documents the Build Plan format carries a fenced one of its own — this
        repo has two such specs. Without fence-stripping the phantom heading wins on line
        order, and the units read out of it are the template's placeholders.
        """
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## How It Works\n\n"
                "Every unit is written like this:\n\n"
                "```markdown\n"
                "## Build Plan\n\n"
                "### 1. `unit_id` — x\n"
                "```\n\n"
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n"
            ),
        )
        build_plan = build_plan_section(spec)
        assert build_plan is not None
        assert [entry.unit_id for entry in _unit_entries(build_plan)] == ["synthetic_unit"]
        assert _violations(
            "synthetic.md", spec, "synthetic-eval-results.md", None,
        ) == []

    def test_a_fenced_example_inside_the_plan_is_not_part_of_it(self):
        """The other half of fence-stripping, and the half the last-heading rule cannot cover.

        A plan that shows an author what an entry looks like fences the example inside the
        Build Plan itself. Left standing, a `## ` heading in that fence cuts the section short
        and the example's placeholder id reads as a unit somebody is waiting on.
        """
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "Write each entry like this:\n\n"
                "```markdown\n"
                "## Anything\n"
                "### 1. `ghost_unit` — x\n"
                "```\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n"
            ),
        )
        build_plan = build_plan_section(spec)
        assert build_plan is not None
        assert [entry.unit_id for entry in _unit_entries(build_plan)] == ["synthetic_unit"]

    def test_a_unit_entry_stops_at_the_next_third_level_heading(self):
        """Not every `###` in a Build Plan opens a unit. Whatever a trailing note carries —
        a checklist, a table, a stray `- [ ]` — belongs to that note and not to the unit
        above it, or a unit with no criteria at all would pass on somebody else's bullets.
        """
        problems = _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "### 1. `synthetic_unit` — it becomes usable\n\n"
                    "What gets built: the files, the behavior, the tests.\n\n"
                    "### Notes on sequencing\n\n"
                    "- [ ] This is a note to ourselves, not a criterion.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        )
        assert len(problems) == 1
        assert "`synthetic_unit` unit has no `- [ ]` acceptance" in problems[0]

    def test_a_deeper_sub_heading_inside_a_unit_does_not_end_it(self):
        """The other side of that boundary. A unit long enough to want `#### What gets built`
        is still one unit, and cutting it at a level-4 heading would report a spec with proper
        criteria as having none — a false red whose cheapest cure is deleting the rule."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "### 1. `synthetic_unit` — it becomes usable\n\n"
                    "#### What gets built\n\n"
                    "The files, the behavior, the tests.\n\n"
                    "**Acceptance criteria:**\n"
                    "- [ ] The synthetic thing happens.\n"
                ),
            ),
            "synthetic-eval-results.md", None,
        ) == []

    def test_the_last_unfenced_build_plan_heading_wins(self):
        """Fence-stripping handles the quoted example; the last-heading rule handles the rest.

        A document can carry two real `## Build Plan` headings — an earlier draft left above a
        revised one, or a plan restated after a change of direction. The later one is the plan
        in force, and taking the first would hand a reader units nobody intends to build.
        """
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `superseded_unit` — the plan as it stood before the rewrite\n\n"
                "- [ ] It happened.\n\n"
                "## Revised after the second debate\n\n"
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n"
            ),
        )
        build_plan = build_plan_section(spec)
        assert build_plan is not None
        assert [entry.unit_id for entry in _unit_entries(build_plan)] == ["synthetic_unit"]

    def test_a_suffixed_build_plan_heading_is_not_the_build_plan(self):
        """Last-wins is right for two identical headings and wrong for a prefix match.

        A plan kept below the real one for the record — `## Build Plan (as originally
        proposed)` — is labelled by its author as not the plan. Matched by prefix it wins on
        line order anyway, and the units actually being built disappear with nothing said.
        """
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n\n"
                "## Build Plan (as originally proposed, kept for the record)\n\n"
                "### 1. `old_unit` — what we thought we were building\n\n"
                "- [ ] It happened.\n"
            ),
        )
        build_plan = build_plan_section(spec)
        assert build_plan is not None
        assert [entry.unit_id for entry in _unit_entries(build_plan)] == ["synthetic_unit"]
        # And the near-miss complaint stays quiet here: the label is doing its job.
        assert near_miss_build_plan_headings(spec) == []
        assert _violations("synthetic.md", spec, "synthetic-eval-results.md", None) == []

    @pytest.mark.parametrize("heading", [
        "## Build Plan (revised after review)",
        "## Build Plan — second attempt",
        "## Build plan",
        "## BUILD PLAN",
        "##  Build Plan",
        "### Build Plan",
    ])
    def test_approved_with_only_a_near_miss_build_plan_heading_fails(self, heading):
        """The other side of the exact match, and the wider silence of the two.

        Matching exactly is what stops a superseded plan from winning, but an author who
        renames the heading instead of duplicating it has one plan, reads it as the plan, and
        gets nothing: no section, so no entries, no ids, no collision check and no complaint.
        Every unit in the spec is invisible with the suite green.

        A rename is only the visible way to miss the match. The case, the heading level and
        the number of spaces after the hashes are each as fatal to the exact comparison and
        none of them is a decision anybody made — `##  Build Plan` with two spaces renders
        character for character like the real one, so its author has no way to see it at all.
        """
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                f"{heading}\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n"
            ),
        )
        assert build_plan_section(spec) is None
        problems = _violations("synthetic.md", spec, "synthetic-eval-results.md", None)
        assert len(problems) == 1
        assert "specs/synthetic.md" in problems[0]
        assert heading.strip() in problems[0]
        assert "exactly `## Build Plan`" in problems[0]

    def test_a_section_about_planning_is_not_a_near_miss_build_plan_heading(self):
        """The complaint above is for a heading that meant to be the Build Plan. `## Build
        Planning notes` is a different section with a similar name, and a spec that has one
        and no plan is the no-plan case rule 7 deliberately leaves alone."""
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan="## Build Planning notes\n\nWe will write the plan after the spike.\n",
        )
        assert near_miss_build_plan_headings(spec) == []
        assert _violations("synthetic.md", spec, "synthetic-eval-results.md", None) == []

    def test_a_four_space_indented_build_plan_heading_is_not_a_near_miss(self):
        """The near-miss net compares a normalized line, and normalizing drops the indentation
        that says the line is quoted. Four spaces make an indented code block — markdown's other
        way to show a line without meaning it, and the one `strip_fenced_blocks` cannot see — so
        a spec whose notes quote the format that way would be refused for a heading it does not
        have, with a sentence saying it has no `## Build Plan` heading but does have
        `## Build Plan`. Four is the threshold, not one; the case below holds the other side."""
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Notes\n\n"
                "The plan's heading has to read exactly:\n\n"
                "    ## Build Plan\n\n"
                "and every unit under it opens with a level-3 heading.\n"
            ),
        )
        assert near_miss_build_plan_headings(spec) == []
        assert indistinguishable_build_plan_headings(spec) == []
        assert _violations("synthetic.md", spec, "synthetic-eval-results.md", None) == []

    @pytest.mark.parametrize("pad", [" ", "  ", "   "])
    def test_a_slightly_indented_build_plan_heading_is_still_refused(self, pad):
        """One, two or three leading spaces is a heading every renderer shows as a heading, and
        the exactness the readers need is stricter than that. So the plan renders normally, its
        author has nothing on the page to look at, and `build_plan_section` finds no plan at all
        — which is rule 7's exemption for a spec that has no units, applied to a spec that has
        them. Silence there is worse than the refusal: nothing in the file looks wrong.

        The complaint has to keep the indentation it is quoting. Stripped, it asks for the
        heading it just said the spec already has."""
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                f"{pad}## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n"
            ),
        )
        assert build_plan_section(spec) is None
        assert near_miss_build_plan_headings(spec) == [f"{pad}## Build Plan"]
        problems = _violations("synthetic.md", spec, "synthetic-eval-results.md", None)
        assert len(problems) == 1
        assert f"`{pad}## Build Plan`" in problems[0]
        assert "no indentation" in problems[0]

    @pytest.mark.parametrize("twin", [
        "##  Build Plan", "## Build plan", "## BUILD PLAN", " ## Build Plan",
    ])
    def test_an_unlabelled_second_build_plan_heading_is_refused_beside_the_real_one(
        self, twin,
    ):
        """The rename precedence is wrong for a heading that carries no label.

        `## Build Plan (as originally proposed)` is its author stating the section is not the
        plan, so an exact heading elsewhere rightly wins and the near-miss net stays quiet. A
        doubled space states nothing — it renders identically — so an author who revised the
        plan under one and left the original above it sees two identical headings, while
        `build_plan_section` takes the exact one and the revision is never read by anything.

        An indented one is here for the same reason: the leading spaces do not render, so it
        is the doubled-space case with a different invisible character.
        """
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `old_unit` — the plan as it stood before the rewrite\n\n"
                "- [ ] It happened.\n\n"
                f"{twin}\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n"
            ),
        )
        # The exact heading wins, so the revision's units are read by nothing.
        build_plan = build_plan_section(spec)
        assert [entry.unit_id for entry in _unit_entries(build_plan)] == ["old_unit"]
        assert near_miss_build_plan_headings(spec) == []
        problems = _violations("synthetic.md", spec, "synthetic-eval-results.md", None)
        assert len(problems) == 1
        assert twin.strip() in problems[0]
        assert "the case, the spacing or the heading level" in problems[0]

    def test_a_third_level_build_plan_heading_above_the_real_one_is_refused(self):
        """Saying nothing is the test, so the heading level is not part of it.

        `### Build Plan` above the real one is the case that falls through everything else. The
        near-miss net is satisfied by the exact heading, and a twin check that counted the
        hashes would read the third `#` as a difference its author meant — so the plan under it
        sits outside the real section and is read by nothing, with the suite green. It renders
        smaller than the real heading, which is the one clue any of these cases gives, and not
        enough to leave a plan unread over.
        """
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "### Build Plan\n\n"
                "### 1. `ghost_unit` — the plan as it stood before the rewrite\n\n"
                "- [ ] It happened.\n\n"
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n"
            ),
        )
        # The exact heading wins, so `ghost_unit` is outside the section every reader takes.
        assert [entry.unit_id for entry in _unit_entries(build_plan_section(spec))] == [
            "synthetic_unit"
        ]
        assert near_miss_build_plan_headings(spec) == []
        problems = _violations("synthetic.md", spec, "synthetic-eval-results.md", None)
        assert len(problems) == 1
        assert "`### Build Plan`" in problems[0]
        assert "the case, the spacing or the heading level" in problems[0]

    def test_a_frontmatter_comment_is_not_a_build_plan_heading(self):
        """Why both nets stop at level 2, said once here so the bound is not read as an
        oversight. Saying nothing is the test and the level is no part of it — above level 1.
        A spec's frontmatter is YAML that keeps its notes on `# ...` comment lines, every spec
        in `specs/` has several, and nothing here strips frontmatter, so a net that read one
        `#` as a heading would refuse a spec over a line no renderer shows. The price is a
        `# Build Plan` written as a real heading going unseen, at the one level a spec's own
        title already occupies."""
        spec = _synthetic_spec("approved", verification=False).replace(
            "status: approved", "# Build Plan\nstatus: approved",
        )
        assert indistinguishable_build_plan_headings(spec) == []
        assert near_miss_build_plan_headings(spec) == []
        assert _violations("synthetic.md", spec, "synthetic-eval-results.md", None) == []

    def test_a_labelled_second_build_plan_heading_is_still_not_a_defect(self):
        """The other half of the case above: a suffix is a label, and a label is an answer. The
        complaint must not widen into every second Build Plan heading, or the repo's own way of
        keeping a superseded plan for the record becomes a suite failure."""
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n\n"
                "## Build Plan (as originally proposed, kept for the record)\n\n"
                "### 1. `old_unit` — what we thought we were building\n\n"
                "- [ ] It happened.\n"
            ),
        )
        assert indistinguishable_build_plan_headings(spec) == []
        assert _violations("synthetic.md", spec, "synthetic-eval-results.md", None) == []

    def test_a_third_level_near_miss_section_stops_at_its_own_level(self):
        """A section bounded by the next `## ` is the right bound for the real heading and too
        wide for a near miss one level down: every sibling `###` section after it is swallowed.
        Only the collision map reads a near-miss plan, so the cost lands on an approved spec
        being told its id collides with an example in a shipped spec's appendix — a complaint
        whose author has nothing to fix."""
        shipped = _synthetic_spec(
            "shipped", verification=False,
            build_plan=(
                "### Build Plan\n\n"
                "### 1. `real_unit` — it becomes usable\n\n"
                "- [ ] It happens.\n\n"
                "### Appendix\n\n"
                "An example of the shape, for reference:\n\n"
                "### 2. `synthetic_unit` — what an entry looks like\n\n"
                "- [ ] Never built.\n"
            ),
        )
        section = near_miss_build_plan_section(shipped)
        assert section is not None
        assert [entry.unit_id for entry in _unit_entries(section)] == ["real_unit"]
        assert _duplicate_unit_ids([
            ("shipped.md", shipped),
            ("approved.md", _synthetic_spec("approved", verification=False)),
        ]) == []

    @pytest.mark.parametrize("following", [
        "## `stats.py` — what changes",
        "## 1. Background",
    ])
    def test_a_level_two_heading_shaped_like_a_unit_still_ends_the_plan(self, following):
        """The continuation exception belongs to the depth the plan heading sits at, and only
        there. A `## Build Plan` has its units a level down, so a level-2 heading after it is a
        new section whatever it opens with — and plenty of them open with a backticked filename
        or an ordinal. Tested at every depth, the exception hands the following section's `###`
        headings to the plan: rule 7 refuses the spec for a missing `- [ ]` on a heading its
        author never planned, and the collision map takes an id from a section that is not a
        plan, which is the exact harm the depth bound was added to stop one level down."""
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n\n"
                f"{following}\n\n"
                "An example of the shape, for reference:\n\n"
                "### 2. `appendix_example` — what an entry looks like\n\n"
                "- [ ] Never built.\n"
            ),
        )
        build_plan = build_plan_section(spec)
        assert [entry.unit_id for entry in _unit_entries(build_plan)] == ["synthetic_unit"]
        assert _violations("synthetic.md", spec, "synthetic-eval-results.md", None) == []
        assert _duplicate_unit_ids([
            ("synthetic.md", spec),
            ("appendix.md", _synthetic_spec(
                "approved", verification=False,
                build_plan=(
                    "## Build Plan\n\n"
                    "### 1. `appendix_example` — it becomes usable\n\n"
                    "- [ ] It happens.\n"
                ),
            )),
        ]) == []

    def test_a_near_miss_heading_still_hands_its_ids_to_the_collision_check(self):
        """Rule 7 gates `approved` specs only, so a `draft` or `shipped` spec keeps a renamed
        heading with nothing said. Reading only the exact heading in the collision map would
        make its planned ids invisible there as well, and an approved spec could take one —
        two specs planning it, no complaint, and one commit subject for both."""
        renamed = _synthetic_spec(
            "shipped", verification=False,
            build_plan=(
                "## Build Plan (as we shipped it)\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] It happens.\n"
            ),
        )
        assert build_plan_section(renamed) is None
        assert near_miss_build_plan_section(renamed) is not None
        problems = _duplicate_unit_ids([
            ("shipped.md", renamed),
            ("approved.md", _synthetic_spec("approved", verification=False)),
        ])
        assert len(problems) == 1
        assert "`synthetic_unit`" in problems[0]

    def test_the_section_stops_at_the_next_heading(self):
        """The Build Plan is not always the last section. Whatever follows it — risks, notes,
        an appendix quoting a unit — is not part of the plan, and a reader that ran to the end
        of the file would report units nobody planned."""
        spec = _synthetic_spec(
            "approved", verification=False,
            build_plan=(
                "## Build Plan\n\n"
                "### 1. `synthetic_unit` — it becomes usable\n\n"
                "- [ ] The synthetic thing happens.\n\n"
                "## Appendix\n\n"
                "### 1. `ghost_unit` — an example of what we are not building\n\n"
                "- [ ] Never.\n"
            ),
        )
        build_plan = build_plan_section(spec)
        assert build_plan is not None
        assert [entry.unit_id for entry in _unit_entries(build_plan)] == ["synthetic_unit"]
        assert "ghost_unit" not in build_plan

    def test_a_four_backtick_fence_is_not_closed_by_a_three_backtick_one(self):
        """`.claude/commands/spec.md` wraps its template in four backticks precisely so the
        ` ```mermaid ` block inside it does not close the fence early. A stripper that assumed
        three would reopen mid-template and leave half of it visible."""
        stripped = strip_fenced_blocks(
            "before\n````markdown\n## Build Plan\n```mermaid\nflowchart TD\n```\n"
            "### 1. `unit_id` — x\n````\nafter\n"
        )
        assert [line for line in stripped.splitlines() if line] == ["before", "after"]

    def test_an_impact_of_none_is_a_legitimate_answer(self):
        """A feature that shipped and changed nothing downstream is a real record, and
        the field is checked for emptiness, not truthiness — `none` must not read as blank."""
        assert _violations(
            "synthetic.md",
            _synthetic_spec("shipped", verification=True, impact="none"),
            "synthetic-eval-results.md", _FILLED,
        ) == []
