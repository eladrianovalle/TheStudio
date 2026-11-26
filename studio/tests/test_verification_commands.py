import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
CREATE_COMMAND = COMMANDS_DIR / "create-verification-skill.md"

MIT_PERMISSION_SENTENCE = (
    "Permission is hereby granted, free of charge, to any person obtaining a copy "
    "of this software and associated documentation files (the \"Software\"), to deal "
    "in the Software without restriction, including without limitation the rights "
    "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell "
    "copies of the Software, and to permit persons to whom the Software is "
    "furnished to do so, subject to the following conditions:"
)

PSTACK_MIT_NOTICE = (
    "MIT License\n\n"
    "Copyright (c) 2026 Lauren Tan\n\n"
    + MIT_PERMISSION_SENTENCE
    + "\n\nThe above copyright notice and this permission notice shall be included in all "
    "copies or substantial portions of the Software.\n\n"
    "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR "
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, "
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE "
    "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER "
    "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, "
    "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE "
    "SOFTWARE."
)

HAND_OFF_TEMPLATE = """\
Verify skill: .claude/skills/verify-<app>/  (uncommitted, N files)
Proved: yes | NO: <step that failed> — <error line>
Feature driven: features/<file>.md via <entry point>
Evidence after cleanup: <absolute path>  <bytes>   (one line per file, from ls -l)
Stand-in gaps: none | <setup steps the proof's stand-in did that the real target will not>
Map: <n> features (<names>); not yet driven: <names>
Wired: CLAUDE.md line <n> | not wired: <why>
Next: review and land as one PR; keep it honest with /maintain-verification-skill (schedule: CLAUDE_CODE_USAGE.md)."""

CURSOR_ONLY_NAMES = {
    "a .cursor/ path": re.compile(r"\.cursor/"),
    "the AskQuestion tool": re.compile(r"AskQuestion"),
    "a .mdc rule file": re.compile(r"\.mdc\b"),
    "Task as a tool name": re.compile(r"`Task`|\bTask tool\b|\bTask\(|\"Task\""),
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def frontmatter_of(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    closing = text.find("\n---\n", 4)
    if closing == -1:
        return ""
    return text[4:closing]


def body_of(text: str) -> str:
    closing = text.find("\n---\n", 4)
    return text[closing + 5:] if text.startswith("---\n") and closing != -1 else text


def verification_command_files() -> list[Path]:
    return sorted(COMMANDS_DIR.glob("*-verification-skill.md"))


class TestEveryVerificationCommandIsFound(unittest.TestCase):
    def test_the_create_command_is_among_the_files_checked(self):
        self.assertIn(
            CREATE_COMMAND,
            verification_command_files(),
            "The licence and Cursor-name checks below iterate every *-verification-skill.md "
            "command. If the create command is not found, they pass without checking anything.",
        )


class TestTheMitNoticeTravelsWithTheFile(unittest.TestCase):
    def test_every_verification_command_carries_lauren_tans_copyright(self):
        for path in verification_command_files():
            with self.subTest(command=path.name):
                self.assertIn(
                    "Copyright (c) 2026 Lauren Tan",
                    read_text(path),
                    f"{path.name} adapts pstack, whose MIT licence requires the copyright "
                    f"notice in every copy. The command file is what installs into each "
                    f"consuming repo, so the notice has to be inside it.",
                )

    def test_every_verification_command_carries_the_mit_permission_sentence(self):
        for path in verification_command_files():
            with self.subTest(command=path.name):
                self.assertIn(
                    MIT_PERMISSION_SENTENCE,
                    collapse_whitespace(read_text(path)),
                    f"{path.name} is missing the MIT permission sentence from pstack's LICENSE.",
                )

    def test_every_verification_command_ends_with_attribution_and_the_full_notice(self):
        for path in verification_command_files():
            text = collapse_whitespace(read_text(path))
            skill_name = path.stem
            with self.subTest(command=path.name):
                self.assertTrue(
                    text.endswith(collapse_whitespace(PSTACK_MIT_NOTICE)),
                    f"{path.name} must end with pstack's full MIT notice, word for word.",
                )
                notice_start = text.rfind("MIT License")
                attribution = text[:notice_start].rstrip()[-400:]
                self.assertIn(f"Adapted from `{skill_name}` in pstack by Lauren Tan", attribution)
                self.assertIn(
                    f"harness/pstack/claude-code/skills/{skill_name}/", attribution
                )
                self.assertIn("cursor/plugins", attribution)


class TestVerificationCommandsOnlyRunWhenAPersonAsks(unittest.TestCase):
    def test_every_verification_command_disables_model_invocation(self):
        for path in verification_command_files():
            with self.subTest(command=path.name):
                frontmatter_lines = frontmatter_of(read_text(path)).splitlines()
                self.assertIn(
                    "disable-model-invocation: true",
                    [line.strip() for line in frontmatter_lines],
                    f"{path.name} must set disable-model-invocation: true in its frontmatter, "
                    f"as pstack's skills do, so an agent cannot start it on its own.",
                )


class TestNoCursorOnlyNamesSurvive(unittest.TestCase):
    def test_no_verification_command_names_a_cursor_only_thing(self):
        for path in verification_command_files():
            text = read_text(path)
            for description, pattern in CURSOR_ONLY_NAMES.items():
                with self.subTest(command=path.name, name=description):
                    match = pattern.search(text)
                    self.assertIsNone(
                        match,
                        f"{path.name} contains {description} ({match.group(0) if match else ''!r}). "
                        f"Claude Code has none of these; map it the way pstack's Claude Code "
                        f"adapter does.",
                    )


class TestTheCreateCommandKeepsPstacksSteps(unittest.TestCase):
    def setUp(self):
        self.body = body_of(read_text(CREATE_COMMAND))

    def test_it_asks_the_five_interview_questions(self):
        for question in ("Surface", "Run", "Drive", "Observe", "Isolate"):
            with self.subTest(question=question):
                self.assertIn(f"- **{question}:**", self.body)

    def test_it_fixes_a_broken_base_before_generating(self):
        self.assertIn("fix that first (or report it precisely)", self.body)
        self.assertIn("verification scaffolding", self.body)

    def test_the_generated_skill_has_each_section_with_its_rule(self):
        rules = {
            "Launch": "Ready means usable, not just that a process answers.",
            "Doctor": "is this instance worth driving?",
            "Drive": "Prefer stable handles",
            "Evidence": "exercise the real user path, not internal setters or test-only endpoints",
            "Cleanup": "Never kill by process name; kill what you started.",
            "Helpers": "A helper the reader has to reverse-engineer is not a helper.",
        }
        for section, rule in rules.items():
            with self.subTest(section=section):
                self.assertIn(f"- **{section}:**", self.body)
                self.assertIn(rule, self.body)

    def test_feature_files_use_the_four_headings_verbatim(self):
        for heading in (
            "## Sub-features",
            "## How to get to it (user POV)",
            "## Driving it with <harness>",
            "## Gotchas",
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"`{heading}`", self.body)
        self.assertIn("Never weaken the journey to make it pass.", self.body)

    def test_it_proves_once_and_confirms_the_evidence_survived_cleanup(self):
        self.assertIn("drive ONE mapped feature", self.body)
        self.assertIn("confirm the evidence still exists", self.body)
        self.assertIn("A generated skill that was never executed is a draft, not a deliverable.", self.body)

    def test_it_writes_the_skill_under_claude_skills(self):
        self.assertIn(".claude/skills/verify-<app>/SKILL.md", self.body)
        self.assertIn(".claude/skills/verify-<app>/features/README.md", self.body)


class TestTheCreateCommandCarriesTheStudioSteps(unittest.TestCase):
    def setUp(self):
        self.body = body_of(read_text(CREATE_COMMAND))

    def test_it_refuses_when_a_verify_skill_already_exists(self):
        locate = self.body[: self.body.index("## 1.")]
        self.assertIn(".claude/skills/verify-*/", locate)
        self.assertIn("/maintain-verification-skill", locate)
        self.assertIn("stop", locate.lower())

    def test_it_seeds_read_only_from_smoke_and_the_observe_command(self):
        self.assertIn(".studio/smoke.toml", self.body)
        self.assertIn("[gate] observe_command", self.body)
        self.assertIn("--help", self.body)
        self.assertIn("read only", self.body)

    def test_evidence_goes_outside_the_checkout_as_absolute_paths(self):
        self.assertIn("outside the checkout", self.body)
        self.assertIn("absolute path", self.body)

    def test_the_proof_runs_in_a_fresh_worktree(self):
        self.assertIn("git worktree add --detach", self.body)
        self.assertIn("git worktree remove", self.body)
        self.assertIn("ls -l", self.body)

    def test_it_writes_one_pointer_line_outside_the_studio_sentinels(self):
        self.assertIn("STUDIO:CODING_PRINCIPLES", self.body)
        pointer = re.search(r"^ *(- Before verifying anything .*)$", self.body, re.MULTILINE)
        self.assertIsNotNone(pointer, "the command must give the exact CLAUDE.md pointer line")
        self.assertIn(".claude/skills/verify-<app>/SKILL.md", pointer.group(1))
        self.assertIn(".claude/skills/verify-<app>/features/README.md", pointer.group(1))

    def test_it_does_not_commit(self):
        self.assertIn("Do not commit", self.body)

    def test_it_carries_the_hand_off_reply_template_word_for_word(self):
        self.assertIn(HAND_OFF_TEMPLATE, self.body)


class TestTheDocsSayWhenToUseIt(unittest.TestCase):
    def test_readme_has_a_row(self):
        readme = read_text(REPO_ROOT / "README.md")
        self.assertRegex(readme, r"(?m)^\| `/create-verification-skill` \| .{40,}\|$")

    def test_the_utility_slash_commands_table_has_a_row(self):
        usage = read_text(REPO_ROOT / "studio" / "docs" / "CLAUDE_CODE_USAGE.md")
        table = usage.split("## Utility Slash Commands", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(table, r"(?m)^\| `/create-verification-skill` \| .{40,}\|$")


if __name__ == "__main__":
    unittest.main()
