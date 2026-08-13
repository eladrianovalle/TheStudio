"""Build the automatic ``session.json`` health record for a finalized run.

A Studio run is a planning session, so rating its output at finalize is noise:
the specs get built later, elsewhere. What you *can* measure the moment a run
ends is session *health*: did the debate converge, did it surface and settle the
right questions, did it reduce uncertainty. All of that is derivable from files
the run already produced, with no human judgment. Nothing here waits for a
person or an agent to type a number in: a measurement that has to be volunteered
never gets volunteered.

This module is the pure core of that record. Like ``stats.py``, everything here
is data-in / data-out: no filesystem, no argparse, no path resolution. The
``run_phase`` finalize handler does the reading (contrarian verdicts, decisions,
clarity snapshots) and hands the collected pieces to
:func:`build_session_record`, which shapes them into the schema documented in
``docs/SESSION_ANALYTICS_PLAN.md``.

Every input is optional. A run with no decisions and no clarity snapshot still
produces a valid record full of sensible zeros and nulls. This must never crash
finalize.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence


def _summarize_decisions(decisions: Sequence) -> Dict:
    """Roll up decision points into the surfaced/answered breakdown.

    Each item is a DecisionPoint-like object with ``priority`` (P0/P1/P2),
    ``answer`` (None until settled), and ``answered_by`` ("user" or
    "assumption"). Attributes are read defensively so a plain namespace works
    in tests just as well as the real dataclass.

    ``p0_assumed`` is the signal that matters most: every blocking (P0) question
    the session answered by guessing rather than by asking.
    """
    surfaced = {"P0": 0, "P1": 0, "P2": 0}
    answered_by_user = 0
    answered_by_assumption = 0
    unanswered = 0
    p0_assumed = 0

    for decision in decisions:
        priority = getattr(decision, "priority", "P2")
        if priority in surfaced:
            surfaced[priority] += 1

        answer = getattr(decision, "answer", None)
        answered_by = getattr(decision, "answered_by", None)

        if answer is None:
            unanswered += 1
        elif answered_by == "assumption":
            answered_by_assumption += 1
            if priority == "P0":
                p0_assumed += 1
        else:
            # An answer with no explicit attribution counts as user-settled;
            # only an explicit "assumption" is a guess.
            answered_by_user += 1

    return {
        "surfaced": surfaced,
        "answered_by_user": answered_by_user,
        "answered_by_assumption": answered_by_assumption,
        "unanswered": unanswered,
        "p0_assumed": p0_assumed,
    }


def build_session_record(
    *,
    run_id: str,
    repo: str,
    phase: str,
    mode: str,
    finalized_iso: str,
    verdict: str,
    iterations: int = 0,
    max_iterations: int = 0,
    rejections: int = 0,
    decisions: Optional[Sequence] = None,
    clarity_mean_before: Optional[float] = None,
    clarity_mean_after: Optional[float] = None,
    clarity_topics_touched: int = 0,
) -> Dict:
    """Assemble the ``session.json`` record from already-gathered run data.

    Pure: no I/O. The caller reads the run directory and passes the pieces in;
    this returns the record dict per ``docs/SESSION_ANALYTICS_PLAN.md``. Every
    input is optional and tolerated: missing decisions or clarity yield sensible
    zeros and nulls rather than an error.

    Every field is counted from a file the run already produced, so the record
    is complete the moment finalize writes it and nobody is asked to fill
    anything in later.
    """
    decisions = decisions or []
    decision_summary = _summarize_decisions(decisions)

    return {
        "run_id": run_id,
        "repo": repo,
        "phase": phase,
        "mode": mode,
        "finalized_iso": finalized_iso,
        "verdict": verdict,
        "convergence": {
            "iterations": iterations,
            "max_iterations": max_iterations,
            "rejections": rejections,
        },
        "decisions": decision_summary,
        "clarity": {
            "mean_before": clarity_mean_before,
            "mean_after": clarity_mean_after,
            "topics_touched": clarity_topics_touched,
        },
    }
