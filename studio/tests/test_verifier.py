"""Tests for the independent finding verifier (Unit 2 core).

Tests cover:
  - select_findings_to_verify / select_rows_for_run: filter to Medium only
    (High/Low skipped), and the Select rows expose only {index, quote}
  - apply_verdict: confirmed->high, unconfirmed->low, uncertain->unchanged,
    unknown verdict rejected (confidence derives from the verdict alone)
  - apply_verdicts_to_run: round trip through findings.json (write, apply, reload)
"""
import pytest

from findings import Finding, load_findings_json, save_findings_json
from verifier import (
    apply_verdict,
    apply_verdicts_to_run,
    select_findings_to_verify,
    select_rows_for_run,
)


def _finding(confidence, flaw="Some flaw"):
    return Finding(
        confidence=confidence,
        flaw=flaw,
        quote=f"`x.py:1` — \"{flaw}\"",
        impact="Something breaks.",
    )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class TestSelectFindingsToVerify:
    """Only Medium-confidence findings are eligible for a second opinion."""

    def test_selects_only_medium(self):
        findings = [
            _finding("high", "high flaw"),
            _finding("medium", "medium flaw"),
            _finding("low", "low flaw"),
            _finding("medium", "another medium"),
        ]
        selected = select_findings_to_verify(findings)

        assert len(selected) == 2
        assert [f.flaw for f in selected] == ["medium flaw", "another medium"]

    def test_no_medium_returns_empty(self):
        findings = [_finding("high"), _finding("low")]
        assert select_findings_to_verify(findings) == []

    def test_empty_input(self):
        assert select_findings_to_verify([]) == []


# ---------------------------------------------------------------------------
# Verdict application
# ---------------------------------------------------------------------------

class TestApplyVerdict:
    """Verdict -> verified_confidence transitions."""

    def test_confirmed_promotes_to_high(self):
        f = _finding("medium")
        apply_verdict(f, "confirmed")

        assert f.verdict == "confirmed"
        assert f.verified_confidence == "high"

    def test_unconfirmed_demotes_to_low(self):
        f = _finding("medium")
        apply_verdict(f, "unconfirmed")

        assert f.verdict == "unconfirmed"
        assert f.verified_confidence == "low"

    def test_uncertain_leaves_confidence_unchanged(self):
        f = _finding("medium")
        apply_verdict(f, "uncertain")

        assert f.verdict == "uncertain"
        # Original confidence is untouched, and verified mirrors it (stays medium).
        assert f.confidence == "medium"
        assert f.verified_confidence == "medium"

    def test_returns_same_finding(self):
        f = _finding("medium")
        assert apply_verdict(f, "confirmed") is f

    def test_unknown_verdict_raises(self):
        f = _finding("medium")
        with pytest.raises(ValueError):
            apply_verdict(f, "maybe")


# ---------------------------------------------------------------------------
# Write-back round trip
# ---------------------------------------------------------------------------

class TestApplyVerdictsToRun:
    """apply_verdicts_to_run round-trips through findings.json."""

    def test_round_trip_updates_verified_confidence(self, tmp_path):
        findings = [
            _finding("medium", "flaw zero"),
            _finding("high", "flaw one"),
            _finding("medium", "flaw two"),
        ]
        save_findings_json(tmp_path, findings)

        verdicts = [
            {"index": 0, "verdict": "confirmed"},
            {"index": 2, "verdict": "unconfirmed"},
        ]
        returned = apply_verdicts_to_run(tmp_path, verdicts)

        # Returned list reflects the applied verdicts.
        assert returned[0].verified_confidence == "high"
        assert returned[2].verified_confidence == "low"

        # And the write-back persisted, so a fresh reload sees the same.
        reloaded = load_findings_json(tmp_path)
        assert reloaded[0].verdict == "confirmed"
        assert reloaded[0].verified_confidence == "high"
        assert reloaded[2].verdict == "unconfirmed"
        assert reloaded[2].verified_confidence == "low"

        # The untouched High finding keeps its unset verifier fields.
        assert reloaded[1].verdict is None
        assert reloaded[1].verified_confidence is None

    def test_no_verdicts_leaves_findings_untouched(self, tmp_path):
        save_findings_json(tmp_path, [_finding("medium")])

        apply_verdicts_to_run(tmp_path, [])

        reloaded = load_findings_json(tmp_path)
        assert reloaded[0].verdict is None
        assert reloaded[0].verified_confidence is None


# ---------------------------------------------------------------------------
# The Select step — the real Python the JS shell shells out to. Covering it here
# is the point: the shell's generated `python -c` string cannot be unit-tested,
# and the earlier inline version was invalid Python that only ran because the
# Select agent hand-repaired it (PR #66 review).
# ---------------------------------------------------------------------------

class TestSelectRowsForRun:
    """select_rows_for_run returns {index, quote} rows for the Medium findings."""

    def test_returns_index_and_quote_for_medium_only(self, tmp_path):
        save_findings_json(
            tmp_path,
            [
                _finding("medium", "flaw zero"),
                _finding("high", "flaw one"),
                _finding("medium", "flaw two"),
            ],
        )
        rows = select_rows_for_run(tmp_path)

        # The High finding (index 1) is excluded; the Medium ones keep their
        # original positions so the write-back can match verdicts back by index.
        assert rows == [
            {"index": 0, "quote": "`x.py:1` — \"flaw zero\""},
            {"index": 2, "quote": "`x.py:1` — \"flaw two\""},
        ]

    def test_accepts_a_str_path(self, tmp_path):
        # The Workflow shell passes sys.argv[1] — a str, not a Path. This is the
        # regression for the TypeError ('str' / 'str') the direct command hit.
        save_findings_json(tmp_path, [_finding("medium")])
        rows = select_rows_for_run(str(tmp_path))
        assert [r["index"] for r in rows] == [0]

    def test_no_medium_returns_empty(self, tmp_path):
        save_findings_json(tmp_path, [_finding("high"), _finding("low")])
        assert select_rows_for_run(tmp_path) == []

    def test_missing_findings_json_returns_empty(self, tmp_path):
        assert select_rows_for_run(tmp_path) == []
