"""Tests for question-surfacing mode (M1).

Tests cover:
  - question_mode module: generate_question_instructions, is_question_mode, header constant
  - DocumentValidator.validate_question_mode: structural checks for question-mode output
"""
import pytest

from question_mode import (
    QUESTION_MODE_HEADER,
    generate_question_instructions,
    generate_question_integrator_instructions,
    is_question_mode,
)
from validators.document_validator import DocumentValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_role_data():
    """Minimal role data dict matching manifest structure."""
    return {
        "title": "Design Lead",
        "advocate_focus": "Define core loop and experiential pillars.",
        "contrarian_focus": "Attack scope bloat and UX ambiguity.",
        "deliverables": ["Core loop sketch", "Experience pillars", "Risk list"],
        "escalate_on": [],
    }


@pytest.fixture
def doc_validator():
    """Create DocumentValidator instance."""
    return DocumentValidator()


# ---------------------------------------------------------------------------
# generate_question_instructions
# ---------------------------------------------------------------------------

def test_generate_question_instructions_returns_tuple(sample_role_data):
    """generate_question_instructions returns (advocate_str, contrarian_str), both non-empty."""
    result = generate_question_instructions(sample_role_data)

    assert isinstance(result, tuple)
    assert len(result) == 2

    advocate_str, contrarian_str = result
    assert isinstance(advocate_str, str)
    assert isinstance(contrarian_str, str)
    assert len(advocate_str.strip()) > 0
    assert len(contrarian_str.strip()) > 0


def test_question_instructions_contain_priority_tags(sample_role_data):
    """Advocate instructions reference P0/P1/P2 priority structure."""
    advocate_str, _ = generate_question_instructions(sample_role_data)

    assert "P0" in advocate_str
    assert "P1" in advocate_str
    assert "P2" in advocate_str


def test_question_instructions_use_decision_blockquote_format(sample_role_data):
    """Advocate instructions use the unified DECISION blockquote format."""
    advocate_str, _ = generate_question_instructions(sample_role_data)

    assert "DECISION [P0]" in advocate_str
    assert "**Unblocks:**" in advocate_str
    # Should NOT use the old numbered-list format
    assert "1. [P0]" not in advocate_str


def test_question_instructions_anti_generic_guardrails(sample_role_data):
    """Advocate instructions contain anti-generic guidance."""
    advocate_str, _ = generate_question_instructions(sample_role_data)

    assert "do not ask questions" in advocate_str.lower()
    assert "answerable from the input" in advocate_str.lower()


def test_question_instructions_contain_role_title(sample_role_data):
    """Advocate instructions include the role title."""
    advocate_str, contrarian_str = generate_question_instructions(sample_role_data)

    assert "Design Lead" in advocate_str
    assert "Design Lead" in contrarian_str


def test_question_instructions_contain_header(sample_role_data):
    """Both advocate and contrarian instructions contain the question mode header."""
    advocate_str, contrarian_str = generate_question_instructions(sample_role_data)

    assert QUESTION_MODE_HEADER in advocate_str
    assert QUESTION_MODE_HEADER in contrarian_str


def test_contrarian_instructions_mention_challenge_rate(sample_role_data):
    """Contrarian instructions specify challenging >= 30% of questions."""
    _, contrarian_str = generate_question_instructions(sample_role_data)

    assert "30%" in contrarian_str


def test_contrarian_instructions_use_decision_blockquote_for_missing(sample_role_data):
    """Contrarian instructions tell agents to use DECISION format for missing questions."""
    _, contrarian_str = generate_question_instructions(sample_role_data)

    assert "DECISION [P0]" in contrarian_str
    assert "**Unblocks:**" in contrarian_str


def test_integrator_instructions_no_roadmap():
    """Integrator instructions explicitly say NOT to produce a roadmap."""
    instructions = generate_question_integrator_instructions()

    assert "do not produce a roadmap" in instructions.lower()
    assert "deduplicate" in instructions.lower()


def test_integrator_instructions_use_decision_format():
    """Integrator instructions use the DECISION blockquote format."""
    instructions = generate_question_integrator_instructions()

    assert "DECISION [P0]" in instructions
    assert "DECISION [P1]" in instructions


# ---------------------------------------------------------------------------
# is_question_mode
# ---------------------------------------------------------------------------

def test_is_question_mode_true():
    assert is_question_mode("questions") is True


def test_is_question_mode_false():
    assert is_question_mode("deliverables") is False


def test_is_question_mode_none():
    assert is_question_mode(None) is False


def test_is_question_mode_case_insensitive():
    assert is_question_mode("Questions") is True
    assert is_question_mode("QUESTIONS") is True


# ---------------------------------------------------------------------------
# QUESTION_MODE_HEADER constant
# ---------------------------------------------------------------------------

def test_question_mode_header_constant():
    assert isinstance(QUESTION_MODE_HEADER, str)
    assert "output_type: questions" in QUESTION_MODE_HEADER


# ---------------------------------------------------------------------------
# DocumentValidator — question mode
# ---------------------------------------------------------------------------

def test_document_validator_question_mode_accepts_valid(doc_validator, tmp_path):
    """A file with >= 3 bullet questions passes question-mode validation."""
    doc = tmp_path / "advocate_questions.md"
    doc.write_text(
        "# Questions\n\n"
        "- What is the target audience's primary motivation?\n"
        "- How does the core loop sustain engagement past hour 10?\n"
        "- What monetisation model avoids pay-to-win perception?\n"
        "- Are there comparable titles that attempted this blend?\n",
        encoding="utf-8",
    )

    result = doc_validator.validate_question_mode(doc)
    assert result.passed, f"Expected pass but got: {result.issues}"


def test_document_validator_question_mode_rejects_empty(doc_validator, tmp_path):
    """An empty file fails question-mode validation."""
    doc = tmp_path / "empty.md"
    doc.write_text("", encoding="utf-8")

    result = doc_validator.validate_question_mode(doc)
    assert not result.passed


def test_document_validator_question_mode_rejects_verdict(doc_validator, tmp_path):
    """A file containing a verdict token fails question-mode validation."""
    doc = tmp_path / "bad_questions.md"
    doc.write_text(
        "# Questions\n\n"
        "- What is the target audience?\n"
        "- How does retention work?\n"
        "- What is the monetisation model?\n\n"
        "VERDICT: APPROVED\n",
        encoding="utf-8",
    )

    result = doc_validator.validate_question_mode(doc)
    assert not result.passed
    assert any("verdict" in issue.lower() for issue in result.issues)


def test_document_validator_question_mode_rejects_few_questions(doc_validator, tmp_path):
    """A file with fewer than 3 question lines fails."""
    doc = tmp_path / "too_few.md"
    doc.write_text(
        "# Questions\n\n"
        "- What is the target audience?\n"
        "- How does retention work?\n",
        encoding="utf-8",
    )

    result = doc_validator.validate_question_mode(doc)
    assert not result.passed
    assert any("3" in issue for issue in result.issues)


def test_document_validator_question_mode_rejects_missing_file(doc_validator, tmp_path):
    """A non-existent file fails validation."""
    doc = tmp_path / "nonexistent.md"

    result = doc_validator.validate_question_mode(doc)
    assert not result.passed


def test_document_validator_question_mode_numbered_questions(doc_validator, tmp_path):
    """Numbered question lines (1. What...?) are counted."""
    doc = tmp_path / "numbered.md"
    doc.write_text(
        "# Questions\n\n"
        "1. What is the core fantasy?\n"
        "2. How does progression work?\n"
        "3. What keeps players coming back?\n",
        encoding="utf-8",
    )

    result = doc_validator.validate_question_mode(doc)
    assert result.passed


def test_document_validator_question_mode_accepts_decision_blockquotes(doc_validator, tmp_path):
    """Blockquote DECISION points are accepted as valid question-mode output."""
    doc = tmp_path / "decisions.md"
    doc.write_text(
        "# Open Questions\n\n"
        "> **DECISION [P0]:** Should the social deduction mechanic be real-time or turn-based?\n"
        "> **Unblocks:** Core loop design\n\n"
        "> **DECISION [P1]:** What monetisation model avoids pay-to-win?\n"
        "> **Unblocks:** Business plan and GTM strategy\n\n"
        "> **DECISION [P2]:** Which art style — pixel or hand-drawn?\n"
        "> **Unblocks:** Art pipeline scheduling\n",
        encoding="utf-8",
    )

    result = doc_validator.validate_question_mode(doc)
    assert result.passed, f"Expected pass but got: {result.issues}"


def test_document_validator_question_mode_mixed_formats(doc_validator, tmp_path):
    """Mixed bullet questions and blockquote DECISION points are both counted."""
    doc = tmp_path / "mixed.md"
    doc.write_text(
        "# Questions\n\n"
        "> **DECISION [P0]:** Should we target mobile or PC first?\n"
        "> **Unblocks:** SDK selection\n\n"
        "- What is the target audience's primary motivation?\n"
        "- How does the core loop sustain engagement?\n",
        encoding="utf-8",
    )

    result = doc_validator.validate_question_mode(doc)
    assert result.passed, f"Expected pass but got: {result.issues}"
