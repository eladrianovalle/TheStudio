#!/usr/bin/env python3
"""Tests for scope-based iteration allocation."""
import tempfile
from pathlib import Path

import pytest

from scopes import (
    CONTRARIAN_MANDATE,
    ScopeConfig,
    ScopesConfig,
    VALID_DEBATE_MODES,
    allocate_iterations,
    generate_scope_instructions,
    generate_scope_prompt,
    load_scopes_config,
)


def _scope_prompt(stance, scope_index=1, question_mode=False):
    scope = ScopeConfig(name="depth", focus="Full analysis", max_iterations=2)
    return generate_scope_prompt(
        scope=scope,
        scope_index=scope_index,
        role_title="Engineering",
        stance=stance,
        run_dir="output/studio/run_x",
        advocate_focus="Build it",
        contrarian_focus="Break it",
        deliverables=["A spec"],
        user_text="A cozy farming sim",
        decisions_md_exists=False,
        question_mode=question_mode,
    )


def test_scope_prompt_contrarian_has_editor_mandate():
    """Contrarian scope prompts carry the always-on editor mandate."""
    prompt = _scope_prompt("contrarian")
    assert "Contrarian Mandate" in prompt
    assert "Default to deletion" in prompt
    # Mandate constant is fully rendered.
    for line in CONTRARIAN_MANDATE:
        if line:
            assert line in prompt


def test_scope_prompt_advocate_has_no_editor_mandate():
    """The editor mandate must not leak into advocate prompts."""
    prompt = _scope_prompt("advocate")
    assert "Contrarian Mandate" not in prompt
    assert "Default to deletion" not in prompt


def test_scope_prompt_contrarian_omits_mandate_in_question_mode():
    """In question-surfacing runs the contrarian must not get the cut-bias mandate."""
    prompt = _scope_prompt("contrarian", question_mode=True)
    assert "Contrarian Mandate" not in prompt
    assert "Default to deletion" not in prompt
    # Still produces a contrarian scope prompt (verdict line remains).
    assert "VERDICT" in prompt


def test_scope_config_validation():
    """Test ScopeConfig validation."""
    # Valid config
    scope = ScopeConfig(name="high_level", focus="Architecture", max_iterations=3)
    assert scope.name == "high_level"
    assert scope.max_iterations == 3
    
    # Invalid: zero iterations
    with pytest.raises(ValueError, match="must have at least 1 iteration"):
        ScopeConfig(name="invalid", focus="Test", max_iterations=0)
    
    # Invalid: negative iterations
    with pytest.raises(ValueError, match="must have at least 1 iteration"):
        ScopeConfig(name="invalid", focus="Test", max_iterations=-1)


def test_scopes_config_total_iterations():
    """Test total iteration calculation."""
    config = ScopesConfig(scopes=[
        ScopeConfig("high_level", "Architecture", 3),
        ScopeConfig("implementation", "Code", 2),
        ScopeConfig("polish", "Docs", 1),
    ])
    assert config.total_iterations == 6


def test_scopes_config_get_scope():
    """Test scope lookup by name."""
    config = ScopesConfig(scopes=[
        ScopeConfig("high_level", "Architecture", 3),
        ScopeConfig("implementation", "Code", 2),
    ])
    
    scope = config.get_scope("high_level")
    assert scope is not None
    assert scope.name == "high_level"
    assert scope.max_iterations == 3
    
    missing = config.get_scope("nonexistent")
    assert missing is None


def test_scopes_config_get_scope_canonical_alias():
    """Test that canonical aliases (alignment/depth/polish) resolve by position."""
    config = ScopesConfig(scopes=[
        ScopeConfig("high_level", "Architecture", 3),
        ScopeConfig("implementation", "Code", 2),
        ScopeConfig("polish", "Polish", 1),
    ])

    # "alignment" should resolve to index 0 (high_level)
    scope = config.get_scope("alignment")
    assert scope is not None
    assert scope.name == "high_level"

    # "depth" should resolve to index 1 (implementation)
    scope = config.get_scope("depth")
    assert scope is not None
    assert scope.name == "implementation"

    # "polish" matches by name directly (exact match takes priority)
    scope = config.get_scope("polish")
    assert scope is not None
    assert scope.name == "polish"

    # Alias out of range returns None
    two_scope = ScopesConfig(scopes=[
        ScopeConfig("first", "First", 1),
        ScopeConfig("second", "Second", 1),
    ])
    assert two_scope.get_scope("polish") is None


def test_load_scopes_config_valid():
    """Test loading valid TOML config."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("""
[scopes.high_level]
focus = "Architecture, plans"
max_iterations = 3

[scopes.implementation]
focus = "Code"
max_iterations = 2
""")
        config_path = Path(f.name)
    
    try:
        config = load_scopes_config(config_path)
        assert len(config.scopes) == 2
        assert config.scopes[0].name == "high_level"
        assert config.scopes[0].focus == "Architecture, plans"
        assert config.scopes[0].max_iterations == 3
        assert config.scopes[1].name == "implementation"
        assert config.total_iterations == 5
    finally:
        config_path.unlink()


def test_load_scopes_config_missing_file():
    """Test error when config file doesn't exist."""
    with pytest.raises(FileNotFoundError, match="Scopes config not found"):
        load_scopes_config(Path("/nonexistent/path.toml"))


def test_load_scopes_config_invalid_toml():
    """Test error on invalid TOML syntax."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("invalid toml [[[")
        config_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError, match="Invalid TOML"):
            load_scopes_config(config_path)
    finally:
        config_path.unlink()


def test_load_scopes_config_missing_scopes_section():
    """Test error when 'scopes' section is missing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("[other]\nkey = 'value'\n")
        config_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError, match="must have 'scopes' section"):
            load_scopes_config(config_path)
    finally:
        config_path.unlink()


def test_load_scopes_config_missing_focus():
    """Test error when scope is missing 'focus' field."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("""
[scopes.high_level]
max_iterations = 3
""")
        config_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError, match="missing 'focus' field"):
            load_scopes_config(config_path)
    finally:
        config_path.unlink()


def test_load_scopes_config_missing_max_iterations():
    """Test error when scope is missing 'max_iterations' field."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("""
[scopes.high_level]
focus = "Architecture"
""")
        config_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError, match="missing 'max_iterations' field"):
            load_scopes_config(config_path)
    finally:
        config_path.unlink()


def test_load_scopes_config_invalid_max_iterations_type():
    """Test error when max_iterations is not an integer."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("""
[scopes.high_level]
focus = "Architecture"
max_iterations = "three"
""")
        config_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError, match="must be an integer"):
            load_scopes_config(config_path)
    finally:
        config_path.unlink()


def test_allocate_iterations_direct():
    """Test iteration allocation using config values directly."""
    config = ScopesConfig(scopes=[
        ScopeConfig("high_level", "Architecture", 3),
        ScopeConfig("implementation", "Code", 2),
        ScopeConfig("polish", "Docs", 1),
    ])
    
    allocations = allocate_iterations(config)
    assert allocations == {
        "high_level": 3,
        "implementation": 2,
        "polish": 1,
    }


def test_allocate_iterations_with_budget():
    """Test iteration allocation with total budget override."""
    config = ScopesConfig(scopes=[
        ScopeConfig("high_level", "Architecture", 3),
        ScopeConfig("implementation", "Code", 2),
    ])
    
    # Total in config is 5, but we want 10
    allocations = allocate_iterations(config, total_budget=10)
    
    # Should scale proportionally: 3/5 * 10 = 6, 2/5 * 10 = 4
    assert allocations["high_level"] == 6
    assert allocations["implementation"] == 4
    assert sum(allocations.values()) == 10


def test_allocate_iterations_ensures_minimum():
    """Test that each scope gets at least 1 iteration."""
    config = ScopesConfig(scopes=[
        ScopeConfig("high_level", "Architecture", 10),
        ScopeConfig("implementation", "Code", 1),
    ])
    
    # Even with small budget, each scope gets at least 1
    allocations = allocate_iterations(config, total_budget=2)
    assert allocations["high_level"] >= 1
    assert allocations["implementation"] >= 1


def test_generate_scope_instructions():
    """Test scope instructions generation."""
    config = ScopesConfig(scopes=[
        ScopeConfig("high_level", "Architecture, plans", 3),
        ScopeConfig("implementation", "Code", 2),
    ])
    allocations = {"high_level": 3, "implementation": 2}
    
    instructions = generate_scope_instructions(config, allocations)
    
    assert "Scope-Based Iteration Plan" in instructions
    assert "High Level" in instructions
    assert "Architecture, plans" in instructions
    assert "Max iterations**: 3" in instructions
    assert "Implementation" in instructions
    assert "Code" in instructions
    assert "Max iterations**: 2" in instructions
    assert "Total iteration budget**: 5" in instructions


def test_integration_load_and_allocate():
    """Integration test: load config and allocate iterations."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("""
[scopes.high_level]
focus = "Architecture"
max_iterations = 4

[scopes.implementation]
focus = "Code"
max_iterations = 3

[scopes.polish]
focus = "Docs"
max_iterations = 1
""")
        config_path = Path(f.name)
    
    try:
        config = load_scopes_config(config_path)
        allocations = allocate_iterations(config, total_budget=10)
        
        # Should scale from 8 total to 10 total
        # high_level: 4/8 * 10 = 5
        # implementation: 3/8 * 10 = 3.75 ≈ 3
        # polish: gets remaining = 2
        assert sum(allocations.values()) == 10
        assert allocations["high_level"] == 5
        assert allocations["polish"] == 2  # Gets remaining to avoid rounding errors
    finally:
        config_path.unlink()


# ---------------------------------------------------------------------------
# New: output_budget, debate_mode, scoped filenames
# ---------------------------------------------------------------------------


def test_scope_config_output_budget():
    """ScopeConfig accepts optional output_budget."""
    scope = ScopeConfig("alignment", "Direction", 2, output_budget=500)
    assert scope.output_budget == 500

    scope_no_budget = ScopeConfig("depth", "Detail", 3)
    assert scope_no_budget.output_budget is None


def test_scope_config_debate_mode_default():
    """ScopeConfig defaults to per_role debate_mode."""
    scope = ScopeConfig("depth", "Detail", 3)
    assert scope.debate_mode == "per_role"


def test_scope_config_debate_mode_all_roles():
    """ScopeConfig accepts all_roles debate_mode."""
    scope = ScopeConfig("alignment", "Direction", 2, debate_mode="all_roles")
    assert scope.debate_mode == "all_roles"


def test_scope_config_invalid_debate_mode():
    """ScopeConfig rejects invalid debate_mode."""
    with pytest.raises(ValueError, match="debate_mode"):
        ScopeConfig("bad", "Bad", 1, debate_mode="invalid")


def test_load_scopes_config_with_budget_and_mode():
    """Loading TOML with output_budget and debate_mode fields."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("""
[scopes.alignment]
focus = "Direction"
max_iterations = 2
output_budget = 500
debate_mode = "all_roles"

[scopes.depth]
focus = "Detail"
max_iterations = 3
debate_mode = "per_role"

[scopes.polish]
focus = "Cross-check"
max_iterations = 1
output_budget = 300
debate_mode = "all_roles"
""")
        config_path = Path(f.name)

    try:
        config = load_scopes_config(config_path)
        assert len(config.scopes) == 3

        alignment = config.get_scope("alignment")
        assert alignment is not None
        assert alignment.output_budget == 500
        assert alignment.debate_mode == "all_roles"

        depth = config.get_scope("depth")
        assert depth is not None
        assert depth.output_budget is None
        assert depth.debate_mode == "per_role"

        polish = config.get_scope("polish")
        assert polish is not None
        assert polish.output_budget == 300
        assert polish.debate_mode == "all_roles"
    finally:
        config_path.unlink()


def test_generate_scope_instructions_with_budget_and_mode():
    """Instructions include output budget and debate mode when set."""
    config = ScopesConfig(scopes=[
        ScopeConfig("alignment", "Direction", 2, output_budget=500, debate_mode="all_roles"),
        ScopeConfig("depth", "Detail", 3, debate_mode="per_role"),
    ])
    allocations = {"alignment": 2, "depth": 3}

    instructions = generate_scope_instructions(config, allocations)

    assert "~500 words" in instructions
    assert "All roles debate simultaneously" in instructions
    assert "Each role debates sequentially" in instructions
    # Depth scope should NOT have an output budget line
    lines = instructions.split("\n")
    depth_idx = next(i for i, l in enumerate(lines) if "Depth" in l)
    # Check next few lines after Depth header don't mention output budget
    depth_section = "\n".join(lines[depth_idx:depth_idx + 5])
    assert "Output budget" not in depth_section


def test_load_default_scopes_config():
    """The shipped default scopes.toml loads correctly."""
    default_path = Path(__file__).resolve().parents[1] / "config" / "scopes.toml"
    if not default_path.exists():
        pytest.skip("Default scopes.toml not found")

    config = load_scopes_config(default_path)
    assert len(config.scopes) == 3

    names = [s.name for s in config.scopes]
    assert "alignment" in names
    assert "depth" in names
    assert "polish" in names

    alignment = config.get_scope("alignment")
    assert alignment.output_budget == 500
    assert alignment.debate_mode == "all_roles"

    depth = config.get_scope("depth")
    assert depth.output_budget is None
    assert depth.debate_mode == "per_role"
