#!/usr/bin/env python3
"""Grade the finish-check hook from Claude Code's own transcripts.

The hook (`finish_check.py`) refuses the first stop of every turn. Whether that
refusal buys anything is the question `specs/shipped-finish-check.md` asks: does
the assistant go on to *do* something in the turn that follows, or just stop
again? Nothing in Studio records the answer, but Claude Code does. Every
transcript under `~/.claude/projects/<project>/<session>.jsonl` holds the
block as a user record flagged `isMeta` whose text starts with the hook's own
paragraph, followed by whatever the assistant did before the next real prompt.

This script reads those transcripts and prints, for every block outside the
Studio source repo, whether the following turn ran any tool and whether it ran
one that changes something: an edit, a write, a commit, a push, a pull request.
It then checks the spec's pass criterion over every window of 30 consecutive
blocks. It writes nothing anywhere.

Run it from the Studio source checkout, which it excludes from the count:

    python studio/finish_check_tally.py --since 2026-09-29
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

# Tools whose use means the assistant changed something, or delegated work that
# will. Everything else (Read, a read-only Bash, a browser screenshot) counts as
# "ran a tool" but not as a concrete change.
WRITING_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit", "Agent", "Task", "Workflow", "Skill"}

# A Bash command that writes: git state, GitHub objects, redirects, file moves.
WRITING_COMMAND = re.compile(
    r"git (commit|push|add|checkout|switch|rebase|merge|worktree|stash)"
    r"|gh (pr|issue) (create|comment|edit|close|merge|ready)"
    r"|sed -i|>>?\s*\S|\btee\b|\brm\b|\bmv\b|\bcp\b|\bmkdir\b|\btouch\b"
)

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


def is_block(record):
    content = content_of(record)
    return (
        record.get("type") == "user"
        and bool(record.get("isMeta"))
        and isinstance(content, str)
        and content.startswith(BLOCK_TEXT)
    )


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
        return bool(WRITING_COMMAND.search(command))
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
        "output_tokens": output_tokens,
    }


def blocks_in(records):
    """Each finish-check block in a transcript, graded on the turn that followed it."""
    graded = []
    index = 0
    while index < len(records):
        if not is_block(records[index]):
            index += 1
            continue
        end = index + 1
        while end < len(records) and not is_user_prompt(records[end]):
            end += 1
        grade = grade_turn(records[index + 1:end])
        grade["timestamp"] = records[index].get("timestamp") or ""
        grade["cwd"] = records[index].get("cwd") or ""
        graded.append(grade)
        index = end
    return graded


def project_dir_name(path):
    """How Claude Code names a project's transcript directory: every non-alphanumeric is a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def scan(projects_dir, excluded_prefix, since):
    blocks = []
    for transcript in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        project = os.path.basename(os.path.dirname(transcript))
        if project.startswith(excluded_prefix):
            continue
        for block in blocks_in(read_records(transcript)):
            if block["timestamp"][:10] >= since:
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


def report(blocks, since):
    lines = []
    total = len(blocks)
    projects = len({block["project"] for block in blocks})
    lines.append(f"Blocked stops outside this repo since {since}: {total}, in {projects} project directories.")
    if total == 0:
        return "\n".join(lines)
    ran = sum(block["ran_a_tool"] for block in blocks)
    changed = sum(block["changed_something"] for block in blocks)
    silent = total - ran
    tokens_after_silent = sum(block["output_tokens"] for block in blocks if not block["ran_a_tool"])
    lines.append(f"  followed by any tool call:         {ran}")
    lines.append(f"  followed by a concrete change:     {changed}")
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
    args = parser.parse_args(argv)
    excluded = project_dir_name(args.exclude or this_repo_root())
    blocks = scan(args.projects_dir, excluded, args.since)
    print(report(blocks, args.since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
