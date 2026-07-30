"""Doc-parity tests (Studio roadmap R2, reframed — see specs/doc-parity-tests.md).

Studio's reference docs are intentionally *richer* than the code, so we do NOT
generate them from source (that would delete authored prose). Instead we assert
that every name the code defines — CLI subcommands, config fields — is
documented, and, where a clean table exists, that no documented name is stale.
Hand-written prose stays untouched; only the names are guarded. Add a command or
a config field and forget the doc, and a test here fails — the /unstale chore,
made automatic and free.
"""
import argparse
import dataclasses
import re
from pathlib import Path

from impl_loop import LoopConfig
from run_phase import build_parser
from scopes import ScopeConfig

_DOCS = Path(__file__).resolve().parent.parent / "docs"


def _cli_command_names() -> set[str]:
    """The CLI subcommand names, straight from the argparse parser."""
    parser = build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return set(subparsers.choices)


def _table_first_column(doc_name: str, header: str) -> set[str]:
    """Backticked tokens in the first column of the markdown table under ``header``.

    Used for the doc tables whose first column IS the source-of-truth name list:
    API.md's command table and SCOPES_GUIDE.md's Scope Fields table. A name counts
    as documented only if it has its own row, not merely a prose mention anywhere
    in the file — otherwise a common-word field like `focus` is effectively
    unguarded (the word appears throughout the prose regardless of the field).
    """
    names: set[str] = set()
    in_table = False
    for line in (_DOCS / doc_name).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(header):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break  # the table ended
            match = re.match(r"\|\s*`([^`]+)`\s*\|", line)
            if match:
                names.add(match.group(1))
    return names


def _toml_assigned_keys(doc_name: str) -> set[str]:
    """Keys that appear as a TOML assignment (`key = value`) in a doc.

    The loop config is documented as a TOML block, not a table, so a field counts
    as documented only when it's genuinely defined (`field = ...`) — not merely
    named in prose, which would let a common-word field like `mandate` pass on an
    incidental sentence mention."""
    text = (_DOCS / doc_name).read_text(encoding="utf-8")
    return set(re.findall(r"(?m)^\s*([a-z_]+)\s*=", text))


class TestCliCommandParity:
    """API.md's command table must match the parser's subcommands, both ways."""

    def test_commands_and_api_md_table_match(self):
        code = _cli_command_names()
        docs = _table_first_column("API.md", "| Command | Description |")
        assert docs, "no `Command | Description` table found in API.md"
        undocumented = code - docs
        stale = docs - code
        assert not undocumented, (
            f"CLI commands missing from API.md's command table: {sorted(undocumented)}"
        )
        assert not stale, (
            f"API.md documents commands that no longer exist: {sorted(stale)}"
        )


class TestScopeConfigParity:
    """Every ScopeConfig knob must be documented in SCOPES_GUIDE.md."""

    def test_fields_documented(self):
        # `name` is the `[scopes.<name>]` TOML section name, not a row key.
        fields = {f.name for f in dataclasses.fields(ScopeConfig)} - {"name"}
        documented = _table_first_column(
            "SCOPES_GUIDE.md", "| Field | Required | Description |"
        )
        assert documented, "no Scope Fields table found in SCOPES_GUIDE.md"
        missing = fields - documented
        assert not missing, (
            "ScopeConfig fields missing a row in the Scope Fields table of "
            f"SCOPES_GUIDE.md: {sorted(missing)}"
        )


class TestLoopConfigParity:
    """Every LoopConfig knob must be documented in IMPLEMENTATION_LOOP_SPEC.md."""

    def test_fields_documented(self):
        fields = {f.name for f in dataclasses.fields(LoopConfig)}
        documented = _toml_assigned_keys("IMPLEMENTATION_LOOP_SPEC.md")
        assert documented, "no TOML assignments found in IMPLEMENTATION_LOOP_SPEC.md"
        missing = fields - documented
        assert not missing, (
            "LoopConfig fields not defined in the TOML config block of "
            f"IMPLEMENTATION_LOOP_SPEC.md: {sorted(missing)}"
        )


def _principle_lines(text: str) -> list[str]:
    """The numbered coding principles in a doc, as `N. Title` plus their content.

    Works on both copies: CODING_PRINCIPLES.md heads each principle with `## N.`,
    this repo's own CLAUDE.md with `### N.`. Blank lines are dropped so the
    comparison is about wording, not spacing.
    """
    lines: list[str] = []
    inside_a_principle = False
    for raw in text.splitlines():
        line = raw.rstrip()
        heading = re.match(r"^#{2,3} (\d+\. .+)$", line)
        if heading:
            inside_a_principle = True
            lines.append(heading.group(1))
            continue
        if line.startswith("#") or line.startswith("---"):
            inside_a_principle = False  # left the principles for another section
        elif inside_a_principle and line:
            lines.append(line)
    return lines


class TestCodingPrinciplesMirror:
    """The principles live in two hand-maintained copies and must not drift.

    `studio/docs/CODING_PRINCIPLES.md` ships to every installed repo; this repo's
    own `CLAUDE.md` carries the same text inline. Edit one and forget the other,
    and Studio starts telling other repos something it doesn't tell itself.
    """

    def test_claude_md_matches_the_shipped_principles(self):
        shipped = _principle_lines(
            (_DOCS / "CODING_PRINCIPLES.md").read_text(encoding="utf-8")
        )
        own = _principle_lines(
            (_DOCS.parent.parent / "CLAUDE.md").read_text(encoding="utf-8")
        )
        assert shipped, "no numbered principles found in CODING_PRINCIPLES.md"

        only_in_claude_md = [line for line in own if line not in shipped]
        only_in_shipped = [line for line in shipped if line not in own]
        assert own == shipped, (
            "CLAUDE.md and docs/CODING_PRINCIPLES.md disagree.\n"
            f"Only in CLAUDE.md: {only_in_claude_md}\n"
            f"Only in CODING_PRINCIPLES.md: {only_in_shipped}"
        )
