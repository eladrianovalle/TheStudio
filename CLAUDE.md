# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

TheGameStudio is an **instruction generator** for structured advocate/contrarian debates in game development workflows. It produces run directories with instructions that an AI assistant (Claude Code, Windsurf/Cascade) executes, then packages results as versioned artifacts. There is no AI runtime — all intelligence lives in the assistant's execution.

## Running a Studio Phase (Claude Code)

Use the slash command to run a full advocate/contrarian debate:

```
/run-phase --phase market --text "A cozy farming sim with social deduction mechanics"
/run-phase --phase tech --text "Build multiplayer lobby system" --max-iterations 5
/run-studio-phase --text "Add AI critique engine" --roles +marketing +engineering
```

Single-phase runs (`/run-phase`) spawn separate Advocate and Contrarian agents per iteration. Multi-role runs (`/run-studio-phase`) process each discipline sequentially, then run an Integrator duel. See `studio/docs/CLAUDE_CODE_USAGE.md` for details.

## CLI Commands

```bash
# Run tests (from studio/ directory)
cd studio && python -m pytest tests/ -v

# Run a single test
cd studio && python -m pytest tests/test_run_phase.py::TestClassName::test_name -v

# Prepare a phase run (manual)
python studio/run_phase.py prepare --phase <market|design|tech|studio> --text "description"

# Prepare with role pack (studio phase only)
python studio/run_phase.py prepare --phase studio --text "..." --role-pack studio_core --roles +product +engineering +qa

# Finalize a completed run
python studio/run_phase.py finalize --phase <phase> --run-id <run_id> --status completed --verdict APPROVED

# Validate a run
python studio/run_phase.py validate --phase <phase> --run-id <run_id>

# Storage cleanup
python studio/run_phase.py cleanup --dry-run
python studio/run_phase.py cleanup
```

## Architecture

All source lives under `studio/`. `run_phase.py` is the sole entrypoint using only stdlib (plus `tomli` on Python 3.10).

### Core modules (all in `studio/`)

- **`run_phase.py`** — Primary entrypoint: `prepare`, `finalize`, `validate`, `cleanup` subcommands.
- **`run_phase_roles.py`** — Role system: loads `studio.manifest.json`, resolves role packs, builds per-role file naming (`advocate--<role>--NN.md`).
- **`cleanup.py`** — TTL-based (30 days) and budget-based (900MB) run artifact cleanup.
- **`scopes.py`** — Scope-based iteration allocation (high_level / implementation / polish).
- **`rerun.py`** — Detects rejection context from prior runs and generates rerun instructions.
- **`verdict.py`** — Extracts APPROVED/REJECTED/UNKNOWN verdict from text.
- **`validators/`** — `DocumentValidator` and `CodeValidator` for post-run quality checks.

### Configuration files

- **`studio.manifest.json`** — Defines all disciplines (marketing, product, design, art, engineering, qa, ml, pmm) with advocate/contrarian focuses, deliverables, and escalation cues.
- **`role_packs/*.json`** — Curated pod presets (e.g., `studio_core` = marketing + product + design + art + engineering + qa). Override with `--roles +role/-role`.
- **`config/studio_settings.toml`** — Cleanup TTL and storage limits.
- **`.studio/scopes.toml`** — Scope-based iteration budgets (auto-loaded if present).
- **`.studio/validation.toml`** — Validation configuration.

### Artifact structure

Runs produce timestamped directories under `output/<phase>/run_<phase>_<timestamp>/` containing:
- `instructions.md`, `run.json`, `summary.md`
- `advocate_N.md` / `contrarian_N.md` (simple phases)
- `advocate--<role>--NN.md` / `contrarian--<role>--NN.md` + `integrator.md` (studio phase)

### Phases

Four phases: `market`, `design`, `tech`, `studio`. Each has distinct advocate/contrarian personas. The `studio` phase supports multi-role pods via role packs.

## Important Conventions

- **Python 3.10+** required. Uses `tomllib` (3.11+) with `tomli` fallback.
- **No heavy dependencies** — keep `run_phase.py` small and bash-friendly.
- **Test-driven discipline** is mandatory for tech phase implementations.
- **Documentation contract**: changes to workflow must update README, STUDIO_INTERACTION_GUIDE.md, and affected bridge docs simultaneously.
- **Working directories**: `.scratch/` for temp files, `.private/` for sensitive data — both gitignored. Never commit `studio/output/` or `studio/knowledge/`.
- Cross-repo usage: when run outside this repo, artifacts go to `<other-repo>/.studio/output/`. Override with `STUDIO_ARTIFACT_ROOT` env var.

## Migration Status

See `STUDIO_MIGRATION_PLAN.md` for the active plan to build Claude Code native execution alongside Windsurf support.
