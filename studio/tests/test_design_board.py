"""Tests for the design-board discipline shipped in docs/DESIGN_BOARD.md.

The discipline is prompt-shaped: no test can tell us an agent actually locates
before it reads. What a test *can* hold is the shape of the shipped text — that
the six rules are present and in order, that the discipline stays conditional,
that it names no board vendor, and that the pointer in the coding principles
stays a pointer instead of growing into a section.
"""
import re
from pathlib import Path

_DOCS = Path(__file__).resolve().parent.parent / "docs"
_DESIGN_BOARD = _DOCS / "DESIGN_BOARD.md"
_CODING_PRINCIPLES = _DOCS / "CODING_PRINCIPLES.md"

# Nouns that belong to a particular board product's model rather than to boards in
# general. Naming the tool is the consuming repo's job, so a shipped Studio doc that
# reaches for one of these has picked a vendor without saying so.
_VENDOR_UI_NOUNS = ("sticky", "stickies", "frame", "frames", "widget", "widgets", "canvas")

# A product name is a proper noun, so look for proper nouns rather than for any
# particular product — a test that hardcoded the vendor it forbids would name the
# vendor in Studio's own tree, which is the thing being avoided.
_PROPER_NOUN = re.compile(r"^[A-Z][a-z]{2,}$")
_LEADING_MARKUP = re.compile(r"^[#>\-*\s0-9.)]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.:!?])\s+")

# Capitalized words the shipped text is allowed to use mid-sentence: they name this
# project and its own documents, not a third-party product.
_ALLOWED_CAPITALIZED = {"Studio"}


def _mid_sentence_capitalized_words(text: str) -> list[str]:
    """Capitalized words that are not the first word of a sentence, heading or bullet.

    A capital in that position is how a product name shows up in prose. Sentence
    openers are skipped because every sentence starts with a capital.
    """
    found = []
    for raw_line in text.splitlines():
        line = _LEADING_MARKUP.sub("", raw_line.strip())
        for sentence in _SENTENCE_SPLIT.split(line):
            words = sentence.split()
            for word in words[1:]:
                bare = word.strip("*_`\"'“”‘’(),.:;!?—–-")
                if _PROPER_NOUN.match(bare) and bare not in _ALLOWED_CAPITALIZED:
                    found.append(bare)
    return found


def _flat(text: str) -> str:
    """The text with every run of whitespace collapsed to one space.

    Both docs are hard-wrapped, so a sentence being looked for often straddles a
    line break. Collapsing first makes the assertions about wording, not wrapping.
    """
    return re.sub(r"\s+", " ", text)


def _pointer_lines() -> list[str]:
    """The non-blank lines of the design-board pointer in CODING_PRINCIPLES.md."""
    lines = _CODING_PRINCIPLES.read_text(encoding="utf-8").splitlines()
    heading_index = next(
        i for i, line in enumerate(lines) if line.strip().lower() == "## design board"
    )
    body = []
    for line in lines[heading_index + 1:]:
        if line.startswith("#") or line.startswith("---"):
            break
        if line.strip():
            body.append(line)
    return body


class TestDesignBoardDiscipline:
    """docs/DESIGN_BOARD.md — the discipline itself."""

    def test_ships_the_six_rules_in_order(self):
        """The rules only work in this order: you cannot source a claim to a region
        you have not located, and you cannot re-read a destination you never proposed."""
        text = _flat(_DESIGN_BOARD.read_text(encoding="utf-8"))
        rules = [
            "Locate before you read",
            "Structure gives addresses, never content",
            "Every claim about the game is sourced to a region read this turn",
            "Re-read the destination region in the same turn, before any write",
            "Propose the exact item and the exact destination before writing",
            "Say so plainly when something cannot be sourced",
        ]
        positions = []
        for rule in rules:
            assert rule in text, f"DESIGN_BOARD.md is missing the rule {rule!r}"
            positions.append(text.index(rule))
        assert positions == sorted(positions), (
            "the six rules are present but out of order — the discipline reads as a "
            "sequence, not a checklist"
        )

    def test_locating_is_the_cheap_call_and_returns_only_addresses(self):
        """Locating is the free call; the content read is the one that costs."""
        text = _flat(_DESIGN_BOARD.read_text(encoding="utf-8"))
        assert "structural listing" in text
        assert "region names, ids and types" in text
        assert "cheap call" in text and "content read is the expensive one" in text

    def test_is_conditional_on_the_repo_naming_a_board(self):
        """A repo that names no board must behave exactly as it does today."""
        opening = _flat(_DESIGN_BOARD.read_text(encoding="utf-8").split("\n\n")[1])
        assert "applies only if this repository names a design board" in opening
        assert "inert" in opening

    def test_names_no_board_vendor(self):
        """Studio's shipped text says 'a design board'; the consuming repo names the
        tool in its own CLAUDE.md. This asserts the absence of the *category* — any
        proper noun, plus the UI nouns that belong to one product's model — so the
        test never has to write the vendor name it is forbidding."""
        text = _DESIGN_BOARD.read_text(encoding="utf-8")
        lowered = text.lower()
        for noun in _VENDOR_UI_NOUNS:
            assert not re.search(rf"\b{noun}\b", lowered), (
                f"DESIGN_BOARD.md uses {noun!r}, a noun from one board product's model"
            )
        assert not _mid_sentence_capitalized_words(text), (
            "DESIGN_BOARD.md carries a proper noun mid-sentence, which is how a "
            f"product name gets in: {_mid_sentence_capitalized_words(text)}"
        )

    def test_writes_land_where_the_repo_designates(self):
        text = _flat(_DESIGN_BOARD.read_text(encoding="utf-8"))
        assert "Agent writes go to the destination the repository designates" in text
        assert "further destinations by purpose" in text
        assert "names only one destination, everything falls to that one" in text

    def test_open_questions_are_a_reading_not_a_status(self):
        """Studio keeps no open-questions list of its own — that is the copy the
        source-of-truth rule forbids."""
        text = _flat(_DESIGN_BOARD.read_text(encoding="utf-8"))
        assert "how it marks something undecided, use that marker" in text
        assert "label it as a reading of what you found, not a status you looked up" in text
        assert "Never keep your own list of open questions" in text

    def test_asks_which_area_when_there_are_too_many_regions(self):
        text = _flat(_DESIGN_BOARD.read_text(encoding="utf-8"))
        assert "ask the designer which area" in text


class TestCodingPrinciplesPointer:
    """The pointer rides the existing CLAUDE.md injection into every consuming repo,
    most of which have no board — so it stays a pointer."""

    def test_pointer_is_three_lines_or_fewer(self):
        assert 0 < len(_pointer_lines()) <= 3, (
            "the design-board pointer has grown past three lines; the discipline "
            "belongs in DESIGN_BOARD.md, not in the coding principles"
        )

    def test_pointer_names_the_doc_and_no_vendor(self):
        body = _flat("\n".join(_pointer_lines()))
        assert "DESIGN_BOARD.md" in body
        assert "If this repository keeps a design board" in body
        for noun in _VENDOR_UI_NOUNS:
            assert not re.search(rf"\b{noun}\b", body.lower())
        assert not _mid_sentence_capitalized_words(body)

    def test_pointer_is_additive_and_not_a_numbered_principle(self):
        """It sits after the seven principles, so the numbered text the CLAUDE.md
        parity test compares is untouched."""
        text = _CODING_PRINCIPLES.read_text(encoding="utf-8")
        assert text.index("## 7. Spec Before Build") < text.index("## Design board")
        assert not re.search(r"^## \d+\. Design board", text, re.M)
