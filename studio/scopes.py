#!/usr/bin/env python3
"""
Scope-based iteration allocation for Studio runs.

Enables users to allocate iteration budgets by scope level (alignment/depth/polish),
spending more iterations on alignment (cheap to change) and fewer
on polish (expensive to change).
"""
from __future__ import annotations

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redefine]  # Python 3.10 fallback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


VALID_DEBATE_MODES = {"all_roles", "per_role"}


@dataclass
class ScopeConfig:
    """Configuration for a single scope level."""
    name: str
    focus: str
    max_iterations: int
    output_budget: int | None = None    # word cap per stance doc (None = unlimited)
    debate_mode: str = "per_role"       # "all_roles" or "per_role"

    def __post_init__(self):
        if self.max_iterations < 1:
            raise ValueError(f"Scope '{self.name}' must have at least 1 iteration")
        if self.debate_mode not in VALID_DEBATE_MODES:
            raise ValueError(
                f"Scope '{self.name}' debate_mode must be one of {VALID_DEBATE_MODES}, got '{self.debate_mode}'"
            )


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
    [scopes.alignment]
    focus = "Directional alignment — should we go this way at all?"
    max_iterations = 2

    [scopes.depth]
    focus = "Detailed analysis per discipline"
    max_iterations = 3

    [scopes.polish]
    focus = "Cross-discipline gut-check"
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
        
        output_budget = scope_config.get("output_budget")
        if output_budget is not None and not isinstance(output_budget, int):
            raise ValueError(f"Scope '{scope_name}' output_budget must be an integer")

        debate_mode = scope_config.get("debate_mode", "per_role")

        scopes.append(ScopeConfig(
            name=scope_name,
            focus=focus,
            max_iterations=max_iterations,
            output_budget=output_budget,
            debate_mode=debate_mode,
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


def generate_scope_prompt(
    scope: ScopeConfig,
    scope_index: int,
    role_title: str,
    stance: str,
    run_dir: str,
    advocate_focus: str,
    contrarian_focus: str,
    deliverables: List[str],
    user_text: str,
    decisions_md_exists: bool,
    s1_files: List[str] | None = None,
    s2_brief_exists: bool = False,
    rejection_context: str | None = None,
) -> str:
    """Generate scope-specific agent instructions for a single agent prompt.

    Returns a complete prompt fragment telling the agent what scope it's in,
    what prior-scope files to read, the decision point protocol, and
    scope-specific focus guidance.

    Args:
        scope: The scope config for the current tier.
        scope_index: 0-based index (0=alignment, 1=depth, 2=polish).
        role_title: Human-readable role name (e.g., "Marketing").
        stance: "advocate" or "contrarian".
        run_dir: Path string for the run directory.
        advocate_focus: Advocate focus description from manifest.
        contrarian_focus: Contrarian focus description from manifest.
        deliverables: List of deliverable strings from manifest.
        user_text: The user's original input/objective text.
        decisions_md_exists: Whether decisions.md exists in run_dir.
        s1_files: For S2/S3: list of S1 file paths this agent should read.
        s2_brief_exists: Whether S2-brief.md exists in run_dir.
        rejection_context: Rejection reasons from prior iteration, if any.

    Returns:
        Markdown prompt fragment for inclusion in agent instructions.
    """
    scope_labels = {0: "ALIGNMENT", 1: "DEPTH", 2: "POLISH"}
    scope_label = scope_labels.get(scope_index, scope.name.upper())
    focus = advocate_focus if stance == "advocate" else contrarian_focus

    lines: List[str] = [
        f"## Scope: {scope_label}",
        "",
        f"**Focus for this scope:** {scope.focus}",
        f"**Your role:** {role_title} ({stance.title()})",
        f"**Your discipline focus:** {focus}",
        f"**Input/objective:** {user_text}",
        "",
    ]

    # Word cap
    if scope.output_budget:
        lines.append(f"**Word cap:** Keep your response under {scope.output_budget} words.")
        lines.append("")

    # Scope-specific guidance
    if scope_index == 0:  # Alignment
        lines.extend([
            "**Scope guidance:** This is a directional alignment pass. Focus on:",
            "- Your high-level stance on the approach",
            "- Any fatal flaws from your discipline",
            "- Key trade-offs to flag for the room",
            "",
            "Do NOT produce full deliverables — save detail for the Depth scope.",
            "",
        ])
    elif scope_index == 1:  # Depth
        lines.extend([
            "**Scope guidance:** This is the full-depth analysis pass. Produce:",
        ])
        if stance == "advocate" and deliverables:
            for d in deliverables:
                lines.append(f"- {d}")
        else:
            lines.append("- Thorough critique of the advocate's depth proposal")
        lines.append("")
    elif scope_index >= 2:  # Polish
        lines.extend([
            "**Scope guidance:** This is the cross-discipline polish pass. Focus ONLY on:",
            "- Unresolved cross-discipline conflicts",
            "- Conditions that overlap or conflict between roles",
            "- Gaps between disciplines that no one owns",
            "",
            "Do NOT introduce new proposals or repeat depth analysis.",
            "",
        ])

    # Prior-scope context
    if s1_files and scope_index >= 1:
        lines.append("**Prior-scope context (Alignment):** Read these S1 files:")
        for f in s1_files:
            lines.append(f"- `{f}`")
        lines.append("")

    if s2_brief_exists and scope_index >= 1:
        lines.append(f"**S2 brief:** Read `{run_dir}/S2-brief.md` for condensed cross-role context.")
        lines.append("")

    # Rejection context
    if rejection_context:
        lines.extend([
            "**Prior rejection context:** The previous iteration was REJECTED. Address these concerns:",
            rejection_context,
            "",
        ])

    # Settled decisions
    if decisions_md_exists:
        lines.extend([
            f"**Settled decisions:** Read `{run_dir}/decisions.md` — treat as hard constraints. Do not re-litigate.",
            "",
        ])

    # Decision point protocol
    lines.extend([
        "**Decision Point Protocol:** When you encounter a gap, ambiguity, or fork that could meaningfully change your approach, flag it inline:",
        "",
        "```",
        "> **DECISION [P0]:** [question]",
        "> **Unblocks:** [what this decision affects]",
        "> **Options:** (a) ... (b) ...",
        "```",
        "",
        "- **P0 (Blocking):** Cannot proceed without an answer.",
        "- **P1 (Important):** State your assumption and continue, but flag it.",
        "- **P2 (Context):** Nice-to-know, logged for completeness.",
        "",
    ])

    if stance == "advocate":
        lines.append("You MUST surface at least 1 decision point (P0 or P1) per output. If nothing is genuinely unsettled, state that explicitly rather than omitting the section.")
    else:
        lines.append("If the advocate assumed something that is actually unsettled, you MUST flag it as a decision point. Decision points are required output when assumptions are unsettled.")

    lines.append("")

    if stance == "contrarian":
        lines.append("End with `VERDICT: APPROVED` or `VERDICT: REJECTED` with numbered reasons.")
        lines.append("")

    return "\n".join(lines)


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
        mode_label = "All roles debate simultaneously" if scope.debate_mode == "all_roles" else "Each role debates sequentially"
        lines.extend([
            f"### {scope.name.replace('_', ' ').title()}",
            f"- **Focus**: {scope.focus}",
            f"- **Debate mode**: {mode_label}",
            f"- **Max iterations**: {allocated}",
        ])
        if scope.output_budget:
            lines.append(f"- **Output budget**: ~{scope.output_budget} words per stance document")
        lines.append("")
    
    total = sum(allocations.values())
    lines.extend([
        f"**Total iteration budget**: {total}",
        "",
        "Work through scopes sequentially. Once a scope's iterations are exhausted or approved, move to the next scope.",
        "",
    ])
    
    return "\n".join(lines)
