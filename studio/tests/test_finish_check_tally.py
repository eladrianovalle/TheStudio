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


def test_delegating_to_an_agent_is_reported_but_is_not_a_change():
    graded = tally.blocks_in([BLOCK, assistant(("Agent", {"prompt": "look around"})), PROMPT])
    assert graded[0]["ran_a_tool"] is True
    assert graded[0]["delegated"] is True
    assert graded[0]["changed_something"] is False


def test_loading_a_skill_is_a_tool_but_not_delegation_or_a_change():
    graded = tally.blocks_in([BLOCK, assistant(("Skill", {"skill": "review"})), PROMPT])
    assert graded[0]["ran_a_tool"] is True
    assert graded[0]["delegated"] is False
    assert graded[0]["changed_something"] is False


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
    write("-Users-x-Repos--StudioTools", [BLOCK, assistant(("Edit", {})), PROMPT])

    blocks = tally.scan(str(tmp_path), "-Users-x-Repos--Studio", since="2026-09-29")
    assert sorted(block["project"] for block in blocks) == [
        "-Users-x-Repos--StudioTools",
        "-Users-x-Repos-consumer",
    ]
    assert all(block["changed_something"] for block in blocks)


def test_report_says_when_there_are_too_few_blocks():
    text = tally.report([dict(BLOCK, project="p", ran_a_tool=False, changed_something=False, delegated=False, output_tokens=5)], "2026-09-29")
    assert "Fewer than 30 blocks" in text


def test_report_prints_the_record_span_delegation_and_windows():
    # 31 blocks, one a day: the first 8 changed something, so the first window has 8,
    # the last (blocks 2..31) has 7, and one of the two windows meets the criterion.
    blocks = [
        dict(
            BLOCK,
            timestamp=f"2026-10-{day:02d}T10:00:00.000Z",
            project="p",
            ran_a_tool=True,
            changed_something=day <= 8,
            delegated=day in (1, 20),
            output_tokens=5,
        )
        for day in range(1, 32)
    ]
    text = tally.report(blocks, "2026-09-29")
    assert "earliest 2026-10-01, latest 2026-10-31" in text
    # Day 1 delegated but also changed something, so only day 20 is delegation alone.
    assert "delegated to an agent, no change of its own: 1 " in text
    assert "with at least 8 changes: 1 of 2." in text
    assert "first window: 8   last window: 7   worst window: 7" in text


@pytest.mark.parametrize(
    "command, writes",
    [
        ("git commit -m x", True),
        ("gh pr create --title t", True),
        ("echo hi > out.txt", True),
        ("echo hi >> notes.md 2>&1", True),
        ('cat > "plan.md" <<\'EOF\'\nsome > text\nEOF', True),
        ("git status && git diff", False),
        ("python -m pytest tests/ -q", False),
        ("git status 2>&1 | head", False),
        ("ls foo 2>/dev/null", False),
        ("python -m pytest -q > /dev/null", False),
        ("jq '.[]|select(.n > 3)' data.json", False),
        ('grep -rn "->" src', False),
        ("python3 - <<'EOF'\nprint(1 > 0)\nEOF", False),
    ],
)
def test_which_shell_commands_count_as_writing(command, writes):
    assert tally.is_writing({"name": "Bash", "input": {"command": command}}) is writes


# --- The two channels: a refused stop ("block") and a context note ("context") ---
#
# A context check writes four records: a `hook_success` attachment whose stdout holds the
# hook's JSON, the `hook_additional_context` attachment, a `stop_hook_summary` system
# record and an `api-request-blob` holding the system-reminder copy. Only the attachment
# is the check. A block also writes a `hook_blocking_error` attachment beside its record.

PARAGRAPH = "FINISH-CHECK (automatic, not the user speaking). Re-read..."


def context_check(timestamp="2026-11-18T10:00:00.000Z", content=None, event="Stop"):
    return {
        "type": "attachment",
        "timestamp": timestamp,
        "cwd": "/somewhere",
        "attachment": {
            "type": "hook_additional_context",
            "hookName": "Stop",
            "hookEvent": event,
            "toolUseID": "hook-1",
            "content": [PARAGRAPH] if content is None else content,
        },
    }


HOOK_SUCCESS = {
    "type": "attachment",
    "attachment": {
        "type": "hook_success",
        "hookEvent": "Stop",
        "stdout": json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": PARAGRAPH}}),
        "exitCode": 0,
    },
}
HOOK_BLOCKING_ERROR = {
    "type": "attachment",
    "attachment": {
        "type": "hook_blocking_error",
        "hookEvent": "Stop",
        "blockingError": {"blockingError": PARAGRAPH, "command": "python finish_check.py"},
    },
}
STOP_HOOK_SUMMARY = {
    "type": "system",
    "subtype": "stop_hook_summary",
    "hookCount": 1,
    "hookInfos": [{"command": "python finish_check.py"}],
    "content": PARAGRAPH,
}
API_REQUEST_BLOB = {
    "type": "api-request-blob",
    "message": {
        "role": "user",
        "content": "<system-reminder>\nStop hook additional context: " + PARAGRAPH + "\n</system-reminder>",
    },
}


def text_reply(chars):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "x" * chars}]}}


def thinking_only():
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "hmm " * 50}]}}


@pytest.mark.parametrize(
    "record, channel",
    [
        (BLOCK, "block"),
        (context_check(), "context"),
        (context_check(content=["some other hook said hi", PARAGRAPH]), "context"),
        (HOOK_BLOCKING_ERROR, None),
        (HOOK_SUCCESS, None),
        (STOP_HOOK_SUMMARY, None),
        (API_REQUEST_BLOB, None),
        (context_check(event="SessionStart"), None),
        (context_check(event="UserPromptSubmit"), None),
        (context_check(content=["some other Stop hook's note"]), None),
        (PROMPT, None),
        (TOOL_RESULT, None),
    ],
    ids=[
        "block",
        "context",
        "context-paragraph-not-first",
        "hook_blocking_error",
        "hook_success",
        "stop_hook_summary",
        "api-request-blob",
        "session-start-context",
        "user-prompt-submit-context",
        "stop-context-without-finish-check",
        "prompt",
        "tool-result",
    ],
)
def test_channel_of_counts_each_check_once(record, channel):
    assert tally.channel_of(record) == channel


def test_is_block_is_gone():
    assert not hasattr(tally, "is_block")


def test_a_context_check_is_graded_with_its_channel_and_final_message_length():
    records = [
        thinking_only(),
        text_reply(321),
        HOOK_SUCCESS,
        context_check(),
        STOP_HOOK_SUMMARY,
        API_REQUEST_BLOB,
        assistant(("Edit", {"file_path": "a.py"})),
        PROMPT,
    ]
    graded = tally.blocks_in(records)
    assert len(graded) == 1
    assert graded[0]["channel"] == "context"
    assert graded[0]["final_chars"] == 321
    assert graded[0]["changed_something"] is True
    assert graded[0]["timestamp"] == "2026-11-18T10:00:00.000Z"


def test_a_block_carries_its_channel_too():
    graded = tally.blocks_in([text_reply(50), BLOCK, HOOK_BLOCKING_ERROR, PROMPT])
    assert len(graded) == 1
    assert graded[0]["channel"] == "block"
    assert graded[0]["final_chars"] == 50


def test_a_thinking_only_final_record_measures_zero_even_after_earlier_text():
    records = [text_reply(900), thinking_only(), HOOK_SUCCESS, context_check(), PROMPT]
    assert tally.final_message_chars(records, 3) == 0
    assert tally.blocks_in(records)[0]["final_chars"] == 0


def test_a_tool_call_only_final_record_measures_zero():
    records = [text_reply(900), {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}}, BLOCK]
    assert tally.final_message_chars(records, 2) == 0


def test_no_assistant_record_before_the_check_measures_zero():
    records = [PROMPT, HOOK_SUCCESS, context_check(), PROMPT]
    assert tally.final_message_chars(records, 2) == 0


def test_non_assistant_records_between_the_reply_and_the_check_are_skipped():
    records = [text_reply(77), TOOL_RESULT, HOOK_SUCCESS, STOP_HOOK_SUMMARY, context_check()]
    assert tally.final_message_chars(records, 4) == 77


def test_text_in_a_record_is_summed_across_its_text_blocks():
    reply = {"type": "assistant", "message": {"content": [{"type": "text", "text": "abc"}, {"type": "tool_use", "name": "Read", "input": {}}, {"type": "text", "text": "de"}]}}
    assert tally.final_message_chars([reply, BLOCK], 1) == 5


# --- Through main: the --channel and --min-final-chars filters ---


def write_projects(tmp_path, block_final_chars, context_final_chars):
    """One consumer project holding one block check and one context check."""
    folder = tmp_path / "-Users-x-Repos-consumer"
    folder.mkdir()
    records = [
        text_reply(block_final_chars),
        BLOCK,
        HOOK_BLOCKING_ERROR,
        assistant(("Edit", {"file_path": "a.py"})),
        PROMPT,
        text_reply(context_final_chars),
        HOOK_SUCCESS,
        context_check(timestamp="2026-11-18T10:00:00.000Z"),
        STOP_HOOK_SUMMARY,
        API_REQUEST_BLOB,
        assistant(("Bash", {"command": "cat a.py"})),
        PROMPT,
    ]
    (folder / "s.jsonl").write_text("\n".join(json.dumps(record) for record in records))
    return str(tmp_path)


def run_main(capsys, projects_dir, *flags):
    exit_code = tally.main(["--projects-dir", projects_dir, "--exclude", "/Users/x/Repos/_Studio", *flags])
    assert exit_code == 0
    return capsys.readouterr().out.splitlines()


def test_main_without_filters_counts_both_forms_and_prints_no_filter_line(tmp_path, capsys):
    projects = write_projects(tmp_path, block_final_chars=10, context_final_chars=10)
    lines = run_main(capsys, projects)
    assert lines[0] == "Blocked stops outside this repo since 0000-00-00: 2, in 1 project directories."
    assert lines[1].startswith("  earliest ")
    assert not any("filtered" in line for line in lines)


def test_min_final_chars_keeps_a_600_char_final_and_drops_a_599_char_one(tmp_path, capsys):
    projects = write_projects(tmp_path, block_final_chars=599, context_final_chars=600)
    lines = run_main(capsys, projects, "--min-final-chars", "600")
    assert lines[0] == "Blocked stops outside this repo since 0000-00-00: 1, in 1 project directories."
    assert lines[1] == "  filtered: final message at least 600 characters"
    # The survivor is the context check, which ran a read-only tool: no change.
    assert "  followed by a concrete change:     0" in lines


def test_channel_context_keeps_only_context_checks(tmp_path, capsys):
    projects = write_projects(tmp_path, block_final_chars=10, context_final_chars=10)
    lines = run_main(capsys, projects, "--channel", "context")
    assert lines[0] == "Blocked stops outside this repo since 0000-00-00: 1, in 1 project directories."
    assert lines[1] == "  filtered: channel context only"
    assert "  earliest 2026-11-18, latest 2026-11-18" in lines[2]
    assert "  followed by a concrete change:     0" in lines


def test_channel_block_keeps_only_block_checks(tmp_path, capsys):
    projects = write_projects(tmp_path, block_final_chars=10, context_final_chars=10)
    lines = run_main(capsys, projects, "--channel", "block")
    assert lines[0] == "Blocked stops outside this repo since 0000-00-00: 1, in 1 project directories."
    assert lines[1] == "  filtered: channel block only"
    assert "  earliest 2026-10-01, latest 2026-10-01" in lines[2]
    assert "  followed by a concrete change:     1" in lines


def test_both_filters_are_named_on_one_line(tmp_path, capsys):
    projects = write_projects(tmp_path, block_final_chars=700, context_final_chars=700)
    lines = run_main(capsys, projects, "--channel", "block", "--min-final-chars", "600")
    assert lines[0] == "Blocked stops outside this repo since 0000-00-00: 1, in 1 project directories."
    assert lines[1] == "  filtered: channel block only, final message at least 600 characters"
    assert sum("filtered" in line for line in lines) == 1


def test_the_filter_line_appears_even_when_nothing_survives(tmp_path, capsys):
    projects = write_projects(tmp_path, block_final_chars=10, context_final_chars=10)
    lines = run_main(capsys, projects, "--min-final-chars", "600")
    assert lines == [
        "Blocked stops outside this repo since 0000-00-00: 0, in 0 project directories.",
        "  filtered: final message at least 600 characters",
    ]


def test_an_unknown_channel_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        tally.main(["--projects-dir", str(tmp_path), "--channel", "email"])


def test_an_assistant_record_with_no_content_list_or_empty_text_measures_zero():
    assert tally.final_message_chars([{"type": "assistant", "message": {}}, BLOCK], 1) == 0
    assert tally.final_message_chars([text_reply(0), BLOCK], 1) == 0


def test_any_positive_minimum_is_named_as_a_filter():
    assert tally.describe_filters(1, None) == "  filtered: final message at least 1 characters"
    assert tally.describe_filters(0, None) is None
