#!/usr/bin/env python3
"""Tests for scope-based iteration allocation."""
import tempfile
from pathlib import Path

import pytest

from scopes import (
    ScopeConfig,
    ScopesConfig,
    allocate_iterations,
    generate_scope_instructions,
    load_scopes_config,
)


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
