"""Tests for the independent finding verifier (Unit 2 core).

Tests cover:
  - select_findings_to_verify: filters to Medium only (High/Low skipped)
  - apply_verdict: confirmed->high, unconfirmed->low, uncertain->unchanged,
    explicit resulting_confidence override, unknown verdict rejected
  - apply_verdicts_to_run: round trip through findings.json (write, apply, reload)
"""
import pytest

from findings import Finding, load_findings_json, save_findings_json
from verifier import (
    apply_verdict,
    apply_verdicts_to_run,
    select_findings_to_verify,
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

    def test_explicit_resulting_confidence_wins(self):
        f = _finding("medium")
        apply_verdict(f, "confirmed", resulting_confidence="medium")

        assert f.verdict == "confirmed"
        # Explicit override beats the confirmed->high derivation.
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

    def test_explicit_resulting_confidence_round_trips(self, tmp_path):
        save_findings_json(tmp_path, [_finding("medium")])

        apply_verdicts_to_run(
            tmp_path,
            [{"index": 0, "verdict": "uncertain", "resulting_confidence": "high"}],
        )

        reloaded = load_findings_json(tmp_path)
        assert reloaded[0].verdict == "uncertain"
        assert reloaded[0].verified_confidence == "high"

    def test_no_verdicts_leaves_findings_untouched(self, tmp_path):
        save_findings_json(tmp_path, [_finding("medium")])

        apply_verdicts_to_run(tmp_path, [])

        reloaded = load_findings_json(tmp_path)
        assert reloaded[0].verdict is None
        assert reloaded[0].verified_confidence is None
