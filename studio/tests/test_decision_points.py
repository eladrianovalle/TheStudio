"""Tests for decision point parsing, formatting, and extraction (T1.5).

Tests cover:
  - parse_decision_points: single/multiple/missing/malformed markers
  - format_decision_point / format_decisions_log: round-trip and grouping
  - extract_decisions_from_run: across flat, studio, and scoped file naming
  - build_instruction_doc: decision point protocol section presence
"""
import pytest

from decision_points import (
    DecisionPoint,
    extract_decisions_from_run,
    format_decision_point,
    format_decisions_log,
    parse_decision_points,
)


# ---------------------------------------------------------------------------
# Sample decision point text blocks (blockquote format)
# ---------------------------------------------------------------------------

SINGLE_P0 = """\
Some preamble text.

> **DECISION [P0]:** Should the social deduction mechanic be real-time or turn-based?
> **Unblocks:** Core loop design — these produce fundamentally different moment-to-moment gameplay
> **Options:** (a) Real-time (Among Us style) (b) Turn-based (Mafia style)

Some trailing text.
"""

MULTI_PRIORITY = """\
> **DECISION [P2]:** Which art style — pixel or hand-drawn?
> **Unblocks:** Art pipeline scheduling
> **Options:** (a) Pixel (b) Hand-drawn (c) 3D low-poly

> **DECISION [P0]:** Singleplayer or multiplayer first?
> **Unblocks:** Entire tech architecture
> **Options:** (a) Singleplayer (b) Multiplayer (c) Both simultaneously

> **DECISION [P1]:** What monetisation model?
> **Unblocks:** Business plan and GTM strategy
> **Options:** (a) Premium (b) F2P with battle pass (c) Subscription
"""

MISSING_OPTIONS = """\
> **DECISION [P0]:** Should we target mobile or PC first?
> **Unblocks:** SDK selection and input design
"""

EXTRA_WHITESPACE = """\
> **DECISION [P1]:**   How large should the starting map be?
> **Unblocks:**    Level design pipeline
> **Options:**  (a) Small  (b) Medium  (c) Large
"""

# Malformed: no blockquote prefix — should not be parsed
MALFORMED_NO_BLOCKQUOTE = """\
**DECISION [P0]:** Orphan decision without blockquote prefix
**Unblocks:** Nothing
**Options:** (a) A (b) B
"""

MALFORMED_MIXED = """\
> **DECISION [P0]:** Valid decision
> **Unblocks:** Something
> **Options:** (a) X (b) Y

**DECISION [P1]:** Invalid — no blockquote prefix
**Unblocks:** Nothing
"""


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

class TestParseDecisionPoints:
    """Tests for parse_decision_points()."""

    def test_parse_single_p0(self):
        """Parse a single P0 decision point from text."""
        results = parse_decision_points(SINGLE_P0)

        assert len(results) == 1
        dp = results[0]
        assert dp.priority == "P0"
        assert "real-time or turn-based" in dp.question
        assert "Core loop design" in dp.unblocks
        assert "Real-time" in dp.options
        assert "Turn-based" in dp.options

    def test_parse_multiple_sorted_by_priority(self):
        """Parse multiple decision points and verify sorted by priority (P0 first)."""
        results = parse_decision_points(MULTI_PRIORITY)

        assert len(results) == 3
        priorities = [dp.priority for dp in results]
        assert priorities == ["P0", "P1", "P2"]

    def test_parse_missing_options_field(self):
        """Parse succeeds when Options field is absent."""
        results = parse_decision_points(MISSING_OPTIONS)

        assert len(results) == 1
        dp = results[0]
        assert dp.priority == "P0"
        assert "mobile or PC" in dp.question
        assert dp.options is None

    def test_parse_extra_whitespace(self):
        """Parse handles extra whitespace in field values."""
        results = parse_decision_points(EXTRA_WHITESPACE)

        assert len(results) == 1
        dp = results[0]
        assert dp.priority == "P1"
        assert "map" in dp.question.lower()
        assert "Level design" in dp.unblocks

    def test_parse_no_decision_points(self):
        """Text with no decision point markers returns empty list."""
        results = parse_decision_points("Just a normal document with no markers.")
        assert results == []

    def test_parse_empty_string(self):
        """Empty string returns empty list."""
        results = parse_decision_points("")
        assert results == []

    def test_parse_malformed_no_blockquote(self):
        """Decision without blockquote prefix is not parsed."""
        results = parse_decision_points(MALFORMED_NO_BLOCKQUOTE)
        assert len(results) == 0

    def test_parse_malformed_mixed_valid_and_invalid(self):
        """Only properly formatted blockquotes are parsed; non-blockquotes skipped."""
        results = parse_decision_points(MALFORMED_MIXED)
        assert len(results) == 1
        assert results[0].priority == "P0"
        assert "Valid decision" in results[0].question

    def test_source_file_attribution(self):
        """source_file is set when provided."""
        results = parse_decision_points(SINGLE_P0, source_file="advocate--design--01.md")

        assert len(results) == 1
        assert results[0].source_file == "advocate--design--01.md"

    def test_source_file_default_none(self):
        """source_file defaults to None when not provided."""
        results = parse_decision_points(SINGLE_P0)
        assert results[0].source_file is None


# ---------------------------------------------------------------------------
# Format tests
# ---------------------------------------------------------------------------

class TestFormatDecisionPoint:
    """Tests for format_decision_point() and format_decisions_log()."""

    def test_format_round_trip(self):
        """parse -> format -> parse produces equivalent decision point."""
        original = parse_decision_points(SINGLE_P0)
        assert len(original) == 1

        formatted = format_decision_point(original[0])
        reparsed = parse_decision_points(formatted + "\n")

        assert len(reparsed) == 1
        assert reparsed[0].priority == original[0].priority
        assert reparsed[0].question == original[0].question
        assert reparsed[0].unblocks == original[0].unblocks

    def test_format_decisions_log_groups_by_priority(self):
        """format_decisions_log groups decisions under priority headings."""
        decisions = parse_decision_points(MULTI_PRIORITY)
        log = format_decisions_log(decisions)

        assert "P0" in log
        assert "P1" in log
        assert "P2" in log
        # P0 should appear before P1 which should appear before P2
        assert log.index("P0") < log.index("P1") < log.index("P2")

    def test_format_decisions_log_includes_source_file(self):
        """format_decisions_log includes source file attribution when present."""
        decisions = parse_decision_points(
            SINGLE_P0, source_file="advocate--design--01.md"
        )
        log = format_decisions_log(decisions)

        assert "advocate--design--01.md" in log


# ---------------------------------------------------------------------------
# Run extraction tests
# ---------------------------------------------------------------------------

class TestExtractDecisionsFromRun:
    """Tests for extract_decisions_from_run()."""

    def _write_file(self, directory, name, content):
        """Helper to write a file in a directory."""
        filepath = directory / name
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_extract_from_simple_advocate_contrarian(self, tmp_path):
        """Finds decisions across advocate_N.md and contrarian_N.md files."""
        run_dir = tmp_path / "run_market_20260318_100000"
        run_dir.mkdir()

        self._write_file(run_dir, "advocate_1.md", SINGLE_P0)
        self._write_file(
            run_dir,
            "contrarian_1.md",
            "> **DECISION [P1]:** Is 6 months enough for MVP?\n"
            "> **Unblocks:** Timeline planning\n"
            "> **Options:** (a) Yes (b) No, need 9 months\n",
        )

        results = extract_decisions_from_run(run_dir)

        assert len(results) == 2
        priorities = {dp.priority for dp in results}
        assert "P0" in priorities
        assert "P1" in priorities

    def test_extract_from_studio_naming(self, tmp_path):
        """Finds decisions in advocate--role--NN.md studio naming convention."""
        run_dir = tmp_path / "run_studio_20260318_100000"
        run_dir.mkdir()

        self._write_file(run_dir, "advocate--marketing--01.md", SINGLE_P0)
        self._write_file(
            run_dir,
            "advocate--design--01.md",
            "> **DECISION [P2]:** Top-down or isometric camera?\n"
            "> **Unblocks:** Art asset creation\n"
            "> **Options:** (a) Top-down (b) Isometric\n",
        )
        self._write_file(
            run_dir, "contrarian--marketing--01.md", "No decisions here."
        )

        results = extract_decisions_from_run(run_dir)

        assert len(results) == 2
        # Check source file attribution
        sources = {dp.source_file for dp in results}
        assert any("marketing" in s for s in sources if s)
        assert any("design" in s for s in sources if s)

    def test_extract_from_scoped_naming(self, tmp_path):
        """Finds decisions in advocate--role--S1-NN.md scoped naming convention."""
        run_dir = tmp_path / "run_studio_20260318_100000"
        run_dir.mkdir()

        self._write_file(run_dir, "advocate--design--S1-01.md", SINGLE_P0)
        self._write_file(
            run_dir,
            "contrarian--design--S2-01.md",
            "> **DECISION [P1]:** Should we prototype in Godot or Unity?\n"
            "> **Unblocks:** Engine setup and CI pipeline\n"
            "> **Options:** (a) Godot (b) Unity (c) Unreal\n",
        )

        results = extract_decisions_from_run(run_dir)

        assert len(results) == 2
        sources = {dp.source_file for dp in results}
        assert any("S1" in s for s in sources if s)
        assert any("S2" in s for s in sources if s)

    def test_extract_from_empty_run_directory(self, tmp_path):
        """Empty run directory returns empty list."""
        run_dir = tmp_path / "run_market_20260318_100000"
        run_dir.mkdir()

        results = extract_decisions_from_run(run_dir)
        assert results == []

    def test_extract_from_files_with_no_decisions(self, tmp_path):
        """Run directory with advocate/contrarian files but no decision points."""
        run_dir = tmp_path / "run_market_20260318_100000"
        run_dir.mkdir()

        self._write_file(run_dir, "advocate_1.md", "Just normal advocate output.")
        self._write_file(run_dir, "contrarian_1.md", "Just normal contrarian output.")

        results = extract_decisions_from_run(run_dir)
        assert results == []


# ---------------------------------------------------------------------------
# Instruction template tests
# ---------------------------------------------------------------------------

class TestInstructionDocDecisionSection:
    """Tests that build_instruction_doc includes or excludes the Decision Point Protocol."""

    @pytest.fixture
    def _prepare_run(self, studio_root):
        """Helper: prepare a run and return (run_dir, instructions_text)."""
        import run_phase
        from conftest import make_prepare_args

        def _inner(**kwargs):
            args = make_prepare_args(**kwargs)
            run_id = run_phase.prepare_run(args)
            run_dir = studio_root / "output" / args.phase / run_id
            instructions = (run_dir / "instructions.md").read_text(encoding="utf-8")
            return run_dir, instructions

        return _inner

    def test_instruction_doc_contains_decision_point_section(self, _prepare_run):
        """build_instruction_doc output contains 'Decision Point Protocol' section."""
        _, instructions = _prepare_run(phase="market", text="Test decision points")
        assert "Decision Point Protocol" in instructions

    def test_instruction_doc_question_mode_no_decision_section(self, _prepare_run):
        """build_instruction_doc in question mode does NOT contain decision point section."""
        _, instructions = _prepare_run(
            phase="market", text="Test question mode", mode="questions",
        )
        assert "Decision Point Protocol" not in instructions

    def test_decision_section_contains_priority_descriptions(self, _prepare_run):
        """Decision point section contains P0, P1, P2 priority level descriptions."""
        _, instructions = _prepare_run(phase="market", text="Test priorities")
        # Find the decision point section and check all priorities mentioned
        assert "P0" in instructions
        assert "P1" in instructions
        assert "P2" in instructions

    def test_decision_section_contains_example_format(self, _prepare_run):
        """Decision point section contains the DECISION blockquote example."""
        _, instructions = _prepare_run(phase="design", text="Test format example")
        assert "DECISION [P0]" in instructions
