# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Coding Principles

Behavioral guidelines to reduce common LLM coding mistakes. These apply to ALL work in this repository — not just Studio runs.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you wrote 200 lines of machinery for a 50-line problem, cut it down — but remove *concepts*, not characters. Aim for fewer moving parts, never the same logic squeezed into denser code (that's what "Write Code for Humans" guards).

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify. Overcomplicated means too many moving parts — not too many characters.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### 5. Git & PR Etiquette

**Open pull requests as drafts first.**

A new PR starts as a **draft**, not ready-for-review. Mark it ready only when the work is complete, tests pass, and you actually want a human to review and merge it. Opening as a draft prevents two failure modes: accidental early merges (a not-yet-finished PR getting merged by mistake) and reviewer churn (reviewers spending attention on a still-moving target). Flip to ready when it's genuinely ready for eyes.

### 6. Write Docs & Comments for Humans

**A person reads your docs and comments. Write for that person.**

This covers everything you write for humans rather than the compiler: doc files, code comments, docstrings, commit messages, and PR descriptions.

- Use plain language. If a term of art is unavoidable, define it the first time or pick a simpler word.
- Say what a thing does and why it matters, not just its name. "Refuses to overwrite your local edits" beats "enforces the clobber-guard precondition."
- Cut the tells of machine-written prose: inflated phrasing, filler, hedging, and padding add length without adding meaning.
- Match the voice already in the file instead of importing your own.

The test: could a teammate who is new to the code read it once and understand it, without asking you to translate?

### 7. Write Code for Humans

**The code's first reader is a person, not the compiler. Write for that person.**

The previous principle covers what you write *around* the code — docs, comments, commits. This one is about the code itself. Simple code and readable code are not the same thing: simple code has few moving parts; readable code spells those parts out. Aim for both, and never trade readability away to save lines.

- Name things in full, for what they are. `remaining_budget` over `rb`, `resolve_source_dir` over `rsd`. A good name is a comment you don't have to write.
- Prefer explicit and a little verbose over compact and clever. One obvious thing per line beats a dense expression a reader has to decode.
- Reach for the plain, conventional form a reader expects. Cleverness is a cost paid again by everyone who reads the code later.
- Don't compress just to shorten. Saving three lines isn't worth making the next person stop and work out what they do.

The test: could a teammate seeing this file for the first time read it top to bottom and follow it — without you narrating over their shoulder?

---

*Adapted from [Andrej Karpathy's coding principles](https://github.com/forrestchang/andrej-karpathy-skills).*

## What This Is

TheGameStudio is an **instruction generator** for structured advocate/contrarian debates in game development workflows. It produces run directories with instructions that an AI assistant (Claude Code is the supported path) executes, then packages results as versioned artifacts. There is no AI runtime — all intelligence lives in the assistant's execution.

## Running a Studio Phase (Claude Code)

Use the slash command to run a full advocate/contrarian debate:

```
/run-phase --phase market --text "A cozy farming sim with social deduction mechanics"
/run-phase --phase tech --text "Build multiplayer lobby system" --max-iterations 5
/run-phase --phase design --text "A cozy farming sim" --mode questions
/run-studio-phase --text "Add AI critique engine" --roles +marketing +engineering
/run-studio-phase --text "Social deduction farming sim" --roles +product +design --mode questions
```

Single-phase runs (`/run-phase`) spawn separate Advocate and Contrarian agents per iteration. Multi-role runs (`/run-studio-phase`) use a three-tier scoped debate by default: **alignment** (all roles, short, parallel) → **depth** (per-role, full, sequential) → **polish** (all roles, short, 1 pass) → integrator duel. Use `--no-scopes` for flat mode. See `studio/docs/CLAUDE_CODE_USAGE.md` for details.

All runs (except `--mode questions`) include inline **decision point surfacing** — agents flag P0 (blocking), P1 (important), and P2 (context) decisions using a standard blockquote format. Every deliverable run also opens with a built-in **Open-Questions Pre-Flight** (Step 0): a fast pass that surfaces what is genuinely unsettled, pauses on P0 blockers, and records the answers before the iteration loop begins — so no run silently assumes. The standalone `--mode questions` remains a heavier, questions-only run for when you want a full prioritized decision set with no deliverables.

The **Contrarian is an editor by default** — beyond hunting flaws and edge cases, it carries an always-on mandate to remove, merge, and simplify. The advocate piles it on; the contrarian carves out the essence (bias toward deletion, clarity, conciseness). This mandate is on in every deliverable run and stance, but deliberately **off in `--mode questions`**, where the contrarian instead judges question *relevance* and must not drop genuinely-open questions to keep the list lean.

## Implementation Loop (Claude Code)

The same advocate/contrarian cadence also runs during **implementation**, via `/studio-implement`:

```
/studio-implement Users can create and view a profile (hardcoded storage)
```

A **writer** agent builds one complete MVI unit and commits its passing state; a fresh **editor** agent (the `CONTRARIAN_MANDATE` applied to code) cuts/refines it against the writer's diff and reverts if an edit breaks green — a one-way pipeline gated on **"MVI unit complete AND tests green."** It runs the `.claude/workflows/implementation-loop.js` Claude Code Workflow, config-driven via `implementation_loop.toml` (editor on/off, read scope, output budget, mutation/static gates), with knobs exposed through `python -m impl_loop`. It is the executor described in `studio/docs/IMPLEMENTATION_LOOP_SPEC.md`. Status: executor + config shipped; cadence tuning (gate granularity vs. editor yield) is ongoing.

## CLI Commands

```bash
# Run tests (from studio/ directory)
cd studio && python -m pytest tests/ -v

# Run a single test
cd studio && python -m pytest tests/test_run_phase.py::TestClassName::test_name -v

# Prepare a phase run (manual)
python studio/run_phase.py prepare --phase <market|design|tech|studio> --text "description"

# Prepare in question-surfacing mode (surfaces open questions instead of deliverables)
python studio/run_phase.py prepare --phase design --text "description" --mode questions

# Prepare with role pack (studio phase only)
python studio/run_phase.py prepare --phase studio --text "..." --role-pack studio_core --roles +product +engineering +qa

# Finalize a completed run
python studio/run_phase.py finalize --phase <phase> --run-id <run_id> --status completed --verdict APPROVED

# Validate a run
python studio/run_phase.py validate --phase <phase> --run-id <run_id>

# Decision management
python studio/run_phase.py check-decisions --file path/to/advocate_1.md
python studio/run_phase.py record-decisions --run-dir <run_dir> --decisions-file answers.json
python studio/run_phase.py extract-decisions --run-dir <run_dir>          # unsettled only (default)
python studio/run_phase.py extract-decisions --run-dir <run_dir> --all   # include already-settled
python studio/run_phase.py inject-context --run-dir <run_dir> --scope alignment --role marketing --stance advocate

# Clarity scores
python studio/run_phase.py show-clarity
python studio/run_phase.py set-clarity --topic core_loop_design --score 0.9
python studio/run_phase.py set-clarity --topic core_loop_design --reset
python studio/run_phase.py recompute-clarity --phase studio --run-id <run_id>

# Agent metrics (token tracking per agent)
python studio/run_phase.py record-metrics --run-dir <path> --agent advocate --total-tokens 5000 --tool-uses 10 --duration-ms 30000 --role marketing --scope alignment
python studio/run_phase.py show-metrics --run-dir <path>

# Quality ratings & cross-run stats (diagnostics + fine-tuning feedback loop)
python studio/run_phase.py rate --run-dir <path> --score 4 --note "solid market read"  # human 1-5 quality score
python studio/run_phase.py stats                       # cross-run dashboard: verdicts, ratings, tokens, decisions, usage
python studio/run_phase.py stats --phase studio        # filter to one phase
python studio/run_phase.py stats --json                # machine-readable aggregate

# Storage cleanup
python studio/run_phase.py cleanup --dry-run
python studio/run_phase.py cleanup

# Outbound notifications (Slack / n8n run digest — see studio/docs/INTEGRATIONS.md)
python studio/run_phase.py notify --run-dir <run_dir>            # post digest to enabled webhooks
python studio/run_phase.py notify --run-dir <run_dir> --dry-run  # print payloads without posting

# Cross-repo install (installs slash commands + source into any project)
python studio/run_phase.py init --target /path/to/project
python studio/run_phase.py check-install --target /path/to/project   # shows which of your local edits an update would overwrite
python studio/run_phase.py update --target /path/to/project          # add --force to overwrite files you've edited locally

# Setup wizard (configure roles, scopes, cleanup after install)
python studio/run_phase.py setup --target . --status
python studio/run_phase.py setup --target . --defaults
python studio/run_phase.py setup --target . --answers answers.json
python studio/run_phase.py setup --target . --role-pack studio_core --roles +ml -art

# Offload analysis (analyze CLAUDE.md for offload opportunities)
python studio/run_phase.py offload --target .
python studio/run_phase.py offload --target . --apply
python studio/run_phase.py offload --target . --rollback
python studio/run_phase.py offload --target . --verify
```

## Architecture

All source lives under `studio/`. `run_phase.py` is the sole entrypoint using only stdlib (plus `tomli` on Python 3.10).

### Core modules (all in `studio/`)

- **`run_phase.py`** — Primary entrypoint: `prepare`, `finalize`, `validate`, `cleanup`, decision, clarity, metrics, rate, stats, install, setup, offload, and notify subcommands. The `rate`/`stats` pair is the diagnostics + fine-tuning feedback loop: `rate` records a human 1-5 quality score per run (`rating.json`, the human counterpart to the agent verdict); `stats` reads every run's `run.json`/`rating.json`/`decisions.json` plus the `.studio/usage.log` and prints a cross-run dashboard (verdict/approval rate, avg rating + lowest-rated improvement targets, token/cost efficiency, decision priority mix + answer rate, usage). All per-run data already existed; `stats` is the first thing that aggregates it across runs.
- **`run_phase_roles.py`** — Role system: loads `studio.manifest.json`, resolves role packs, applies project-local overrides, builds per-role file naming (`advocate--<role>--NN.md`).
- **`role_overrides.py`** — Project-local role customization: loads `.studio/roles/*.json` overlays, validates structure, shallow-merges with manifest roles.
- **`persona_overrides.py`** — Project-local single-phase persona overrides: loads `.studio/personas.toml`, validates structure, per-phase shallow-merges over the shipped `PHASE_DETAILS` defaults (advocate/contrarian/notes/implementer/integrator).
- **`cleanup.py`** — TTL-based (30 days) and budget-based (900MB) run artifact cleanup, plus loose file removal for legacy artifacts outside run directories.
- **`scopes.py`** — Three-tier scope system (alignment / depth / polish) with output budgets and debate modes (`all_roles` vs `per_role`).
- **`rerun.py`** — Detects rejection context from prior runs and generates rerun instructions.
- **`question_mode.py`** — Question-surfacing mode: generates P0/P1/P2 question instructions for advocate/contrarian instead of deliverable prompts. Pure function library, no I/O.
- **`decision_points.py`** — Parses and formats inline decision points (P0/P1/P2 blockquotes) from agent output. Extracts decisions from completed runs into a consolidated log.
- **`clarity.py`** — Per-topic Clarity Score tracking. Computes confidence from answered decisions, controls agent question density, persists to `clarity.json`. CLI: `show-clarity`, `set-clarity`, `recompute-clarity`.
- **`verdict.py`** — Extracts APPROVED/REJECTED/UNKNOWN verdict from text.
- **`install.py`** — Cross-repo installer: `init`/`check-install`/`update` copies the Studio source, slash commands, and workflows into any project. Tracks every copied file's checksum so `update` warns you (and stops, unless `--force`) before overwriting a file you've edited locally. Also injects coding principles into the target's `CLAUDE.md` via sentinel markers for safe updates.
- **`offload.py`** — CLAUDE.md analyzer: classifies sections, detects embedded constraints, scores pointer strength, generates offload reports and manages canary tokens.
- **`setup.py`** — Setup wizard: project configuration after install. Tracks setup state in `.studio/SETUP.json`, generates role overrides, scopes, and cleanup config. Supports incremental re-configuration when new features are added.
- **`impl_loop.py`** — Implementation-loop config: `LoopConfig` dataclass + `load_loop_config()` (tomllib/tomli fallback, resolution chain explicit → `.studio/` → shipped → defaults, patterned on `scopes.py`). `runtime_knobs()` + a `python -m impl_loop` JSON CLI project the resolved config into the knobs the `.claude/workflows/implementation-loop.js` Workflow consumes (editor on/off, read scope, output budget, mutation/static gates). The only Python piece of the writer/editor implementation loop; see `studio/docs/IMPLEMENTATION_LOOP_SPEC.md`.
- **`validators/`** — `DocumentValidator` (including `validate_question_mode()`) and `CodeValidator` for post-run quality checks.
- **`integrations/slack_digest.py`** — Outbound run-digest notifier. Posts a finalized run's status/verdict/summary to a Slack Incoming Webhook (Block Kit) and/or an n8n Webhook node (flat JSON), stdlib `urllib` only. Config from `.studio/integrations.toml`; webhook URLs resolved from env vars (secrets never committed). Fires via the `notify` subcommand and, when enabled, auto-fires on `finalize` (soft-fail). See `studio/docs/INTEGRATIONS.md`.

### Configuration files

- **`studio.manifest.json`** — Defines all disciplines (marketing, product, design, art, engineering, test_engineer, qa, web_engineering, web_product, web_test_engineer, web_qa, ml, ai_engineer, pmm) with advocate/contrarian focuses, deliverables, escalation cues, and role dependencies.
- **`role_packs/*.json`** — Curated pod presets (e.g., `studio_core` = marketing + product + design + art + engineering + test_engineer + qa). Override with `--roles +role/-role`. Role dependencies in the manifest auto-inject co-required roles (e.g., engineering always brings test_engineer).
- **`config/scopes.toml`** — Default three-tier scope configuration (alignment → depth → polish) with output budgets and debate modes.
- **`config/studio_settings.toml`** — Cleanup TTL and storage limits.
- **`config/implementation_loop.toml`** — Shipped defaults for the implementation writer/editor loop: `[loop]` (`deliver_on_gate_fail`), `[gate]` (`test_command`, `static_checks`, `require_mutation_check`), `[editor]` (`mandate`, `read_scope`, `output_budget`). Override with `.studio/implementation_loop.toml`. Loaded by `impl_loop.py`.
- **`.studio/scopes.toml`** — Scope-based iteration budgets (auto-loaded if present).
- **`.studio/validation.toml`** — Validation configuration.
- **`.studio/roles/*.json`** — Project-local role overrides. Shallow-merge with manifest roles (override keys replace base, unspecified keys inherit).
- **`.studio/personas.toml`** — Project-local single-phase persona overrides (market/design/tech/studio advocate, contrarian, notes, implementer, integrator). Per-phase shallow merge over the shipped `PHASE_DETAILS` defaults; loaded via `persona_overrides.py`, authored by the setup wizard.
- **`.studio/integrations.toml`** — Optional outbound-webhook config for run digests. `[slack]` and `[n8n]` tables, each with `enabled` and `webhook_url_env` (env var holding the secret URL); `[n8n]` also takes optional `auth_header`/`auth_value_env` for Header Auth. Absent or no target `enabled` → notifications are off. Loaded by `integrations/slack_digest.py`.
- **`.studio/unstale.toml`** — Optional per-repo override for the `/unstale` staleness audit: `[snapshot]` commands (`test_count`, `module_inventory`, `cli_help`) and `[audit]` globs (`doc_globs`, `source_globs`, `cross_refs`). When absent, `/unstale` self-detects the stack (Rust/Unity/Node/Python/Go) from marker files. Read directly by the `/unstale` command, not Python code.
- **`.studio/implementation_loop.toml`** — Optional per-repo override for the implementation writer/editor loop config (shallow over `config/implementation_loop.toml`). Loaded by `impl_loop.py`; consumed by the `implementation-loop.js` Workflow via `python -m impl_loop`.

### Artifact structure

Runs produce timestamped directories under `output/<phase>/run_<phase>_<timestamp>/` containing:
- `instructions.md`, `run.json`, `summary.md`
- `advocate_N.md` / `contrarian_N.md` (simple phases)
- `advocate--<role>--NN.md` / `contrarian--<role>--NN.md` + `integrator.md` (studio flat mode)
- `advocate--<role>--S1-NN.md` / `S2-NN.md` / `S3-NN.md` (studio scoped mode: alignment/depth/polish)

### Phases

Four phases: `market`, `design`, `tech`, `studio`. Each has distinct advocate/contrarian personas. The `studio` phase supports multi-role pods via role packs.

## Important Conventions

- **Python 3.10+** required. Uses `tomllib` (3.11+) with `tomli` fallback.
- **No heavy dependencies** — keep `run_phase.py` small and bash-friendly.
- **MVI (Minimum Viable Interaction)** — every task, sprint, and milestone must end in something usable. "Build a skateboard, not a wheel." Product, Engineering, and Design contrarians enforce this. See `studio/docs/MVI_METHODOLOGY.md`.
- **AI-TDD discipline** is mandatory for tech phase implementations. AI writes scenarios and boilerplate; humans own assertions. See `studio/docs/AI_TDD_METHODOLOGY.md` for the full methodology (scenario-first, stack boundary, mutation verification, anti-pattern detection).
- **Documentation contract**: changes to workflow must update README, CLAUDE_CODE_USAGE.md, and affected bridge docs simultaneously.
- **Working directories**: `.scratch/` for temp files, `.private/` for sensitive data — both gitignored. Never commit `studio/output/` or `studio/knowledge/`.
- Cross-repo usage: when run outside this repo, artifacts go to `<repo>/.studio/output/`. First run auto-scaffolds `.studio/` and a bridge doc. Override with `--artifact-root` flag or `STUDIO_ARTIFACT_ROOT` env var. Priority: flag > env > cwd detection.
