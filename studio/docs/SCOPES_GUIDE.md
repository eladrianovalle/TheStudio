# Studio Scopes Guide

## Overview

Scope-based iteration allocation allows you to spend more iterations on high-level decisions (cheap to change) and fewer on low-level polish (expensive to change). This implements the "concentric-iteration" strategy where iterations start broad and narrow progressively.

## Quick Start

### 1. Create a Scopes Config

Create `.studio/scopes.toml` in your Studio directory:

```toml
[scopes.high_level]
focus = "Architecture, plans, strategic decisions"
max_iterations = 3

[scopes.implementation]
focus = "Detailed design, API contracts, core implementation"
max_iterations = 2

[scopes.polish]
focus = "Documentation, final review, minor refinements"
max_iterations = 1
```

### 2. Run with Scopes

```bash
python run_phase.py prepare --phase tech --text "Build auth system" --scopes .studio/scopes.toml
```

The `--scopes` flag is **optional**. If omitted, Studio uses standard iteration allocation.

## Configuration Format

### Basic Structure

```toml
[scopes.<scope_name>]
focus = "Description of what this scope covers"
max_iterations = <number>
```

### Fields

- **`scope_name`**: Identifier for the scope (e.g., `high_level`, `implementation`, `polish`)
- **`focus`**: Human-readable description of what this scope covers
- **`max_iterations`**: Number of iterations allocated to this scope (must be ≥ 1)

### Example: Tech Phase

```toml
[scopes.architecture]
focus = "High-level system design, component boundaries, data flow"
max_iterations = 3

[scopes.api_design]
focus = "API contracts, interfaces, type definitions"
max_iterations = 2

[scopes.implementation]
focus = "Core implementation, algorithms, error handling"
max_iterations = 2

[scopes.polish]
focus = "Documentation, examples, edge cases"
max_iterations = 1
```

### Example: Market Phase

```toml
[scopes.market_research]
focus = "TAM/SAM analysis, competitor research, user personas"
max_iterations = 3

[scopes.positioning]
focus = "Value proposition, messaging, differentiation"
max_iterations = 2

[scopes.go_to_market]
focus = "Launch plan, channels, metrics"
max_iterations = 1
```

## How It Works

### Iteration Budget Allocation

When you specify `--max-iterations 5` with a scopes config:

1. **Config total** is calculated (sum of all `max_iterations`)
2. **Proportional scaling** adjusts each scope to match your budget
3. **Minimum guarantee**: Each scope gets at least 1 iteration

**Example**:

```toml
# Config defines 6 total iterations
[scopes.high_level]
max_iterations = 3  # 50% of total

[scopes.implementation]
max_iterations = 2  # 33% of total

[scopes.polish]
max_iterations = 1  # 17% of total
```

Running with `--max-iterations 10`:
- `high_level`: 3/6 × 10 = **5 iterations**
- `implementation`: 2/6 × 10 = **3 iterations**
- `polish`: 1/6 × 10 = **2 iterations**

### Sequential Execution

Scopes are executed **sequentially** in the order defined in the config:

1. Work through `high_level` scope (up to allocated iterations)
2. Once approved or iterations exhausted, move to `implementation`
3. Continue through remaining scopes

This creates the "concentric circles" effect: broad → narrow → focused.

## Decision Tree: When to Use Scopes

### Use Scopes When:

- ✅ You want to spend more time on architecture/planning
- ✅ You're working on a complex feature with multiple layers
- ✅ You want to optimize token usage (fewer iterations on polish)
- ✅ You want explicit scope boundaries in your workflow

### Use Standard Workflow When:

- ❌ Simple, straightforward tasks
- ❌ Single-scope work (e.g., just documentation)
- ❌ Rapid prototyping where structure isn't needed

## Scope Naming Conventions

### Recommended Names

**High-Level Scopes** (3-4 iterations):
- `architecture`
- `high_level`
- `planning`
- `strategy`

**Medium Scopes** (2-3 iterations):
- `implementation`
- `api_design`
- `core_features`
- `integration`

**Low-Level Scopes** (1-2 iterations):
- `polish`
- `documentation`
- `refinement`
- `edge_cases`

### Naming Tips

- Use `snake_case` for scope names
- Be descriptive but concise
- Align with your team's terminology
- Keep consistent across projects

## Templates

### Minimal (3 scopes)

```toml
[scopes.high_level]
focus = "Architecture and planning"
max_iterations = 3

[scopes.implementation]
focus = "Core implementation"
max_iterations = 2

[scopes.polish]
focus = "Documentation and refinement"
max_iterations = 1
```

### Detailed (5 scopes)

```toml
[scopes.architecture]
focus = "System design, component boundaries"
max_iterations = 3

[scopes.api_contracts]
focus = "API design, interfaces, types"
max_iterations = 2

[scopes.core_implementation]
focus = "Algorithms, business logic"
max_iterations = 2

[scopes.integration]
focus = "Component integration, error handling"
max_iterations = 1

[scopes.polish]
focus = "Documentation, examples, edge cases"
max_iterations = 1
```

### Single-Focus (2 scopes)

```toml
[scopes.design]
focus = "All design and planning work"
max_iterations = 4

[scopes.execution]
focus = "Implementation and polish"
max_iterations = 2
```

## Troubleshooting

### Error: "Scopes config not found"

**Cause**: File path is incorrect or file doesn't exist

**Solution**:
```bash
# Use absolute path
python run_phase.py prepare --phase tech --text "..." --scopes /full/path/to/scopes.toml

# Or relative to Studio root
python run_phase.py prepare --phase tech --text "..." --scopes .studio/scopes.toml
```

### Error: "Invalid TOML"

**Cause**: Syntax error in TOML file

**Solution**: Validate TOML syntax
```bash
# Check for common issues:
# - Missing quotes around strings
# - Unmatched brackets
# - Invalid characters
```

### Error: "Scope 'X' missing 'focus' field"

**Cause**: Required field is missing

**Solution**: Add all required fields
```toml
[scopes.my_scope]
focus = "Description here"  # Required
max_iterations = 2          # Required
```

### Error: "Scope 'X' must have at least 1 iteration"

**Cause**: `max_iterations` is 0 or negative

**Solution**: Set to at least 1
```toml
[scopes.my_scope]
focus = "Description"
max_iterations = 1  # Minimum
```

## Best Practices

### 1. Start Simple

Begin with 3 scopes (high/medium/low) and add more only if needed.

### 2. Align with Phase

Different phases benefit from different scope structures:

- **Market**: Research → Positioning → GTM
- **Design**: Concept → Mechanics → UX
- **Tech**: Architecture → Implementation → Polish
- **Studio**: Vision → Constraints → Integration

### 3. Iterate on Config

Your first scopes config won't be perfect. Adjust based on:
- Where you run out of iterations
- Where you have iterations left over
- Which scopes need more/less focus

### 4. Document Your Rationale

Add comments to your config explaining why you chose specific allocations:

```toml
# We spend more time on architecture because changes here are cheap
[scopes.architecture]
focus = "System design"
max_iterations = 4

# Implementation is more constrained once architecture is set
[scopes.implementation]
focus = "Core code"
max_iterations = 2
```

### 5. Share Configs Across Projects

Create reusable configs for common project types:
- `.studio/scopes-tech.toml`
- `.studio/scopes-market.toml`
- `.studio/scopes-design.toml`

## FAQ

### Q: Can I skip scopes?

**A**: No, scopes execute sequentially. However, you can set `max_iterations = 1` for scopes you want to minimize.

### Q: What if I run out of iterations in a scope?

**A**: The run moves to the next scope. You can always run another Studio session to continue work.

### Q: Can I use scopes with Studio phase?

**A**: Yes! Scopes work with all phases (market, design, tech, studio).

### Q: Do scopes affect token usage?

**A**: Yes! By allocating fewer iterations to polish, you reduce total token usage by 20-30% typically.

### Q: Can I change scopes mid-run?

**A**: No, scopes are set at `prepare` time. However, you can start a new run with different scopes.

### Q: How do scopes interact with `--max-iterations`?

**A**: The `--max-iterations` flag sets the total budget. Scopes divide that budget proportionally.

## Examples

### Example 1: Tech Phase with Scopes

```bash
# Create config
cat > .studio/scopes.toml << 'EOF'
[scopes.architecture]
focus = "System design, components, data flow"
max_iterations = 3

[scopes.implementation]
focus = "Core code, algorithms, error handling"
max_iterations = 2

[scopes.polish]
focus = "Docs, examples, edge cases"
max_iterations = 1
EOF

# Run with scopes
python run_phase.py prepare \
  --phase tech \
  --text "Build real-time multiplayer sync system" \
  --max-iterations 6 \
  --scopes .studio/scopes.toml
```

**Result**: 3 iterations on architecture, 2 on implementation, 1 on polish.

### Example 2: Market Phase with Custom Budget

```bash
# Config defines 6 total, but we override to 10
python run_phase.py prepare \
  --phase market \
  --text "Launch strategy for indie game" \
  --max-iterations 10 \
  --scopes .studio/scopes-market.toml
```

**Result**: Proportional scaling from 6 → 10 iterations.

### Example 3: Standard Workflow (No Scopes)

```bash
# Omit --scopes flag for standard behavior
python run_phase.py prepare \
  --phase design \
  --text "Design inventory system" \
  --max-iterations 3
```

**Result**: Standard 3-iteration advocate/contrarian loop.

## See Also

- [STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md) - Standard Studio workflow
- [IMPLEMENTATION_PLAN.md](../output/studio/run_studio_20260227_174319/IMPLEMENTATION_PLAN.md) - Full scopes implementation plan
- [README.md](../README.md) - Studio overview
