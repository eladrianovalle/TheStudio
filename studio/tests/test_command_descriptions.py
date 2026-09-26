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
import tempfile
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


def split_frontmatter(command_file: Path) -> tuple[str, str]:
    """Return ``(frontmatter, body)`` for a command file, or ``("", whole file)``.

    Line endings are normalised first. A checkout with CRLF endings has no ``"---\n"`` to
    find, and every reader here would then quietly fall back to treating the frontmatter as
    body — which reads as "this command has no description" and skips the test instead of
    failing it. A guard that disappears on someone else's checkout is worse than no guard.
    """
    text = command_file.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        return "", text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return "", text
    # The opening `---` is a delimiter, not frontmatter. Returning it means every caller
    # has to know to skip a line that parses as neither a key nor a value.
    return parts[0][len("---\n"):], parts[1]


def flags_in(text: str) -> set[str]:
    """Every ``--flag`` token in *text*, as whole words.

    Whole words because a substring test cannot tell ``--plan`` from ``--planner``: a hint
    offering the second would satisfy a command documenting the first, and the check would
    pass on a flag nobody can type.
    """
    return set(re.findall(r"--[a-z][a-z-]*", text))


def read_description(command_file: Path) -> str:
    """Return the ``description`` from a command's frontmatter, or ""."""
    frontmatter, _ = split_frontmatter(command_file)
    match = re.search(r"^description:\s*([\"']?)(.*?)\1(\s+#.*)?\s*$", frontmatter, re.MULTILINE)
    return match.group(2) if match else ""


def malformed_quoted_values(command_file: Path) -> list[str]:
    """Return frontmatter lines whose quoted value closes before the line ends.

    A YAML loader ends a double-quoted scalar at the first ``"`` not escaped with
    a backslash, and a single-quoted one at the first ``'`` not doubled as ``''``.
    Anything after that other than a ``# comment`` fails to parse and takes the
    whole frontmatter block with it. The suite has no YAML dependency, so this
    checks for that one mistake.
    """
    frontmatter, _ = split_frontmatter(command_file)
    bad = []
    for line in frontmatter.splitlines():
        _, sep, value = line.partition(":")
        value = value.strip()
        if not sep or not value or value[0] not in "\"'":
            continue
        quote = value[0]
        inner = re.sub(r"\\." if quote == '"' else "''", "", value[1:])
        end = inner.find(quote)
        if end == -1 or not re.fullmatch(r"(\s+#.*|\s*)", inner[end + 1 :]):
            bad.append(line)
    return bad


def read_argument_hint(command_file: Path) -> str | None:
    """Return the ``argument-hint`` from a command's frontmatter, or None if absent."""
    frontmatter, _ = split_frontmatter(command_file)
    match = re.search(r"""^argument-hint:\s*(["'])(.*)\1\s*$""", frontmatter, re.MULTILINE)
    return match.group(2) if match else None


def documented_flags(command_file: Path) -> list[str]:
    """Every ``--flag`` the command's own Arguments section documents."""
    _, body = split_frontmatter(command_file)
    # `(?=^## |\Z)` so a file whose Arguments section runs to the end of the file is read
    # rather than returning nothing — which would have skipped that command silently.
    section = re.search(r"^## Arguments\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
    if not section:
        return []
    # Flags are read out of inline-code spans, not the prose around them. Some commands
    # document a flag on its own (`--plan`) and others inside a format string
    # (`--phase <market|design|tech> --text "..."`); both count, while a flag merely
    # mentioned in a sentence does not.
    code_spans = re.findall(r"`([^`]+)`", section.group(1))
    return sorted({flag for span in code_spans for flag in flags_in(span)})


class TestArgumentHints(unittest.TestCase):
    """The hint is the only argument list most people ever read.

    It appears inline as someone types the command, where the body below it does not. A
    flag missing from the hint is a flag most users never learn exists; a flag promised by
    the hint and documented nowhere is worse, because they will try it.
    """

    def test_the_hint_offers_every_flag_the_command_documents(self):
        for name in SLASH_COMMANDS:
            path = COMMANDS_DIR / name
            flags = documented_flags(path)
            if not flags:
                continue
            hint = read_argument_hint(path) or ""
            missing = sorted(set(flags) - flags_in(hint))
            with self.subTest(command=name):
                self.assertEqual(
                    missing, [],
                    f"{name} documents {missing} but its argument-hint does not offer them. "
                    f"The hint is what a user reads while typing; a flag left out of it is "
                    f"one most people never find.",
                )

    def test_the_hint_promises_nothing_the_command_does_not_document(self):
        for name in SLASH_COMMANDS:
            path = COMMANDS_DIR / name
            hint = read_argument_hint(path)
            if hint is None:
                continue
            documented = documented_flags(path)
            invented = sorted(flags_in(hint) - set(documented))
            with self.subTest(command=name):
                self.assertEqual(
                    invented, [],
                    f"{name}'s argument-hint offers {invented}, which its Arguments section "
                    f"never documents. A hint that promises a flag nobody implemented sends "
                    f"people to try it.",
                )


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



class TestTheReadersDoNotSilentlySkip(unittest.TestCase):
    """Every way these helpers can return "nothing" is a test that passes without checking.

    The checks above iterate real command files and `continue` when a helper finds no
    frontmatter or no documented flags. That is right for a command with nothing to check and
    wrong for a helper that failed to read one — and the two are indistinguishable from the
    outside, so each way of failing to read gets pinned here.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, text: str) -> Path:
        path = self.dir / "cmd.md"
        path.write_text(text, encoding="utf-8", newline="")
        return path

    def test_crlf_frontmatter_is_still_read(self):
        path = self._write(
            '---\r\ndescription: "Use to do a thing. Triggers include \'do the thing\'."\r\n'
            'argument-hint: "[--plan]"\r\n---\r\n\r\n'
            "## Arguments\r\n\r\n- Optional `--plan`: dry run.\r\n"
        )
        self.assertIn("Triggers include", read_description(path))
        self.assertEqual(read_argument_hint(path), "[--plan]")
        self.assertEqual(documented_flags(path), ["--plan"])

    def test_arguments_as_the_final_section_is_still_read(self):
        path = self._write(
            '---\ndescription: "x"\nargument-hint: "[--plan]"\n---\n\n'
            "## Arguments\n\n- Optional `--plan`: dry run.\n"
        )
        self.assertEqual(
            documented_flags(path), ["--plan"],
            "a command whose Arguments section runs to the end of the file read as having no "
            "flags, which skips it silently instead of checking it",
        )

    def test_crlf_frontmatter_is_still_checked_for_bad_quoting(self):
        """The quoting guard is a reader too, and it skipped the same way the others did."""
        path = self._write(
            '---\r\ndescription: "closes early" and then keeps going\r\n---\r\n\r\n# Body\r\n'
        )
        self.assertTrue(
            malformed_quoted_values(path),
            "a CRLF checkout made the YAML-quoting guard return nothing, which reads as "
            "'this file is fine' rather than 'I could not look'",
        )

    def test_a_longer_flag_does_not_satisfy_a_shorter_one(self):
        """`--plan` is a prefix of `--planner`; a substring test cannot tell them apart."""
        self.assertNotIn("--plan", flags_in("[--planner <name>]"))
        self.assertEqual(flags_in("[--planner <name>]"), {"--planner"})
        self.assertEqual(flags_in("[--plan] [--planner <name>]"), {"--plan", "--planner"})


if __name__ == "__main__":
    unittest.main()
