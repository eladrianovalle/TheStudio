"""Every shipped slash command must say *when* to use it, not just what it is.

A model picking a command reads one line: the ``description`` in the file's
frontmatter. The body below it is only read after the command has already been
chosen, so a command whose description is missing — or which describes the
machinery rather than the moment to reach for it — can only be invoked by
someone who already knew it existed. That is how a capability ships and is
never used.

These tests hold the description to the shape that makes it selectable: it
opens by naming the situation ("Use when/to/before …") and it lists the words
a person actually says when they want this command.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from install import SLASH_COMMANDS  # noqa: E402

COMMANDS_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "commands"

# Long enough that a description has to name a situation and its triggers. The
# bar is deliberately low against what the commands carry today (the shortest is
# ~330 characters); it catches a description that regressed to a bare label, not
# one that is merely concise.
MINIMUM_DESCRIPTION_LENGTH = 150


def read_description(command_file: Path) -> str:
    """Return the ``description`` from a command's frontmatter, or ""."""
    text = command_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ""
    frontmatter = text.split("\n---\n", 1)[0]
    match = re.search(r'^description:\s*"?(.*?)"?\s*$', frontmatter, re.MULTILINE)
    return match.group(1) if match else ""


def malformed_quoted_values(command_file: Path) -> list[str]:
    """Return frontmatter lines whose quoted value closes before the line ends.

    A YAML loader ends a double-quoted scalar at the first ``"`` not escaped with
    a backslash, and a single-quoted one at the first ``'`` not doubled as ``''``.
    Anything after that other than a ``# comment`` fails to parse and takes the
    whole frontmatter block with it. The suite has no YAML dependency, so this
    checks for that one mistake.
    """
    text = command_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return []
    frontmatter = text[4:].split("\n---\n", 1)[0]
    bad = []
    for line in frontmatter.splitlines():
        _, sep, value = line.partition(":")
        value = value.strip()
        if not sep or not value or value[0] not in "\"'":
            continue
        quote = value[0]
        inner = re.sub(r"\\." if quote == '"' else "''", "", value[1:])
        end = inner.find(quote)
        if end == -1 or not re.fullmatch(r"\s*(#.*)?", inner[end + 1 :]):
            bad.append(line)
    return bad


class TestCommandDescriptions(unittest.TestCase):
    def test_frontmatter_quoted_values_are_well_formed(self):
        for name in SLASH_COMMANDS:
            with self.subTest(command=name):
                bad = malformed_quoted_values(COMMANDS_DIR / name)
                self.assertEqual(
                    bad,
                    [],
                    f"{name} has a quoted frontmatter value with an unescaped inner "
                    f"quote. YAML ends the value there, so the whole frontmatter block, "
                    f"description included, fails to load. Use the other quote style, "
                    f"or escape it: \\\" inside double quotes, '' inside single.",
                )

    def test_every_shipped_command_has_a_description(self):
        for name in SLASH_COMMANDS:
            with self.subTest(command=name):
                description = read_description(COMMANDS_DIR / name)
                self.assertTrue(
                    description,
                    f"{name} has no description in its frontmatter. That line is the "
                    f"only thing read when choosing between commands, so without it "
                    f"this command can only be found by someone who already knows it.",
                )

    def test_descriptions_name_the_situation_first(self):
        for name in SLASH_COMMANDS:
            with self.subTest(command=name):
                description = read_description(COMMANDS_DIR / name)
                self.assertTrue(
                    description.startswith("Use "),
                    f"{name}'s description starts with {description[:40]!r}. Open with "
                    f"'Use when…' / 'Use to…' / 'Use before…' so it answers when to reach "
                    f"for this command rather than what the command is made of.",
                )

    def test_descriptions_list_the_words_someone_would_say(self):
        for name in SLASH_COMMANDS:
            with self.subTest(command=name):
                description = read_description(COMMANDS_DIR / name)
                self.assertIn(
                    "Triggers include",
                    description,
                    f"{name}'s description names no triggers. List the phrases someone "
                    f"actually says when they want this, so it is recognisable from the "
                    f"request rather than only from the command's own vocabulary.",
                )

    def test_descriptions_are_long_enough_to_say_when(self):
        for name in SLASH_COMMANDS:
            with self.subTest(command=name):
                description = read_description(COMMANDS_DIR / name)
                self.assertGreaterEqual(
                    len(description),
                    MINIMUM_DESCRIPTION_LENGTH,
                    f"{name}'s description is {len(description)} characters. A label that "
                    f"short cannot carry both the situation and its triggers.",
                )


if __name__ == "__main__":
    unittest.main()
