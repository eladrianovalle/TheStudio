"""The spec-verification convention, enforced (see specs/prompt-feature-verification.md).

Some features are prose — a mandate, a blacklist, a passage giving a stuck writer
permission to stop. No pytest can tell you those broke, so their specs carry a
``## Verification`` section: a pass criterion written before the build, and a results
file beside the spec that has to be filled in before anyone says the feature works.

This file is what makes that claim cost evidence. Flip a spec to ``status: shipped``
while its results file still says ``FILL_ME`` and the suite goes red. So does dropping one
of the pre-written headings, or clearing a placeholder and leaving the skeleton's own
question sitting there with no answer under it.

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
REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "specs"
SPEC_COMMAND = REPO_ROOT / ".claude" / "commands" / "spec.md"

_STATUSES = {"draft", "approved", "shipped"}
_RESULTS_SUFFIX = "-eval-results.md"
_FILL = "FILL_ME"

# The four headings an evidence file is born with, stated once. /spec's skeleton prints these
# and rule 4 below requires them; `test_the_skeleton_prints_exactly_the_required_headings`
# holds the two lists to each other so neither side can drift out from under the other.
_REQUIRED_HEADINGS = (
    "## Pass criterion (written before the build)",
    "## What happened",
    "## What this doesn't prove",
    "## Verdict",
)

# The line the evidence skeleton opens with inside spec.md. Extraction has to be scoped to
# this block: spec.md also carries the *spec* template, whose headings are a different list.
_SKELETON_TITLE = "# <Feature> — Verification Results"


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


def _skeleton_block(command_text: str) -> list[str]:
    """The evidence skeleton /spec prints, lifted out of .claude/commands/spec.md.

    Scoped to the fenced block that opens with the results title and stopping at that
    fence's close, because spec.md also carries the spec template. Lines come back
    stripped: the skeleton sits two spaces indented inside a bullet, and that same
    normalization is what makes them comparable to an evidence file's own lines.
    """
    lines = [line.strip() for line in command_text.splitlines()]
    if _SKELETON_TITLE not in lines:
        return []
    block: list[str] = []
    for line in lines[lines.index(_SKELETON_TITLE):]:
        if line.startswith("```"):
            break
        block.append(line)
    return block


def _printed_lines(skeleton_lines: list[str]) -> frozenset[str]:
    """Every non-blank, non-heading line /spec's evidence skeleton prints under a heading.

    These are the lines an evidence file is born with — the questions, the guidance, the empty
    table, the placeholders. Not one of them is somebody's finding. Takes the block
    ``_skeleton_block`` already found, so the fence scoping happens in exactly one place.
    """
    printed: set[str] = set()
    in_section = False
    for line in skeleton_lines:
        if line.startswith("#"):
            # The title, and the preamble under it, sit outside every section.
            in_section = line.startswith("## ")
            continue
        if in_section and line:
            printed.add(line)
    return frozenset(printed)


def _preamble_rules(skeleton_lines: list[str]) -> str:
    """The paragraph stating the rules, from the top matter above the first section.

    Everything above the first `## ` is preamble; its last paragraph is the one that tells
    the reader what filling this file in requires. Taken structurally rather than by its
    opening words, so a reword still lands in the same place.
    """
    preamble: list[str] = []
    for line in skeleton_lines[1:]:
        if line.startswith("## "):
            break
        preamble.append(line)
    paragraphs = "\n".join(preamble).strip().split("\n\n")
    return paragraphs[-1].strip() if paragraphs else ""


def _section_body(results_text: str, heading: str) -> str | None:
    """Everything under `heading` up to the next heading, or None if the heading isn't there."""
    lines = results_text.splitlines()
    stripped = [line.strip() for line in lines]
    if heading not in stripped:
        return None
    body: list[str] = []
    for line in lines[stripped.index(heading) + 1:]:
        if line.strip().startswith("#"):
            break
        body.append(line)
    return "\n".join(body)


def _own_words(body: str, printed: frozenset[str]) -> bool:
    """Whether anything under this heading was written by the reporter.

    A line the skeleton printed is not a report; neither is a blank one. Whatever survives
    that, someone typed on purpose.
    """
    return any(line.strip() and line.strip() not in printed for line in body.splitlines())


_SKELETON_LINES = _skeleton_block(SPEC_COMMAND.read_text(encoding="utf-8"))
_PRINTED_LINES = _printed_lines(_SKELETON_LINES)
_PREAMBLE_RULES = _preamble_rules(_SKELETON_LINES)


def _violations(
    spec_name: str,
    spec_text: str,
    results_name: str,
    results_text: str | None,
) -> list[str]:
    """Every way this spec breaks the convention, in plain sentences.

    ``results_text`` is ``None`` when the results file does not exist. Four rules, and
    rules 2 to 4 stay quiet unless the spec actually has a Verification section — that
    tolerance is what leaves a spec with no prose-shaped behavior alone.
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

    # Rule 4: a claim costs the whole shape. Every required heading must still be there, and
    # each must carry at least one line the reporter wrote rather than one the skeleton printed.
    # An independent `if`, not an `elif` after rule 3: this function returns a list precisely so
    # one CI run tells you everything that is wrong. `approved` stays untouched — a hollow
    # skeleton there is the pre-registration the whole convention rests on.
    if promised_evidence and status == "shipped" and results_text is not None:
        for heading in _REQUIRED_HEADINGS:
            body = _section_body(results_text, heading)
            if body is None:
                problems.append(
                    f"specs/{spec_name} is marked `status: shipped`, but {results_name} no longer "
                    f"has '{heading}'. These headings were written before the data existed so they "
                    "could not be dropped once the data turned out inconvenient. Either put the "
                    "section back and answer it, or set this spec back to `status: approved`."
                )
            elif not _own_words(body, _PRINTED_LINES):
                problems.append(
                    f"specs/{spec_name} is marked `status: shipped`, but nothing under '{heading}' "
                    f"in {results_name} was written by you — every line there is one /spec's "
                    "skeleton printed, so the section is still asking its question with no answer "
                    "under it. Either write what you actually found, or set this spec back to "
                    "`status: approved`."
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
    f"{_FILL}\n\n"
    "## Verdict\n\n"
    f"{_FILL}\n"
)

# Pulled out so the fixtures below can swap one section at a time and stay readable.
_FILLED_CRITERION = "This works if and only if something observable happens.\n"
_FILLED_LIMITS = "Three runs is a small sample, and the same author read all six outputs.\n"

_FILLED = (
    "# Synthetic — Verification Results\n\n"
    "## Pass criterion (written before the build)\n\n"
    f"{_FILLED_CRITERION}\n"
    "## What happened\n\n"
    "| Condition | What was run | Criterion met |\n"
    "|---|---|---|\n"
    "| Baseline (feature off) | three runs, feature off | no |\n"
    "| With the feature | three runs, feature on | yes |\n\n"
    "## What this doesn't prove\n\n"
    f"{_FILLED_LIMITS}\n"
    "## Verdict\n\n"
    "Criterion met — the effect held in all three runs.\n"
)

# The skeleton's own guidance under "What this doesn't prove", with the placeholder cleared and
# nothing written in its place. That is the easiest route to a green suite with nothing reported,
# and the one rule 4 exists to close. Taken from the real skeleton rather than retyped, so the
# hollow case below cannot quietly drift into a paraphrase that proves nothing.
_SKELETON_TEXT = "\n".join(_SKELETON_LINES)
_UNANSWERED = "".join(
    f"{line}\n"
    for line in (_section_body(_SKELETON_TEXT, "## What this doesn't prove") or "").splitlines()
    if line.strip() and _FILL not in line
)

# Each of these differs from `_FILLED` in exactly one section, so the case it proves is obvious.
_HOLLOW = _FILLED.replace(_FILLED_LIMITS, _UNANSWERED)
_MISSING_HEADING = _FILLED.replace(f"## What this doesn't prove\n\n{_FILLED_LIMITS}\n", "")
_ANSWER_AS_BLOCKQUOTE = _FILLED.replace(_FILLED_LIMITS, f"> {_FILLED_LIMITS}")
_CRITERION_AS_BLOCKQUOTE = _FILLED.replace(_FILLED_CRITERION, f"> {_FILLED_CRITERION}")


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

    def test_the_skeleton_block_is_findable_and_prints_body_lines(self):
        """Rule 4 leans on finding this block, and both ways of losing it are silent.

        If extraction came back empty, every line in every evidence file would count as the
        reporter's own words and rule 4 would stop firing while the suite stayed green. So
        moving or renaming that fence has to turn the tree red instead.
        """
        assert _SKELETON_LINES, (
            f"{_SKELETON_TITLE!r} is no longer in {SPEC_COMMAND.name} — has the evidence "
            "skeleton moved or been retitled? Rule 4 cannot tell boilerplate from a report "
            "without it, and would pass everything."
        )
        assert _PRINTED_LINES, (
            f"the skeleton in {SPEC_COMMAND.name} was found but prints no lines under any of "
            "its headings, so rule 4 would read every line of an evidence file as a finding."
        )
        assert _UNANSWERED.strip(), (
            "the skeleton prints no guidance under \"What this doesn't prove\", so the "
            "unanswered-section case below has nothing to be unanswered with."
        )

    def test_every_copy_of_the_skeleton_preamble_matches_the_live_one(self):
        """The preamble lives by hand in more than one file, and nothing synced them.

        `.claude/commands/spec.md` is the one the tests read and the one `/spec` prints, so it
        is the source. Every evidence file quotes the same paragraph, and the spec that defines
        the convention transcribes the whole skeleton. Reword the source and those copies go on
        stating a rule that no longer exists, with the suite green — which is how the spec's own
        transcription came to describe the honour system rule 4 replaced with a test.
        """
        assert _PREAMBLE_RULES, (
            f"no rules paragraph found above the first section of the skeleton in "
            f"{SPEC_COMMAND.name}; the copies below cannot be checked against anything."
        )
        assert "status: shipped" in _PREAMBLE_RULES, (
            f"the skeleton's rules paragraph in {SPEC_COMMAND.name} no longer mentions "
            "`status: shipped`, so it has stopped naming when these rules bite. Either the "
            "wording drifted or the preamble's last paragraph is no longer the rules."
        )

        transcribers = [
            path
            for path in sorted(SPECS_DIR.glob("*.md"))
            if _SKELETON_TITLE in path.read_text(encoding="utf-8")
        ]
        for path in transcribers:
            assert _PREAMBLE_RULES in path.read_text(encoding="utf-8"), (
                f"specs/{path.name} transcribes the evidence skeleton but its rules paragraph "
                f"no longer matches {SPEC_COMMAND.name}. Update the copy, or stop copying it."
            )

        for results in sorted(SPECS_DIR.glob(f"*{_RESULTS_SUFFIX}")):
            assert _PREAMBLE_RULES in results.read_text(encoding="utf-8"), (
                f"specs/{results.name} states different rules than the skeleton in "
                f"{SPEC_COMMAND.name} prints. An evidence file that quotes a rule the skeleton "
                "no longer states tells its reporter the wrong thing about what filling it in "
                "requires."
            )

    def test_the_skeleton_prints_exactly_the_required_headings(self):
        """The heading list, agreed both ways — two documents that must match.

        A heading required here but no longer printed means every new evidence file is born
        failing. A heading printed but not required here can be deleted for free at `shipped`.
        """
        printed_headings = [line for line in _SKELETON_LINES if line.startswith("## ")]
        assert printed_headings == list(_REQUIRED_HEADINGS), (
            f"the skeleton in {SPEC_COMMAND.name} prints {printed_headings}, but rule 4 "
            f"requires {list(_REQUIRED_HEADINGS)}. Change both or neither."
        )

    def test_unfilled_sections_are_regenerable_from_the_skeleton(self):
        """A section still holding a placeholder has not been reported in, so every other line
        in it came from the template. One that didn't means this file was built from a skeleton
        that has since changed — and rule 4 would read that stale line as somebody's finding.
        """
        for results in sorted(SPECS_DIR.glob(f"*{_RESULTS_SUFFIX}")):
            text = results.read_text(encoding="utf-8")
            for heading in _REQUIRED_HEADINGS:
                body = _section_body(text, heading)
                if body is None or _FILL not in body:
                    continue
                for line in body.splitlines():
                    stray = line.strip()
                    if not stray or stray in _PRINTED_LINES:
                        continue
                    pytest.fail(
                        f"{results.name} still has {_FILL} under '{heading}', so nothing there "
                        f"has been reported yet — but {stray!r} is not a line the skeleton in "
                        f"{SPEC_COMMAND.name} prints. Rebuild that section from the skeleton as "
                        "it stands now, or put the guidance line back the way it prints."
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
        # Rule 4 also has plenty to say about an untouched skeleton at `shipped`, so pick out
        # the placeholder complaint rather than asserting it is the only one.
        placeholders = [problem for problem in problems if _FILL in problem]
        assert len(placeholders) == 1
        # Two honest exits, so nobody is cornered into deleting this test to get green.
        assert "fill it in" in placeholders[0]
        assert "`status: approved`" in placeholders[0]

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

    def test_shipped_with_a_required_heading_deleted_fails(self):
        """Deleting a section is the cheapest route past a rule that only counts placeholders."""
        problems = _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _MISSING_HEADING,
        )
        assert len(problems) == 1
        assert "no longer has '## What this doesn't prove'" in problems[0]
        # The same two honest exits rule 3 offers.
        assert "put the section back and answer it" in problems[0]
        assert "`status: approved`" in problems[0]

    def test_shipped_with_an_unanswered_section_fails(self):
        """The easier route: clear the placeholder, leave the skeleton's question, write nothing.

        There is not a single placeholder left in this file, so rule 3 has nothing to say — the
        heading is present and the section still looks full.
        """
        assert _FILL not in _HOLLOW
        problems = _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _HOLLOW,
        )
        assert len(problems) == 1
        assert "nothing under '## What this doesn't prove'" in problems[0]
        assert "was written by you" in problems[0]
        assert "write what you actually found" in problems[0]
        assert "`status: approved`" in problems[0]

    def test_an_answer_written_as_a_blockquote_passes(self):
        """Excluding blockquotes was designed and rejected: reporters are allowed the shape."""
        assert _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _ANSWER_AS_BLOCKQUOTE,
        ) == []

    def test_a_copied_criterion_written_as_a_blockquote_passes(self):
        """The one real evidence file quotes its criterion, so the rule meant to protect it
        must not fail it — the reason the blockquote exclusion was thrown out."""
        assert _violations(
            "synthetic.md", _synthetic_spec("shipped", verification=True),
            "synthetic-eval-results.md", _CRITERION_AS_BLOCKQUOTE,
        ) == []
