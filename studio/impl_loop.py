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
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


STUDIO_ROOT = Path(__file__).resolve().parent

VALID_MANDATES = {"contrarian", "off"}

VALID_READ_SCOPES = {"touched", "touched+importers"}


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

    Optional ``argv[1]`` is an explicit config path for a non-standard location. With no
    arg the normal resolution chain runs, which now finds the project override at the
    consuming repo root (``<repo>/.studio/implementation_loop.toml``) on its own, so
    callers no longer need to pass it explicitly just to honor an installed repo's override.
    """
    path = Path(argv[1]) if len(argv) > 1 else None
    return json.dumps(runtime_knobs(load_loop_config(path)))


if __name__ == "__main__":
    import sys
    print(_cli(sys.argv))
