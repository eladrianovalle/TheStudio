# Studio Default Behavior

## Scope-Based Iteration (Enabled by Default)

As of 2026-02-27, Studio **automatically uses scope-based iteration** for all runs if `.studio/scopes.toml` exists.

### Why Default?

The concentric-iteration strategy (agent-gauntlet learnings) provides:
- **20-30% token savings** by allocating fewer iterations to polish
- **Better focus** with clear boundaries between planning, implementation, and refinement
- **Faster convergence** by spending more time on high-level decisions

### How to Use

**Standard workflow** (scopes enabled automatically):
```bash
python run_phase.py prepare --phase tech --text "Build feature" --max-iterations 5
```

**Output**:
```
Loaded scopes config: $STUDIO_ROOT/.studio/scopes.toml
- Total iteration budget: 5
  - high_level: 2 iterations
  - implementation: 1 iterations
  - polish: 2 iterations
```

### Customization

**Override with custom config**:
```bash
python run_phase.py prepare --phase tech --text "Build feature" \
  --max-iterations 5 --scopes my-custom-scopes.toml
```

**Disable scopes** (use standard iteration):
```bash
python run_phase.py prepare --phase tech --text "Build feature" \
  --max-iterations 5 --no-scopes
```

### Default Config

The default `.studio/scopes.toml` allocates iterations as:
- **50% to high-level** (architecture, plans, strategic decisions)
- **33% to implementation** (detailed design, API contracts)
- **17% to polish** (documentation, final review)

This ratio is based on the principle that **high-level changes are cheap, low-level changes are expensive**.

### Modifying Defaults

Edit `.studio/scopes.toml` to change default behavior:

```toml
# More aggressive (spend more on planning)
[scopes.high_level]
max_iterations = 4

[scopes.implementation]
max_iterations = 1

[scopes.polish]
max_iterations = 1

# More balanced
[scopes.high_level]
max_iterations = 2

[scopes.implementation]
max_iterations = 2

[scopes.polish]
max_iterations = 2
```

### Disabling Globally

To disable scopes by default:
1. Rename `.studio/scopes.toml` to `.studio/scopes.toml.disabled`
2. Or delete the file
3. Or always use `--no-scopes` flag

### Per-Project Configs

Different projects can have different default scopes:

```bash
# Game project
.studio/scopes.toml  # High-level focused

# Web app project
.studio/scopes-webapp.toml  # Balanced

# Use specific config
python run_phase.py prepare --phase tech --text "..." \
  --scopes .studio/scopes-webapp.toml
```

## Other Default Behaviors

### Automatic Cleanup

Studio automatically runs cleanup on every `prepare` to enforce:
- **30-day TTL**: Deletes runs older than 30 days
- **900 MB size cap**: Deletes oldest runs if total exceeds limit

**Disable**: Use `--skip-cleanup` flag

### Rerun Detection

Studio automatically detects previous rejections and injects context.

**No configuration needed** - works automatically when contrarian files exist.

### Validation

Validation is **opt-in** - run manually after finalize:

```bash
python run_phase.py validate --phase tech --run-id run_tech_20260227_184406
```

## Summary

| Feature | Default Behavior | Override |
|---------|------------------|----------|
| Scopes | Enabled (if `.studio/scopes.toml` exists) | `--no-scopes` or `--scopes custom.toml` |
| Cleanup | Enabled | `--skip-cleanup` |
| Rerun | Automatic | N/A (always on) |
| Validation | Opt-in | Run `validate` command |

**Philosophy**: Sensible defaults that improve quality and reduce costs, with easy opt-out when needed.
