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
import inspect
import re
from pathlib import Path

from impl_loop import LoopConfig
from run_phase import build_parser, get_artifact_root
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


_REPO_ROOT = Path(__file__).resolve().parents[2]

# The files that describe `/forge --work-dir` to a reader. The spec itself
# (`specs/forge-work-dir.md`) is deliberately absent: it is where the don't-oversell
# rule is written down, so it quotes the banned wording on purpose.
_WORK_DIR_DOCS = (
    "CHANGELOG.md",
    ".claude/commands/forge.md",
    "studio/docs/IMPLEMENTATION_LOOP_SPEC.md",
    "studio/docs/CLAUDE_CODE_USAGE.md",
)

# Claims the feature cannot back up. Every git command it renders is prompt text an
# agent may ignore, and the path check runs once, before the agents start.
_WORK_DIR_OVERCLAIMS = (
    "worktree-safe",
    "worktree safe",
    "prevents the accident",
    "exists to prevent",
    "cannot move main",
)

# Files a person reads to learn how to run the loop. `pin_loop_to_worktree.py` was the
# hand-rolled workaround `--work-dir` replaced; none of these may still tell you to run it.
_HOW_TO_RUN_DOCS = (
    *_WORK_DIR_DOCS,
    "README.md",
    "CLAUDE.md",
    ".claude/workflows/implementation-loop.js",
)


class TestWorkDirIsDocumentedHonestly:
    """`--work-dir` is a safety feature, which is exactly why its docs must not oversell it.

    Two failures are possible here and only one is obvious. The obvious one is
    leaving the flag undocumented. The other is documenting it as protection it
    can't provide: the loop's git commands are text in an agent's prompt, so a
    reader who believes the loop is now safe stops checking, and the first agent
    that ignores its instructions moves the wrong branch again.
    """

    def test_reference_docs_document_the_flag_and_its_up_front_validation(self):
        """Both reference docs name the flag, and say the check runs before the loop.

        Up-front validation is the property that makes the flag worth using — a bad
        path costs nothing rather than failing after both agents have run — so it is
        not an optional detail of the write-up.
        """
        for doc_name in ("IMPLEMENTATION_LOOP_SPEC.md", "CLAUDE_CODE_USAGE.md"):
            text = (_DOCS / doc_name).read_text(encoding="utf-8")
            assert "--work-dir" in text, f"{doc_name} does not document --work-dir"
            assert "validated before the loop starts" in text, (
                f"{doc_name} does not say the work dir is validated before the loop starts"
            )
            for reason in ("missing", "not-a-worktree", "different-repo", "unquotable"):
                assert f"`{reason}`" in text, (
                    f"{doc_name} does not name the `{reason}` refusal reason"
                )

    def test_no_doc_repeats_a_known_overclaim(self):
        """A blacklist of five phrases, four of which were deleted to make this pass.

        Read the name literally: this catches the specific wordings we already found
        and removed, so they cannot come back. It cannot catch a NEW overclaim in
        different words — "guarantees commits land on the right branch" sails through
        untouched. Lengthening the list would only add more guesses.

        `test_every_doc_states_the_limit` below is the durable guard: it requires every
        describing doc to say what the feature does NOT do, which a new overclaim has to
        contradict in the same file to be worth worrying about.
        """
        for rel_path in _WORK_DIR_DOCS:
            text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8").lower()
            for claim in _WORK_DIR_OVERCLAIMS:
                assert claim not in text, (
                    f"{rel_path} claims {claim!r}; --work-dir reduces the blast radius "
                    "of a run in the wrong directory, it cannot make one impossible"
                )

    def test_every_doc_states_the_limit(self):
        for rel_path in _WORK_DIR_DOCS:
            text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
            assert "blast radius" in text, (
                f"{rel_path} describes --work-dir without stating what it does not do"
            )

    def test_no_doc_still_tells_you_to_run_the_retired_pin_script(self):
        runs_the_script = re.compile(r"(python|\./|bash)\s*\S*pin_loop_to_worktree")
        for rel_path in _HOW_TO_RUN_DOCS:
            text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
            assert not runs_the_script.search(text), (
                f"{rel_path} still instructs the reader to run pin_loop_to_worktree.py, "
                "which was deleted when --work-dir replaced it"
            )


def _doc_section(doc_name: str, heading: str) -> str:
    """The text of one markdown section: its heading down to the next heading."""
    lines = (_DOCS / doc_name).read_text(encoding="utf-8").splitlines()
    section: list[str] = []
    for line in lines:
        if section and line.startswith("#"):
            break
        if section or line.strip() == heading:
            section.append(line)
    return "\n".join(section)


# Each artifact-root branch as (a line of get_artifact_root, the phrase the doc uses
# for it). Both lists must stay in the same order: the doc explains the chain as an
# ordered walk, so a reordered branch in the code silently makes the doc wrong.
_ARTIFACT_ROOT_BRANCHES = [
    (
        "if cwd == studio_root or _is_within(cwd, studio_root):",
        "**cwd is inside `studio/` itself**",
    ),
    (
        "if installed_root is None and _is_within(cwd, studio_root.parent):",
        "**cwd is elsewhere in the source repo**",
    ),
    (
        "found = _find_installed_root_upwards(cwd)",
        "**A `.studio/VERSION` above cwd**",
    ),
    (
        'if (cwd / ".studio").is_dir():',
        "**A bare `.studio/` in cwd**",
    ),
]


class TestArtifactRootChainParity:
    """ARCHITECTURE.md must describe the branches `get_artifact_root()` really walks.

    Where the artifacts of a run land is the one thing every other path hangs off,
    and it is invisible from the outside — so the doc is the only place a reader
    can learn it. Add or reorder a branch and this test fails until the doc agrees.
    """

    def test_doc_lists_every_branch_in_code_order(self):
        code = inspect.getsource(get_artifact_root)
        doc = _doc_section("ARCHITECTURE.md", "### Where Artifacts Land")
        assert doc, "no 'Where Artifacts Land' section found in ARCHITECTURE.md"

        code_positions = []
        doc_positions = []
        for code_line, doc_phrase in _ARTIFACT_ROOT_BRANCHES:
            assert code_line in code, (
                f"get_artifact_root() no longer contains this branch: {code_line}"
            )
            assert doc_phrase in doc, (
                "ARCHITECTURE.md's artifact-root section never describes the branch "
                f"{doc_phrase}"
            )
            code_positions.append(code.index(code_line))
            doc_positions.append(doc.index(doc_phrase))

        assert code_positions == sorted(code_positions), (
            "get_artifact_root() runs its branches in a different order than this "
            "test lists them; fix the list, then the doc"
        )
        assert doc_positions == sorted(doc_positions), (
            "ARCHITECTURE.md describes the artifact-root branches out of the order "
            "get_artifact_root() actually tries them"
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
