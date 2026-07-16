"""
Independent second opinion on contrarian findings (Studio roadmap R1, Unit 2).

Unit 1 (findings.py) turned each contrarian flaw into a parseable Finding record
in findings.json. This module is the tested seam of the verifier that re-checks
the shaky ones. The rule that makes verification worth anything lives in the
Workflow shell (.claude/workflows/finding-verifier.js), not here: the checker is
a fresh agent shown ONLY the finding's quote and the demotion rules, never the
contrarian's reasoning. This module holds the pure, gate-testable pieces around
that firewall:

  - which findings are eligible for a second opinion (Medium only),
  - how a verdict maps to an adjusted confidence, and
  - writing those adjusted confidences back into findings.json.

Pure stdlib, patterned on findings.py / decision_points.py. The filesystem is
touched only in apply_verdicts_to_run, which round-trips through findings.json.
"""
from __future__ import annotations

from findings import Finding, load_findings_json, save_findings_json

# Verdict -> resulting confidence band when the caller does not pass one
# explicitly. 'uncertain' leaves the finding's own confidence untouched (it stays
# Medium), so it maps to None here and the current confidence is carried through.
_VERDICT_TO_CONFIDENCE: dict[str, str | None] = {
    "confirmed": "high",     # two voices agree -> promote
    "unconfirmed": "low",    # the second voice can't confirm the flaw -> demote
    "uncertain": None,       # not enough to move it -> unchanged (stays medium)
}


def select_findings_to_verify(findings: list[Finding]) -> list[Finding]:
    """Return only the findings eligible for an independent second opinion.

    MVI = Medium confidence only. High is already the most self-gated tier (the
    shipped contrarian gate defines High as "quoted and shown"), and Low is
    already demoted out of the main list, so re-checking either duplicates work.
    Medium is the tier literally tagged "verify this."
    """
    return [f for f in findings if f.confidence == "medium"]


def apply_verdict(
    finding: Finding,
    verdict: str,
    resulting_confidence: str | None = None,
) -> Finding:
    """Record a verifier's verdict on a finding and set its verified confidence.

    verdict is one of 'confirmed' | 'unconfirmed' | 'uncertain'. The resulting
    verified_confidence is the caller's resulting_confidence when passed, else it
    is derived from the verdict: confirmed -> 'high' (promoted), unconfirmed ->
    'low' (demoted), uncertain -> unchanged (the finding's current confidence).

    Mutates and returns the same Finding, mirroring how the finding record is the
    overlay that carries its own verified confidence (no separate artifact).
    """
    if verdict not in _VERDICT_TO_CONFIDENCE:
        raise ValueError(
            f"unknown verdict {verdict!r}; "
            f"expected one of {sorted(_VERDICT_TO_CONFIDENCE)}"
        )

    finding.verdict = verdict
    if resulting_confidence is not None:
        finding.verified_confidence = resulting_confidence
    else:
        derived = _VERDICT_TO_CONFIDENCE[verdict]
        # 'uncertain' derives None -> carry the finding's own confidence through,
        # so verified_confidence is always populated after a verdict.
        finding.verified_confidence = derived if derived is not None else finding.confidence
    return finding


def apply_verdicts_to_run(run_dir, verdicts: list[dict]) -> list[Finding]:
    """Load findings.json, apply the verifier verdicts, and write it back.

    verdicts is a list of records, each keyed to a finding by its position in the
    ordered findings.json list::

        {"index": 2, "verdict": "confirmed", "resulting_confidence": "high"}

    resulting_confidence is optional; when omitted it is derived from the verdict
    (see apply_verdict). Returns the updated Finding list (also persisted).
    """
    findings = load_findings_json(run_dir)
    for verdict_record in verdicts:
        index = verdict_record["index"]
        apply_verdict(
            findings[index],
            verdict_record["verdict"],
            verdict_record.get("resulting_confidence"),
        )
    save_findings_json(run_dir, findings)
    return findings
