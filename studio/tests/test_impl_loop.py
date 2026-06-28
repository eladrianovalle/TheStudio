#!/usr/bin/env python3
"""Tests for the implementation writer/editor loop config loader."""
import tempfile
from pathlib import Path

import pytest

from impl_loop import (
    LoopConfig,
    VALID_MANDATES,
    VALID_READ_SCOPES,
    load_loop_config,
    runtime_knobs,
)


def _write_toml(text: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(text)
        return Path(f.name)


def test_loop_config_defaults_match_spec():
    """A bare LoopConfig carries the shipped defaults from spec §4."""
    config = LoopConfig()
    assert config.deliver_on_gate_fail is True
    assert config.test_command == "pytest -q"
    assert config.static_checks == ["ruff"]
    assert config.require_mutation_check is True
    assert config.mandate == "contrarian"
    assert config.read_scope == "touched+importers"
    assert config.output_budget == 400
    assert config.editor_enabled is True


def test_loop_config_off_mandate_disables_editor():
    """mandate = 'off' disables the editor pass."""
    config = LoopConfig(mandate="off")
    assert config.editor_enabled is False


def test_loop_config_invalid_mandate():
    """LoopConfig rejects an unknown mandate."""
    with pytest.raises(ValueError, match="mandate"):
        LoopConfig(mandate="bogus")
    assert "contrarian" in VALID_MANDATES
    assert "off" in VALID_MANDATES


def test_loop_config_invalid_output_budget_type():
    """output_budget must be an integer (and not a bool)."""
    with pytest.raises(ValueError, match="output_budget"):
        LoopConfig(output_budget="lots")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="output_budget"):
        LoopConfig(output_budget=True)  # type: ignore[arg-type]


def test_loop_config_invalid_static_checks_type():
    """static_checks must be a list."""
    with pytest.raises(ValueError, match="static_checks"):
        LoopConfig(static_checks="ruff")  # type: ignore[arg-type]


def test_loop_config_invalid_read_scope():
    """read_scope must be one of the known values, not an arbitrary string."""
    with pytest.raises(ValueError, match="read_scope"):
        LoopConfig(read_scope="everything")
    assert "touched+importers" in VALID_READ_SCOPES


def test_loop_config_invalid_bool_fields():
    """The boolean knobs reject non-bool values (e.g. a stray TOML string)."""
    with pytest.raises(ValueError, match="deliver_on_gate_fail"):
        LoopConfig(deliver_on_gate_fail="yes")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="require_mutation_check"):
        LoopConfig(require_mutation_check="no")  # type: ignore[arg-type]


def test_load_loop_config_valid():
    """A valid TOML file parses into a LoopConfig."""
    config_path = _write_toml("""
[loop]
deliver_on_gate_fail = false

[gate]
test_command = "python -m pytest tests/ -q"
static_checks = ["ruff", "mypy"]
require_mutation_check = false

[editor]
mandate = "off"
read_scope = "touched"
output_budget = 250
""")
    try:
        config = load_loop_config(config_path)
        assert config.deliver_on_gate_fail is False
        assert config.test_command == "python -m pytest tests/ -q"
        assert config.static_checks == ["ruff", "mypy"]
        assert config.require_mutation_check is False
        assert config.mandate == "off"
        assert config.read_scope == "touched"
        assert config.output_budget == 250
    finally:
        config_path.unlink()


def test_load_loop_config_partial_inherits_defaults():
    """Unspecified keys inherit the shipped defaults (shallow merge)."""
    config_path = _write_toml("""
[editor]
output_budget = 999
""")
    try:
        config = load_loop_config(config_path)
        # Overridden
        assert config.output_budget == 999
        # Inherited defaults
        assert config.test_command == "pytest -q"
        assert config.static_checks == ["ruff"]
        assert config.mandate == "contrarian"
        assert config.deliver_on_gate_fail is True
    finally:
        config_path.unlink()


def test_load_loop_config_explicit_missing_path_raises():
    """An explicit path that doesn't exist is an error (a typo), not a silent default.

    End-of-chain absence still yields defaults — see the no_config_anywhere test below.
    """
    with pytest.raises(FileNotFoundError):
        load_loop_config(Path("/nonexistent/implementation_loop.toml"))


def test_load_loop_config_no_config_anywhere_returns_defaults():
    """When the resolution chain finds nothing, defaults are returned."""
    with tempfile.TemporaryDirectory() as tmp:
        # Empty studio_root: no .studio/ and no config/ files exist.
        config = load_loop_config(studio_root=Path(tmp))
        assert config == LoopConfig()


def test_load_loop_config_invalid_toml():
    """Malformed TOML raises a clear ValueError."""
    config_path = _write_toml("invalid toml [[[")
    try:
        with pytest.raises(ValueError, match="Invalid TOML"):
            load_loop_config(config_path)
    finally:
        config_path.unlink()


def test_load_loop_config_studio_override_beats_shipped_default():
    """.studio/implementation_loop.toml wins over config/implementation_loop.toml."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".studio").mkdir()
        (root / "config").mkdir()
        (root / "config" / "implementation_loop.toml").write_text(
            '[editor]\noutput_budget = 400\n'
        )
        (root / ".studio" / "implementation_loop.toml").write_text(
            '[editor]\noutput_budget = 123\n'
        )
        config = load_loop_config(studio_root=root)
        assert config.output_budget == 123


def test_load_loop_config_falls_back_to_shipped_default():
    """With no .studio override, the shipped config/ default is used."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "config").mkdir()
        (root / "config" / "implementation_loop.toml").write_text(
            '[editor]\nmandate = "off"\n'
        )
        config = load_loop_config(studio_root=root)
        assert config.mandate == "off"


def test_explicit_path_beats_resolution_chain():
    """An explicit path takes priority over the .studio/config chain."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".studio").mkdir()
        (root / ".studio" / "implementation_loop.toml").write_text(
            '[editor]\noutput_budget = 50\n'
        )
        explicit = _write_toml('[editor]\noutput_budget = 777\n')
        try:
            config = load_loop_config(explicit, studio_root=root)
            assert config.output_budget == 777
        finally:
            explicit.unlink()


def test_runtime_knobs_default_config():
    """runtime_knobs maps a default LoopConfig to the expected knob dict."""
    knobs = runtime_knobs(LoopConfig())
    assert knobs == {
        "editor_enabled": True,
        "test_command": "pytest -q",
        "static_checks": ["ruff"],
        "require_mutation_check": True,
        "read_scope": "touched+importers",
        "output_budget": 400,
    }


def test_runtime_knobs_off_mandate_disables_editor():
    """mandate = 'off' surfaces as editor_enabled False in the knobs."""
    knobs = runtime_knobs(LoopConfig(mandate="off"))
    assert knobs["editor_enabled"] is False


def test_runtime_knobs_reflects_loaded_override():
    """Values from a loaded .studio override flow through to the knobs."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".studio").mkdir()
        (root / ".studio" / "implementation_loop.toml").write_text(
            "[gate]\n"
            'test_command = "python -m pytest tests/ -q"\n'
            'static_checks = ["ruff", "mypy"]\n'
            "require_mutation_check = false\n"
            "[editor]\n"
            'mandate = "off"\n'
            'read_scope = "touched"\n'
            "output_budget = 250\n"
        )
        config = load_loop_config(studio_root=root)
        knobs = runtime_knobs(config)
        assert knobs == {
            "editor_enabled": False,
            "test_command": "python -m pytest tests/ -q",
            "static_checks": ["ruff", "mypy"],
            "require_mutation_check": False,
            "read_scope": "touched",
            "output_budget": 250,
        }


def test_load_default_loop_config():
    """The shipped default implementation_loop.toml loads correctly."""
    default_path = Path(__file__).resolve().parents[1] / "config" / "implementation_loop.toml"
    if not default_path.exists():
        pytest.skip("Default implementation_loop.toml not found")

    config = load_loop_config(default_path)
    assert config.deliver_on_gate_fail is True
    assert config.test_command == "pytest -q"
    assert config.static_checks == ["ruff"]
    assert config.require_mutation_check is True
    assert config.mandate == "contrarian"
    assert config.read_scope == "touched+importers"
    assert config.output_budget == 400
