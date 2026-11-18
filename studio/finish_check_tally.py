#!/usr/bin/env python3
"""Grade the finish-check hook from Claude Code's own transcripts.

The hook (`finish_check.py`) refuses the first stop of every turn. Whether that
refusal buys anything is the question `specs/shipped-finish-check.md` asks: does
the assistant go on to *do* something in the turn that follows, or just stop
again? Nothing in Studio records the answer, but Claude Code does. Every
transcript under `~/.claude/projects/<project>/<session>.jsonl` holds each
check in one of two forms, followed by whatever the assistant did before the
next real prompt:

- a refused stop ("block"): a user record flagged `isMeta` whose text starts
  with the hook's own paragraph;
- a context note ("context"): a `hook_additional_context` attachment from the
  Stop hook whose content list holds the FINISH-CHECK paragraph.

This script reads those transcripts and prints, for every block outside the
Studio source repo, whether the following turn ran any tool and whether it ran
one that changes something: an edit, a write, a commit, a push, a pull request.
It then checks the spec's pass criterion over every window of 30 consecutive
blocks. It writes nothing anywhere.

Two filters sit next to `--since`: `--channel block|context` keeps one form
only (default: both), and `--min-final-chars N` keeps only checks whose final
assistant message had at least N characters of text. The report names any
active filter on the line after its first.

Run it from the Studio source checkout, which it excludes from the count:

    python studio/finish_check_tally.py --since 2026-09-29
    python studio/finish_check_tally.py --since <date> --channel block --min-final-chars 600
"""

import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

BLOCK_TEXT = "Stop hook feedback:\nFINISH-CHECK"
CONTEXT_TEXT = "FINISH-CHECK"

# Tools whose use means the assistant changed something. Everything else (Read,
# a read-only Bash, a browser screenshot) counts as "ran a tool" but not as a
# concrete change.
WRITING_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}

# Tools that hand work to another agent. What that agent did is in its own
# transcript, which this script does not read, so delegation is reported on its
# own line and never counted as a change.
DELEGATING_TOOLS = {"Agent", "Task", "Workflow"}

# A Bash command that writes: git state, GitHub objects, file moves.
WRITING_COMMAND = re.compile(
    r"git (commit|push|add|checkout|switch|rebase|merge|worktree|stash)"
    r"|gh (pr|issue) (create|comment|edit|close|merge|ready)"
    r"|sed -i|\btee\b|\brm\b|\bmv\b|\bcp\b|\bmkdir\b|\btouch\b"
)

# A redirect into a file. `2>&1` and `>/dev/null` write nothing, so they don't count.
# It is matched only after heredoc bodies and quoted strings are taken out, so a `>`
# inside a jq filter, a grep pattern or an inline script is not mistaken for one.
REDIRECT_TO_FILE = re.compile(r"(?<![-=<>])\d*>>?\s*(?!&|/dev/null\b)[\w./~$]")
HEREDOC_BODY = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2[^\n]*\n).*?^\s*\3\s*$", re.S | re.M)
QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")


def redirects_to_a_file(command):
    unquoted = QUOTED.sub("_", HEREDOC_BODY.sub(r"\1", command))
    return bool(REDIRECT_TO_FILE.search(unquoted))


# The criterion as written in the spec: of 30 consecutive blocks, at least 8
# must be followed by a concrete change.
WINDOW = 30
NEEDED = 8


def read_records(path):
    """Every JSON record in one transcript, in file order; unreadable lines are skipped."""
    records = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def content_of(record):
    return (record.get("message") or {}).get("content")


def channel_of(record):
    """Which way a finish-check reached the assistant in this record, or None if it didn't.

    "block" is the older refused stop: a `user` record flagged `isMeta` carrying the
    hook's paragraph. "context" is the newer form: a `hook_additional_context`
    attachment from a Stop hook with a FINISH-CHECK entry in its content list. Each
    check also writes sibling records (a `hook_blocking_error` or `hook_success`
    attachment, a `stop_hook_summary`, an `api-request-blob`); those return None so
    no check is counted twice. SessionStart and UserPromptSubmit hooks write the same
    attachment type, which is why the event is checked.
    """
    content = content_of(record)
    if (
        record.get("type") == "user"
        and bool(record.get("isMeta"))
        and isinstance(content, str)
        and content.startswith(BLOCK_TEXT)
    ):
        return "block"
    attachment = record.get("attachment") or {}
    if (
        record.get("type") == "attachment"
        and attachment.get("type") == "hook_additional_context"
        and attachment.get("hookEvent") == "Stop"
        and isinstance(attachment.get("content"), list)
        and any(
            isinstance(entry, str) and entry.startswith(CONTEXT_TEXT)
            for entry in attachment["content"]
        )
    ):
        return "context"
    return None


def final_message_chars(records, index):
    """How much text the assistant wrote in the message the check at `index` followed.

    Claude Code writes each content block as its own record, so only the nearest
    earlier `assistant` record is the final one. If it holds no text (thinking or a
    tool call only), the turn ended without text and this returns 0 rather than
    measuring an earlier message. No assistant record before the check also returns 0.
    """
    for record in reversed(records[:index]):
        if record.get("type") != "assistant":
            continue
        content = content_of(record)
        if not isinstance(content, list):
            return 0
        return sum(
            len(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return 0


def is_user_prompt(record):
    """A real prompt from the person, which is where the turn after a block ends.

    Tool results also arrive as `user` records, as does every hook's feedback,
    so neither of those closes the turn.
    """
    if record.get("type") != "user" or record.get("isMeta"):
        return False
    content = content_of(record)
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content
        )
    return False


def tool_uses(record):
    if record.get("type") != "assistant":
        return []
    content = content_of(record)
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"]


def is_writing(tool_use):
    name = tool_use.get("name", "")
    if name in WRITING_TOOLS:
        return True
    if name == "Bash":
        command = (tool_use.get("input") or {}).get("command", "")
        return bool(WRITING_COMMAND.search(command)) or redirects_to_a_file(command)
    return False


def grade_turn(records):
    """What the assistant did in one turn's records: ran a tool, changed something, cost."""
    uses = [use for record in records for use in tool_uses(record)]
    output_tokens = sum(
        ((record.get("message") or {}).get("usage") or {}).get("output_tokens", 0)
        for record in records
        if record.get("type") == "assistant"
    )
    return {
        "ran_a_tool": bool(uses),
        "changed_something": any(is_writing(use) for use in uses),
        "delegated": any(use.get("name") in DELEGATING_TOOLS for use in uses),
        "output_tokens": output_tokens,
    }


def blocks_in(records):
    """Each finish-check in a transcript, in either form, graded on the turn that followed it."""
    graded = []
    index = 0
    while index < len(records):
        channel = channel_of(records[index])
        if channel is None:
            index += 1
            continue
        end = index + 1
        while end < len(records) and not is_user_prompt(records[end]):
            end += 1
        grade = grade_turn(records[index + 1:end])
        grade["timestamp"] = records[index].get("timestamp") or ""
        grade["cwd"] = records[index].get("cwd") or ""
        grade["channel"] = channel
        grade["final_chars"] = final_message_chars(records, index)
        graded.append(grade)
        index = end
    return graded


def project_dir_name(path):
    """How Claude Code names a project's transcript directory: every non-alphanumeric is a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def scan(projects_dir, excluded_prefix, since, min_final_chars=0, channel=None):
    """Every graded block outside the excluded repo, oldest first.

    `min_final_chars` keeps only checks whose final message had at least that many
    characters of text; `channel` ("block" or "context") keeps only that form.

    The exclusion drops the repo's own directory and `<repo>-...`, which is how its
    worktrees are named. A sibling repo whose name continues with a dash or a dot
    (`Studio-old`, `Studio.bak`) is dropped too, because the directory encoding turns
    `/`, `.` and `-` all into `-` and nothing else tells them apart.
    """
    blocks = []
    for transcript in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        project = os.path.basename(os.path.dirname(transcript))
        # The repo itself, and worktrees nested inside it; not a sibling repo whose
        # name merely starts the same way.
        if project == excluded_prefix or project.startswith(excluded_prefix + "-"):
            continue
        for block in blocks_in(read_records(transcript)):
            if block["timestamp"][:10] < since:
                continue
            if block["final_chars"] < min_final_chars:
                continue
            if channel is not None and block["channel"] != channel:
                continue
            block["project"] = project
            blocks.append(block)
    blocks.sort(key=lambda block: block["timestamp"])
    return blocks


def windows_met(blocks):
    """How many of the windows of 30 consecutive blocks meet the criterion, and the worst one."""
    if len(blocks) < WINDOW:
        return 0, 0, 0
    counts = [
        sum(block["changed_something"] for block in blocks[start:start + WINDOW])
        for start in range(len(blocks) - WINDOW + 1)
    ]
    return sum(count >= NEEDED for count in counts), len(counts), min(counts)


def describe_filters(min_final_chars, channel):
    """The one report line naming the active filters, or None when there are none."""
    filters = []
    if channel is not None:
        filters.append(f"channel {channel} only")
    if min_final_chars > 0:
        filters.append(f"final message at least {min_final_chars} characters")
    if not filters:
        return None
    return "  filtered: " + ", ".join(filters)


def report(blocks, since, min_final_chars=0, channel=None):
    lines = []
    total = len(blocks)
    projects = len({block["project"] for block in blocks})
    lines.append(f"Blocked stops outside this repo since {since}: {total}, in {projects} project directories.")
    filter_line = describe_filters(min_final_chars, channel)
    if filter_line is not None:
        lines.append(filter_line)
    if total == 0:
        return "\n".join(lines)
    lines.append(
        f"  earliest {blocks[0]['timestamp'][:10]}, latest {blocks[-1]['timestamp'][:10]}"
        " (Claude Code deletes old transcripts, so the earliest is where the surviving record starts)"
    )
    ran = sum(block["ran_a_tool"] for block in blocks)
    changed = sum(block["changed_something"] for block in blocks)
    silent = total - ran
    tokens_after_silent = sum(block["output_tokens"] for block in blocks if not block["ran_a_tool"])
    lines.append(f"  followed by any tool call:         {ran}")
    lines.append(f"  followed by a concrete change:     {changed}")
    delegated_only = sum(block["delegated"] and not block["changed_something"] for block in blocks)
    lines.append(f"  delegated to an agent, no change of its own: {delegated_only}  (not counted as a change)")
    lines.append(f"  followed by no tool call at all:   {silent}  ({tokens_after_silent} output tokens spent on those turns)")
    met, windows, worst = windows_met(blocks)
    if windows:
        first = sum(block["changed_something"] for block in blocks[:WINDOW])
        last = sum(block["changed_something"] for block in blocks[-WINDOW:])
        lines.append(f"Windows of {WINDOW} consecutive blocks with at least {NEEDED} changes: {met} of {windows}.")
        lines.append(f"  first window: {first}   last window: {last}   worst window: {worst}")
    else:
        lines.append(f"Fewer than {WINDOW} blocks, so the criterion cannot be checked yet.")
    per_project = collections.Counter(block["project"] for block in blocks)
    lines.append("Per project directory (count, changed):")
    for project, count in per_project.most_common():
        changed_here = sum(block["changed_something"] for block in blocks if block["project"] == project)
        lines.append(f"  {count:5d} {changed_here:5d}  {project}")
    return "\n".join(lines)


def this_repo_root():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return os.getcwd()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default="0000-00-00", help="only blocks on or after this date (YYYY-MM-DD)")
    parser.add_argument(
        "--projects-dir",
        default=os.path.expanduser("~/.claude/projects"),
        help="where Claude Code keeps transcripts",
    )
    parser.add_argument(
        "--exclude",
        default=None,
        help="a repo whose transcripts are left out; default: the repo this is run from",
    )
    parser.add_argument(
        "--min-final-chars",
        type=int,
        default=0,
        help="only checks whose final message had at least this many characters of text",
    )
    parser.add_argument(
        "--channel",
        choices=["block", "context"],
        default=None,
        help="only checks in this form; default: both",
    )
    args = parser.parse_args(argv)
    excluded = project_dir_name(args.exclude or this_repo_root())
    blocks = scan(args.projects_dir, excluded, args.since, args.min_final_chars, args.channel)
    print(report(blocks, args.since, args.min_final_chars, args.channel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
