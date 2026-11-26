"""What this repository owes, worked out from its specs and its commit log.

An **obligation** is one unfinished thing. There are four kinds:

* a unit an approved spec planned that no commit says was built,
* a spec whose work is finished while its frontmatter still says ``status: approved``,
  so the shipped-features block leaves out a feature that actually landed,
* a finished spec whose verification failed or needs clarification,
* a spec that promised evidence by a date that has passed, with the evidence file blank.

Nothing here is stored. Every obligation is derived at the moment it is asked for, so one
can never outlive the facts that imply it — the property the completion ledger was built
on, inherited rather than re-decided.

Everything in this module is pure: no filesystem, no git, no clock of its own. The caller
reads the specs directory and the commit log, builds one :class:`SpecView` per approved
spec, and passes in today's date. ``run_phase._collect_obligations`` is that caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

if TYPE_CHECKING:  # Annotations only — nothing here calls into stats at runtime.
    from stats import PlannedUnit, UnitLedger

UNBUILT_UNIT = "unbuilt_unit"
STALE_STATUS = "stale_status"
EVIDENCE_FOLLOW_UP = "evidence_follow_up"
EVIDENCE_OVERDUE = "evidence_overdue"

# Both the dashboard and the brief use this order.
RANK = (STALE_STATUS, EVIDENCE_FOLLOW_UP, EVIDENCE_OVERDUE, UNBUILT_UNIT)

# What a spec's evidence file is called, and the placeholder its skeleton is full of until
# somebody fills it in. Shared with the spec-verification suite by convention rather than
# by import: that suite deliberately depends on no Studio code.
EVIDENCE_SUFFIX = "-eval-results.md"
EVIDENCE_PLACEHOLDER = "FILL_ME"

# The heading under each group of obligations in the dashboard. The list is sorted by RANK,
# so a group is however many obligations of one kind sit together in it.
_KIND_HEADINGS = {
    STALE_STATUS: "Finished but still `approved` — waiting for /sprint-review",
    EVIDENCE_FOLLOW_UP: "Evidence needs follow-up",
    EVIDENCE_OVERDUE: "Evidence overdue — the results file is still blank",
    UNBUILT_UNIT: "Planned and never built",
}


@dataclass(frozen=True)
class Obligation:
    """One thing this repository owes, derived — never stored.

    ``command`` is the exact line a reader can run, or ``""`` when discharging this is an
    edit rather than a command. ``silence`` is the exact line to write in the spec to close
    it on purpose without doing it, so the way out is always in front of the reader — the
    part of today's brief that people actually use. It is ``""`` for an obligation with no
    honest way out: a spec whose work is finished is either flipped or it is not.
    """

    kind: str
    subject: str  # a unit_id, or a spec slug for the spec-level kinds
    spec_file: str  # repo-relative path to the spec that defines it
    detail: str  # one plain sentence: what is owed, and why it is owed now
    command: str
    silence: str
    units_off_default_branch: Optional[Tuple[str, ...]] = None


class Evidence(Enum):
    BLANK = "blank"
    PASSED = "criterion met"
    FAILED = "criterion not met"
    INCONCLUSIVE = "inconclusive"
    UNCLEAR = "unclear"


_EVIDENCE_ACTIONS = {
    Evidence.FAILED: "shows the measurement failed — revise the spec or rerun the evaluation",
    Evidence.INCONCLUSIVE: "is inconclusive — resolve the uncertainty",
    Evidence.UNCLEAR: "has no clear verdict — clarify the declaration under `## Verdict`",
}


@dataclass(frozen=True)
class SpecView:
    """One approved spec, as the derivation needs to see it.

    Built by the caller that touches the filesystem, which is what keeps this module free
    of paths and of the question of where a repository keeps its specs.
    """

    slug: str
    spec_file: str
    status: str
    promises_evidence: bool  # True when the spec carries a `## Verification` section
    verification_due: str  # the raw frontmatter value; "" when there is none
    evidence: Evidence
    units: Tuple["PlannedUnit", ...]


def evidence_file_for(spec_file: str) -> str:
    """Where a spec keeps its evidence: ``<spec>-eval-results.md``, beside the spec.

    String work on a name, not a reading of a path, so both the caller checking whether the
    file is blank and the sentence telling a reader to fill it in name the same file.
    """
    stem = spec_file[: -len(".md")] if spec_file.endswith(".md") else spec_file
    return stem + EVIDENCE_SUFFIX


def derive(
    specs: Sequence[SpecView],
    ledger: "UnitLedger",
    *,
    today: date,
    merged_ids: Optional[set] = None,
) -> List[Obligation]:
    """Every obligation these inputs imply, sorted by RANK, then spec_file, then subject.

    Returns ``[]`` — never a guess — when ``ledger.built_known`` is False. With no built set
    every planned unit reads unbuilt and every spec reads unfinished, so silence beats a
    lie. This is the same call ``reconcile_units`` already makes, inherited rather than
    re-decided.
    """
    if not ledger.built_known:
        return []

    obligations = [_unbuilt_unit(unit) for unit in ledger.unbuilt]

    # A unit is still owed if the ledger put it in one of its outstanding states, dropped if
    # it closed on purpose, and built if it is in neither — the ledger reports built work by
    # nothing, which is the whole point of it. Keyed on the spec file as well as the id
    # because two specs can carry the same slug, and a spec's units are its own.
    still_owed = {_key(unit) for unit in ledger.unbuilt + ledger.escalated}
    dropped = {_key(unit) for unit in ledger.dropped}

    for spec in specs:
        if spec.status != "approved":
            continue
        follow_up = _completed_spec(spec, still_owed, dropped, merged_ids)
        if follow_up is not None:
            obligations.append(follow_up)
        overdue = _evidence_overdue(spec, today)
        if overdue is not None:
            obligations.append(overdue)

    return sorted(
        obligations,
        key=lambda owed: (RANK.index(owed.kind), owed.spec_file, owed.subject),
    )


def format_queue(obligations: Sequence[Obligation]) -> List[str]:
    """The queue as a person reads it: each obligation, and the way out under it.

    Obligations arrive sorted by kind, so a heading is printed whenever the kind changes
    and counts the run of obligations under it. A kind nothing owes gets no heading at all —
    a report that looks the same whether or not it has news is one people stop reading.
    """
    lines: List[str] = []
    current_kind = None
    for obligation in obligations:
        if obligation.kind != current_kind:
            current_kind = obligation.kind
            same_kind = sum(1 for owed in obligations if owed.kind == current_kind)
            lines.append(f"  {_KIND_HEADINGS[current_kind]}: {same_kind}")
        lines.append(f"    {obligation.detail}")
        if obligation.command:
            lines.append(f"      Run: {obligation.command}")
        if obligation.silence:
            lines.append(f"      Or close it on purpose: {obligation.silence}")
    return lines


def _key(unit: "PlannedUnit") -> Tuple[str, str]:
    """What identifies one planned unit: the spec that planned it, and its id."""
    return (unit.spec_file, unit.unit_id)


def _unbuilt_unit(unit: "PlannedUnit") -> Obligation:
    """A unit an approved spec planned that no commit says was built."""
    outcome = f' — "{unit.title}"' if unit.title else ""
    return Obligation(
        kind=UNBUILT_UNIT,
        subject=unit.unit_id,
        spec_file=unit.spec_file,
        detail=(
            f"`{unit.unit_id}`, planned by `{unit.slug}` in {unit.spec_file}, is not in any "
            f"commit{outcome}"
        ),
        command=f"/forge --spec {unit.spec_file} --unit {unit.unit_id}",
        silence=(
            f"open a PR adding `- **Dropped:** YYYY-MM-DD — <reason>` under that unit's "
            f"heading in {unit.spec_file}"
        ),
    )


def _completed_spec(
    spec: SpecView,
    still_owed: set,
    dropped: set,
    merged_ids: Optional[set],
) -> Optional[Obligation]:
    """A completed spec owes the action its promised verification supports.

    Empty or entirely dropped plans have no built work. Outstanding units (including
    escalations) still belong to the ledger. A blank record has its own deadline reminder.
    """
    if not spec.units:
        return None
    if any(_key(unit) in still_owed for unit in spec.units):
        return None
    if all(_key(unit) in dropped for unit in spec.units):
        return None
    if spec.promises_evidence:
        if spec.evidence is Evidence.BLANK:
            return None
        if spec.evidence is not Evidence.PASSED:
            return Obligation(
                kind=EVIDENCE_FOLLOW_UP,
                subject=spec.slug,
                spec_file=spec.spec_file,
                detail=(f"Evidence for `{spec.slug}` ({evidence_file_for(spec.spec_file)}) "
                        f"{_EVIDENCE_ACTIONS[spec.evidence]}"),
                command="",
                silence="",
            )
    units_off_default_branch = None
    if merged_ids is not None:
        units_off_default_branch = tuple(
            unit.unit_id for unit in spec.units
            if _key(unit) not in dropped and unit.unit_id not in merged_ids
        )
    return Obligation(
        kind=STALE_STATUS,
        subject=spec.slug,
        spec_file=spec.spec_file,
        detail=(
            f"every unit `{spec.slug}` plans in {spec.spec_file} is built or dropped and "
            f"nothing is waiting on evidence, but its frontmatter still says "
            f"`status: approved`. Leave the frontmatter alone: finished specs are reviewed "
            f"with the human and flipped together in one pull request"
        ),
        command="/sprint-review",
        silence="",
        units_off_default_branch=units_off_default_branch,
    )


def _evidence_overdue(spec: SpecView, today: date) -> Optional[Obligation]:
    """A spec past the date it promised evidence by, with the evidence file still blank."""
    due = parse_due(spec.verification_due)
    if due is None or due > today or spec.evidence is not Evidence.BLANK:
        return None
    return Obligation(
        kind=EVIDENCE_OVERDUE,
        subject=spec.slug,
        spec_file=spec.spec_file,
        detail=(
            f"`{spec.slug}` promised evidence by {due.isoformat()} and "
            f"{evidence_file_for(spec.spec_file)} is still blank — fill it in, replacing "
            f"every `{EVIDENCE_PLACEHOLDER}`"
        ),
        command="",
        silence=(
            f"move `verification_due` in {spec.spec_file} past today, which is an edit "
            f"anyone reviewing the spec can see"
        ),
    )


def parse_due(raw_value: str) -> Optional[date]:
    """The date a ``verification_due`` value names, or ``None`` if there isn't a readable one.

    The frontmatter template writes trailing comments after a value, and the frontmatter
    reader strips whitespace but not comments, so this can arrive as ``2026-09-30   # 30
    days from approval``. Everything from the first ``#`` on is a note to the reader.

    Malformed reads the same as missing, which is what rule 6 of the spec-verification suite
    already does with it: a date nothing can parse holds no deadline no matter how it got
    that way, and the suite is already red over that spec.
    """
    date_token = raw_value.split("#", 1)[0].strip()
    try:
        return date.fromisoformat(date_token)
    except ValueError:
        return None
