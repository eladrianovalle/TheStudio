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
