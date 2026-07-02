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

`run_phase.py` is the single entrypoint. The commands below are the ones you
reach for most; run `python studio/run_phase.py --help` for the full subcommand
list and **`studio/docs/API.md`** for the argument-by-argument contract.

```bash
# Tests (from studio/)
cd studio && python -m pytest tests/ -v
cd studio && python -m pytest tests/test_run_phase.py::TestClassName::test_name -v

# Prepare / finalize / validate a run
python studio/run_phase.py prepare --phase <market|design|tech|studio> --text "description"
python studio/run_phase.py prepare --phase design --text "description" --mode questions
python studio/run_phase.py finalize --phase <phase> --run-id <run_id> --status completed --verdict APPROVED
python studio/run_phase.py validate --phase <phase> --run-id <run_id>

# Rate a run + record what it led to (outcome), then view the cross-run dashboard
python studio/run_phase.py rate --run-dir <path> --score 4 --note "..." \
    --shipped yes --impact major --changed "cut lobby scope in half"
python studio/run_phase.py stats                       # verdicts, ratings, outcomes, tokens, decisions

# Bridge outcomes from a consuming repo back to this one (see API.md)
python studio/run_phase.py export-outcomes --repo <name> --out outcomes.jsonl
python studio/run_phase.py import-outcomes --from outcomes.jsonl

# Cross-repo install / update (also: check-install, setup, offload, notify, cleanup)
python studio/run_phase.py init --target /path/to/project
python studio/run_phase.py update --target /path/to/project
```

Other subcommands — decision management (`check-decisions`, `record-decisions`,
`extract-decisions`, `inject-context`), clarity (`show-clarity`, `set-clarity`,
`recompute-clarity`), metrics (`record-metrics`, `show-metrics`), `cleanup`,
`notify`, `setup`, `offload` — are documented in `studio/docs/API.md`.

## Architecture

All source lives under `studio/`. `run_phase.py` is the sole entrypoint using only stdlib (plus `tomli` on Python 3.10).

### Modules (all in `studio/`)

`run_phase.py` is the CLI entrypoint; the rest are focused modules it imports.
See **`studio/docs/ARCHITECTURE.md`** for the full per-module reference.

- **Debate / flow:** `scopes.py`, `question_mode.py`, `decision_points.py` (owns the canonical decision-point emit/parse format), `clarity.py`, `verdict.py`, `rerun.py`
- **Roles / personas:** `run_phase_roles.py`, `role_overrides.py`, `persona_overrides.py` (+ `studio.manifest.json`, `role_packs/`)
- **Diagnostics:** `stats.py` (pure cross-run aggregation, ratings, and the outcome summary that `rate`/`export-outcomes`/`import-outcomes` feed), `session.py` (pure; builds the automatic `session.json` health record finalize writes for each run)
- **Implementation loop:** `impl_loop.py` — config for `.claude/workflows/implementation-loop.js`; see `studio/docs/IMPLEMENTATION_LOOP_SPEC.md`
- **Cross-repo + hygiene:** `install.py`, `setup.py`, `offload.py`, `cleanup.py`
- **Shared:** `config_loading.py` (the single TOML loader), `validators/`, `integrations/slack_digest.py`

### Configuration files

Shipped defaults live in `config/` and `studio.manifest.json`; per-repo overrides
live in `.studio/` and are shallow-merged over the defaults. `setup.cfg` holds the
mutmut (mutation-testing) config. See `studio/docs/ARCHITECTURE.md` for the full
catalog and each file's schema.

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
- **No heavy dependencies** — stdlib only (plus `tomli` on Python 3.10). `run_phase.py` has grown large; a decomposition is planned in `studio/docs/RUN_PHASE_SPLIT_PLAN.md`.
- **MVI (Minimum Viable Interaction)** — every task, sprint, and milestone must end in something usable. "Build a skateboard, not a wheel." Product, Engineering, and Design contrarians enforce this. See `studio/docs/MVI_METHODOLOGY.md`.
- **AI-TDD discipline** is mandatory for tech phase implementations. AI writes scenarios and boilerplate; humans own assertions. See `studio/docs/AI_TDD_METHODOLOGY.md` for the full methodology (scenario-first, stack boundary, mutation verification, anti-pattern detection).
- **Documentation contract**: changes to workflow must update README, CLAUDE_CODE_USAGE.md, and affected bridge docs simultaneously.
- **Working directories**: `.scratch/` for temp files, `.private/` for sensitive data — both gitignored. Never commit `studio/output/` or `studio/knowledge/`.
- Cross-repo usage: when run outside this repo, artifacts go to `<repo>/.studio/output/`. First run auto-scaffolds `.studio/` and a bridge doc. Override with `--artifact-root` flag or `STUDIO_ARTIFACT_ROOT` env var. Priority: flag > env > cwd detection.
