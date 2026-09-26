"""The obligation queue: everything this repository owes, worked out from fixtures.

`derive` is pure — specs in, a sorted list out — so every test here builds its inputs by
hand. No repository, no git, no clock: the date is a parameter, which is the whole reason a
deadline can be tested at all. The tests that touch the world live beside the code that does
the reading: the dashboard block in `test_stats.py`, the session brief in `test_update_check.py`.
"""
from __future__ import annotations

from datetime import date

from obligations import (
    EVIDENCE_OVERDUE,
    RANK,
    STALE_STATUS,
    UNBUILT_UNIT,
    Obligation,
    SpecView,
    derive,
    evidence_file_for,
    parse_due,
)
from stats import PlannedUnit, reconcile_units

TODAY = date(2026, 9, 25)


def _unit(unit_id: str, *, slug: str = "a-feature", dropped: bool = False) -> PlannedUnit:
    return PlannedUnit(
        slug=slug,
        unit_id=unit_id,
        title=f"what {unit_id} is for",
        dropped_on="2026-09-16" if dropped else "",
        dropped_reason="a reason" if dropped else "",
        spec_file=f"specs/{slug}.md",
    )


def _view(
    *units: PlannedUnit,
    slug: str = "a-feature",
    status: str = "approved",
    promises_evidence: bool = False,
    verification_due: str = "",
    evidence_is_blank: bool = True,
) -> SpecView:
    return SpecView(
        slug=slug,
        spec_file=f"specs/{slug}.md",
        status=status,
        promises_evidence=promises_evidence,
        verification_due=verification_due,
        evidence_is_blank=evidence_is_blank,
        units=units,
    )


def _queue(views, *, built=(), escalated=(), today=TODAY):
    """`derive` over the real reconciliation, so the two cannot drift apart in a fixture."""
    planned = [unit for view in views for unit in view.units]
    ledger = reconcile_units(planned, set(built), set(escalated), set())
    return derive(views, ledger, today=today)


# --- criterion 1: a unit nobody built, with the command that builds it ---------


def test_an_unbuilt_unit_carries_its_spec_its_id_and_its_outcome():
    """Everything the old "Planned work" block carried, plus the way out of it.

    The slug is what somebody types at `/forge` and the spec path is what identifies the
    file — two approved specs may share a slug, so the path has to be there as well.
    """
    queue = _queue([_view(_unit("built_one"), _unit("owed_one"))], built=["built_one"])

    assert [owed.kind for owed in queue] == [UNBUILT_UNIT]
    owed = queue[0]
    assert owed.subject == "owed_one"
    assert owed.spec_file == "specs/a-feature.md"
    assert owed.detail == (
        "`owed_one`, planned by `a-feature` in specs/a-feature.md, is not in any commit "
        '— "what owed_one is for"'
    )
    assert owed.command == "/forge --spec specs/a-feature.md --unit owed_one"
    assert owed.silence == (
        "open a PR adding `- **Dropped:** YYYY-MM-DD — <reason>` under that unit's heading "
        "in specs/a-feature.md"
    )


def test_a_unit_with_no_outcome_still_names_itself():
    """A Build Plan entry with no title after the id is legal, and still owes the build."""
    bare = PlannedUnit("a-feature", "bare_unit", "", "", "", "specs/a-feature.md")
    queue = _queue([_view(bare)])

    assert queue[0].detail.endswith("is not in any commit")
    assert "`bare_unit`" in queue[0].detail


def test_a_dropped_unit_owes_nothing():
    """The escape hatch the ledger already honours: a drop closes a unit on purpose."""
    queue = _queue([_view(_unit("owed_one"), _unit("closed_one", dropped=True))])

    assert [owed.subject for owed in queue] == ["owed_one"]


def test_an_escalated_unit_is_not_reported_as_unbuilt():
    """A writer that stopped on purpose is a state the ledger reports, not an obligation.

    Telling a fresh session to run `/forge` on a unit a writer walked away from would send it
    straight back into whatever stopped the first one.
    """
    assert _queue([_view(_unit("stuck_one"))], escalated=["stuck_one"]) == []


# --- criterion 2: finished work whose frontmatter has not caught up ------------


def test_a_spec_with_every_unit_built_owes_the_flip_to_shipped():
    """The three-times-in-one-week case: a feature that landed and is missing from `stats`."""
    queue = _queue(
        [_view(_unit("built_one"), _unit("built_two"))],
        built=["built_one", "built_two"],
    )

    assert [(owed.kind, owed.subject) for owed in queue] == [(STALE_STATUS, "a-feature")]
    owed = queue[0]
    assert owed.spec_file == "specs/a-feature.md"
    assert owed.detail == (
        "every unit `a-feature` plans in specs/a-feature.md is built or dropped and nothing "
        "is waiting on evidence, but its frontmatter still says `status: approved` — edit it "
        "to `status: shipped` and fill in `shipped_impact` and `shipped_changed`"
    )
    # An edit, not a command — and there is no honest way to close it without making the edit.
    assert owed.command == ""
    assert owed.silence == ""


def test_a_spec_that_still_owes_a_unit_owes_no_flip():
    """Producing a `stale_status` must not also report the spec's units as unbuilt, and the
    other way round: one unbuilt unit means the work is not finished."""
    queue = _queue(
        [_view(_unit("built_one"), _unit("owed_one"))],
        built=["built_one"],
    )

    assert [owed.kind for owed in queue] == [UNBUILT_UNIT]


def test_a_built_spec_whose_evidence_is_in_owes_the_flip():
    """Evidence gates the flip, and filled-in evidence opens it again."""
    view = _view(
        _unit("built_one"),
        promises_evidence=True,
        verification_due="2099-01-01",
        evidence_is_blank=False,
    )

    assert [owed.kind for owed in _queue([view], built=["built_one"])] == [STALE_STATUS]


def test_a_unit_both_built_and_dropped_still_counts_as_built():
    """The ledger's own rule: a drop line on a unit git says was built is not a drop."""
    view = _view(_unit("built_one", dropped=True), _unit("built_two"))

    assert [owed.kind for owed in _queue([view], built=["built_one", "built_two"])] == [
        STALE_STATUS
    ]


# --- criterion 3: a spec still waiting on evidence owes nothing yet ------------


def test_a_spec_waiting_on_evidence_owes_neither_a_flip_nor_anything_else():
    """Flipping it would be an edit the spec-verification suite rejects.

    Rule 3 of that suite turns red on a `shipped` spec whose evidence file still says
    `FILL_ME`, so naming this one would be telling its reader to break the build.
    """
    view = _view(
        _unit("built_one"),
        promises_evidence=True,
        verification_due="2099-01-01",
        evidence_is_blank=True,
    )

    assert _queue([view], built=["built_one"]) == []


# --- criterion 4: the two silent edge cases, and a date nothing can read -------


def test_a_spec_that_planned_nothing_owes_no_flip():
    """"Every unit is built" is vacuously true of it, and it has been shown to finish nothing."""
    assert _queue([_view()]) == []


def test_a_spec_whose_every_unit_was_dropped_owes_no_flip():
    """It was abandoned rather than shipped, and `shipped` would be a false claim about it."""
    view = _view(_unit("closed_one", dropped=True), _unit("closed_two", dropped=True))

    assert _queue([view]) == []


def test_a_verification_due_that_is_not_a_date_produces_nothing():
    """Malformed reads as no deadline, the same way rule 6 of the suite reads it.

    The suite is already red over that spec, and the queue does not restate a failure
    something else already reports.
    """
    view = _view(
        _unit("built_one"),
        promises_evidence=True,
        verification_due="whenever we get to it",
    )

    assert _queue([view], built=["built_one"]) == []


def test_a_spec_that_is_not_approved_is_skipped_and_the_next_one_is_still_read():
    """Approved is the filter. A draft is an argument in progress; a shipped spec is history.

    The spec after it still gets read: a filter that stopped at the first draft would hide
    every obligation behind it, and which spec comes first is decided by filename order.
    """
    draft = _view(_unit("built_one"), status="draft", verification_due="2020-01-01")
    approved = _view(
        _unit("built_two", slug="b-feature"),
        slug="b-feature",
        promises_evidence=True,
        verification_due="2020-01-01",
    )
    queue = _queue([draft, approved], built=["built_one", "built_two"])

    assert [(owed.kind, owed.subject) for owed in queue] == [(EVIDENCE_OVERDUE, "b-feature")]


# --- criterion 5: evidence that is past due -----------------------------------


def test_evidence_past_its_date_is_owed_and_moving_the_date_removes_it():
    """One obligation per overdue spec, and the escape hatch is a visible edit."""
    overdue = _view(
        _unit("built_one"),
        promises_evidence=True,
        verification_due="2026-09-01",
    )
    queue = _queue([overdue], built=["built_one"])

    assert [(owed.kind, owed.subject) for owed in queue] == [(EVIDENCE_OVERDUE, "a-feature")]
    assert queue[0].detail == (
        "`a-feature` promised evidence by 2026-09-01 and specs/a-feature-eval-results.md is "
        "still blank — fill it in, replacing every `FILL_ME`"
    )
    assert queue[0].command == ""
    assert queue[0].silence == (
        "move `verification_due` in specs/a-feature.md past today, which is an edit anyone "
        "reviewing the spec can see"
    )

    moved = _view(
        _unit("built_one"),
        promises_evidence=True,
        verification_due="2099-01-01",
    )
    assert _queue([moved], built=["built_one"]) == []


def test_evidence_due_today_is_already_owed():
    """On or before, not strictly before: the day it is due is the day it is late."""
    view = _view(
        _unit("built_one"),
        promises_evidence=True,
        verification_due=TODAY.isoformat(),
    )

    assert [owed.kind for owed in _queue([view], built=["built_one"])] == [EVIDENCE_OVERDUE]


def test_evidence_that_is_in_owes_nothing_however_late_it_was():
    """The deadline is not the obligation — the blank file is."""
    view = _view(
        _unit("built_one"),
        promises_evidence=True,
        verification_due="2020-01-01",
        evidence_is_blank=False,
    )

    assert [owed.kind for owed in _queue([view], built=["built_one"])] == [STALE_STATUS]


# --- criterion 6: silence beats a lie -----------------------------------------


def test_an_unknown_built_set_derives_nothing_at_all():
    """With no built set every planned unit reads unbuilt and every spec reads unfinished.

    This is the failure that matters most: a shallow CI clone or a box with no git would
    otherwise be told that nothing in it was ever built.
    """
    views = [_view(_unit("owed_one"), _unit("built_one"))]
    ledger = reconcile_units([unit for view in views for unit in view.units], None, set(), set())

    assert ledger.built_known is False
    assert derive(views, ledger, today=TODAY) == []


# --- criterion 7: the order the queue is read in ------------------------------


def test_the_queue_sorts_by_kind_then_spec_then_subject():
    """Rank first, so the brief names the cheapest, most-missed thing to fix.

    `stale_status` leads because a finished spec left at `approved` is missing from the
    shipped-features block — the only record of what landed — and it is the cheapest of the
    three to discharge.
    """
    finished = _view(_unit("done_one", slug="z-feature"), slug="z-feature")
    overdue = _view(
        _unit("done_two", slug="m-feature"),
        slug="m-feature",
        promises_evidence=True,
        verification_due="2020-01-01",
    )
    owing = _view(
        _unit("second_owed", slug="a-feature"),
        _unit("first_owed", slug="a-feature"),
    )
    queue = _queue(
        [owing, overdue, finished],
        built=["done_one", "done_two"],
    )

    assert [(owed.kind, owed.subject) for owed in queue] == [
        (STALE_STATUS, "z-feature"),
        (EVIDENCE_OVERDUE, "m-feature"),
        (UNBUILT_UNIT, "first_owed"),
        (UNBUILT_UNIT, "second_owed"),
    ]
    assert RANK == (STALE_STATUS, EVIDENCE_OVERDUE, UNBUILT_UNIT)


def test_two_specs_sharing_a_slug_each_keep_their_own_units():
    """Rule 7 forbids a duplicate `unit_id`, not a duplicate slug.

    A spec's units are matched by the file that planned them as well as by their ids, so one
    spec's built work can never be read as another's.
    """
    first = SpecView("shared", "specs/a-feature.md", "approved", False, "", True,
                     (PlannedUnit("shared", "built_one", "t", "", "", "specs/a-feature.md"),))
    second = SpecView("shared", "specs/b-feature.md", "approved", False, "", True,
                      (PlannedUnit("shared", "owed_one", "t", "", "", "specs/b-feature.md"),))
    queue = _queue([first, second], built=["built_one"])

    assert [(owed.kind, owed.spec_file) for owed in queue] == [
        (STALE_STATUS, "specs/a-feature.md"),
        (UNBUILT_UNIT, "specs/b-feature.md"),
    ]


# --- the small pure readers ---------------------------------------------------


def test_the_evidence_file_sits_beside_the_spec():
    assert evidence_file_for("specs/a-feature.md") == "specs/a-feature-eval-results.md"
    assert evidence_file_for(".studio/specs/a.md") == ".studio/specs/a-eval-results.md"


def test_a_trailing_comment_is_not_part_of_the_date():
    """The frontmatter template writes its notes after the value, and nothing strips them."""
    assert parse_due("2026-09-30   # 30 days from approval") == date(2026, 9, 30)
    assert parse_due("") is None
    assert parse_due("soon") is None


def test_the_derived_values_cannot_be_edited_after_the_fact():
    """Derived, never stored — and never quietly rewritten by a caller either."""
    import dataclasses

    assert dataclasses.fields(Obligation)
    for shape in (Obligation, SpecView):
        assert shape.__dataclass_params__.frozen, f"{shape.__name__} must be frozen"
