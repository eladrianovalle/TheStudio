# Studio Collaboration Plan

Status: **COMPLETE** — all milestones shipped (M1–M5)

## Vision

Studio should feel collaborative, not autonomous. When agents hit decisions that could meaningfully change their approach, they pause, surface the decision to the user, incorporate the answer, and continue. The user stays connected to what agents are doing and shapes the output through the process — not just at the end.

Clarity Score is the intelligence layer on top: it tracks per-topic confidence, adapts question density to scope, and lets the system naturally transition from heavy collaboration (early, vague ideas) to mostly-autonomous execution (well-specified features).

## Design Principles

- **Collaboration over autonomy** — agents ask on meaningful decisions rather than assuming
- **Inline, not modal** — questions happen during normal deliverables runs, not in a separate "question mode"
- **Clarity is scoped** — the same project can have high clarity on core loop but low clarity on monetization; agents adjust per-topic
- **Clarity adapts to context** — analyzing a whole game = broad scope, building one feature = narrow scope
- **Advocates own decision points** — they're doing the creative work and hitting the gaps
- **Contrarians flag unsettled assumptions** — rarely generate new decisions, mostly catch when the advocate assumed something that isn't actually decided
- **User validates clarity** — the system tracks markers automatically, but the user confirms or overrides

## Prior Work (from Migration Plan)

The original migration (M0-M5) built the shared-core Studio with Claude Code and Windsurf as execution peers. That plan is complete. See `STUDIO_MIGRATION_PLAN.md`.

### M1 Infrastructure (complete)

M1 originally built the question-mode infrastructure under a binary `--mode questions` UX. This was reworked into the Decision Point Protocol:

- **`decision_points.py`** — parser, formatter, `decisions.md` generator, run directory scanner. Pure function library.
- **`question_mode.py`** — templates updated to use unified blockquote DECISION format. Reframed as pre-flight decision collection.
- **`build_instruction_doc()`** — "Decision Point Protocol" section injected into all non-question-mode instructions.
- **`DocumentValidator.validate_question_mode()`** — accepts both bullet questions and blockquote DECISION format.
- **`finalize_run()`** — generates `decisions.md` for question-mode runs by scanning agent output.
- **249 tests passing** (27 new for decision points and unified format).

## Milestones

### M1: Decision Point Protocol

**Goal:** Agents know how to flag decision points in their output during normal deliverables runs.

This is the instruction-layer piece — what agents write when they hit a gap.

- [x] **T1.1** Define decision point output format
  - Markdown blockquote format, readable by humans, AI, and any assistant:
    ```
    > **DECISION [P0]:** Should the social deduction mechanic be real-time or turn-based?
    > **Unblocks:** Core loop design — fundamentally different gameplay
    > **Options:** (a) Real-time (Among Us style) (b) Turn-based (Mafia style)
    ```
  - P0 = orchestrator must pause and ask user before continuing
  - P1 = surface to user but agent continues with stated assumption
  - P2 = logged for context, no pause

- [x] **T1.2** Create `decision_points.py` module
  - `DecisionPoint` dataclass, parser, formatter, `decisions.md` log generator
  - `extract_decisions_from_run()` scans advocate/contrarian files across all naming conventions
  - Reuses P0/P1/P2 framework from `question_mode.py`

- [x] **T1.3** Update instruction templates in `build_instruction_doc()`
  - "Decision Point Protocol" section added to all non-question-mode runs
  - Advocate and contrarian guidance included

- [x] **T1.4** Keep `--mode questions` as pre-flight decision collection
  - Reframed as "what don't I know yet?" reconnaissance mode
  - Templates updated to use unified blockquote DECISION format
  - Generates `decisions.md` on finalize by scanning agent output

- [x] **T1.5** Tests (27 new tests)
  - 22 tests in `test_decision_points.py` (parsing, formatting, extraction, instruction templates)
  - 5 tests in `test_question_mode.py` (unified format, validator acceptance)

- [x] **T1.6** Update usage docs
  - CLAUDE_CODE_USAGE.md, STUDIO_INTERACTION_GUIDE.md, CLAUDE.md updated

**MVI test:** Run a phase, advocate output contains well-formatted decision points with clear P0/P1/P2 markers.

---

### M2: Orchestrator Pause-and-Ask

**Goal:** The slash command detects decision points, surfaces them to the user, and injects answers into subsequent agents.

This is the UX piece — where it actually feels collaborative.

- [x] **T2.1** Decision point detection in orchestrator
  - After each agent completes, parse output for decision point markers
  - Separate P0s (must ask) from P1s (show but continue) from P2s (log only)

- [x] **T2.2** User interaction flow
  - Surface P0 decision points to user (all at once from a single agent)
  - Wait for user response
  - P1s shown as "FYI — agent is assuming X, override if needed"

- [x] **T2.3** Answer injection via `decisions.md`
  - Write user answers to `{run_dir}/decisions.md` with metadata (which agent asked, when, user's response)
  - All subsequent agent prompts include: "Read decisions.md for user-settled constraints"
  - Decisions accumulate across the full run

- [x] **T2.4** Update slash commands (`run-phase.md`, `run-studio-phase.md`)
  - Add orchestrator logic: after spawning agent, read output, check for decision points, pause if P0s found
  - Pass `decisions.md` context to next agent

- [x] **T2.5** Tests and usage docs

**M2 complete (2026-03-18):** Orchestrator pause-and-ask shipped. Slash commands detect decision points after each agent, pause on P0s, show P1s as FYI, and inject answers into subsequent agents via `decisions.md`. Both `/run-phase` and `/run-studio-phase` updated. `record-decisions` and `check-decisions` subcommands added to `run_phase.py`. 259 tests passing (10 new).

**MVI test:** Run a phase, get asked questions between advocate and contrarian, see your answers reflected in the contrarian's response as settled constraints.

---

### M3: Clarity Score

**Goal:** Per-topic confidence tracking that controls question density and adapts to scope.

This is the intelligence layer — the system gets smarter about when to ask.

- [x] **T3.1** Clarity score model
  - Per-topic scores (e.g., `core_loop: 0.8`, `monetization: 0.3`)
  - Computed from: questions answered, decisions made, assumption-to-fact ratio
  - Scoped to context: broad (whole game analysis) or narrow (single feature)

- [x] **T3.2** Automatic marker tracking
  - Track which topics have been addressed by user decisions
  - Increment clarity when questions are answered, decisions confirmed
  - Decrement or flag when contrarians challenge settled assumptions

- [x] **T3.3** User validation
  - After clarity is computed, surface it to user for confirmation
  - User can override: "I'm not actually confident about X" or "X is more settled than you think"
  - Validated clarity persists in `decisions.md` or a dedicated `clarity.json`

- [x] **T3.4** Clarity-driven question density
  - Low clarity topics → agents instructed to surface more decision points
  - High clarity topics → agents instructed to treat prior decisions as constraints, only flag genuine new gaps
  - Maps naturally to scoped debate: S1 alignment (low clarity, many questions) → S2 depth (higher clarity, fewer questions) → S3 polish (high clarity, rare questions)

- [x] **T3.5** Context-adaptive scoping
  - When user asks about "the game" → broad clarity scope
  - When user asks about "the inventory system" → narrow scope, clarity tracked for that feature's concerns

- [x] **T3.6** Tests and usage docs

**M3 complete (2026-03-19):** Clarity Score shipped. `clarity.py` module with per-topic scoring, automatic tracking from decisions, user override CLI (`show-clarity`, `set-clarity`, `recompute-clarity`), context-adaptive scoping (broad/narrow), and clarity-driven question density injected into agent instructions. Slash commands show clarity after decision recording. 338 tests passing (57 new).

**MVI test:** Run a multi-scope studio phase, observe question density naturally decrease as you answer decision points. Clarity scores visible and overridable.

---

### M4: Role Customization

**Goal:** Projects can extend/override base roles with project-specific definitions.

- [x] **T4.1** `role_overrides.py` module
  - Load `.studio/roles/*.json` overlay files
  - Shallow key-level merge: override keys replace base, unspecified keys inherit
  - `validate_role_override()` for structural correctness
  - Type-checked validation: string fields, list fields, unknown key rejection

- [x] **T4.2** Wire into `run_phase_roles.py`
  - `get_role_spec()` and `build_role_details()` accept optional `overrides` parameter
  - `_resolve_studio_roles()` loads overrides from `get_artifact_root()/.studio/roles/`
  - Applied overrides logged in `run.json` under `studio_roles.role_overrides_applied`

- [x] **T4.3** Tests and usage docs

**M4 complete (2026-03-19):** Role Customization shipped. `role_overrides.py` module with per-project `.studio/roles/*.json` overlays, shallow key-level merge, structural validation, and integration into `run_phase_roles.py`. CLAUDE_CODE_USAGE.md, STUDIO_INTERACTION_GUIDE.md, CLAUDE.md updated. 366 tests passing (28 new).

**MVI test:** Create a `.studio/roles/engineering.json` override with custom advocate_focus, run a phase, see the override reflected in instructions.

---

### M5: Cross-Repo Install (REORDERED — doing next)

**Goal:** `studio init` installs Studio into any project so `/run-phase` and `/run-studio-phase` work out of the box — including pause-and-ask.

**Why now:** M2's pause-and-ask only works via slash commands, but cross-repo projects don't have them. This is the blocker.

- [x] **T5.1** `install.py` module — init/check/update
  - `studio init --target <path>` — copies slash commands to `.claude/commands/`, Python source to `.studio/source/`, config, manifest, role packs, prompt docs
  - Slash commands auto-rewritten: `$STUDIO_ROOT` → `.studio/source`
  - `studio check-install --target <path>` — SHA-256 comparison against source
  - `studio update --target <path>` — refreshes source, preserves user customizations
  - VERSION file with commit hash and install timestamp

- [x] **T5.2** Install manifest and selective copy
  - MANIFEST.json with per-file SHA-256 checksums
  - Copies: source Python, config, manifest, role packs, prompt docs, bridge template
  - Skips: tests/, output/, knowledge/
  - Slash command rewriting handles `$STUDIO_ROOT/` and bare `studio/` prompt doc references

- [x] **T5.3** Tests (20 new)
  - Install: creates dirs, copies files, rewrites commands, idempotent, preserves user files
  - Check: detects not-installed, up-to-date, changed files
  - Update: no-op when current, refreshes changed files, raises if not installed
  - Rewriting: $STUDIO_ROOT replacement, prompt doc refs, preserves other content

**M5 complete (2026-03-19):** Cross-repo install shipped. `studio init` installs slash commands + source into any project. `/run-phase` and `/run-studio-phase` work natively with pause-and-ask. 281 tests passing (20 new).

**MVI test:** Run `python run_phase.py init --target /path/to/project`, then `/run-phase --phase design --text "Boss fight"` from that project — get paused on P0 decisions.
