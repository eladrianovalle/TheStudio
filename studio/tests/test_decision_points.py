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
    format_settled_decisions,
    load_decisions_json,
    parse_decision_points,
    save_decisions_json,
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

# Alternate format: question inside bold (what agents naturally produce)
ALT_FORMAT_INSIDE_BOLD = """\
> **DECISION [P0]: When does the boss phase trigger?**
> **Unblocks:** Round progression design, endgame pacing
> **Options:** (a) After round 5 (b) After all enemies cleared
"""

ALT_FORMAT_MIXED = """\
> **DECISION [P0]:** Standard format question
> **Unblocks:** Something
> **Options:** (a) A (b) B

> **DECISION [P1]: Alt format question inside bold**
> **Unblocks:** Something else
> **Options:** (a) X (b) Y
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

    def test_parse_alt_format_question_inside_bold(self):
        """Parse decision point where question is inside the bold markers."""
        results = parse_decision_points(ALT_FORMAT_INSIDE_BOLD)
        assert len(results) == 1
        dp = results[0]
        assert dp.priority == "P0"
        assert "boss phase" in dp.question.lower()
        assert "Round progression" in dp.unblocks

    def test_parse_alt_format_mixed_with_standard(self):
        """Parse both standard and alt format decision points in the same text."""
        results = parse_decision_points(ALT_FORMAT_MIXED)
        assert len(results) == 2
        assert results[0].priority == "P0"
        assert results[1].priority == "P1"

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


# ---------------------------------------------------------------------------
# Answer-aware features tests (M2 T2.1/T2.3)
# ---------------------------------------------------------------------------

class TestDecisionPointAnswerFields:
    """Tests for the answer and answered_by fields on DecisionPoint."""

    def test_answer_fields_default_none(self):
        """New DecisionPoint has answer=None and answered_by=None by default."""
        dp = DecisionPoint(priority="P0", question="Q?", unblocks="U")
        assert dp.answer is None
        assert dp.answered_by is None

    def test_answer_fields_set(self):
        """DecisionPoint with answer and answered_by set explicitly."""
        dp = DecisionPoint(
            priority="P1",
            question="Turn-based?",
            unblocks="Core loop",
            answer="Yes",
            answered_by="user",
        )
        assert dp.answer == "Yes"
        assert dp.answered_by == "user"


class TestFormatSettledDecisions:
    """Tests for format_settled_decisions()."""

    def _make_dp(self, priority="P0", question="Q?", unblocks="U",
                 answer=None, answered_by=None, source_file=None):
        return DecisionPoint(
            priority=priority,
            question=question,
            unblocks=unblocks,
            answer=answer,
            answered_by=answered_by,
            source_file=source_file,
        )

    def test_format_settled_only_answered(self):
        """Only decisions with answers appear in the output."""
        decisions = [
            self._make_dp(question="Answered?", answer="Yes", answered_by="user"),
            self._make_dp(question="Not answered?"),
        ]
        result = format_settled_decisions(decisions)
        assert "Answered?" in result
        assert "Not answered?" not in result

    def test_format_settled_empty(self):
        """No answered decisions produces minimal output."""
        decisions = [self._make_dp(question="Unanswered")]
        result = format_settled_decisions(decisions)
        assert "No decisions have been answered yet" in result

    def test_format_settled_table_format(self):
        """Table row count matches answered decisions."""
        decisions = [
            self._make_dp(question="Q1", answer="A1", answered_by="user"),
            self._make_dp(question="Q2", answer="A2", answered_by="user"),
            self._make_dp(question="Q3"),  # no answer
        ]
        result = format_settled_decisions(decisions)
        # Count data rows in the table (lines starting with "| " and a digit)
        table_rows = [line for line in result.splitlines()
                      if line.startswith("| ") and line[2:3].isdigit()]
        assert len(table_rows) == 2

    def test_format_settled_includes_metadata(self):
        """Output includes answer, answered_by, and source metadata."""
        dp = self._make_dp(
            question="Real-time or turn-based?",
            answer="Turn-based",
            answered_by="user",
            source_file="advocate--design--S1-01.md",
        )
        result = format_settled_decisions([dp])
        assert "Turn-based" in result
        assert "user" in result
        assert "advocate--design--S1-01.md" in result


class TestSaveLoadDecisionsJson:
    """Tests for save_decisions_json() and load_decisions_json()."""

    def test_save_and_load_round_trip(self, tmp_path):
        """Save decisions, load them back, verify equal."""
        decisions = [
            DecisionPoint(
                priority="P0",
                question="Real-time?",
                unblocks="Core loop",
                options=["Real-time", "Turn-based"],
                source_file="advocate_1.md",
            ),
            DecisionPoint(
                priority="P1",
                question="Art style?",
                unblocks="Art pipeline",
            ),
        ]
        save_decisions_json(tmp_path, decisions)
        loaded = load_decisions_json(tmp_path)

        assert len(loaded) == 2
        assert loaded[0].priority == "P0"
        assert loaded[0].question == "Real-time?"
        assert loaded[0].options == ["Real-time", "Turn-based"]
        assert loaded[1].priority == "P1"
        assert loaded[1].options is None

    def test_load_missing_file(self, tmp_path):
        """Returns empty list when decisions.json does not exist."""
        result = load_decisions_json(tmp_path)
        assert result == []

    def test_save_with_answers(self, tmp_path):
        """Decisions with answer fields persist correctly."""
        decisions = [
            DecisionPoint(
                priority="P0",
                question="Multiplayer?",
                unblocks="Architecture",
                answer="Yes",
                answered_by="user",
            ),
        ]
        save_decisions_json(tmp_path, decisions)
        loaded = load_decisions_json(tmp_path)

        assert loaded[0].answer == "Yes"
        assert loaded[0].answered_by == "user"

    def test_load_without_answer_fields(self, tmp_path):
        """Backward compat: old JSON without answer/answered_by loads with None."""
        import json
        old_data = [
            {
                "priority": "P0",
                "question": "Old question?",
                "unblocks": "Something",
                "options": None,
                "source_file": None,
            }
        ]
        (tmp_path / "decisions.json").write_text(
            json.dumps(old_data, indent=2), encoding="utf-8"
        )
        loaded = load_decisions_json(tmp_path)

        assert len(loaded) == 1
        assert loaded[0].answer is None
        assert loaded[0].answered_by is None
