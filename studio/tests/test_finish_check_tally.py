"""Scenario tests for finish_check_tally: grading a blocked stop by the turn that followed it.

Each transcript here is built from the record shapes Claude Code writes: a block is a
`user` record flagged `isMeta` carrying the hook's paragraph, tool results arrive as
`user` records too, and only a real prompt from the person ends the turn.
"""

import json
from pathlib import Path

import pytest

import finish_check_tally as tally

BLOCK = {
    "type": "user",
    "isMeta": True,
    "timestamp": "2026-10-01T10:00:00.000Z",
    "cwd": "/somewhere",
    "message": {"role": "user", "content": tally.BLOCK_TEXT + " (automatic, not the user speaking). Re-read..."},
}
PROMPT = {"type": "user", "message": {"role": "user", "content": "next thing please"}}
TOOL_RESULT = {
    "type": "user",
    "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
}


def assistant(*uses, output_tokens=10):
    content = [{"type": "text", "text": "working"}]
    content += [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp} for i, (name, inp) in enumerate(uses)]
    return {"type": "assistant", "message": {"role": "assistant", "content": content, "usage": {"output_tokens": output_tokens}}}


def test_an_edit_after_the_block_is_a_concrete_change():
    graded = tally.blocks_in([BLOCK, assistant(("Edit", {"file_path": "a.py"})), PROMPT])
    assert len(graded) == 1
    assert graded[0]["ran_a_tool"] is True
    assert graded[0]["changed_something"] is True


def test_a_tool_result_does_not_end_the_turn():
    records = [
        BLOCK,
        assistant(("Bash", {"command": "git status"})),
        TOOL_RESULT,
        assistant(("Bash", {"command": "git commit -m 'done'"})),
        PROMPT,
    ]
    graded = tally.blocks_in(records)
    assert graded[0]["changed_something"] is True


def test_a_read_only_command_counts_as_a_tool_but_not_as_a_change():
    graded = tally.blocks_in([BLOCK, assistant(("Bash", {"command": "cat a.py"})), PROMPT])
    assert graded[0]["ran_a_tool"] is True
    assert graded[0]["changed_something"] is False


def test_stopping_again_with_no_tool_is_no_change_and_its_tokens_are_counted():
    graded = tally.blocks_in([BLOCK, assistant(output_tokens=42), PROMPT])
    assert graded[0]["ran_a_tool"] is False
    assert graded[0]["changed_something"] is False
    assert graded[0]["output_tokens"] == 42


def test_each_block_is_graded_on_its_own_turn():
    records = [BLOCK, PROMPT, BLOCK, assistant(("Write", {"file_path": "b.md"})), PROMPT]
    graded = tally.blocks_in(records)
    assert [block["changed_something"] for block in graded] == [False, True]


def test_hook_feedback_is_not_a_prompt():
    assert tally.is_user_prompt(BLOCK) is False
    assert tally.is_user_prompt(TOOL_RESULT) is False
    assert tally.is_user_prompt(PROMPT) is True


def test_the_criterion_needs_thirty_blocks_and_eight_changes():
    assert tally.windows_met([]) == (0, 0, 0)
    blocks = [{"changed_something": index < 8} for index in range(30)]
    assert tally.windows_met(blocks) == (1, 1, 8)
    blocks[7]["changed_something"] = False
    assert tally.windows_met(blocks) == (0, 1, 7)


def test_project_dir_name_matches_claude_code_encoding():
    assert tally.project_dir_name("/Users/x/Repos/_Foo Bar") == "-Users-x-Repos--Foo-Bar"


def test_scan_leaves_out_the_excluded_repo_and_older_blocks(tmp_path: Path):
    def write(project: str, records: list) -> None:
        folder = tmp_path / project
        folder.mkdir()
        (folder / "s.jsonl").write_text("\n".join(json.dumps(record) for record in records))

    old_block = dict(BLOCK, timestamp="2026-09-01T00:00:00.000Z")
    write("-Users-x-Repos-consumer", [old_block, PROMPT, BLOCK, assistant(("Edit", {})), PROMPT])
    write("-Users-x-Repos--Studio", [BLOCK, assistant(("Edit", {})), PROMPT])
    write("-Users-x-Repos--Studio-worktree", [BLOCK, PROMPT])

    blocks = tally.scan(str(tmp_path), "-Users-x-Repos--Studio", since="2026-09-29")
    assert [block["project"] for block in blocks] == ["-Users-x-Repos-consumer"]
    assert blocks[0]["changed_something"] is True


def test_report_says_when_there_are_too_few_blocks():
    text = tally.report([dict(BLOCK, project="p", ran_a_tool=False, changed_something=False, output_tokens=5)], "2026-09-29")
    assert "Fewer than 30 blocks" in text


@pytest.mark.parametrize(
    "command, writes",
    [
        ("git commit -m x", True),
        ("gh pr create --title t", True),
        ("echo hi > out.txt", True),
        ("git status && git diff", False),
        ("python -m pytest tests/ -q", False),
    ],
)
def test_which_shell_commands_count_as_writing(command, writes):
    assert tally.is_writing({"name": "Bash", "input": {"command": command}}) is writes
