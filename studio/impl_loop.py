#!/usr/bin/env python3
"""
Configuration for the implementation writer/editor loop.

Mirrors the ScopeConfig / load_scopes_config() pattern in scopes.py: a dataclass
for the shipped config tables plus a loader with the tomllib/tomli fallback and a
resolution chain (explicit path → .studio/ override → shipped default → defaults).

See studio/docs/IMPLEMENTATION_LOOP_SPEC.md §4 for the table shape.
"""
from __future__ import annotations

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redefine]  # Python 3.10 fallback
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

    @property
    def editor_enabled(self) -> bool:
        """Whether the editor pass runs (mandate other than 'off')."""
        return self.mandate != "off"


def _resolve_config_path(path: Path | None, studio_root: Path) -> Path | None:
    """Resolve the config path via the resolution chain.

    explicit path → .studio/implementation_loop.toml → config/implementation_loop.toml.
    Returns None when nothing in the chain exists (caller falls back to defaults).
    """
    if path is not None:
        return Path(path)
    local = studio_root / ".studio" / "implementation_loop.toml"
    if local.exists():
        return local
    shipped = studio_root / "config" / "implementation_loop.toml"
    if shipped.exists():
        return shipped
    return None


def load_loop_config(path: Path | None = None, studio_root: Path | None = None) -> LoopConfig:
    """
    Load loop configuration from TOML, mirroring load_scopes_config().

    Resolution chain: explicit ``path`` → ``.studio/implementation_loop.toml`` →
    ``config/implementation_loop.toml`` → built-in defaults. An end-of-chain miss
    (no ``path`` given and nothing found) yields the default LoopConfig — the loop
    ships with a working default, so absence is not a failure. But an explicit
    ``path`` that does not exist raises FileNotFoundError: a typo'd config path is an
    error, not a silent request for defaults.

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
        mandate=editor.get("mandate", defaults.mandate),
        read_scope=editor.get("read_scope", defaults.read_scope),
        output_budget=editor.get("output_budget", defaults.output_budget),
    )
