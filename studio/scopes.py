#!/usr/bin/env python3
"""
Scope-based iteration allocation for Studio runs.

Enables users to allocate iteration budgets by scope level (high/medium/low),
spending more iterations on high-level decisions (cheap to change) and fewer
on low-level polish (expensive to change).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class ScopeConfig:
    """Configuration for a single scope level."""
    name: str
    focus: str
    max_iterations: int
    
    def __post_init__(self):
        if self.max_iterations < 1:
            raise ValueError(f"Scope '{self.name}' must have at least 1 iteration")


@dataclass
class ScopesConfig:
    """Complete scopes configuration for a Studio run."""
    scopes: List[ScopeConfig]
    
    @property
    def total_iterations(self) -> int:
        """Total iteration budget across all scopes."""
        return sum(scope.max_iterations for scope in self.scopes)
    
    def get_scope(self, name: str) -> ScopeConfig | None:
        """Get scope by name."""
        for scope in self.scopes:
            if scope.name == name:
                return scope
        return None


def load_scopes_config(config_path: Path) -> ScopesConfig:
    """
    Load scopes configuration from TOML file.
    
    Expected format:
    ```toml
    [scopes.high_level]
    focus = "Architecture, plans, strategic decisions"
    max_iterations = 3
    
    [scopes.implementation]
    focus = "Detailed design, API contracts"
    max_iterations = 2
    
    [scopes.polish]
    focus = "Documentation, final review"
    max_iterations = 1
    ```
    
    Args:
        config_path: Path to .toml configuration file
        
    Returns:
        ScopesConfig with parsed scope definitions
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config format is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Scopes config not found: {config_path}")
    
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in {config_path}: {e}") from e
    
    if "scopes" not in data:
        raise ValueError(f"Config must have 'scopes' section: {config_path}")
    
    scopes_data = data["scopes"]
    if not isinstance(scopes_data, dict):
        raise ValueError(f"'scopes' must be a table/dict: {config_path}")
    
    scopes: List[ScopeConfig] = []
    for scope_name, scope_config in scopes_data.items():
        if not isinstance(scope_config, dict):
            raise ValueError(f"Scope '{scope_name}' must be a table/dict")
        
        focus = scope_config.get("focus", "")
        if not focus:
            raise ValueError(f"Scope '{scope_name}' missing 'focus' field")
        
        max_iterations = scope_config.get("max_iterations")
        if max_iterations is None:
            raise ValueError(f"Scope '{scope_name}' missing 'max_iterations' field")
        if not isinstance(max_iterations, int):
            raise ValueError(f"Scope '{scope_name}' max_iterations must be an integer")
        
        scopes.append(ScopeConfig(
            name=scope_name,
            focus=focus,
            max_iterations=max_iterations
        ))
    
    if not scopes:
        raise ValueError(f"No scopes defined in {config_path}")
    
    return ScopesConfig(scopes=scopes)


def allocate_iterations(scopes_config: ScopesConfig, total_budget: int | None = None) -> Dict[str, int]:
    """
    Allocate iteration budget across scopes.
    
    If total_budget is provided and differs from config total, scales proportionally.
    Otherwise uses max_iterations from each scope directly.
    
    Args:
        scopes_config: Loaded scopes configuration
        total_budget: Optional total iteration budget (overrides config totals)
        
    Returns:
        Dict mapping scope name to allocated iterations
        
    Example:
        >>> config = ScopesConfig(scopes=[
        ...     ScopeConfig("high_level", "Architecture", 3),
        ...     ScopeConfig("implementation", "Code", 2),
        ... ])
        >>> allocate_iterations(config)
        {'high_level': 3, 'implementation': 2}
        >>> allocate_iterations(config, total_budget=10)
        {'high_level': 6, 'implementation': 4}
    """
    config_total = scopes_config.total_iterations
    
    if total_budget is None or total_budget == config_total:
        # Use config values directly
        return {scope.name: scope.max_iterations for scope in scopes_config.scopes}
    
    # Scale proportionally to match total_budget
    allocations: Dict[str, int] = {}
    remaining_budget = total_budget
    
    for i, scope in enumerate(scopes_config.scopes):
        if i == len(scopes_config.scopes) - 1:
            # Last scope gets remaining budget to avoid rounding errors
            allocations[scope.name] = remaining_budget
        else:
            # Proportional allocation
            proportion = scope.max_iterations / config_total
            allocated = max(1, int(total_budget * proportion))
            allocations[scope.name] = allocated
            remaining_budget -= allocated
    
    return allocations


def generate_scope_instructions(scopes_config: ScopesConfig, allocations: Dict[str, int]) -> str:
    """
    Generate human-readable scope instructions for inclusion in run instructions.
    
    Args:
        scopes_config: Loaded scopes configuration
        allocations: Iteration allocations per scope
        
    Returns:
        Formatted markdown string describing scopes and iteration budgets
    """
    lines = [
        "## Scope-Based Iteration Plan",
        "",
        "This run uses scope-based iteration allocation:",
        "",
    ]
    
    for scope in scopes_config.scopes:
        allocated = allocations.get(scope.name, 0)
        lines.extend([
            f"### {scope.name.replace('_', ' ').title()}",
            f"- **Focus**: {scope.focus}",
            f"- **Max iterations**: {allocated}",
            "",
        ])
    
    total = sum(allocations.values())
    lines.extend([
        f"**Total iteration budget**: {total}",
        "",
        "Work through scopes sequentially. Once a scope's iterations are exhausted or approved, move to the next scope.",
        "",
    ])
    
    return "\n".join(lines)
