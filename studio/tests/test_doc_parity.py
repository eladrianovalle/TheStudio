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


def _api_md_command_names() -> set[str]:
    """Command names in the `Command | Description` table of docs/API.md."""
    names: set[str] = set()
    in_table = False
    for line in (_DOCS / "API.md").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("| Command | Description |"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break  # the table ended
            match = re.match(r"\|\s*`([^`]+)`\s*\|", line)
            if match:
                names.add(match.group(1))
    return names


def _undocumented(doc_name: str, names: set[str]) -> set[str]:
    """Names not mentioned in a doc. A config key counts as documented if its
    name appears as a whole word anywhere — a TOML example (`key = value`), a
    backticked mention, or prose all count; only a genuinely absent name fails."""
    text = (_DOCS / doc_name).read_text(encoding="utf-8")
    return {
        name for name in names
        if not re.search(rf"\b{re.escape(name)}\b", text)
    }


class TestCliCommandParity:
    """API.md's command table must match the parser's subcommands, both ways."""

    def test_commands_and_api_md_table_match(self):
        code = _cli_command_names()
        docs = _api_md_command_names()
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
        missing = _undocumented("SCOPES_GUIDE.md", fields)
        assert not missing, (
            f"ScopeConfig fields undocumented in SCOPES_GUIDE.md: {sorted(missing)}"
        )


class TestLoopConfigParity:
    """Every LoopConfig knob must be documented in IMPLEMENTATION_LOOP_SPEC.md."""

    def test_fields_documented(self):
        fields = {f.name for f in dataclasses.fields(LoopConfig)}
        missing = _undocumented("IMPLEMENTATION_LOOP_SPEC.md", fields)
        assert not missing, (
            "LoopConfig fields undocumented in IMPLEMENTATION_LOOP_SPEC.md: "
            f"{sorted(missing)}"
        )
