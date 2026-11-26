import re
from pathlib import Path

import pytest

import install

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_FILE = REPO_ROOT / ".claude" / "commands" / "sprint-review.md"
SPEC_FILE = REPO_ROOT / "specs" / "sprint-review.md"
SPEC_COMMAND_FILE = REPO_ROOT / ".claude" / "commands" / "spec.md"

STOP_MESSAGES_BY_STEP = [
    (1, "Opening the batch needs the GitHub CLI signed in. Run `gh auth login` and try again."),
    (
        1,
        "Batch #N (<url>) is still open. Merge or close it, then run /sprint-review again — "
        "a second batch now would flip the same specs twice.",
    ),
    (
        1,
        "I can't reach `origin`, so I can't see what has merged or branch from an up-to-date "
        "default branch.",
    ),
    (
        2,
        "I can't tell what's finished: git history couldn't be read here (a shallow clone, or not "
        "a git work tree). Nothing was changed.",
    ),
    (
        2,
        "I can't tell which branch is the default here, so I can't tell what has merged or where "
        "to open the pull request. If this repo has a GitHub remote called `origin`, run "
        "`git remote set-head origin --auto` and try again.",
    ),
    (2, "Nothing finished is waiting for review."),
    (5, "No yes and no hold — nothing to commit, no pull request."),
    (
        5,
        "`<slug>` changed on `<default>` during the meeting, so your answer was about an older "
        "version; left out. Run /sprint-review again to review it as it is now.",
    ),
    (
        5,
        "Every answered spec changed on `<default>` during the meeting — nothing to commit, no "
        "pull request. Run /sprint-review again to review them as they are now.",
    ),
]


def collapse_whitespace(text):
    return re.sub(r"\s+", " ", text)


def command_text():
    return COMMAND_FILE.read_text(encoding="utf-8")


def step_sections():
    text = command_text()
    headings = list(re.finditer(r"^### Step (\d+):", text, re.MULTILINE))
    sections = {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        end_of_steps = text.find("\n## ", heading.start())
        if end_of_steps != -1 and end_of_steps < end:
            end = end_of_steps
        sections[int(heading.group(1))] = text[heading.start():end]
    return [int(heading.group(1)) for heading in headings], sections


def answer_writes_section():
    text = command_text()
    start = text.index("## What each answer writes")
    return text[start:]


def hold_writes():
    section = answer_writes_section()
    return section[section.index("- **hold**"):]


def test_command_file_exists_and_is_registered():
    assert COMMAND_FILE.is_file()
    assert "sprint-review.md" in install.SLASH_COMMANDS


def test_steps_zero_to_five_appear_once_each_in_order():
    step_numbers, _ = step_sections()
    assert step_numbers == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize(("step_number", "message"), STOP_MESSAGES_BY_STEP)
def test_each_stop_message_is_the_specs_wording_inside_its_step(step_number, message):
    assert message in collapse_whitespace(SPEC_FILE.read_text(encoding="utf-8"))
    _, sections = step_sections()
    assert message in collapse_whitespace(sections[step_number])


def test_only_a_row_with_exactly_an_empty_list_takes_an_answer():
    _, sections = step_sections()
    meeting = collapse_whitespace(sections[4])
    assert "Only a row whose `units_off_default_branch` is exactly `[]`" in meeting


def test_the_meeting_offers_exactly_yes_edit_and_hold():
    _, sections = step_sections()
    answers = re.findall(r"^- \*\*([a-z]+)\*\* —", sections[4], re.MULTILINE)
    assert answers == ["yes", "edit", "hold"]
    assert 'there is no "skip"' in collapse_whitespace(sections[4])


def test_the_batch_branches_a_worktree_from_the_remote_default_branch():
    _, sections = step_sections()
    batch = collapse_whitespace(sections[5])
    assert re.search(
        r"`git worktree add -b sprint-review/<YYYY-MM-DD-HHMM> [^`]+ origin/<default>`", batch
    )


def test_the_batch_stages_explicit_paths_only():
    _, sections = step_sections()
    batch = collapse_whitespace(sections[5])
    assert "`git add -- <each path written>`" in batch
    text = command_text()
    assert "git add -A" not in text
    assert "git add ." not in text


def test_the_batch_makes_one_commit():
    _, sections = step_sections()
    assert "one commit" in collapse_whitespace(sections[5]).lower()


def test_the_pull_request_opens_ready_for_review():
    _, sections = step_sections()
    batch = collapse_whitespace(sections[5])
    pr_commands = [span for span in re.findall(r"`([^`]+)`", batch) if "gh pr create" in span]
    assert pr_commands
    assert all("--draft" not in span for span in pr_commands)
    assert "without `--draft`" in batch


def test_the_pr_lookup_is_a_fixed_string_grep_with_no_word_boundary():
    _, sections = step_sections()
    rows = collapse_whitespace(sections[3])
    assert '`git log origin/<default> -F --grep "writer: <unit_id>" --format=%H`' in rows
    assert "\\b" not in command_text()


def test_a_hold_replaces_an_existing_verification_section():
    hold = collapse_whitespace(hold_writes())
    assert "replaced, never duplicated" in hold
    assert "If a line starts `## Verification`, replace from it up to the next line starting `## `" in hold
    assert "otherwise insert the section above `## Build Plan`" in hold


def test_a_hold_sets_verification_due_thirty_days_out():
    hold = collapse_whitespace(hold_writes())
    assert "**`verification_due`** set to the review date plus 30 days" in hold


def test_a_hold_points_at_the_spec_command_skeleton_instead_of_copying_it():
    hold = collapse_whitespace(hold_writes())
    assert "the evidence skeleton in `.claude/commands/spec.md`" in hold
    spec_command_lines = SPEC_COMMAND_FILE.read_text(encoding="utf-8").splitlines()
    assert any(
        line.strip().startswith("# ") and "Verification Results" in line
        for line in spec_command_lines
    )
    assert "Verification Results" not in command_text()


@pytest.mark.parametrize("doc", ["README.md", "studio/docs/CLAUDE_CODE_USAGE.md"])
def test_the_command_tables_list_sprint_review(doc):
    text = (REPO_ROOT / doc).read_text(encoding="utf-8")
    assert re.search(r"^\| `/sprint-review` \|", text, re.MULTILINE)
