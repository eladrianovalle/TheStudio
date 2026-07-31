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


@dataclass
class LoopConfig:
    """Configuration for the implementation writer/editor loop.

    Field defaults are the shipped defaults from the spec §4, so an absent or
    empty config yields a fully usable LoopConfig.
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
    ``<studio-root>/config/implementation_loop.toml`` → built-in defaults. An end-of-chain
    miss (no ``path`` given and nothing found) yields the default LoopConfig; the loop
    ships with a working default, so absence is not a failure. But an explicit ``path``
    that does not exist raises FileNotFoundError: a typo'd config path is an error rather
    than a silent request for defaults.

    All tables/keys are optional; unspecified keys inherit the LoopConfig defaults.
    See config/implementation_loop.toml (the shipped default) and SPEC §4 for the
    canonical table shape.

    Args:
        path: Explicit path to a .toml config. When None, the resolution chain runs.
        studio_root: Base for the resolution chain (defaults to the studio package
            dir). Exposed for testing.

    Returns:
        LoopConfig with parsed values merged over defaults.

    Raises:
        FileNotFoundError: If an explicit ``path`` is given but does not exist.
        ValueError: If the resolved file has invalid TOML or invalid field values.
    """
    if path is not None and not Path(path).exists():
        raise FileNotFoundError(f"Loop config not found at explicit path: {path}")

    root = studio_root if studio_root is not None else STUDIO_ROOT
    config_path = _resolve_config_path(path, root)

    if config_path is None or not config_path.exists():
        return LoopConfig()

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

    defaults = LoopConfig()
    return LoopConfig(
        deliver_on_gate_fail=loop.get("deliver_on_gate_fail", defaults.deliver_on_gate_fail),
        test_command=gate.get("test_command", defaults.test_command),
        static_checks=gate.get("static_checks", list(defaults.static_checks)),
        require_mutation_check=gate.get("require_mutation_check", defaults.require_mutation_check),
        mutation_command=gate.get("mutation_command", defaults.mutation_command),
        mandate=editor.get("mandate", defaults.mandate),
        read_scope=editor.get("read_scope", defaults.read_scope),
        output_budget=editor.get("output_budget", defaults.output_budget),
    )


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
    except WorkDirError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
