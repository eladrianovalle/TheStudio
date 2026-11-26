import re
import shutil
from pathlib import Path

import pytest

from install import install_studio, update_studio

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND = REPO_ROOT / ".claude" / "commands" / "correct.md"

MIT_NOTICE_LINES = [
    "Copyright (c) 2026 Lauren Tan",
    "Permission is hereby granted, free of charge, to any person obtaining a copy",
    "of this software and associated documentation files (the \"Software\"), to deal",
    "in the Software without restriction, including without limitation the rights",
    "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell",
    "copies of the Software, and to permit persons to whom the Software is",
    "furnished to do so, subject to the following conditions:",
    "The above copyright notice and this permission notice shall be included in all",
    "copies or substantial portions of the Software.",
    "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR",
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,",
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE",
    "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER",
    "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,",
    "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE",
    "SOFTWARE.",
]

REPEAT_SENTENCE = (
    "When you are corrected, fix the mistake and write its rule in a tracked file. If the rule "
    "was already written there and nothing enforces it, the correction is a repeat: encode it as "
    "a check (a test, a lint rule, a hook) in the same change, not a memory note or another "
    "written rule. A check catches the next slip by itself; a note only works if someone reads "
    "it at the right moment."
)

RUN_IT_LINE = "Run `/correct` right after you correct an agent"


def _frontmatter_and_body(text: str) -> tuple[str, str]:
    assert text.startswith("---\n"), "correct.md has no frontmatter"
    frontmatter, _, body = text[len("---\n"):].partition("\n---\n")
    return frontmatter, body


def notice_problems(text: str) -> list[str]:
    heading = "\n## pstack license\n"
    if heading not in text:
        return ["no `## pstack license` section"]
    license_section = text.split(heading, 1)[1]
    if "\n## " in license_section:
        return ["`## pstack license` is not the last section"]
    section_lines = [line.strip() for line in license_section.splitlines()]
    return [f"the notice lacks {line!r}" for line in MIT_NOTICE_LINES if line not in section_lines]


def test_the_command_cannot_be_invoked_by_an_agent_and_says_when_to_use_it():
    frontmatter, _ = _frontmatter_and_body(COMMAND.read_text(encoding="utf-8"))
    assert re.search(r"^disable-model-invocation: true$", frontmatter, re.MULTILINE)
    description = re.search(r'^description: "(.*)"$', frontmatter, re.MULTILINE)
    assert description, "correct.md has no quoted description"
    assert description.group(1).startswith("Use when")


def test_the_command_holds_the_sweep_every_step_and_the_reply_block():
    _, body = _frontmatter_and_body(COMMAND.read_text(encoding="utf-8"))
    assert "**With no argument, sweep first.**" in body
    assert "Then fix the most frequent classes now." in body
    step_numbers = re.findall(r"^(\d)\. \*\*", body, re.MULTILINE)
    assert step_numbers == ["1", "2", "3", "4", "5", "6", "7"]
    for reply_field in [
        "### <the rule sentence>",
        "- Evidence:",
        "- Repeat:",
        "- Level:",
        "- Why not higher:",
        "- Proof:",
        "- Table:",
        "- For you:",
    ]:
        assert reply_field in body, f"the reply block lacks {reply_field!r}"


def test_the_command_credits_pstack_and_ends_with_its_full_mit_notice():
    text = COMMAND.read_text(encoding="utf-8")
    assert (
        "Adapted from the `correct` skill in pstack, Copyright (c) 2026 Lauren Tan, MIT License."
        in " ".join(text.split())
    )
    assert notice_problems(text) == []
    assert "THIRD_PARTY_NOTICES" not in text


@pytest.mark.parametrize(
    "broken_text",
    [
        "# Body\n",
        "# Body\n\n## pstack license\n\nCopyright (c) 2026 Lauren Tan\n\n## Afterwards\n",
        "# Body\n\n## pstack license\n\nMIT License\n\nCopyright (c) 2026 Lauren Tan\n",
    ],
)
def test_a_missing_misplaced_or_partial_notice_is_reported(broken_text):
    assert notice_problems(broken_text)


@pytest.mark.parametrize(
    "sentence",
    [
        "Group the mistakes into classes. A class counts once it has happened twice.",
        "Hide internals so the wrong import fails. Replace hand-synced lists with one source of truth.",
        "Fix or delete any test that still passes when the behavior it checks breaks, or that fails when only the internals change.",
    ],
)
def test_the_command_keeps_pstacks_own_sentences(sentence):
    flattened = " ".join(COMMAND.read_text(encoding="utf-8").split())
    assert sentence in flattened


@pytest.mark.parametrize(
    "studio_only_text",
    ["has no past instance", "studio/tests/", "cd studio", "specs/judged-rules.md"],
)
def test_the_command_names_nothing_an_installed_repository_lacks(studio_only_text):
    assert studio_only_text not in COMMAND.read_text(encoding="utf-8")


def test_an_installed_repository_gets_the_command_with_its_full_notice(tmp_path):
    studio_dir = REPO_ROOT / "studio"
    target = tmp_path / "game"
    target.mkdir()
    install_studio(target, studio_dir, install_hook=False, install_finish_check=False)
    installed = target / ".claude" / "commands" / "correct.md"
    assert installed.read_text(encoding="utf-8") == COMMAND.read_text(encoding="utf-8")
    assert notice_problems(installed.read_text(encoding="utf-8")) == []


def test_an_update_that_changes_the_command_keeps_its_full_notice(tmp_path):
    source_root = tmp_path / "studio_source"
    shutil.copytree(
        REPO_ROOT / "studio",
        source_root / "studio",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "output", "knowledge"),
    )
    shutil.copytree(REPO_ROOT / ".claude" / "commands", source_root / ".claude" / "commands")
    target = tmp_path / "game"
    target.mkdir()
    install_studio(target, source_root / "studio", install_hook=False, install_finish_check=False)

    source_command = source_root / ".claude" / "commands" / "correct.md"
    changed_text = source_command.read_text(encoding="utf-8").replace(
        "**With no argument, sweep first.**", "**With no argument, sweep history first.**"
    )
    source_command.write_text(changed_text, encoding="utf-8")

    result = update_studio(
        target, source_root / "studio", fetch=False, install_hook=False, install_finish_check=False
    )

    installed = (target / ".claude" / "commands" / "correct.md").read_text(encoding="utf-8")
    assert not result.get("blocked")
    assert "sweep history first" in installed
    assert notice_problems(installed) == []


@pytest.mark.parametrize("relative_path", ["CLAUDE.md", "studio/docs/CODING_PRINCIPLES.md"])
def test_the_principles_say_a_correction_writes_its_rule_and_a_repeat_gets_a_check(relative_path):
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert REPEAT_SENTENCE in text.splitlines()
    assert "When the same correction comes up twice" not in text


def test_claude_md_names_the_rule_table_outside_the_principles():
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    principles_start = text.index("\n## Coding Principles\n")
    principles_end = text.index("\n## ", principles_start + 1)
    outside_the_principles = text[:principles_start] + text[principles_end:]
    naming_lines = [
        line
        for line in outside_the_principles.splitlines()
        if "/correct" in line and "rule table" in line and "`studio/tests/test_enforced_rules.py`" in line
    ]
    assert len(naming_lines) == 1


@pytest.mark.parametrize(
    "relative_path", ["README.md", "studio/docs/CLAUDE_CODE_USAGE.md", "studio/docs/ARCHITECTURE.md"]
)
def test_the_docs_say_when_to_run_the_command(relative_path):
    flattened = " ".join((REPO_ROOT / relative_path).read_text(encoding="utf-8").split())
    assert RUN_IT_LINE in flattened
