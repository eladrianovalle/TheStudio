#!/usr/bin/env python3
"""
Configuration for the implementation writer/editor loop.

Mirrors the ScopeConfig / load_scopes_config() pattern in scopes.py: a dataclass
for the shipped config tables plus a loader with the tomllib/tomli fallback and a
resolution chain (explicit path → .studio/ override → shipped default → defaults).

See studio/docs/IMPLEMENTATION_LOOP_SPEC.md §4 for the table shape.
"""
from __future__ import annotations

from config_loading import tomllib
import argparse
import json
import os
import string
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


STUDIO_ROOT = Path(__file__).resolve().parent

VALID_MANDATES = {"contrarian", "off"}

VALID_READ_SCOPES = {"touched", "touched+importers"}

# The four ways a --work-dir can be unusable. /forge prints the one it hit, so a
# refused run says what is actually wrong instead of just "bad path".
WORK_DIR_MISSING = "missing"
WORK_DIR_NOT_A_WORKTREE = "not-a-worktree"
WORK_DIR_DIFFERENT_REPO = "different-repo"
WORK_DIR_UNQUOTABLE = "unquotable"

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


class LoopConfigError(ValueError):
    """A resolved loop config the loop cannot run, raised with what to do about it."""


# Marker files that identify a stack, looked for at the repository root only. A pattern
# holding a `*` is globbed; every other pattern is an exact path test.
#
# `rust` is recognised but unserved: Studio ships no gate commands for it, which is how
# the loader says "I know what this is and still have no command for it" instead of
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
    the loader decides whether it is fatal, because an override may still supply the
    command.

    ``static_checks`` is a tuple rather than a list because PROFILES is module-level
    shared state, and ``frozen=True`` would not stop a caller mutating a list in place.
    """
    stacks: tuple[str, ...] = ()
    test_command: str | None = None
    static_checks: tuple[str, ...] = ()
    require_mutation_check: bool = False
    mutation_command: str | None = None


# The gate commands for each stack whose answer is the same in every repository. Node is
# missing on purpose: what it can offer depends on what package.json declares, so
# _node_profile works it out per repo.
PROFILES: dict[str, StackProfile] = {
    "python": StackProfile(
        stacks=("python",),
        test_command="pytest -q",
        static_checks=("ruff",),
        require_mutation_check=True,
        mutation_command="mutmut run",
    ),
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
    detection exists to remove. eslint is required only when the repo shows some sign of
    having it — a ``lint`` script or an ``eslint`` dev dependency.
    """
    package = _read_package_json(root)
    scripts = package.get("scripts")
    dev_dependencies = package.get("devDependencies")
    if not isinstance(scripts, dict):
        scripts = {}
    if not isinstance(dev_dependencies, dict):
        dev_dependencies = {}

    has_test_script = bool(str(scripts.get("test", "")).strip())
    has_linter = "lint" in scripts or "eslint" in dev_dependencies

    return StackProfile(
        stacks=("node",),
        test_command="npm test" if has_test_script else None,
        static_checks=("eslint",) if has_linter else (),
    )


def resolve_profile(root: Path) -> StackProfile:
    """The gate defaults for the repository at ``root``.

    A profile whose test_command is None is a valid result meaning "recognised, no
    command known" — the loader decides whether that is fatal, because an override may
    still supply one.
    """
    stacks = tuple(detect_stacks(root))
    if len(stacks) != 1:
        return StackProfile(stacks=stacks)
    if stacks[0] == "node":
        return _node_profile(root)
    return PROFILES[stacks[0]]


def _detected_line(profile: StackProfile, root: Path) -> str:
    """The one line of the refusal that says what was found here, and why it is no help."""
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


def _no_test_command_message(profile: StackProfile, root: Path) -> str:
    """Why the loop is refusing to start, and the exact three lines that fix it.

    Five repositories in ten reach this message rather than a detected profile, so it is
    not an edge case — it is this feature's main interface. It never offers a value that
    skips the gate: the only command that would satisfy such a value is one that does
    nothing, which reopens the hole the refusal closes.
    """
    override = root / ".studio" / "implementation_loop.toml"
    return "\n".join([
        "gate.test_command is not set, and Studio has no default for this repository.",
        "",
        f"  Looked in:  {root}",
        f"  Detected:   {_detected_line(profile, root)}",
        "",
        "/forge runs a test gate; without a command it would ask the writer agent to invent",
        "one and then believe whatever it reported back. It will not do that.",
        "",
        f"Set the command in {override}:",
        "",
        "    [gate]",
        '    test_command = "<the command that runs this repo\'s tests>"',
        "",
        "Or run /studio-setup, which writes that file for you.",
    ])


def _no_mutation_command_message(root: Path) -> str:
    """The other way a gate can be unrunnable: the check is on and has nothing to run."""
    override = root / ".studio" / "implementation_loop.toml"
    return "\n".join([
        "gate.require_mutation_check is on, but gate.mutation_command is empty.",
        "",
        f"  Looked in:  {root}",
        "",
        "The writer would be told to run the mutation check with no command to run.",
        "",
        f"Give it one in {override}, or turn the check off there:",
        "",
        "    [gate]",
        '    mutation_command = "<the command that mutation-tests this repo>"',
        "    # or, if this repo has no mutation tooling:",
        "    require_mutation_check = false",
    ])


def _require_gate_commands(config: LoopConfig, detected: StackProfile, root: Path) -> None:
    """Refuse a resolved config whose gate the loop cannot actually run.

    Deliberately not a branch in ``LoopConfig.__post_init__``: that checks types, while
    this asks whether a resolved config is *runnable*, which needs the detection context
    to explain itself. An empty string passes __post_init__ today and would flow all the
    way to the writer, which is told to run the command and then believed when it reports
    the result.

    ``static_checks`` is never a refusal — an empty list already means "skip the static
    check", and the command that runs is authored per unit by /forge.
    """
    if not config.test_command.strip():
        raise LoopConfigError(_no_test_command_message(detected, root))
    if config.require_mutation_check and not config.mutation_command.strip():
        raise LoopConfigError(_no_mutation_command_message(root))


@dataclass
class LoopConfig:
    """Configuration for the implementation writer/editor loop.

    The [loop] and [editor] defaults are the shipped defaults from the spec §4. The
    [gate] defaults are Python's, and they are **not** what a repository gets:
    ``load_loop_config`` builds its merge base from ``resolve_profile`` instead, so a
    Node repo starts from Node's commands and a repo Studio cannot identify starts from
    none at all. They are kept here as plain literals rather than a factory reading
    PROFILES — that would trade a readable default for indirection, to prevent a drift
    that ``test_shipped_config_matches_dataclass_defaults`` already catches.
    """
    # [loop]
    deliver_on_gate_fail: bool = True
    # [gate]
    test_command: str = "pytest -q"
    static_checks: List[str] = field(default_factory=lambda: ["ruff"])
    require_mutation_check: bool = True
    mutation_command: str = "mutmut run"
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

    @property
    def editor_enabled(self) -> bool:
        """Whether the editor pass runs (mandate other than 'off')."""
        return self.mandate != "off"


def _project_artifact_root(studio_root: Path) -> Path:
    """The consuming repo root where project-local config lives.

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


def _resolve_config_path(path: Path | None, studio_root: Path) -> Path | None:
    """Resolve the config path via the resolution chain.

    explicit ``path`` → ``<artifact-root>/.studio/implementation_loop.toml`` (the project
    override, which lives at the consuming repo root, NOT under the source snapshot) →
    ``<studio-root>/config/implementation_loop.toml`` (the shipped default). Returns None
    when nothing in the chain exists (caller falls back to built-in defaults).
    """
    if path is not None:
        return Path(path)
    local = _project_artifact_root(studio_root) / ".studio" / "implementation_loop.toml"
    if local.exists():
        return local
    shipped = studio_root / "config" / "implementation_loop.toml"
    if shipped.exists():
        return shipped
    return None


def load_loop_config(path: Path | None = None, studio_root: Path | None = None) -> LoopConfig:
    """
    Load loop configuration from TOML, mirroring load_scopes_config().

    Resolution chain: explicit ``path`` → project override at
    ``<artifact-root>/.studio/implementation_loop.toml`` (the consuming repo root, found
    even when this module runs from an installed ``.studio/source`` snapshot) → shipped
    ``<studio-root>/config/implementation_loop.toml``. An explicit ``path`` that does not
    exist raises FileNotFoundError: a typo'd config path is an error rather than a silent
    request for defaults.

    **The gate commands come from the repository, not from a shipped default.** The merge
    base is ``resolve_profile``'s answer for the repo being built in, so a config file
    that sets only ``gate.test_command`` no longer inherits ``ruff`` and ``mutmut``
    through the gap. When nothing supplies a test command — no override, and a repo Studio
    cannot identify — this raises LoopConfigError rather than returning a config the loop
    would fail on later for a reason that has nothing to do with your code.

    All tables/keys are optional; unspecified keys inherit the detected profile for the
    gate and the LoopConfig defaults for everything else. See
    config/implementation_loop.toml (the shipped default) and SPEC §4 for the canonical
    table shape.

    Args:
        path: Explicit path to a .toml config. When None, the resolution chain runs.
        studio_root: Base for the resolution chain (defaults to the studio package
            dir). Exposed for testing.

    Returns:
        LoopConfig with parsed values merged over the detected profile.

    Raises:
        FileNotFoundError: If an explicit ``path`` is given but does not exist.
        LoopConfigError: If the resolved gate has no command to run.
        ValueError: If the resolved file has invalid TOML or invalid field values.
    """
    if path is not None and not Path(path).exists():
        raise FileNotFoundError(f"Loop config not found at explicit path: {path}")

    root = studio_root if studio_root is not None else STUDIO_ROOT
    repo_root = _project_artifact_root(root)
    detected = resolve_profile(repo_root)
    defaults = LoopConfig(
        test_command=detected.test_command or "",
        static_checks=list(detected.static_checks),
        require_mutation_check=detected.require_mutation_check,
        mutation_command=detected.mutation_command or "",
    )

    config_path = _resolve_config_path(path, root)
    if config_path is None or not config_path.exists():
        _require_gate_commands(defaults, detected, repo_root)
        return defaults

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

    resolved = LoopConfig(
        deliver_on_gate_fail=loop.get("deliver_on_gate_fail", defaults.deliver_on_gate_fail),
        test_command=gate.get("test_command", defaults.test_command),
        static_checks=gate.get("static_checks", list(defaults.static_checks)),
        require_mutation_check=gate.get("require_mutation_check", defaults.require_mutation_check),
        mutation_command=gate.get("mutation_command", defaults.mutation_command),
        mandate=editor.get("mandate", defaults.mandate),
        read_scope=editor.get("read_scope", defaults.read_scope),
        output_budget=editor.get("output_budget", defaults.output_budget),
    )
    _require_gate_commands(resolved, detected, repo_root)
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
        raise WorkDirError(unquotable)
    if not path.is_dir():
        raise WorkDirError(f"work-dir {WORK_DIR_MISSING}: no directory at {path}")

    work_dir_git = _git_common_dir(path)
    if work_dir_git is None:
        raise WorkDirError(
            f"work-dir {WORK_DIR_NOT_A_WORKTREE}: {path} is not inside a git worktree"
        )

    main_repo_git = _git_common_dir(main_repo if main_repo is not None else STUDIO_ROOT)
    if work_dir_git != main_repo_git:
        raise WorkDirError(
            f"work-dir {WORK_DIR_DIFFERENT_REPO}: {path} belongs to the repository at "
            f"{work_dir_git}, not to this one ({main_repo_git})"
        )
    return path


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
        "read_scope": config.read_scope,
        "output_budget": config.output_budget,
    }


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

    Raises:
        WorkDirError: If ``--work-dir`` is given and is not a worktree of this repo.
        LoopConfigError: If this repository's gate has no test command to run.
    """
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
    args = parser.parse_args(argv[1:])

    path = Path(args.config_path) if args.config_path else None
    knobs = runtime_knobs(load_loop_config(path))

    if args.work_dir:
        knobs["work_dir"] = str(validate_work_dir(args.work_dir))

    return json.dumps(knobs)


if __name__ == "__main__":
    import sys
    try:
        print(_cli(sys.argv))
    except (WorkDirError, LoopConfigError) as e:
        # Both are refusals with an explanation already written for a person: print the
        # message alone, with no traceback in front of it, and stop the run.
        print(e, file=sys.stderr)
        sys.exit(1)
