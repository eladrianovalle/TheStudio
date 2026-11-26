#!/usr/bin/env python3
"""
Configuration for the implementation writer/editor loop.

Mirrors the ScopeConfig / load_scopes_config() pattern in scopes.py: a dataclass
for the shipped config tables plus a loader with the tomllib/tomli fallback and a
resolution chain (explicit path → .studio/ override → shipped default → defaults).
The [gate] table is the exception: its commands come from the repo's own config file and
from nowhere else — a key that file leaves out is empty, not a guess — and load_loop_config
refuses rather than falling back when nothing supplies a runnable test command. Detection
(STACK_MARKERS → resolve_profile) survives here as the setup wizard's opening guess; the
loader does not call it.

See studio/docs/IMPLEMENTATION_LOOP_SPEC.md §4 for the table shape.
"""
from __future__ import annotations

from config_loading import tomllib
import gate_routes
import argparse
import configparser
import json
import os
import re
import shlex
import string
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List


STUDIO_ROOT = Path(__file__).resolve().parent

VALID_MANDATES = {"contrarian", "off"}

VALID_READ_SCOPES = {"touched", "touched+importers"}

# The static-check tool NAMES Studio itself once documented and once wrote into config files,
# each with the command that replaces it. static_checks now holds commands, so one of these
# left behind would run nothing while the loop reported a clean check — the loader refuses it
# by name instead. Only these three: Studio owes a migration for values it authored, and
# refusing anything that merely *looks* like a name would reject someone's one-word script.
LEGACY_STATIC_CHECK_COMMANDS = {
    "ruff": "ruff check {paths}",
    "eslint": "npx eslint {paths}",
    "mypy": "mypy {paths}",
}

# The four ways a --work-dir can be unusable. /forge prints the one it hit, so a
# refused run says what is actually wrong instead of just "bad path".
WORK_DIR_MISSING = "missing"
WORK_DIR_NOT_A_WORKTREE = "not-a-worktree"
WORK_DIR_DIFFERENT_REPO = "different-repo"
WORK_DIR_UNQUOTABLE = "unquotable"

# The three ways the tree a run is about to commit to can be unsafe. /forge prints the
# one it hit, as it does for a refused --work-dir.
BRANCH_PROTECTED = "protected-branch"
BRANCH_WRONG = "wrong-branch"
BRANCH_DIRTY_TREE = "dirty-tree"

# A unit's commits belong on a branch a pull request can carry, never on these.
_PROTECTED_BRANCHES = ("main", "master")

# How many uncommitted paths a dirty-tree refusal lists before it only counts the rest.
_DIRTY_PATHS_SHOWN = 10

# The characters a --work-dir is allowed to contain. The path is interpolated into
# `git -C "<path>"` inside instruction text an agent then runs, so anything that
# survives into that string can change what runs. Listing what is accepted rather
# than what is banned means a character nobody thought of is refused by default
# instead of waved through.
_ALLOWED = set(string.ascii_letters + string.digits + "/._- ~")

# Why a particular character is dangerous. This only ever explains a refusal —
# _ALLOWED alone decides one, and it already excludes every key here. Two lists
# that could each refuse a path would be two lists that could drift apart.
_KNOWN_BAD = {
    '"': "ends the quoted string early",
    "\\": "a trailing one escapes the closing quote",
    "`": "runs as a command substitution",
    "$": "expands as a variable",
}

# Characters with no printable form, so the message can still point at where they are.
_INVISIBLE = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

# Spelled out rather than derived from _ALLOWED: a space has nothing to print, and a
# joined list of punctuation reads as line noise. test_impl_loop.py checks that this
# sentence and _ALLOWED still describe the same set.
_ALLOWED_SUMMARY = "letters, digits, and any of / . _ - ~ or a space"


class WorkDirError(ValueError):
    """A --work-dir the loop must refuse before any agent spawns."""


class BranchError(ValueError):
    """A working tree the loop must refuse to commit to before any agent spawns."""


class LoopConfigError(ValueError):
    """A resolved loop config the loop cannot run, raised with what to do about it."""


# Marker files that identify a stack, looked for at the repository root only. A pattern
# holding a `*` is globbed; every other pattern is an exact path test.
#
# `rust` is recognised but unserved: Studio ships no gate commands for it, which is how
# the wizard says "I know what this is and still have no command for it" instead of
# guessing. It is load-bearing. Without the row, a Rust game whose package.json only
# describes CI tooling matches node alone and gets handed `npm test`, which passes while
# testing none of the game — a wrong-reason *pass*, worse than the wrong-reason failure
# this detection removes. There is no `go` row because no repo here is Go; it is one line
# to add the day one appears.
#
# Deliberately NOT shared with the three suggest_*_from_stack ladders in setup.py: those
# have to return a best guess, this one has to refuse. Same markers, opposite policy.
STACK_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("unity", ("ProjectSettings/ProjectVersion.txt", "*.csproj")),
    ("rust", ("Cargo.toml",)),
    ("python", ("pyproject.toml", "setup.py", "requirements.txt", "conftest.py")),
    ("node", ("package.json",)),
]


@dataclass(frozen=True)
class StackProfile:
    """The gate commands Studio can offer a repository, and what it found there.

    ``stacks`` holds every stack whose markers are present. None of them means nothing
    was recognised, and two or more means the repository is ambiguous; both carry no
    commands and both are refusals. A single stack whose ``test_command`` is None is the
    third no-command case — recognised, but Studio has nothing honest to run (Unity,
    Rust, a Node package declaring no test script). That is a valid result, not an error:
    the wizard writes a blank template from it and the person filling that template in
    supplies the command.

    ``static_checks`` is a tuple rather than a list because PROFILES is module-level
    shared state, and ``frozen=True`` would not stop a caller mutating a list in place.
    """
    stacks: tuple[str, ...] = ()
    test_command: str | None = None
    static_checks: tuple[str, ...] = ()
    require_mutation_check: bool = False
    mutation_command: str | None = None
    mutation_note: str = ""


# The gate commands for each stack whose answer is the same in every repository. Node and
# Python are missing on purpose: what each can offer depends on what the repository itself
# declares, so _node_profile and _python_profile work them out per repo.
PROFILES: dict[str, StackProfile] = {
    # Recognised, deliberately unserved. A Unity test run needs a wrapper that reads the
    # result file (the editor reports success even when it discovered no tests at all),
    # and no Rust profile is shipped, so both fall through to the refusal.
    "unity": StackProfile(stacks=("unity",)),
    "rust": StackProfile(stacks=("rust",)),
}


def _first_marker(root: Path, patterns: tuple[str, ...]) -> str | None:
    """The first of ``patterns`` present at ``root``, named for the error message."""
    for pattern in patterns:
        if "*" in pattern:
            matches = sorted(match.name for match in root.glob(pattern))
            if matches:
                return matches[0]
        elif (root / pattern).exists():
            return pattern
    return None


def _matched_markers(root: Path) -> list[tuple[str, str]]:
    """Every (stack, the marker file that gave it away) present at ``root``."""
    matched = []
    for stack, patterns in STACK_MARKERS:
        marker = _first_marker(root, patterns)
        if marker is not None:
            matched.append((stack, marker))
    return matched


def detect_stacks(root: Path) -> list[str]:
    """Every stack whose markers are present at ``root``, in STACK_MARKERS order.

    Every match, never just the first. Zero matches and two-or-more matches are both
    refusals, with different messages, so STACK_MARKERS order survives only as the order
    the ambiguity message lists things in — never as a tiebreak. Every ranking is wrong
    for some real repository: rank package.json first and a Rust game with a CI-tooling
    package.json gets a green gate over nothing; rank Cargo.toml first and a Node repo
    vendoring a Rust crate is refused for the wrong reason.
    """
    return [stack for stack, _ in _matched_markers(root)]


def _read_package_json(root: Path) -> dict:
    """``package.json`` as a dict, or empty when it is missing or unreadable.

    A malformed package.json is not this loader's problem to report: it falls through to
    "no test script", and the refusal that follows names the file to fix.
    """
    try:
        with open(root / "package.json", "rb") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _node_profile(root: Path) -> StackProfile:
    """Node's gate commands, read out of the repository's own package.json.

    ``npm test`` is offered only when a ``test`` script is declared: without one it exits
    with *"missing script: test"*, which is exactly the wrong-reason failure this
    detection exists to remove.

    The lint command comes from the two signs a repo can show, told apart because they
    need different commands: a ``lint`` script is run through npm, while eslint sitting in
    devDependencies with no script is run directly. Neither means no static check, which
    is the honest answer for a package that declares neither.
    """
    package = _read_package_json(root)
    scripts = package.get("scripts")
    dev_dependencies = package.get("devDependencies")
    if not isinstance(scripts, dict):
        scripts = {}
    if not isinstance(dev_dependencies, dict):
        dev_dependencies = {}

    has_test_script = bool(str(scripts.get("test", "")).strip())
    # The same .strip() the test script gets, and for a sharper reason now that the script
    # IS the command: `"lint": ""` runs nothing, exits 0, and would report a clean static
    # check. A blank script is no script.
    lint_script = str(scripts.get("lint", "")).strip()
    has_eslint_dependency = "eslint" in dev_dependencies

    if lint_script:
        # Deliberately no {paths}: `npm run lint -- src/foo.js` appends to a script that
        # usually already names its own target (`eslint .`), which widens the run rather
        # than narrowing it. Do not "fix" this by adding `-- {paths}`.
        static_checks: tuple[str, ...] = ("npm run lint",)
    elif has_eslint_dependency:
        static_checks = ("npx eslint {paths}",)
    else:
        static_checks = ()

    return StackProfile(
        stacks=("node",),
        test_command="npm test" if has_test_script else None,
        static_checks=static_checks,
    )


def _is_set(value: object) -> bool:
    """Is this a `paths_to_mutate` value mutmut could actually act on?

    An empty string, an empty list, and a list of blanks all say the same thing as saying
    nothing: they leave mutmut guessing. The two config formats reach this from different
    directions — TOML gives a list or a string, an INI file gives a string — so the emptiness
    test lives in one place rather than being spelled twice and drifting.

    Anything that is neither a string nor a list of them is **not** configuration. TOML will
    happily hand back ``paths_to_mutate = {}``, ``0`` or ``true``, and none of those name a
    path mutmut could mutate. The rest of this probe treats "unclear" as "not configured" —
    an unreadable file, a section with no value — and this is the same rule: a gate switches
    on for an answer, never for the absence of a clear no.
    """
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(_is_set(item) for item in value)
    return False


def _mutmut_paths_are_set(root: Path) -> bool:
    """Has this repository told mutmut what to mutate?

    The question is not whether mutmut is mentioned somewhere. It is whether
    ``paths_to_mutate`` is set, because that is the single setting that decides whether
    ``mutmut run`` mutates this repository's code or goes looking for a ``src/`` directory
    that may not exist.

    Both files are parsed, never searched for a substring. ``[mutmut]`` appears inside a
    comment, a docstring, or a line somebody commented out while debugging, and none of
    those mean the tool is configured — a gate should not switch on over text nobody
    intended as configuration.

    A ``mutmut_config.py`` is deliberately not a signal. It is mutmut's hook file, holding
    ``pre_mutation`` and ``post_mutation``, and it sets no paths: a repository can have one
    and still be a repository where ``mutmut run`` finds nothing to mutate.
    """
    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file():
        # Raw, so a `%` in a path is a `%`. The interpolating parser expands values at
        # `get()` and raises on a lone `%` — `paths_to_mutate=src/%s` is enough — and that
        # call would be outside the try below. A gate probe must not be able to crash the
        # wizard over a character in somebody's path.
        parser = configparser.RawConfigParser()
        try:
            parser.read(setup_cfg, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            pass  # Unreadable is not configured: never switch the gate on from a guess.
        else:
            # An empty value tells mutmut nothing, so it is not configuration. Read the
            # value rather than asking whether the key exists: `has_option` is true for a
            # bare `paths_to_mutate=`, which would switch the gate on over a setting
            # somebody started and did not finish.
            if _is_set(parser.get("mutmut", "paths_to_mutate", fallback="")):
                return True

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            with open(pyproject, "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, ValueError):
            return False
        tool = data.get("tool")
        mutmut = tool.get("mutmut") if isinstance(tool, dict) else None
        if isinstance(mutmut, dict) and _is_set(mutmut.get("paths_to_mutate")):
            return True

    return False


def _python_profile(root: Path) -> StackProfile:
    """Python's gate commands, with the mutation gate decided by this repository.

    ``pytest -q`` and ``ruff check`` mean the same thing everywhere. ``mutmut run`` does
    not: it needs the repository to say what to mutate. So the gate is offered only to a
    repo that has said, and every other repo gets it switched off with a note saying what
    to add — rather than a gate that fails on the first unit for a reason that has nothing
    to do with the code being built.

    ``mutation_command`` is written either way, so turning the gate on later is a one-word
    edit rather than a lookup.
    """
    if _mutmut_paths_are_set(root):
        return StackProfile(
            stacks=("python",),
            test_command="pytest -q",
            static_checks=("ruff check {paths}",),
            require_mutation_check=True,
            mutation_command="mutmut run",
        )
    return StackProfile(
        stacks=("python",),
        test_command="pytest -q",
        static_checks=("ruff check {paths}",),
        require_mutation_check=False,
        mutation_command="mutmut run",
        mutation_note=(
            "The mutation gate is off because nothing here sets mutmut's paths_to_mutate, so "
            "`mutmut run` would guess at a directory this repository may not have. To turn "
            "it on, set paths_to_mutate in a [mutmut] section of setup.cfg (or [tool.mutmut] "
            "in pyproject.toml), then set require_mutation_check to true. Scope it narrowly: "
            "mutmut runs the whole suite again for every mutant."
        ),
    )


def resolve_profile(root: Path) -> StackProfile:
    """The gate commands Studio would offer the repository at ``root``.

    The setup wizard's opening guess, and nothing else: ``load_loop_config`` does not
    call this, because a repository's own config file is the only thing that decides how
    /forge gates it. A profile whose test_command is None is a valid result meaning
    "recognised, no command known" — the wizard writes a blank template for it.
    """
    stacks = tuple(detect_stacks(root))
    if len(stacks) != 1:
        return StackProfile(stacks=stacks)
    if stacks[0] == "node":
        return _node_profile(root)
    if stacks[0] == "python":
        return _python_profile(root)
    return PROFILES[stacks[0]]


def _detected_line(profile: StackProfile, root: Path) -> str:
    """The one line of the wizard's template that says what was found here, and why it is
    no help. Written into the file someone is about to edit; the loader's refusal no
    longer mentions detection at all."""
    markers = dict(_matched_markers(root))
    named = [f"{stack} ({markers[stack]})" for stack in profile.stacks]

    if not named:
        # Deliberately no list of the stacks Studio knows: the table recognises more of
        # them than it serves, so naming a few while recognising more reads as a lie.
        return "nothing — no marker file Studio recognises is present here."

    if len(named) > 1:
        both = (
            f"{named[0]} and {named[1]} both match"
            if len(named) == 2
            else ", ".join(named[:-1]) + f" and {named[-1]} all match"
        )
        return (
            f"{both}. Pick one by writing the command yourself; guessing here would gate "
            "one language's code with the other's test runner."
        )

    stack = profile.stacks[0]
    if stack == "unity":
        return (
            f"{named[0]}. Studio ships no test command for Unity — a batchmode run needs a "
            "wrapper that reads the result file, because Unity reports success even when "
            "it discovered no tests at all."
        )
    if stack == "node":
        return (
            f'{named[0]}. package.json declares no "test" script. `npm test` in this repo '
            'exits with "missing script: test", which would fail your unit for the wrong '
            "reason."
        )
    return f"{named[0]}. Studio ships no test command for {stack.capitalize()}."


FORGE_RULES_FILE = ".claude/commands/forge.md"


def _with_fix(message: str, fix: str) -> str:
    return f"{message}\n  Fix: {fix}\n  See {FORGE_RULES_FILE}"


def _no_test_command_message(config_path: Path) -> str:
    """Why the loop is refusing to start, and the exact lines that fix it.

    Five repositories in ten reach this message rather than a filled-in gate, so it is
    not an edge case — it is this feature's main interface. It never offers a value that
    skips the gate: the only command that would satisfy such a value is one that does
    nothing, which reopens the hole the refusal closes.

    The two wordings are chosen by whether ``config_path`` is *there*, and never by which
    branch of the resolution chain handed it over. A file passed in explicitly with a
    blank key is a blank key, not a missing file, and telling its owner the path does not
    exist sends them looking for something they are already holding.

    It says nothing about what was detected, because by the time anyone reads this nothing
    has been: the file is the only thing that decides how a repo is gated.
    """
    if config_path.exists():
        found = "the file is there, but gate.test_command in it is blank or missing."
        fix = [
            f"Fill in the test_command line in {config_path}:",
            "",
            "    [gate]",
            '    test_command = "<the command that runs this repo\'s tests>"',
        ]
        fix_line = f"fill in gate.test_command in {config_path} with the command that runs this repo's tests."
    else:
        found = "there is no file at that path."
        fix = [
            f"Write {config_path}:",
            "",
            "    [gate]",
            '    test_command = "<the command that runs this repo\'s tests>"',
            "",
            "Or run /studio-setup, which writes that file for you.",
        ]
        fix_line = f"write {config_path} with a [gate] test_command, or run /studio-setup, which writes it."
    return _with_fix("\n".join([
        "gate.test_command is not set, and Studio has no default for this repository.",
        "",
        f"  Looked in:  {config_path}",
        f"  Found:      {found}",
        "",
        "/forge runs a test gate; without a command it would ask the writer agent to invent",
        "one and then believe whatever it reported back. It will not do that.",
        "",
        *fix,
        "",
        "If this repository has no tests at all, that is the real answer and there is",
        "nothing to set: /forge is for code you can prove still works. Use /spec to",
        "settle the design and build it the ordinary way.",
    ]), fix_line)


def _no_mutation_command_message(config_path: Path) -> str:
    """The other way a gate can be unrunnable: the check is on and has nothing to run."""
    return "\n".join([
        "gate.require_mutation_check is on, but gate.mutation_command is empty.",
        "",
        f"  Looked in:  {config_path}",
        "",
        "The writer would be told to run the mutation check with no command to run.",
        "",
        f"Give it one in {config_path}, or turn the check off there:",
        "",
        "    [gate]",
        '    mutation_command = "<the command that mutation-tests this repo>"',
        "    # or, if this repo has no mutation tooling:",
        "    require_mutation_check = false",
    ])


def _bare_static_check_name_message(entry: str, config_path: Path) -> str:
    """Why a leftover tool name is refused, and the exact line that replaces it.

    Studio itself planted these: `/studio-setup` in a Python repo wrote
    ``static_checks = ["ruff"]`` and never overwrites what it wrote, so a config file out
    there says a name where the loop now expects a command. Refusing beats auto-upgrading —
    an auto-upgrade leaves the file saying one thing while the loop runs another.
    """
    replacement = LEGACY_STATIC_CHECK_COMMANDS[entry.strip()]
    return _with_fix("\n".join([
        f'gate.static_checks holds "{entry}", which is a tool name and not a command to run.',
        "",
        f"  Looked in:  {config_path}",
        "",
        "static_checks now holds the commands /forge actually runs, so a bare name would run",
        "nothing and still report a clean static check.",
        "",
        f"Replace that entry in {config_path}:",
        "",
        "    [gate]",
        f'    static_checks = ["{replacement}"]',
        "",
        "{paths} is replaced with the paths the unit is scoped to. A command without it runs as",
        'written, which is what you want for a wrapper like "make lint" or "npm run lint".',
    ]), f'replace "{entry}" with "{replacement}" in {config_path}.')


def _require_gate_commands(config: LoopConfig, config_path: Path) -> None:
    """Refuse a resolved config whose gate the loop cannot actually run.

    ``config_path`` is the file that decides this repo's gate, and every refusal here
    names it — so it is passed in rather than worked out again, and it is the same path
    whether that file exists or not.

    Deliberately not a branch in ``LoopConfig.__post_init__``: that checks types, while
    this asks whether a resolved config is *runnable*, which needs to know which file
    should have supplied the command to explain itself. An empty string passes
    __post_init__ today and would flow all the way to the writer, which is told to run the
    command and then believed when it reports the result.

    ``static_checks`` holds the commands the loop runs. An empty list is still not a
    refusal — it means "skip the static check" — and any command is taken as written. The
    one refusal is a leftover bare tool name, which would run nothing at all.
    """
    if not config.test_command.strip():
        raise LoopConfigError(_no_test_command_message(config_path))
    if config.require_mutation_check and not config.mutation_command.strip():
        raise LoopConfigError(_no_mutation_command_message(config_path))
    for entry in config.static_checks:
        if isinstance(entry, str) and entry.strip() in LEGACY_STATIC_CHECK_COMMANDS:
            raise LoopConfigError(_bare_static_check_name_message(entry, config_path))


@dataclass
class LoopConfig:
    """Configuration for the implementation writer/editor loop.

    The [loop] and [editor] defaults are the shipped defaults from the spec §4. The
    [gate] fields have no such defaults, and that is the point: a repository's own config
    file is the only thing that says how /forge gates it, so a key that file leaves out
    has to arrive here as nothing rather than as Python's idea of a reasonable command.
    Give them literals again — ``"pytest -q"``, ``"mutmut run"`` — and a repo whose file
    sets only ``test_command`` quietly starts being told to run tools it does not have.

    ``test_command`` has no default at all, so ``LoopConfig()`` is a TypeError rather than
    a config that gates on nothing. A gate with no command is a real state, reached by
    writing ``test_command=""``; it is never reached by leaving the argument off.
    """
    # [gate]
    test_command: str
    static_checks: List[str] = field(default_factory=list)
    require_mutation_check: bool = False
    mutation_command: str = ""
    observe_command: str = ""
    # [loop]
    deliver_on_gate_fail: bool = True
    # [editor]
    mandate: str = "contrarian"
    read_scope: str = "touched+importers"
    output_budget: int = 400

    def __post_init__(self):
        if self.mandate not in VALID_MANDATES:
            raise ValueError(
                f"editor.mandate must be one of {VALID_MANDATES}, got '{self.mandate}'"
            )
        if not isinstance(self.static_checks, list):
            raise ValueError("gate.static_checks must be a list")
        if not isinstance(self.output_budget, int) or isinstance(self.output_budget, bool):
            raise ValueError("editor.output_budget must be an integer")
        if self.read_scope not in VALID_READ_SCOPES:
            raise ValueError(
                f"editor.read_scope must be one of {VALID_READ_SCOPES}, got '{self.read_scope}'"
            )
        if not isinstance(self.test_command, str):
            raise ValueError("gate.test_command must be a string")
        if not isinstance(self.deliver_on_gate_fail, bool):
            raise ValueError("loop.deliver_on_gate_fail must be a boolean")
        if not isinstance(self.require_mutation_check, bool):
            raise ValueError("gate.require_mutation_check must be a boolean")
        if not isinstance(self.mutation_command, str):
            raise ValueError("gate.mutation_command must be a string")
        if not isinstance(self.observe_command, str):
            raise ValueError("gate.observe_command must be a string")

    @property
    def editor_enabled(self) -> bool:
        """Whether the editor pass runs (mandate other than 'off')."""
        return self.mandate != "off"


def project_artifact_root(studio_root: Path) -> Path:
    """The consuming repo root where project-local config lives.

    Public because ``setup.py`` asks it where ``/forge`` will look: one function, two
    callers, so the wizard cannot write a file the loader never reads.

    Mirrors run_phase.get_artifact_root's installed-layout detection WITHOUT importing
    run_phase (impl_loop ships standalone to .studio/source/): honor STUDIO_ARTIFACT_ROOT,
    else map an installed snapshot ``<repo>/.studio/source`` to ``<repo>``, else fall back
    to the source root itself (the Studio source repo, where they coincide).
    """
    env = os.environ.get("STUDIO_ARTIFACT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if studio_root.name == "source" and studio_root.parent.name == ".studio":
        return studio_root.parent.parent
    return studio_root


def project_config_root(repo_root: Path) -> Path:
    """Where ``repo_root`` keeps its project-local Studio config.

    ``project_artifact_root`` answers this for the Studio *this process is running from*.
    ``setup.py`` needs the same answer about a repo named by ``--target``, which may be a
    different one entirely — so it asks here, naming the repo rather than inheriting ours.

    A Studio source checkout keeps project-local config under ``studio/`` — beside the
    ``integrations.toml`` already there — because in that layout the artifact root IS the
    package directory, which is what ``run_phase.get_artifact_root`` returns for it too. Every
    other repo keeps it at the root. Get this wrong in the source repo and the wizard writes a
    file ``/forge`` never reads (issue #133).
    """
    package = repo_root / "studio"
    if (package / "impl_loop.py").is_file():
        return package
    return repo_root


def _resolve_config_path(path: Path | None, studio_root: Path) -> Path | None:
    """Resolve the config path via the resolution chain.

    explicit ``path`` → ``<artifact-root>/.studio/implementation_loop.toml`` (the project
    override, which lives at the consuming repo root, NOT under the source snapshot) →
    ``<studio-root>/config/implementation_loop.toml`` (the shipped default). Returns None
    when nothing in the chain exists (caller refuses with ``LoopConfigError``).
    """
    if path is not None:
        return Path(path)
    local = project_artifact_root(studio_root) / ".studio" / "implementation_loop.toml"
    if local.exists():
        return local
    shipped = studio_root / "config" / "implementation_loop.toml"
    if shipped.exists():
        return shipped
    return None


def _gate_config_path(path: Path | None, repo_root: Path) -> Path:
    """The file that decides this repo's gate, which every gate refusal names.

    The explicitly requested file when there is one, and otherwise the repo's own
    ``.studio/implementation_loop.toml`` — named whether or not it is there, because
    "there is no file at that path" is the useful half of the refusal for a repo that
    has never written one.

    The resolution chain must never land here on Studio's shipped
    ``config/implementation_loop.toml``. That file carries no [gate] table at all, so it is
    never what gates a repository, and sending someone to edit it would send them to a copy
    the next update overwrites. Ask for it by name and the refusal does name it — you are
    holding that file, and being told about a different one would be the confusing answer.
    """
    if path is not None:
        return Path(path)
    return repo_root / ".studio" / "implementation_loop.toml"


def load_loop_config(
    path: Path | None = None,
    studio_root: Path | None = None,
    test_command_fallback: str | None = None,
) -> LoopConfig:
    """
    Load loop configuration from TOML, mirroring load_scopes_config().

    Resolution chain: explicit ``path`` → project override at
    ``<artifact-root>/.studio/implementation_loop.toml`` (the consuming repo root, found
    even when this module runs from an installed ``.studio/source`` snapshot) → shipped
    ``<studio-root>/config/implementation_loop.toml``. An explicit ``path`` that does not
    exist raises FileNotFoundError: a typo'd config path is an error rather than a silent
    request for defaults.

    **The gate commands come from that file and from nowhere else.** A [gate] key the file
    leaves out is empty, not a guess: nothing is detected here, and no shipped default
    fills the gap. When nothing supplies a test command this raises LoopConfigError rather
    than returning a config the loop would fail on later for a reason that has nothing to
    do with your code, and the refusal names the file it read.

    All tables/keys are optional; unspecified [gate] keys resolve to empty, and
    unspecified [loop]/[editor] keys to the LoopConfig defaults. See
    config/implementation_loop.toml (the shipped default) and SPEC §4 for the canonical
    table shape.

    Args:
        path: Explicit path to a .toml config. When None, the resolution chain runs.
        studio_root: Base for the resolution chain (defaults to the studio package
            dir). Exposed for testing.

    Returns:
        LoopConfig with the file's values, and nothing where it named nothing.

    Raises:
        FileNotFoundError: If an explicit ``path`` is given but does not exist.
        LoopConfigError: If the resolved gate has no command to run.
        ValueError: If the resolved file has invalid TOML or invalid field values.
    """
    if path is not None and not Path(path).exists():
        raise FileNotFoundError(f"Loop config not found at explicit path: {path}")

    root = studio_root if studio_root is not None else STUDIO_ROOT
    repo_root = project_artifact_root(root)
    gate_file = _gate_config_path(path, repo_root)

    config_path = _resolve_config_path(path, root)
    if config_path is None:
        raise LoopConfigError(_no_test_command_message(gate_file))

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in {config_path}: {e}") from e

    loop = data.get("loop", {})
    gate = data.get("gate", {})
    editor = data.get("editor", {})
    for name, table in (("loop", loop), ("gate", gate), ("editor", editor)):
        if not isinstance(table, dict):
            raise ValueError(f"'{name}' must be a table/dict: {config_path}")

    # An empty gate, kept only so the [loop] and [editor] fallbacks below read out of the
    # dataclass rather than being written a second time here, where they could drift.
    defaults = LoopConfig(test_command="")
    test_command = gate.get("test_command", defaults.test_command)
    if test_command_fallback and isinstance(test_command, str) and not test_command.strip():
        test_command = test_command_fallback
    resolved = LoopConfig(
        deliver_on_gate_fail=loop.get("deliver_on_gate_fail", defaults.deliver_on_gate_fail),
        test_command=test_command,
        static_checks=gate.get("static_checks", list(defaults.static_checks)),
        require_mutation_check=gate.get("require_mutation_check", defaults.require_mutation_check),
        mutation_command=gate.get("mutation_command", defaults.mutation_command),
        observe_command=gate.get("observe_command", defaults.observe_command),
        mandate=editor.get("mandate", defaults.mandate),
        read_scope=editor.get("read_scope", defaults.read_scope),
        output_budget=editor.get("output_budget", defaults.output_budget),
    )
    _require_gate_commands(resolved, gate_file)
    return resolved


def _git_common_dir(directory: Path) -> str | None:
    """The shared git directory of the repository ``directory`` belongs to.

    Returns None when ``directory`` is not inside a git worktree at all, which is
    how the caller tells "not a worktree" apart from "a worktree of some other repo".

    Two details here are load-bearing, both verified against real git:

    - ``--path-format=absolute``. Without it git answers with a path relative to
      where it ran, so the main checkout reports a bare ``.git`` while a linked
      worktree reports an absolute path, and the two never compare equal.
    - ``--git-common-dir``, never ``--git-dir``. A linked worktree's own git dir is
      ``<common>/worktrees/<name>``, so it differs from the main repo's by design.
      The common dir is the one thing a worktree and its main repo share.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=str(directory),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return os.path.realpath(result.stdout.strip())


def _show(character: str) -> str:
    """The character as the user typed it, with the invisible ones spelled out.

    ``repr()`` is no good here: it renders a backslash as ``'\\\\'`` and a newline as
    ``'\\n'``, so a reader comparing the message against their own directory name sees
    two characters where they typed one.
    """
    return _INVISIBLE.get(character, character)


def explain_unquotable_path(path_text: str) -> str | None:
    """Say which characters of ``path_text`` are not accepted, or None if all are.

    The message points at each offending character with a caret under the path,
    then gives a reason for the ones ``_KNOWN_BAD`` can explain.
    """
    if all(character in _ALLOWED for character in path_text):
        return None

    shown_path = ""
    carets = ""
    for character in path_text:
        shown = _show(character)
        shown_path += shown
        carets += ("^" if character not in _ALLOWED else " ") * len(shown)

    lines = [
        f"work-dir {WORK_DIR_UNQUOTABLE}: this path holds characters the loop "
        "cannot safely quote:",
        "",
        f"    {shown_path}",
        f"    {carets.rstrip()}",
    ]

    # First-appearance order, so the reasons read in the same order as the carets.
    reported: list[str] = []
    for character in path_text:
        if character in _KNOWN_BAD and character not in reported:
            reported.append(character)
            lines.append(f"    '{_show(character)}' {_KNOWN_BAD[character]}")

    lines += [
        "",
        'The loop renders this path into `git -C "<path>"` inside instruction text '
        "an agent then runs, so anything outside the accepted set could change what "
        f"that agent runs. Accepted: {_ALLOWED_SUMMARY}. Rename the directory.",
    ]
    return "\n".join(lines)


def validate_work_dir(work_dir: str | Path, main_repo: Path | None = None) -> Path:
    """Check that ``work_dir`` is a git worktree of this repository.

    Returns the resolved absolute path, which is what /forge pins the rest of the run
    to. Raises WorkDirError naming which of the four failures it hit (``missing``,
    ``not-a-worktree``, ``different-repo``, ``unquotable``) and the path it tried.

    Validation has to live here in Python because the Workflow sandbox the loop runs
    in has no filesystem or process access — it can only spawn agents and build
    strings, so it cannot stat a path or ask git anything.

    Args:
        work_dir: The directory the agents are being told to work in.
        main_repo: A directory inside the repository ``work_dir`` must belong to
            (defaults to this module's own checkout). Exposed for testing.
    """
    path = Path(work_dir).expanduser().resolve()
    # Checked before is_dir on purpose: a directory with a hostile name can genuinely
    # exist, and the point is to refuse it rather than confirm it is there.
    unquotable = explain_unquotable_path(str(path))
    if unquotable is not None:
        raise WorkDirError(_with_fix(
            unquotable,
            "rename the directory so its path holds only the accepted characters, and pass the new path.",
        ))
    if not path.is_dir():
        raise WorkDirError(_with_fix(
            f"work-dir {WORK_DIR_MISSING}: no directory at {path}",
            "pass --work-dir the path of an existing worktree of this repository; "
            "`git worktree list` shows them.",
        ))

    work_dir_git = _git_common_dir(path)
    if work_dir_git is None:
        raise WorkDirError(_with_fix(
            f"work-dir {WORK_DIR_NOT_A_WORKTREE}: {path} is not inside a git worktree",
            "make one with `git worktree add <path> <branch>` and pass that path, or drop --work-dir.",
        ))

    main_repo_git = _git_common_dir(main_repo if main_repo is not None else STUDIO_ROOT)
    if work_dir_git != main_repo_git:
        raise WorkDirError(_with_fix(
            f"work-dir {WORK_DIR_DIFFERENT_REPO}: {path} belongs to the repository at "
            f"{work_dir_git}, not to this one ({main_repo_git})",
            "pass a worktree of this repository, or run /forge from the repository that path belongs to.",
        ))
    return path


def _git_output(directory: Path, *arguments: str) -> str | None:
    """What ``git <arguments>`` prints when run in ``directory``, or None if git refuses."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(directory),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def validate_branch(directory: str | Path, expected_branch: str) -> str:
    """Check that ``directory`` is a clean checkout of ``expected_branch``.

    /forge runs this as its last step before the loop starts, on the branch its plan
    named. Returns the branch name. Raises BranchError naming which of three failures
    it hit:

    - ``protected-branch``: the plan names main or master. The loop commits, and a
      unit's commits never go straight onto the main branch.
    - ``wrong-branch``: the tree is on some other branch, or on none. Another session
      can switch a shared checkout between the plan and the first commit, and the
      writer commits to whatever branch it finds.
    - ``dirty-tree``: something is uncommitted. The writer commits with ``git add -A``,
      which would sweep it into the unit, and the loop undoes a bad edit with
      ``git reset --hard``, which would delete it.

    Like the work-dir check, this lives in Python because the Workflow sandbox the
    loop runs in cannot ask git anything.
    """
    path = Path(directory)
    if expected_branch in _PROTECTED_BRANCHES:
        raise BranchError(_with_fix(
            f"branch {BRANCH_PROTECTED}: the loop commits as it goes and never commits "
            f"straight to {expected_branch}. Switch {path} to a feature branch, such as "
            "impl/<unit_id>, and run /forge again.",
            "create a feature branch such as impl/<unit_id>, switch the tree to it, and run /forge again.",
        ))

    current_branch = (_git_output(path, "branch", "--show-current") or "").strip()
    if current_branch != expected_branch:
        found = (
            f"is on {current_branch}"
            if current_branch
            else "is not on any branch (a detached HEAD, or not a git repository)"
        )
        raise BranchError(_with_fix(
            f"branch {BRANCH_WRONG}: the plan commits to {expected_branch}, but {path} "
            f"{found}. Something moved the checkout after the plan was made. Check it out "
            "again, or give the run a worktree of its own with --work-dir, and run /forge "
            "again.",
            "check out the planned branch again, or give the run its own worktree with --work-dir.",
        ))

    status = _git_output(path, "status", "--porcelain")
    if status is None:
        # Git found the branch but can't say what is uncommitted (a corrupt index, a
        # permissions problem). A tree nobody can vouch for is refused, not assumed clean.
        raise BranchError(_with_fix(
            f"branch {BRANCH_DIRTY_TREE}: `git status` failed in {path}, so there is no "
            "telling whether anything is uncommitted. Run `git status` there, fix what it "
            "reports, then run /forge again.",
            "run `git status` in that directory, fix what it reports, then run /forge again.",
        ))

    uncommitted = status.splitlines()
    if uncommitted:
        lines = [
            f"branch {BRANCH_DIRTY_TREE}: {path} has {len(uncommitted)} uncommitted "
            "path(s):",
            "",
        ]
        lines += [f"    {entry}" for entry in uncommitted[:_DIRTY_PATHS_SHOWN]]
        if len(uncommitted) > _DIRTY_PATHS_SHOWN:
            lines.append(f"    ... and {len(uncommitted) - _DIRTY_PATHS_SHOWN} more")
        lines += [
            "",
            "The writer commits with `git add -A`, so these would land in the unit's "
            "commit, and the loop undoes a bad edit with `git reset --hard`, which would "
            "delete the uncommitted ones. Commit or stash them there, then run /forge again.",
        ]
        raise BranchError(_with_fix("\n".join(lines), "commit or stash those paths, then run /forge again."))

    return expected_branch


def runtime_knobs(config: LoopConfig) -> dict:
    """Project a resolved LoopConfig onto the runtime knobs the JS workflow needs.

    This is the consume side of load_loop_config(): the /forge command runs this
    module as a script (``python .studio/source/impl_loop.py``, or
    ``python studio/impl_loop.py`` in the Studio source repo), reads this dict, and
    merges it into the workflow args. Only already-resolved config is exposed; no
    new fields.
    """
    return {
        "editor_enabled": config.editor_enabled,
        "test_command": config.test_command,
        "static_checks": config.static_checks,
        "require_mutation_check": config.require_mutation_check,
        "mutation_command": config.mutation_command,
        "observe_command": config.observe_command,
        "read_scope": config.read_scope,
        "output_budget": config.output_budget,
    }


def pack_check_command(path: Path | None = None) -> str | None:
    import packs

    config_path = _resolve_config_path(path, STUDIO_ROOT).resolve()
    try:
        departments = packs.load_declaration(config_path)
    except packs.PackConfigError as error:
        raise LoopConfigError(str(error)) from error
    if not departments:
        return None
    run_phase = STUDIO_ROOT / "run_phase.py"
    for quoted_path in (sys.executable, str(run_phase), str(config_path)):
        refusal = explain_unquotable_path(quoted_path)
        if refusal is not None:
            raise LoopConfigError(
                f"{config_path} declares a pack, but its check cannot be quoted into static_checks.\n{refusal}"
            )
    return f'"{sys.executable}" "{run_phase}" check-packs --config "{config_path}"'


def _gate_suites(config_path: Path) -> tuple[dict, str | None]:
    with open(config_path, "rb") as handle:
        gate = tomllib.load(handle).get("gate", {})
    top_level = _git_output(config_path.parent, "rev-parse", "--show-toplevel")
    if top_level is None:
        gate_config = None
        repository_root = _tree_root(Path.cwd())
    else:
        repository_root = Path(top_level.strip()).resolve()
        gate_config = config_path.relative_to(repository_root).as_posix()
    if "suites" not in gate:
        return {}, gate_config
    try:
        suites = gate_routes.check_suites(gate["suites"], repository_root, config_path)
    except gate_routes.SuiteError as error:
        raise LoopConfigError(_with_fix(str(error), error.fix)) from error
    return suites, gate_config


def load_knobs(path: Path | None = None, test_command_fallback: str | None = None) -> dict:
    knobs = runtime_knobs(load_loop_config(path, test_command_fallback=test_command_fallback))
    pack_check = pack_check_command(path)
    if pack_check is not None:
        knobs["static_checks"] = [*knobs["static_checks"], pack_check]
    knobs["suites"], knobs["gate_config"] = _gate_suites(_resolve_config_path(path, STUDIO_ROOT).resolve())
    return knobs


LOOP_RECORD_NAME = "studio-forge.json"
LOOP_LOCK_NAME = "studio-forge.lock"

RECORD_UNCHECKED = "unchecked-loop"
RECORD_UNREADABLE = "unreadable-record"
RECORD_LAUNCHING = "launch-in-progress"

CHECK_WRONG_BRANCH = "wrong-branch"
CHECK_NO_WRITER_COMMIT = "no-writer-commit"
CHECK_TESTS_FAILED = "tests-failed"
CHECK_PACKS_FAILED = "packs-failed"
CHECK_GATE_CONFIG_CHANGED = "gate-config-changed"

_RECORD_TEXT_FIELDS = ("unit_id", "branch", "tree", "base_sha", "test_command", "started_at")
_RECORD_OPTIONAL_TEXT_FIELDS = ("pack_check", "checked_at")

_MISSING_UNIT_ID_MESSAGE = (
    "--branch needs a unit id: pass --unit <id>, or a --spec whose Build Plan has exactly one unit. "
    "If /forge sent this, the session is running an older copy of the command: restart it."
)


class RecordError(ValueError):
    pass


class CheckError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_dir(tree: Path) -> Path | None:
    output = _git_output(tree, "rev-parse", "--absolute-git-dir")
    if output is None:
        return None
    return Path(output.strip())


def _tree_root(tree: Path) -> Path:
    output = _git_output(tree, "rev-parse", "--show-toplevel")
    if output is None:
        return tree.resolve()
    return Path(output.strip())


def check_command(tree: Path) -> str:
    return shlex.join([sys.executable, str(STUDIO_ROOT / "impl_loop.py"), "--check", "--work-dir", str(tree)])


def _write_record(path: Path, record: dict) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
    os.replace(temporary_name, path)


def _read_record(path: Path) -> dict:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"it is not readable JSON: {error}") from error
    if not isinstance(record, dict):
        raise ValueError("it does not hold a JSON object")
    for name in _RECORD_TEXT_FIELDS:
        if not isinstance(record.get(name), str):
            raise ValueError(f"its {name} is missing or is not text")
    for name in _RECORD_OPTIONAL_TEXT_FIELDS:
        if name not in record or not (record[name] is None or isinstance(record[name], str)):
            raise ValueError(f"its {name} is missing or is neither text nor null")
    if not isinstance(record.get("problems"), list):
        raise ValueError("its problems is missing or is not a list")
    suites = record.get("suites", {})
    try:
        gate_routes.check_suites(suites, None, path)
    except gate_routes.SuiteError as error:
        raise ValueError(f"its suites is malformed: {error}") from error
    gate_config = record.get("gate_config")
    if not (gate_config is None or isinstance(gate_config, str)):
        raise ValueError("its gate_config is neither text nor null")
    return {**record, "suites": suites, "gate_config": gate_config}


@contextmanager
def _record_lock(lock_path: Path, refusal: Exception):
    # The same protocol as the portable host (forge_host.mjs): the lock is held while the file exists.
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise refusal from error
    try:
        yield
    finally:
        os.close(descriptor)
        lock_path.unlink()


def open_loop_record(
    tree: Path,
    unit_id: str,
    branch: str,
    base_sha: str,
    test_command: str,
    pack_check: str | None,
    suites: dict,
    gate_config: str | None,
) -> str:
    root = _tree_root(tree)
    path = _git_dir(root) / LOOP_RECORD_NAME
    lock_path = path.with_name(LOOP_LOCK_NAME)
    refusal = RecordError(_with_fix(
        f"{RECORD_LAUNCHING}: another /forge run, launch or check holds {lock_path} and is using this tree "
        "right now, so nothing was launched.",
        f"let it finish, then run /forge again; if nothing is running, remove {lock_path}.",
    ))
    with _record_lock(lock_path, refusal):
        if path.exists():
            try:
                existing = _read_record(path)
            except ValueError as why:
                raise RecordError(_with_fix(
                    f"{RECORD_UNREADABLE}: {path} is there but cannot be read as a /forge loop record ({why}). "
                    "A /forge run may still be holding this tree, so nothing was launched.",
                    f"look at {path}; once no /forge run is using this tree, remove it and run /forge again.",
                )) from why
            if existing["checked_at"] is None:
                raise RecordError(_with_fix(
                    f"{RECORD_UNCHECKED}: the /forge run of {existing['unit_id']} on {existing['branch']}, "
                    f"started {existing['started_at']}, was never checked. Check it before launching another:\n\n"
                    f"    {check_command(root)}",
                    "run that command, read what it reports, then run /forge again.",
                ))
        launched_at = _utc_now()
        _write_record(path, {
            "unit_id": unit_id,
            "branch": branch,
            "tree": str(root),
            "base_sha": base_sha,
            "test_command": test_command,
            "pack_check": pack_check,
            "suites": suites,
            "gate_config": gate_config,
            "started_at": launched_at,
            "checked_at": None,
            "problems": [],
        })
        return launched_at


def _is_writer_commit(subject: str, unit_id: str) -> bool:
    return re.match(rf"writer: {re.escape(unit_id)}(?![A-Za-z0-9_])", subject) is not None


def _git_problems(root: Path, record: dict) -> list[dict]:
    problems = []
    current_branch = (_git_output(root, "branch", "--show-current") or "").strip()
    if current_branch != record["branch"]:
        found = f"on {current_branch}" if current_branch else "on no branch"
        problems.append({
            "name": CHECK_WRONG_BRANCH,
            "detail": f"{root} is {found}, not on {record['branch']}, the branch the loop was launched on.",
        })
    subjects = _git_output(root, "log", "--format=%s", f"{record['base_sha']}..HEAD")
    if subjects is None:
        problems.append({
            "name": CHECK_NO_WRITER_COMMIT,
            "detail": f"git cannot list the commits from {record['base_sha']} to HEAD, so no "
                      f"`writer: {record['unit_id']}` commit can be found.",
        })
    elif not any(_is_writer_commit(subject, record["unit_id"]) for subject in subjects.splitlines()):
        problems.append({
            "name": CHECK_NO_WRITER_COMMIT,
            "detail": f"no commit from {record['base_sha']} to HEAD has a subject starting "
                      f"`writer: {record['unit_id']}`.",
        })
    return problems


def _run_pack_check(command: str, root: Path) -> tuple[int, str]:
    result = subprocess.run(
        command, shell=True, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    sys.stderr.write(result.stdout)
    printed_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    first_line = printed_lines[0] if printed_lines else "it printed nothing"
    return result.returncode, first_line


def check_loop(tree: Path) -> int:
    if not tree.is_dir():
        raise CheckError(f"Could not check: there is no directory at {tree}.")
    git_dir = _git_dir(tree)
    if git_dir is None:
        raise CheckError(f"Could not check: {tree} is not inside a git worktree, so it has no /forge loop record.")
    path = git_dir / LOOP_RECORD_NAME
    lock_path = git_dir / LOOP_LOCK_NAME
    refusal = CheckError(
        f"Could not check: another /forge run, launch or check holds {lock_path} and is using this tree "
        f"right now. No test was run. If nothing is running, remove {lock_path}."
    )
    with _record_lock(lock_path, refusal):
        return _check_record(tree, path)


def _check_record(tree: Path, path: Path) -> int:
    if not path.exists():
        raise CheckError(f"Nothing to check: there is no /forge loop record at {path}.")
    try:
        record = _read_record(path)
    except ValueError as why:
        raise CheckError(
            f"Could not check: {path} cannot be read as a /forge loop record ({why}). No test was run."
        ) from why

    root = _tree_root(tree)
    problems = _git_problems(root, record)
    tests = []
    packs = None
    if record["pack_check"] is not None:
        packs = {"command": record["pack_check"], "exit_code": None}

    if not problems:
        try:
            changed = gate_routes.changed_files(root, record["base_sha"])
            gate_config_changed = gate_routes.config_changed(root, record["base_sha"], record["gate_config"])
        except gate_routes.RoutesError as error:
            raise CheckError(f"Could not check: {error}. No test was run.") from error
        if gate_config_changed:
            problems.append(_gate_config_changed_problem(record))
        routes, _unclaimed = gate_routes.route(record["suites"], record["test_command"], changed)
        tests = gate_routes.run(root, routes)
        for test_run in tests:
            if test_run["exit_code"] != 0:
                problems.append(_tests_failed_problem(test_run))
        if packs is not None:
            packs["exit_code"], first_line = _run_pack_check(record["pack_check"], root)
            if packs["exit_code"] != 0:
                problems.append({
                    "name": CHECK_PACKS_FAILED,
                    "detail": f"the pack check exited {packs['exit_code']}: {first_line}",
                })

    clean = not problems
    if clean:
        path.unlink()
    else:
        _write_record(path, {
            **record,
            "checked_at": _utc_now(),
            "problems": [f"{problem['name']}: {problem['detail']}" for problem in problems],
        })

    print(json.dumps({
        "clean": clean,
        "unit_id": record["unit_id"],
        "branch": record["branch"],
        "tests": tests,
        "packs": packs,
        "problems": problems,
    }))
    if not clean:
        sentences = "\n".join(f"{problem['name']}: {problem['detail']}" for problem in problems)
        fix = (
            "fix what each problem names and run the check again; until it passes, tell the user before "
            "the branch is pushed."
        )
        if any(problem["name"] == CHECK_GATE_CONFIG_CHANGED for problem in problems):
            fix += (
                f" Checking again cannot clear {CHECK_GATE_CONFIG_CHANGED}: once a person has read that change, "
                f"delete {path} or launch the unit again."
            )
        print(_with_fix(f"The /forge unit {record['unit_id']} is not clean.\n{sentences}", fix), file=sys.stderr)
        return 1
    return 0


def _tests_failed_problem(test_run: dict) -> dict:
    if test_run["suite"] is None:
        named = "the default test command"
    else:
        named = f"the {test_run['suite']} suite's command"
    return {
        "name": CHECK_TESTS_FAILED,
        "detail": f"{named} `{test_run['command']}` exited {test_run['exit_code']}.",
    }


def _gate_config_changed_problem(record: dict) -> dict:
    return {
        "name": CHECK_GATE_CONFIG_CHANGED,
        "detail": f"{record['gate_config']} changed since {record['base_sha']}, so the next launch on this branch "
                  "would be gated by a config this unit wrote; a person should read that change.",
    }


def _spec_file(spec: str) -> Path | None:
    file_name = spec if spec.endswith(".md") else f"{spec}.md"
    candidates = (
        Path(spec),
        Path(file_name),
        Path("specs") / file_name,
        Path(".studio") / "specs" / file_name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _launch_unit_id(unit: str | None, spec: str | None) -> str | None:
    if unit:
        return unit
    if not spec:
        return None
    from stats import parse_build_plan

    spec_path = _spec_file(spec)
    if spec_path is None:
        return None
    units = parse_build_plan(spec_path.read_text(encoding="utf-8"), spec_path.stem, str(spec_path))
    if len(units) != 1:
        return None
    return units[0].unit_id


def _parse_arguments(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="impl_loop.py",
        description="Print the implementation loop's runtime knobs as JSON.",
    )
    parser.add_argument(
        "config_path",
        nargs="?",
        help="Explicit path to a loop config .toml (default: the resolution chain).",
    )
    parser.add_argument(
        "--work-dir",
        help="Directory the loop's agents must work in; must be a git worktree of this repo.",
    )
    parser.add_argument(
        "--branch",
        help="Branch the loop is about to commit to; the tree must be clean and on it.",
    )
    parser.add_argument(
        "--unit",
        help="The unit this launch builds; --branch needs it, or a --spec planning exactly one unit.",
    )
    parser.add_argument(
        "--spec",
        help="The spec the unit comes from; with no --unit, its Build Plan must hold exactly one unit.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="After a /forge run: run the recorded suites the unit's changes fall under, plus the default, and say whether the unit is clean.",
    )
    args = parser.parse_args(argv[1:])
    if args.check:
        if args.config_path or args.branch or args.unit or args.spec:
            parser.error("--check takes only --work-dir.")
        return args
    if args.branch:
        args.unit_id = _launch_unit_id(args.unit, args.spec)
        if args.unit_id is None:
            parser.error(_MISSING_UNIT_ID_MESSAGE)
    return args


def _launch(args: argparse.Namespace) -> str:
    path = Path(args.config_path) if args.config_path else None
    knobs = load_knobs(path)

    if args.work_dir:
        knobs["work_dir"] = str(validate_work_dir(args.work_dir))

    if args.branch:
        tree_being_built = Path(knobs["work_dir"]) if args.work_dir else Path.cwd()
        knobs["branch"] = validate_branch(tree_being_built, args.branch)
        knobs["base_sha"] = subprocess.check_output(
            ["git", "-C", tree_being_built, "rev-parse", "HEAD"], text=True,
        ).strip()
        knobs["launched_at"] = open_loop_record(
            tree_being_built,
            unit_id=args.unit_id,
            branch=knobs["branch"],
            base_sha=knobs["base_sha"],
            test_command=knobs["test_command"],
            pack_check=pack_check_command(path),
            suites=knobs["suites"],
            gate_config=knobs["gate_config"],
        )

    return json.dumps(knobs)


def _cli(argv: List[str]) -> str:
    """Return the runtime-knobs JSON for the CLI.

    The optional positional argument is an explicit config path for a non-standard
    location. With no arg the normal resolution chain runs, which now finds the project
    override at the consuming repo root (``<repo>/.studio/implementation_loop.toml``) on
    its own, so callers no longer need to pass it explicitly just to honor an installed
    repo's override.

    ``--work-dir`` is checked here, before /forge invokes the workflow, so a bad path
    stops the run before any agent spawns. When it is good, the emitted JSON carries a
    ``work_dir`` key holding the resolved absolute path — that is the path /forge pins
    the rest of the run to.

    ``--branch`` is the last check before the loop starts: the tree the agents will
    commit in (the work dir, or with none the directory this was run from) must be clean
    and on that branch, and the branch must not be main. When it passes, the emitted
    JSON carries a ``branch`` key. Without the flag nothing about the branch is checked,
    so printing the knobs alone works from any tree.

    Raises:
        WorkDirError: If ``--work-dir`` is given and is not a worktree of this repo.
        BranchError: If ``--branch`` is given and the tree is not a clean checkout of it.
        LoopConfigError: If this repository's gate has no test command to run.
    """
    return _launch(_parse_arguments(argv))


def main(argv: List[str]) -> int:
    args = _parse_arguments(argv)
    if args.check:
        try:
            return check_loop(Path(args.work_dir).expanduser().resolve() if args.work_dir else Path.cwd())
        except CheckError as error:
            print(error, file=sys.stderr)
            return 2
    try:
        print(_launch(args))
    except (WorkDirError, BranchError, LoopConfigError, RecordError) as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
