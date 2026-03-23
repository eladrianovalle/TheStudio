# Studio Scopes Guide

## Overview

Studio multi-role runs use a **three-tier scoped debate** by default: alignment, depth, polish. Each tier has a different goal, word budget, and debate mode. This reduces token waste by catching bad directions cheaply in alignment before committing to expensive depth analysis.

## Default Configuration

The shipped config lives at `config/scopes.toml`:

```toml
[scopes.alignment]
focus = "Directional alignment — approach, fatal flaws, high-level trade-offs only."
max_iterations = 2
output_budget = 500        # ~500 words per agent
debate_mode = "all_roles"  # All roles run in parallel

[scopes.depth]
focus = "Full analysis — detailed deliverables, edge cases, concrete recommendations."
max_iterations = 3
debate_mode = "per_role"   # Roles run sequentially

[scopes.polish]
focus = "Cross-discipline conflicts — flag remaining issues, no new proposals."
max_iterations = 1
output_budget = 300
debate_mode = "all_roles"
```

## How It Works

```
┌─ ALIGNMENT ─────────────────────────────────┐
│ All roles in parallel. ~500 words each.     │
│ "Should we go this way at all?"             │
│ Catches fatal flaws cheaply.                │
├─ DEPTH ─────────────────────────────────────┤
│ Each role sequentially. Full deliverables.  │
│ "How exactly should we do this?"            │
│ Starts focused thanks to alignment context. │
├─ POLISH ────────────────────────────────────┤
│ All roles in parallel. ~300 words each.     │
│ "Anything still broken across disciplines?" │
│ Final cross-check before integrator.        │
├─ INTEGRATOR ────────────────────────────────┤
│ Synthesize all roles into unified roadmap.  │
│ Own advocate/contrarian duel.               │
└─────────────────────────────────────────────┘
```

### Scope Fields

| Field | Required | Description |
|-------|----------|-------------|
| `focus` | Yes | Guidance included in agent prompts for this scope |
| `max_iterations` | Yes | Advocate/contrarian rounds before moving on (min 1) |
| `output_budget` | No | Word cap per agent output (omit for no cap) |
| `debate_mode` | No | `"all_roles"` (parallel) or `"per_role"` (sequential). Default: `"all_roles"` |

### File Naming

Scope is encoded in filenames: `advocate--marketing--S1-01.md` (alignment), `advocate--engineering--S2-02.md` (depth iteration 2), `advocate--qa--S3-01.md` (polish).

## Usage

Scopes are **enabled by default** for studio phase runs. No flags needed:

```
/run-studio-phase --text "Evaluate multiplayer architecture" --roles +engineering +qa
```

### Disable scopes (flat mode)

```
/run-studio-phase --text "..." --no-scopes
```

Flat mode runs all roles at full depth with no tiers — the original behavior.

### Custom scopes config

```bash
python studio/run_phase.py prepare --phase studio --text "..." --scopes /path/to/custom-scopes.toml
```

### Per-project override

Place a `.studio/scopes.toml` in your project root. Studio auto-loads it when present.

## Customization

You can adjust the default config or create project-specific ones. The key levers:

- **More alignment iterations** if your team frequently debates direction
- **Higher output_budget** for depth if agents produce thin analysis
- **Lower output_budget** for alignment if agents waste words on detail too early
- **`per_role` debate_mode** for any scope where sequential role-by-role analysis matters

## Interaction with Decision Points and Metrics

- **Decision points** are extracted and surfaced after every agent in every scope
- **Agent metrics** (token usage) are recorded per-agent, so you can see which scope consumes the most tokens via `show-metrics`
- **Clarity scores** inform agent question density across scopes — settled topics get fewer questions

## See Also

- [CLAUDE_CODE_USAGE.md](./CLAUDE_CODE_USAGE.md) — slash commands and agent workflow
- [ARCHITECTURE.md](./ARCHITECTURE.md) — system design
- [README.md](../../README.md) — project overview
