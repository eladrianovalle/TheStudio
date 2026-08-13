"""Tests for the automatic session.json health record.

Covers session.build_session_record as a pure function over representative
run data, plus one check that finalize_run actually drops a session.json.
"""
from __future__ import annotations

import run_phase
from decision_points import DecisionPoint, save_decisions_json
from session import build_session_record
from conftest import make_finalize_args, make_prepare_args


def _decision(priority, answer=None, answered_by=None):
    return DecisionPoint(
        priority=priority,
        question=f"q-{priority}-{answer}",
        unblocks="something",
        answer=answer,
        answered_by=answered_by,
    )


# ---------------------------------------------------------------------------
# Pure build_session_record
# ---------------------------------------------------------------------------


def test_normal_studio_run_shapes_full_record():
    decisions = [
        _decision("P0", answer="use postgres", answered_by="user"),
        _decision("P1", answer="skip oauth", answered_by="user"),
        _decision("P1", answer="assume 100 users", answered_by="assumption"),
        _decision("P2"),  # unanswered
    ]

    record = build_session_record(
        run_id="run_studio_20260701_x",
        repo="Pictorly",
        phase="studio",
        mode="deliverables",
        finalized_iso="2026-07-01T00:00:00+00:00",
        verdict="APPROVED",
        iterations=3,
        max_iterations=4,
        rejections=2,
        decisions=decisions,
        clarity_mean_before=0.42,
        clarity_mean_after=0.71,
        clarity_topics_touched=3,
    )

    # Top-level identity + convergence
    assert record["run_id"] == "run_studio_20260701_x"
    assert record["repo"] == "Pictorly"
    assert record["verdict"] == "APPROVED"
    assert record["convergence"] == {"iterations": 3, "max_iterations": 4, "rejections": 2}

    # Decisions breakdown
    dec = record["decisions"]
    assert dec["surfaced"] == {"P0": 1, "P1": 2, "P2": 1}
    assert dec["answered_by_user"] == 2
    assert dec["answered_by_assumption"] == 1
    assert dec["unanswered"] == 1
    assert dec["p0_assumed"] == 0

    # Clarity delta passes through
    assert record["clarity"] == {"mean_before": 0.42, "mean_after": 0.71, "topics_touched": 3}

    # Nothing a human or an agent had to type in survives in the record.
    assert set(record) == {
        "run_id", "repo", "phase", "mode", "finalized_iso", "verdict",
        "convergence", "decisions", "clarity",
    }


def test_empty_inputs_yield_zeros_and_nulls():
    record = build_session_record(
        run_id="run_market_1",
        repo="repo",
        phase="market",
        mode="deliverables",
        finalized_iso="iso",
        verdict="UNKNOWN",
    )

    assert record["convergence"] == {"iterations": 0, "max_iterations": 0, "rejections": 0}
    assert record["decisions"] == {
        "surfaced": {"P0": 0, "P1": 0, "P2": 0},
        "answered_by_user": 0,
        "answered_by_assumption": 0,
        "unanswered": 0,
        "p0_assumed": 0,
    }
    assert record["clarity"] == {"mean_before": None, "mean_after": None, "topics_touched": 0}


def test_p0_answered_by_assumption_is_counted():
    decisions = [
        _decision("P0", answer="guessed the auth model", answered_by="assumption"),
        _decision("P0", answer="asked the user", answered_by="user"),
    ]

    dec = build_session_record(
        run_id="r", repo="repo", phase="tech", mode="deliverables",
        finalized_iso="iso", verdict="APPROVED", decisions=decisions,
    )["decisions"]

    assert dec["surfaced"]["P0"] == 2
    assert dec["answered_by_assumption"] == 1
    assert dec["answered_by_user"] == 1
    assert dec["p0_assumed"] == 1


def test_answer_without_attribution_counts_as_user():
    # An answer set but answered_by left None is a settled decision, not a guess.
    dec = build_session_record(
        run_id="r", repo="repo", phase="tech", mode="deliverables",
        finalized_iso="iso", verdict="APPROVED",
        decisions=[_decision("P1", answer="settled", answered_by=None)],
    )["decisions"]

    assert dec["answered_by_user"] == 1
    assert dec["answered_by_assumption"] == 0
    assert dec["unanswered"] == 0


def test_decision_counts_accumulate_and_priority_defaults():
    from types import SimpleNamespace

    decisions = [
        _decision("P0", answer="g1", answered_by="assumption"),
        _decision("P0", answer="g2", answered_by="assumption"),
        _decision("P1"),  # unanswered
        _decision("P1"),  # unanswered
        SimpleNamespace(answer=None),  # no priority attr -> defaults to P2, unanswered
    ]

    dec = build_session_record(
        run_id="r", repo="repo", phase="studio", mode="deliverables",
        finalized_iso="iso", verdict="APPROVED", decisions=decisions,
    )["decisions"]

    # Each counter must truly accumulate, not latch at 1.
    assert dec["answered_by_assumption"] == 2
    assert dec["p0_assumed"] == 2
    assert dec["unanswered"] == 3
    # The attribute-less decision falls back to the default P2 bucket.
    assert dec["surfaced"] == {"P0": 2, "P1": 2, "P2": 1}


# ---------------------------------------------------------------------------
# finalize_run wiring
# ---------------------------------------------------------------------------


def test_finalize_writes_session_json(studio_root, monkeypatch, capsys):
    # Some other test may leave a global artifact-root override set; clear it so
    # this run resolves to studio_root like the fixture intends.
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    run_id = run_phase.prepare_run(make_prepare_args(max_iterations=2))
    run_dir = studio_root / "output" / "market" / run_id

    # Two iterations: contrarian rejects once, then approves.
    (run_dir / "advocate_1.md").write_text("word " * 200, encoding="utf-8")
    (run_dir / "advocate_2.md").write_text("word " * 120, encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("Too thin.\nVERDICT: REJECTED\n", encoding="utf-8")
    (run_dir / "contrarian_2.md").write_text("Good enough.\nVERDICT: APPROVED\n", encoding="utf-8")
    (run_dir / "summary.md").write_text("Summary output", encoding="utf-8")

    save_decisions_json(run_dir, [
        _decision("P0", answer="settled it", answered_by="user"),
        _decision("P1", answer="guessed", answered_by="assumption"),
    ])

    run_phase.finalize_run(make_finalize_args(run_id=run_id))
    finalize_output = capsys.readouterr().out

    session = run_phase.load_json(run_dir / "session.json")

    # Every top-level key from the schema is present, and nothing else: each one
    # is counted from a file in the run directory.
    assert set(session) == {
        "run_id", "repo", "phase", "mode", "finalized_iso", "verdict",
        "convergence", "decisions", "clarity",
    }

    assert session["run_id"] == run_id
    assert session["phase"] == "market"
    assert session["verdict"] == "APPROVED"

    # Derived behaviorally from files on disk, not passed in.
    assert session["convergence"]["iterations"] == 2
    assert session["convergence"]["rejections"] == 1  # one REJECTED before the final APPROVED
    assert session["decisions"]["answered_by_user"] == 1
    assert session["decisions"]["answered_by_assumption"] == 1

    # run.json carries no aggregated agent metrics, and finalize says nothing
    # about them.
    assert "metrics" not in run_phase.load_json(run_dir / "run.json")
    assert "Agent metrics" not in finalize_output
