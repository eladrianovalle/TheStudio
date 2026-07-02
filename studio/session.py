"""Build the automatic ``session.json`` health record for a finalized run.

A Studio run is a planning session, so rating its output at finalize is noise:
the specs get built later, elsewhere. What you *can* measure the moment a run
ends is session *health*: did the debate converge, did it surface and settle the
right questions, did it reduce uncertainty, and at what cost. All of that is
derivable from files the run already produced, with no human judgment.

This module is the pure core of that record. Like ``stats.py``, everything here
is data-in / data-out: no filesystem, no argparse, no path resolution. The
``run_phase`` finalize handler does the reading (contrarian verdicts, decisions,
clarity snapshots, metrics, advocate word counts) and hands the collected pieces
to :func:`build_session_record`, which shapes them into the schema documented in
``docs/SESSION_ANALYTICS_PLAN.md``.

Every input is optional. A run with no decisions, no clarity snapshot, and no
metrics still produces a valid record full of sensible zeros and nulls. This
must never crash finalize.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from stats import _summarize_metrics


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


def _summarize_cost(metrics_entries: List[Dict], settled_decisions: int) -> Dict:
    """Roll up the cost block, reusing ``stats._summarize_metrics``.

    ``tokens_per_settled_decision`` turns a raw token count into "what the spend
    bought": total tokens divided by the number of decisions that ended up
    answered. It is None when nothing was settled (dividing by zero buys
    nothing). ``scope_pct`` reports each scope's share of the total tokens as a
    whole-number percentage; a run that burned most of its budget in polish is a
    misallocation worth seeing.
    """
    summary = _summarize_metrics(metrics_entries)
    total_tokens = summary["total_tokens"]

    scope_pct: Dict[str, int] = {}
    if total_tokens:
        for scope, data in summary["by_scope"].items():
            scope_pct[scope] = round(100 * data["total_tokens"] / total_tokens)

    if settled_decisions:
        tokens_per_settled = round(total_tokens / settled_decisions)
    else:
        tokens_per_settled = None

    return {
        "total_tokens": total_tokens,
        "duration_ms": summary["total_duration_ms"],
        "agents": summary["agents"],
        "tokens_per_settled_decision": tokens_per_settled,
        "scope_pct": scope_pct,
    }


def _summarize_editor(advocate_word_counts: Sequence[int]) -> Dict:
    """Roll up the editor-liveness block from advocate doc word counts.

    ``advocate_word_counts`` is the word count of each advocate document in the
    order it was written (first draft first, final last). ``shrink_ratio`` is
    how much the doc shrank from first to final: 0.33 means a third was cut.
    It is a crude liveness check, not a quality score. It catches the real
    failure mode: a dead editor mandate where docs only ever grow.

    Shrink is 0.0 when there is no first draft to measure against, which also
    guards the divide-by-zero when the first draft is empty.
    """
    counts = list(advocate_word_counts)
    if not counts:
        return {"first_draft_words": 0, "final_words": 0, "shrink_ratio": 0.0}

    first_draft_words = counts[0]
    final_words = counts[-1]
    if first_draft_words:
        shrink_ratio = round(1 - (final_words / first_draft_words), 4)
    else:
        shrink_ratio = 0.0

    return {
        "first_draft_words": first_draft_words,
        "final_words": final_words,
        "shrink_ratio": shrink_ratio,
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
    metrics_entries: Optional[List[Dict]] = None,
    advocate_word_counts: Optional[Sequence[int]] = None,
) -> Dict:
    """Assemble the ``session.json`` record from already-gathered run data.

    Pure: no I/O. The caller reads the run directory and passes the pieces in;
    this returns the record dict per ``docs/SESSION_ANALYTICS_PLAN.md``. Every
    input is optional and tolerated: missing decisions, clarity, or metrics
    yield sensible zeros and nulls rather than an error.

    ``outcome`` starts null and is the only field a human ever edits later (to
    record whether the plan actually got built); the rest is judgment-free.
    """
    decisions = decisions or []
    metrics_entries = metrics_entries or []
    advocate_word_counts = advocate_word_counts or []

    decision_summary = _summarize_decisions(decisions)
    settled_decisions = (
        decision_summary["answered_by_user"]
        + decision_summary["answered_by_assumption"]
    )

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
        "cost": _summarize_cost(metrics_entries, settled_decisions),
        "editor": _summarize_editor(advocate_word_counts),
        "outcome": None,
    }
