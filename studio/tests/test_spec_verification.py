"""The spec-verification convention, enforced (see specs/prompt-feature-verification.md).

Some features are prose — a mandate, a blacklist, a passage giving a stuck writer
permission to stop. No pytest can tell you those broke, so their specs carry a
``## Verification`` section: a pass criterion written before the build, and a results
file beside the spec that has to be filled in before anyone says the feature works.

This file is what makes that claim cost evidence. Flip a spec to ``status: shipped``
while its results file still says ``FILL_ME`` and the suite goes red.

It is a separate file from ``test_doc_parity.py`` on purpose: that one asserts every
name the code defines is documented, while this one compares two documents to each
other. Same spirit, different contract.

Be straight about the limit: this enforces that a *claim* of verification is backed,
not that verification happened. The only trigger is a human typing ``shipped``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# CI runs pytest with `working-directory: studio`, so relative paths are out.
# parents[2] is the repo root — the same idiom test_claude_code.py uses.
SPECS_DIR = Path(__file__).resolve().parents[2] / "specs"

_STATUSES = {"draft", "approved", "shipped"}
_RESULTS_SUFFIX = "-eval-results.md"
_FILL = "FILL_ME"


def _spec_files(specs_dir: Path) -> list[Path]:
    """Every spec in the directory, excluding the results files that sit beside them."""
    return sorted(
        path for path in specs_dir.glob("*.md") if not path.name.endswith(_RESULTS_SUFFIX)
    )


def _frontmatter_status(spec_text: str) -> str:
    """The ``status:`` value from the spec's frontmatter, or ``""`` if there isn't one.

    Only the leading ``---`` block counts, so a spec that discusses statuses in its
    prose doesn't accidentally declare one.
    """
    match = re.match(r"---\n(.*?)\n---", spec_text, re.DOTALL)
    if not match:
        return ""
    status = re.search(r"(?m)^status:\s*(\S+)", match.group(1))
    return status.group(1) if status else ""


def _has_verification_section(spec_text: str) -> bool:
    """Whether the spec carries a ``## Verification`` section.

    Matched by prefix, not by line equality, so a heading someone widened to
    ``## Verification & Evidence`` is still gated. For a gate, the forgiving reading
    is the correct one.
    """
    return any(line.startswith("## Verification") for line in spec_text.splitlines())


def _section_of_first_fill(results_text: str) -> str:
    """The nearest heading above the first ``FILL_ME``, to point the failure somewhere."""
    heading = "(no heading)"
    for line in results_text.splitlines():
        if line.startswith("##"):
            heading = line.strip()
        if _FILL in line:
            return heading
    return heading


def _violations(
    spec_name: str,
    spec_text: str,
    results_name: str,
    results_text: str | None,
) -> list[str]:
    """Every way this spec breaks the convention, in plain sentences.

    ``results_text`` is ``None`` when the results file does not exist. Three rules,
    and rules 2 and 3 stay quiet unless the spec actually has a Verification section —
    that tolerance is what leaves a spec with no prose-shaped behavior alone.
    """
    problems: list[str] = []
    status = _frontmatter_status(spec_text)
    promised_evidence = _has_verification_section(spec_text)

    # Rule 1: known status. A typo (`Shipped`, `ship`, `done`) would otherwise switch
    # the two rules below off forever while the suite stayed green.
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

    return problems


def _synthetic_spec(status: str, *, verification: bool, heading: str = "## Verification") -> str:
    """A minimal spec body for the synthetic cases below.

    `heading` exists so one case can widen it and prove the prefix match is doing real work.
    """
    lines = ["---", "feature: Synthetic", "slug: synthetic", f"status: {status}", "---", ""]
    lines += ["# Synthetic — Architecture Spec", ""]
    if verification:
        lines += [
            heading,
            "",
            "- **Pass criterion.** This works if and only if something observable happens.",
            "",
        ]
    lines += ["## Build Plan", "", "1. Build it.", ""]
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
    f"{_FILL}\n"
)

_FILLED = (
    "# Synthetic — Verification Results\n\n"
    "## Pass criterion (written before the build)\n\n"
    "This works if and only if something observable happens.\n\n"
    "## What happened\n\n"
    "| Condition | What was run | Criterion met |\n"
    "|---|---|---|\n"
    "| Baseline (feature off) | three runs, feature off | no |\n"
    "| With the feature | three runs, feature on | yes |\n\n"
    "## What this doesn't prove\n\n"
    "Three runs is a small sample, and the same author read all six outputs.\n"
)


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
        assert len(problems) == 1
        assert _FILL in problems[0]
        # Two honest exits, so nobody is cornered into deleting this test to get green.
        assert "fill it in" in problems[0]
        assert "`status: approved`" in problems[0]

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
