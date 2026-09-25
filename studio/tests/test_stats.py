"""The completion ledger: what approved specs planned against what git says was built.

The reconciliation itself is pure — text in, values out — so most of this file hands
`stats.py` strings and checks the answer. The three tests that touch the world are the ones
about `run_phase._built_unit_ids`, which has to tell "git says nothing was built" apart from
"I could not read git at all", and the dashboard tests, which check the block a person
actually sees.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_phase
from obligations import STALE_STATUS, UNBUILT_UNIT, Obligation
from stats import (
    PlannedUnit,
    UnitLedger,
    built_unit_ids,
    format_obligations,
    mentioned_unit_ids,
    parse_build_plan,
    reconcile_units,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "specs"

# `git log --all --no-merges -E --grep '^(writer|editor)' --format=%s%n%b%n%x1e`, captured from
# this repository. The audit count is measured against this file and never against the live
# tree: CI clones at `fetch-depth: 1`, where `_built_unit_ids` answers `None` and the live count
# is zero, and on a full clone the number moves with every commit anyone makes.
GIT_LOG_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "git_log_built_units.txt"


def _spec(
    build_plan: str,
    *,
    status: str = "approved",
    slug: str = "a-feature",
    verification_due: str = "",
) -> str:
    """A spec file's text: frontmatter, a little prose, then the plan under test."""
    return (
        "---\n"
        "feature: A Feature\n"
        f"slug: {slug}\n"
        f"status: {status}\n"
        f"verification_due: {verification_due}\n"
        "---\n\n"
        "# A Feature\n\nSome prose.\n\n"
        f"{build_plan}"
    )


def _plan(spec_text: str, slug: str = "a-feature") -> list[PlannedUnit]:
    """``parse_build_plan`` for a test that is about the reader, not about which file it read."""
    return parse_build_plan(spec_text, slug, f"specs/{slug}.md")


# --- parse_build_plan: the tolerant reader ---------------------------------


def test_both_entry_openers_are_read_in_document_order():
    """The heading form this repo writes and the list form four consuming repos already have.

    Rule 7 holds new approved specs to the heading form, and it runs in Studio's CI and
    nowhere else — so a reader that demanded it would find nothing at all in 23 of the 24
    approved specs on this machine, and nothing found is indistinguishable from nothing
    unfinished. That silence is what this feature exists to end.
    """
    spec = _spec(
        "## Build Plan\n\n"
        "### 1. `first_unit` — the first usable outcome\n\n"
        "Body text.\n\n"
        "2. **`second_unit` — the second usable outcome**\n\n"
        "More body text.\n\n"
        "### 3. `third_unit` — the third usable outcome\n"
    )
    units = _plan(spec)

    assert [unit.unit_id for unit in units] == ["first_unit", "second_unit", "third_unit"]
    assert units[0].title == "the first usable outcome"
    assert units[1].title == "the second usable outcome"
    assert all(unit.slug == "a-feature" for unit in units)


def test_an_opener_whose_backticked_token_is_not_an_id_is_skipped():
    """A file path in the backticks is not a unit, and naming it would name a dead command.

    `/forge --spec doc-parity-tests --unit studio/tests/test_doc_parity.py` cannot run. A
    reader that accepted anything backticked would print commands that stall, which is worse
    than saying nothing — so the `snake_case` demand is the reader's, not a style preference.
    """
    spec = _spec(
        "## Build Plan\n\n"
        "### 1. `studio/tests/test_doc_parity.py` — built by hand, not by /forge\n\n"
        "### 2. `Capitalised` — not an id either\n\n"
        "### 3. `real_unit` — the one unit here\n"
    )
    assert [unit.unit_id for unit in _plan(spec)] == ["real_unit"]


def test_a_spec_with_no_build_plan_plans_nothing():
    """The normal state of a document with no units, not a defect anyone should hear about."""
    assert _plan(_spec("## Risks\n\nNothing here opens a unit.\n")) == []


def test_a_fenced_build_plan_is_not_the_plan():
    """A spec that documents the plan format carries a fenced `## Build Plan` heading.

    `build_plan_section` strips fences before it looks, so the example cannot win on line
    order — otherwise the day this repo's own ledger spec was approved, the dashboard would
    have named a unit called `unit_id` out of the template it quotes.
    """
    spec = _spec(
        "## How to write one\n\n"
        "```markdown\n"
        "## Build Plan\n\n"
        "### 1. `unit_id` — the shape to copy\n"
        "```\n\n"
        "## Build Plan\n\n"
        "### 1. `real_unit` — the real one\n"
    )
    assert [unit.unit_id for unit in _plan(spec)] == ["real_unit"]


# --- Dropping a unit on purpose --------------------------------------------


def test_a_drop_needs_both_a_date_and_a_reason():
    """Both halves, for the same reason `verification_due` demands a date.

    A bare "dropped" is a way to make the nudge stop without deciding anything, so a line
    missing either half leaves the unit exactly where it was: planned and owed.
    """
    spec = _spec(
        "## Build Plan\n\n"
        "### 1. `dropped_properly` — closed on purpose\n"
        "- **Dropped:** 2026-09-16 — superseded by `rank_the_ladder`.\n\n"
        "### 2. `no_date` — a drop with no date\n"
        "- **Dropped:** superseded by something.\n\n"
        "### 3. `no_reason` — a drop with no reason\n"
        "- **Dropped:** 2026-09-16 —\n"
    )
    units = {unit.unit_id: unit for unit in _plan(spec)}

    assert units["dropped_properly"].dropped_on == "2026-09-16"
    assert units["dropped_properly"].dropped_reason == "superseded by `rank_the_ladder`."
    assert units["no_date"].dropped_on == "" and units["no_date"].dropped_reason == ""
    assert units["no_reason"].dropped_on == "" and units["no_reason"].dropped_reason == ""


def test_a_drop_belongs_to_the_unit_it_sits_under():
    """The entry boundary is what attributes the line, so a drop cannot leak to its neighbour."""
    spec = _spec(
        "## Build Plan\n\n"
        "### 1. `live_unit` — still owed\n\n"
        "Body text.\n\n"
        "### 2. `closed_unit` — closed on purpose\n"
        "- **Dropped:** 2026-09-16 — the divisor cannot satisfy both ranking rules.\n"
    )
    units = {unit.unit_id: unit for unit in _plan(spec)}

    assert units["live_unit"].dropped_on == ""
    assert units["closed_unit"].dropped_on == "2026-09-16"


def test_a_unit_entry_stops_at_the_next_heading_that_is_not_a_unit():
    """A plan's last entry ends at the `### Tests` heading under it, not at the end of the plan.

    Several specs in this repository close their Build Plan with a section that is not a unit.
    Without the boundary the last unit would swallow it, and a `Dropped:` line written there
    about something else would quietly close a unit nobody dropped.
    """
    spec = _spec(
        "## Build Plan\n\n"
        "### 1. `live_unit` — still owed\n\n"
        "Body text.\n\n"
        "### Tests\n\n"
        "- **Dropped:** 2026-09-16 — an example of the line, not a drop of the unit above.\n\n"
        "### Notes\n\n"
        "More prose.\n"
    )
    units = _plan(spec)

    assert [unit.unit_id for unit in units] == ["live_unit"]
    assert units[0].dropped_on == ""


def test_a_drop_belongs_to_its_own_unit_even_with_no_blank_lines():
    """Markdown does not require a blank line before a heading, and neither does this reader.

    Written tight, the drop sits on the line immediately above the next unit's opener — the one
    place a slice off by a line would hand one unit's closure to its neighbour and stop the
    dashboard nagging about work nobody closed.
    """
    spec = _spec(
        "## Build Plan\n"
        "### 1. `closed_unit` — closed on purpose\n"
        "- **Dropped:** 2026-09-16 — superseded.\n"
        "### 2. `live_unit` — still owed\n"
        "### Tests\n"
        "- **Dropped:** 2026-09-17 — an example of the line, in a section that is not a unit.\n"
    )
    units = {unit.unit_id: unit for unit in _plan(spec)}

    assert units["closed_unit"].dropped_on == "2026-09-16"
    assert units["live_unit"].dropped_on == ""
    assert units["live_unit"].dropped_reason == ""


def test_a_list_form_entry_is_bounded_by_the_next_entry():
    """A plan written as a numbered list has no headings to bound its entries.

    The next opener is the only boundary there, so a drop under the second item must not be
    read as closing the first — the shape four consuming repos already write.
    """
    spec = _spec(
        "## Build Plan\n\n"
        "1. **`first_unit` — still owed**\n"
        "   Some body text.\n\n"
        "2. **`second_unit` — closed on purpose**\n"
        "   - **Dropped:** 2026-09-16 — superseded.\n\n"
        "3. **`third_unit` — still owed too**\n"
        "   Some more body text.\n"
    )
    units = {unit.unit_id: unit for unit in _plan(spec)}

    assert [unit.unit_id for unit in _plan(spec)] == [
        "first_unit", "second_unit", "third_unit",
    ]
    assert units["first_unit"].dropped_on == ""
    assert units["second_unit"].dropped_on == "2026-09-16"
    assert units["third_unit"].dropped_on == ""


@pytest.mark.parametrize("separator", ["—", "--", "-"])
def test_a_hand_typed_hyphen_closes_a_unit_too(separator):
    """The template writes an em dash; a hyphen that silently failed would nag with no hint why."""
    spec = _spec(
        "## Build Plan\n\n"
        "### 1. `closed_unit` — closed on purpose\n"
        f"- **Dropped:** 2026-09-16 {separator} a reason.\n"
    )
    assert _plan(spec)[0].dropped_reason == "a reason."


def test_every_unit_carries_the_file_the_caller_read_it_from():
    """The reader is handed the spec's path and stamps it on each unit; there is no default.

    Two approved specs may share a slug, so the path is the only thing that tells them apart.
    A caller that could omit it would put every unit under one empty string and undercount the
    specs that owe work — silently, which is why the argument is required rather than defaulted.
    """
    spec = _spec(
        "## Build Plan\n\n"
        "### 1. `first_unit` — the first outcome\n\n"
        "### 2. `second_unit` — the second outcome\n"
    )
    units = parse_build_plan(spec, "a-feature", "specs/somewhere/a-feature.md")

    assert [unit.spec_file for unit in units] == ["specs/somewhere/a-feature.md"] * 2

    with pytest.raises(TypeError):
        parse_build_plan(spec, "a-feature")


# --- built_unit_ids: reading git ------------------------------------------


def test_built_ids_come_from_subjects_and_bodies():
    """Bodies count, so a squash that kept the loop's own subjects still reads as built.

    `git merge --squash` writes the squashed messages into the body indented, which is why
    the leading whitespace is allowed rather than anchored at the first column.
    """
    log = (
        "writer: first_unit\nA body line.\n\x1e\n"
        "Squashed commit of the following:\n\n"
        "    writer: second_unit\n    editor: third_unit\n\x1e\n"
    )
    built, escalated = built_unit_ids(log)

    assert built == {"first_unit", "second_unit", "third_unit"}
    assert escalated == set()


def test_githubs_default_squash_body_reads_as_built():
    """The commonest way a merged unit reaches a log: one bullet per squashed subject.

    The git-side `--grep` has to allow the bullet too, or the Python side never sees the line
    — see `run_phase._built_unit_ids`.
    """
    log = (
        "Some pull request title (#186)\n\n"
        "* writer: first_unit\n"
        "* editor: first_unit\n"
        "- writer(stuck): second_unit\n\x1e\n"
    )
    built, escalated = built_unit_ids(log)

    assert built == {"first_unit"}
    assert escalated == {"second_unit"}


def test_an_escalation_alone_is_not_built():
    """`writer(stuck):` means the writer stopped on purpose rather than fake a finish.

    Counting it as built would delete from the report the one case a fresh session most needs
    to be told about.
    """
    built, escalated = built_unit_ids("writer(stuck): foo\n\x1e\n")

    assert built == set()
    assert escalated == {"foo"}


def test_built_wins_over_an_earlier_escalation():
    """A unit that got stuck and was then finished is finished.

    Neither set carries any order, so this is decided by membership and never by commit time —
    the writer only ever commits a passing state.
    """
    built, escalated = built_unit_ids("writer(stuck): foo\n\x1e\nwriter: foo\n\x1e\n")

    assert built == {"foo"}
    assert escalated == set()


def test_prose_that_merely_mentions_a_writer_commit_is_not_a_build():
    """The subject shape is the whole signal: `writer:` at the head of a line, then an id."""
    built, escalated = built_unit_ids("Docs: explain what writer: means\n\x1e\n")

    assert built == set() and escalated == set()


# --- reconcile_units -------------------------------------------------------


def _planned(
    unit_id: str, *, slug: str = "a-feature", dropped: bool = False, spec_file: str = ""
) -> PlannedUnit:
    return PlannedUnit(
        slug=slug,
        unit_id=unit_id,
        title=f"what {unit_id} is for",
        dropped_on="2026-09-16" if dropped else "",
        dropped_reason="a reason" if dropped else "",
        spec_file=spec_file or f"specs/{slug}.md",
    )


def test_every_planned_unit_lands_in_exactly_one_state():
    """Unbuilt, escalated, built (reported by nothing) or dropped — never two, never none."""
    planned = [
        _planned("unbuilt_unit"),
        _planned("escalated_unit"),
        _planned("built_unit"),
        _planned("dropped_unit", dropped=True),
    ]
    ledger = reconcile_units(planned, {"built_unit"}, {"escalated_unit"}, set())

    assert [unit.unit_id for unit in ledger.unbuilt] == ["unbuilt_unit"]
    assert [unit.unit_id for unit in ledger.escalated] == ["escalated_unit"]
    assert [unit.unit_id for unit in ledger.dropped] == ["dropped_unit"]
    reported = [
        unit.unit_id
        for group in (ledger.unbuilt, ledger.escalated, ledger.dropped)
        for unit in group
    ]
    assert len(reported) == len(set(reported)) == 3
    assert "built_unit" not in reported


def test_a_dropped_unit_stays_closed_even_with_no_build():
    """State next to the plan, in a reviewed commit: the one honest way to stop the nudge."""
    ledger = reconcile_units([_planned("closed", dropped=True)], set(), set(), set())

    assert ledger.unbuilt == () and ledger.escalated == ()
    assert [unit.unit_id for unit in ledger.dropped] == ["closed"]


def test_an_unreadable_built_set_reports_nothing_as_unbuilt():
    """`None` is "I cannot see", not "nothing was built", and the two must not print the same.

    With no built set every planned unit reads unbuilt, so a repo with approved specs would be
    told that none of their units was ever built. Silence beats a lie — and it is silence on
    every field, drops included: a drop only counts on a unit git does not say was built, so
    an unknown built set cannot decide that one either.
    """
    planned = [_planned("one"), _planned("two"), _planned("closed", dropped=True)]
    ledger = reconcile_units(planned, None, None, set())

    assert ledger.unbuilt == ()
    assert ledger.escalated == ()
    assert ledger.unplanned == ()
    assert ledger.dropped == ()
    assert ledger.built_known is False


def test_a_drop_on_a_built_unit_is_not_a_drop():
    """Built work is reported by nothing. Only an unbuilt unit can be closed on purpose.

    A unit that shipped and later collected a `Dropped:` line would otherwise be counted under
    "Dropped on purpose", which reads as work somebody decided against.
    """
    ledger = reconcile_units([_planned("shipped_then_closed", dropped=True)],
                             {"shipped_then_closed"}, set(), set())

    assert ledger.dropped == ()
    assert ledger.unbuilt == () and ledger.escalated == ()


def test_an_unreadable_built_set_says_it_is_unreadable():
    """Empty tuples alone cannot tell "nothing is outstanding" from "I could not look".

    Every caller that renders the ledger has to know which one it is holding, so the answer
    travels with the ledger rather than being re-derived from what the caller happened to pass.
    """
    planned = [_planned("one"), _planned("two")]

    assert reconcile_units(planned, None, None, set()).built_known is False
    assert reconcile_units(planned, set(), set(), set()).built_known is True


def test_half_a_drop_closes_nothing():
    """A date with no reason, or a reason with no date, leaves the unit exactly where it was.

    Both halves are required for the same reason `verification_due` demands a date: a bare
    "dropped" is a way to make the nudge stop without deciding anything.
    """
    planned = [
        PlannedUnit("a-feature", "no_reason", "a title", "2026-09-16", "", "specs/a-feature.md"),
        PlannedUnit("a-feature", "no_date", "a title", "", "superseded", "specs/a-feature.md"),
    ]
    ledger = reconcile_units(planned, set(), set(), set())

    assert ledger.dropped == ()
    assert [unit.unit_id for unit in ledger.unbuilt] == ["no_reason", "no_date"]


def test_an_id_any_spec_mentions_is_not_unplanned():
    """A unit planned under a spec that has since shipped is finished work, not stray work."""
    ledger = reconcile_units([], {"mentioned_somewhere", "nobody_planned_this"}, set(),
                             {"mentioned_somewhere"})

    assert ledger.unplanned == ("nobody_planned_this",)


def test_mentioned_ids_are_read_from_anywhere_in_a_spec():
    """The audit direction asks a different question, so it reads the whole document."""
    text = "A shipped spec that says `some_unit_id` in its prose and `CamelCase` too.\n"

    assert mentioned_unit_ids(text) == {"some_unit_id"}


def test_the_audit_count_against_this_repo_stays_near_the_truth():
    """Measured against the captured log and this repo's specs, not the live tree.

    Without the "does any spec mention this id?" check the same input reports roughly twice as
    many orphans, because every unit planned under a spec that has since shipped is counted as
    work nobody proposed. A count twice the truth is one people learn to ignore.
    """
    built, escalated = built_unit_ids(GIT_LOG_FIXTURE.read_text(encoding="utf-8"))
    mentioned: set = set()
    for spec_path in sorted(SPECS_DIR.glob("*.md")):
        if spec_path.name.endswith("-eval-results.md"):
            continue
        mentioned |= mentioned_unit_ids(spec_path.read_text(encoding="utf-8"))

    ledger = reconcile_units([], built, escalated, mentioned)

    assert len(built) > 20, "the fixture should carry a real repository's worth of built units"
    assert len(ledger.unplanned) <= 20, (
        f"{len(ledger.unplanned)} ids read as built-but-never-planned; the ceiling is 20.\n"
        "20 is a MEASUREMENT of this repository on 2026-09-19, not a property of the code. The git\n"
        "side is frozen in the fixture, but the mention set is read from the live specs/ directory,\n"
        "so deleting a spec, renaming one to *-eval-results.md, or rewriting prose that quoted a\n"
        "built id raises this count without touching the reader.\n"
        "If mentioned_unit_ids or reconcile_units changed, fix the reader. If specs/ changed,\n"
        "re-measure and re-pin this number in the same commit that moved it."
    )
    assert len(reconcile_units([], built, escalated, set()).unplanned) > len(ledger.unplanned)


# --- format_obligations: the block a person actually reads --------------------


def _owed(unit_id: str, *, slug: str = "a-feature", spec_file: str = "") -> Obligation:
    """One `unbuilt_unit` obligation, the shape `derive` builds for a unit nobody built."""
    return Obligation(
        kind=UNBUILT_UNIT,
        subject=unit_id,
        spec_file=spec_file or f"specs/{slug}.md",
        detail=f"`{unit_id}`, planned by `{slug}`, is not in any commit",
        command=f"/forge --spec {spec_file or f'specs/{slug}.md'} --unit {unit_id}",
        silence="open a PR adding `- **Dropped:** YYYY-MM-DD — <reason>`",
    )


def test_an_empty_queue_prints_one_line_and_no_empty_headings():
    """A report that looks the same with and without news is one people stop reading."""
    lines = format_obligations((), UnitLedger((), (), (), ()))

    assert lines == [
        "",
        "What this repository owes (approved specs vs. git):",
        "  Nothing owed — every unit an approved spec plans is built or dropped, and every "
        "finished spec says so.",
    ]


def test_an_unknown_built_set_prints_no_block_at_all():
    """Nothing was reconciled, so there is nothing the block could honestly say.

    "Nothing owed" is the specific lie to avoid here: a shallow CI checkout or a box with
    no git is exactly where it would claim every planned unit is built.
    """
    ledger = reconcile_units([_planned("owed_unit")], None, None, set())

    assert format_obligations((), ledger) == []


def test_the_block_names_each_state_it_has_something_to_say_about():
    """What a person reads: the queue, the escalations, the counts, and the caveat."""
    ledger = UnitLedger(
        unbuilt=(_planned("owed_unit"),),
        escalated=(_planned("stuck_unit", slug="other-feature"),),
        dropped=(_planned("closed_unit", dropped=True),),
        unplanned=("stray_id",),
    )
    block = "\n".join(format_obligations((_owed("owed_unit"),), ledger))

    assert "1 obligation, most important first:" in block
    assert "Planned and never built: 1" in block
    assert "`owed_unit`, planned by `a-feature`, is not in any commit" in block
    assert "Run: /forge --spec specs/a-feature.md --unit owed_unit" in block
    assert "Started and escalated" in block and "[other-feature] stuck_unit" in block
    assert "Dropped on purpose: 1 unit" in block
    assert "Built but never planned: 1 id" in block
    assert "Nothing owed" not in block


def test_obligations_are_listed_even_when_nothing_else_has_news():
    """The commonest shape there is: work outstanding, nothing dropped, nothing stray.

    It has to print the queue rather than the "nothing owed" line, which is the whole
    reason that line is gated on the queue and all three ledger states being empty.
    """
    block = "\n".join(format_obligations((_owed("owed_unit"),), UnitLedger((), (), (), ())))

    assert "`owed_unit`" in block
    assert "Nothing owed" not in block


def test_each_kind_gets_its_own_heading_its_own_count_and_its_own_indent():
    """Obligations arrive sorted by kind, so the headings count the run under each.

    The indentation is checked line for line: a heading, its obligations one level in, and
    the way out one level further. That shape is the only thing separating the three groups
    on a terminal, and a substring match would not notice it going.
    """
    stale = Obligation(
        kind=STALE_STATUS, subject="b-feature", spec_file="specs/b-feature.md",
        detail="every unit `b-feature` plans is built", command="", silence="",
    )
    lines = format_obligations(
        (stale, _owed("first"), _owed("second")), UnitLedger((), (), (), ())
    )

    assert lines == [
        "",
        "What this repository owes (approved specs vs. git):",
        "  3 obligations, most important first:",
        "  Finished but still `approved` — the frontmatter owes a flip: 1",
        "    every unit `b-feature` plans is built",
        "  Planned and never built: 2",
        "    `first`, planned by `a-feature`, is not in any commit",
        "      Run: /forge --spec specs/a-feature.md --unit first",
        "      Or close it on purpose: open a PR adding "
        "`- **Dropped:** YYYY-MM-DD — <reason>`",
        "    `second`, planned by `a-feature`, is not in any commit",
        "      Run: /forge --spec specs/a-feature.md --unit second",
        "      Or close it on purpose: open a PR adding "
        "`- **Dropped:** YYYY-MM-DD — <reason>`",
    ]


def test_the_counts_read_as_plurals_when_there_is_more_than_one():
    """Two of everything, said the way a person would say it."""
    ledger = UnitLedger(
        unbuilt=(),
        escalated=(),
        dropped=(_planned("closed", dropped=True), _planned("also_closed", dropped=True)),
        unplanned=("one_id", "another_id"),
    )
    block = "\n".join(format_obligations(
        (_owed("first"), _owed("second", slug="other-feature")), ledger
    ))

    assert "2 obligations, most important first:" in block
    assert "Dropped on purpose: 2 units" in block
    assert "Built but never planned: 2 ids" in block


def test_two_specs_sharing_a_slug_each_name_their_own_file():
    """Rule 7 forbids a duplicate `unit_id`, not a duplicate slug.

    Every obligation carries the file that defines it, so two specs sharing a slug can never
    send a reader to the wrong one — the `/forge` line under each names its own spec.
    """
    block = "\n".join(format_obligations(
        (
            _owed("first", spec_file="specs/a-feature.md"),
            _owed("second", spec_file="specs/a-feature-revised.md"),
        ),
        UnitLedger((), (), (), ()),
    ))

    assert "/forge --spec specs/a-feature.md --unit first" in block
    assert "/forge --spec specs/a-feature-revised.md --unit second" in block


def test_escalated_units_from_two_specs_sharing_a_slug_name_their_files():
    """A count that says two specs over two identical `[a-feature]` prefixes explains nothing.

    Only the shared slug gives way: a unit whose slug belongs to one file keeps it, because
    the slug is what the reader recognises and what they would type at `/forge`.
    """
    ledger = UnitLedger(
        unbuilt=(),
        escalated=(
            _planned("first", spec_file="specs/a-feature.md"),
            _planned("second", spec_file="specs/a-feature-revised.md"),
            _planned("third", slug="b-feature"),
        ),
        dropped=(),
        unplanned=(),
    )
    lines = format_obligations((), ledger)

    assert "    [a-feature] first — what first is for" in lines
    assert "    [a-feature-revised] second — what second is for" in lines
    assert "    [b-feature] third — what third is for" in lines


def test_a_long_escalated_title_is_cut_and_a_missing_one_is_left_out():
    """The line has to stay one line, and a unit with no title still names its id."""
    long_title = PlannedUnit("a-feature", "wordy_unit", "x" * 81, "", "", "specs/a-feature.md")
    just_short = PlannedUnit("a-feature", "terse_unit", "y" * 80, "", "", "specs/a-feature.md")
    untitled = PlannedUnit("a-feature", "bare_unit", "", "", "", "specs/a-feature.md")
    lines = format_obligations(
        (), UnitLedger((), (long_title, just_short, untitled), (), ())
    )

    assert "    [a-feature] wordy_unit — " + "x" * 77 + "..." in lines
    assert "    [a-feature] terse_unit — " + "y" * 80 in lines
    assert "    [a-feature] bare_unit" in lines


def test_counts_that_have_nothing_to_report_are_left_out():
    """Zeroes are noise. Only a state with something in it gets a line."""
    block = "\n".join(format_obligations((), UnitLedger((), (), (), ("stray_id",))))

    assert "Built but never planned" in block
    assert "Planned and never built" not in block
    assert "Dropped on purpose" not in block


# --- run_phase._built_unit_ids: the I/O edge -------------------------------


def _repo_with_commits(root: Path, *subjects: str) -> Path:
    root.mkdir(parents=True)

    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    for subject in subjects:
        run("commit", "-q", "--allow-empty", "-m", subject)
    return root


def test_built_ids_are_read_out_of_a_real_repository(tmp_path):
    """The one test that lets git answer for itself, because the plumbing is the thing tested."""
    repo = _repo_with_commits(
        tmp_path / "repo",
        "init",
        "writer: a_built_unit",
        "writer(stuck): a_stuck_unit",
    )
    built, escalated = run_phase._built_unit_ids(repo)

    assert built == {"a_built_unit"}
    assert escalated == {"a_stuck_unit"}


def test_a_squashed_pull_request_is_read_out_of_a_real_repository(tmp_path):
    """git's `--grep` is the gate: what it filters out, the Python pattern never sees.

    The subject here is a PR title and every loop commit survives only as a bullet in the body,
    which is what GitHub's squash button writes.
    """
    repo = _repo_with_commits(
        tmp_path / "squashed",
        "init",
        "A pull request title (#186)\n\n* writer: a_built_unit\n* editor: a_built_unit\n",
    )
    built, escalated = run_phase._built_unit_ids(repo)

    assert built == {"a_built_unit"}
    assert escalated == set()


def test_a_directory_that_is_not_a_work_tree_reads_as_unknown(tmp_path):
    """Not `set()`: the caller has to be able to tell "no git here" from "nothing built"."""
    outside = tmp_path / "not-a-repo"
    outside.mkdir()

    assert run_phase._built_unit_ids(outside) is None


def test_git_missing_from_the_path_reads_as_unknown(tmp_path, monkeypatch):
    """A machine with no git is a machine whose built set is unknown, not empty."""
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(run_phase.subprocess, "run", no_git)

    assert run_phase._built_unit_ids(tmp_path) is None


def test_a_shallow_clone_reads_as_unknown(tmp_path, monkeypatch):
    """Truncated history drops old `writer:` commits, so built units would read unbuilt.

    CI checks out at `fetch-depth: 1` and lands here, which is why it is one cheap call rather
    than a surprise in the dashboard.
    """
    answers = {"--is-inside-work-tree": "true", "--is-shallow-repository": "true"}

    def fake_git(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=answers.get(command[-1], ""), stderr="")

    monkeypatch.setattr(run_phase.subprocess, "run", fake_git)

    assert run_phase._built_unit_ids(tmp_path) is None


def test_a_log_that_hangs_reads_as_unknown(tmp_path, monkeypatch):
    """Five seconds is the ceiling; a timeout is read the same way a missing repo is."""
    def slow_git(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(run_phase.subprocess, "run", slow_git)

    assert run_phase._built_unit_ids(tmp_path) is None


# --- The dashboard block ---------------------------------------------------


@pytest.fixture
def specs_root(studio_root, monkeypatch):
    """A seeded Studio root the dashboard will actually read its specs out of.

    The override is cleared because it is process-global and one test in the suite sets it
    without putting it back (`test_inject_context_basic` calls `set_artifact_root` directly).
    It beats the environment variable the `studio_root` fixture sets, so whichever of these
    tests runs after it would otherwise read some other test's temporary directory.
    """
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)
    return studio_root


def _seed_spec(studio_root: Path, text: str, name: str = "a-feature.md") -> Path:
    specs_dir = studio_root.parent / "specs"
    specs_dir.mkdir(exist_ok=True)
    spec_path = specs_dir / name
    spec_path.write_text(text, encoding="utf-8")
    return spec_path


def _stats_output(capsys) -> str:
    run_phase.show_stats(SimpleNamespace(artifact_root=None, phase=None, json=False))
    return capsys.readouterr().out


def test_stats_prints_the_obligation_queue(specs_root, monkeypatch, capsys):
    """The dashboard block, end to end: an approved spec's owed unit, named with its spec.

    The unit line carries everything the "Planned work" block carried before the queue
    replaced it — the slug, the id and the one-line outcome — plus the command that builds it.
    """
    _seed_spec(specs_root, _spec(
        "## Build Plan\n\n"
        "### 1. `already_built` — done\n\n"
        "### 2. `still_owed` — the one nobody built\n\n"
        "### 3. `closed_on_purpose` — closed\n"
        "- **Dropped:** 2026-09-16 — superseded.\n"
    ))
    monkeypatch.setattr(run_phase, "_built_unit_ids", lambda target: ({"already_built"}, set()))

    output = _stats_output(capsys)

    assert "What this repository owes (approved specs vs. git):" in output
    assert "1 obligation, most important first:" in output
    assert "Planned and never built: 1" in output
    assert "`still_owed`, planned by `a-feature` in specs/a-feature.md" in output
    assert '— "the one nobody built"' in output
    assert "Run: /forge --spec specs/a-feature.md --unit still_owed" in output
    assert "already_built" not in output
    assert "Dropped on purpose: 1 unit" in output


def test_stats_prints_the_two_spec_level_obligations(specs_root, monkeypatch, capsys):
    """A spec finished but still `approved`, and one whose evidence is past due.

    Both are edits rather than commands, so each has to say in words what to change — a
    kind of obligation with no `/forge` line under it is the reason `command` can be empty.
    """
    _seed_spec(specs_root, _spec("## Build Plan\n\n### 1. `already_built` — done\n"))
    _seed_spec(specs_root, _spec(
        "## Build Plan\n\n### 1. `also_built` — done\n\n"
        "## Verification\n\nEvidence was promised.\n",
        slug="b-feature", verification_due="2020-01-01",
    ), name="b-feature.md")
    monkeypatch.setattr(
        run_phase, "_built_unit_ids", lambda target: ({"already_built", "also_built"}, set())
    )

    output = _stats_output(capsys)

    assert "Finished but still `approved` — the frontmatter owes a flip: 1" in output
    assert "`status: shipped`" in output and "`shipped_impact`" in output
    assert "Evidence overdue — the results file is still blank: 1" in output
    assert "specs/b-feature-eval-results.md is still blank" in output
    # The overdue spec is waiting on evidence, so it owes no flip — and the finished one
    # promised no evidence, so it is not overdue. One obligation each, never both.
    assert "2 obligations, most important first:" in output


def test_stats_says_nothing_is_owed_rather_than_printing_an_empty_block(
    specs_root, monkeypatch, capsys
):
    """One line when there is no news, not a heading with nothing under it.

    The spec here has its every unit built and still says `approved`, which is usually a
    `stale_status` obligation — but it promised evidence that is not due yet, and flipping it
    to `shipped` is an edit the spec-verification suite would reject while that file is blank.
    """
    _seed_spec(specs_root, _spec(
        "## Build Plan\n\n### 1. `already_built` — done\n\n"
        "## Verification\n\nEvidence is due later.\n",
        verification_due="2099-01-01",
    ))
    monkeypatch.setattr(run_phase, "_built_unit_ids", lambda target: ({"already_built"}, set()))

    output = _stats_output(capsys)

    assert "Nothing owed" in output
    assert "Planned and never built" not in output
    assert "Finished but still" not in output


def test_stats_does_not_nag_about_every_unit_when_git_cannot_be_read(
    specs_root, monkeypatch, capsys
):
    """The dangerous failure: an unknown built set must not turn into "nothing was ever built"."""
    _seed_spec(specs_root, _spec(
        "## Build Plan\n\n### 1. `one_unit` — a\n\n### 2. `another_unit` — b\n"
    ))
    monkeypatch.setattr(run_phase, "_built_unit_ids", lambda target: None)

    output = _stats_output(capsys)

    assert "one_unit" not in output and "another_unit" not in output
    # And it does not swing the other way either: with no built set, "nothing owed" is the
    # same lie wearing the opposite sign. The block is left out entirely.
    assert "Nothing owed" not in output
    assert "What this repository owes (approved specs vs. git):" not in output


def test_a_draft_spec_owes_nobody_a_build(specs_root, monkeypatch, capsys):
    """Approved is the filter: a draft is an argument in progress, not a promise."""
    _seed_spec(specs_root, _spec(
        "## Build Plan\n\n### 1. `argued_about` — not agreed yet\n", status="draft"
    ))
    monkeypatch.setattr(run_phase, "_built_unit_ids", lambda target: (set(), set()))

    output = _stats_output(capsys)

    assert "argued_about" not in output
    assert "Nothing owed" in output
