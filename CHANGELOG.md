# Changelog

All notable changes to TheGameStudio are documented here.

---

## [Unreleased]

### Added
- Coding principle 8, "Talk to Humans": how the agent speaks in the live conversation, alongside the existing rules for docs (§6) and code (§7). Updates and decision-flags are written for a reader who hasn't opened the files, docs, or notes the agent just produced — lead with what changed and why it matters, don't drop bare internal handles (file names, config keys, PR/ticket IDs) as if they explain themselves, and when asking for a call, give enough context plus a recommendation to answer without digging. Reaches installing repos through the same `CLAUDE.md` sentinel injection that carries the other principles
- `/smoke` slash command: stands up a live, running version of whatever the repo builds so you can hand-test it (web app on a URL, game in Play mode, service on a port, CLI). Distinct from tests-green: a smoke means the thing actually runs and a person can use it. The command detects a profile, preps/builds, launches in the background, polls readiness, then hands off the entry point plus a golden-path checklist and tears down on request. Stack-agnostic self-detection, or an optional per-repo `.studio/smoke.toml` (`[smoke]` table) pins the exact setup/build/launch, readiness check, and golden path; Unity projects stand up via MCP Play mode. Ships on cross-repo install; setup wizard gains a `smoke_config` step (`CURRENT_SETUP_VERSION` 4) that authors the file via `suggest_smoke_from_stack`
- Session analytics, first slice (built via the `/studio-implement` writer/editor loop). `finalize` now auto-writes a judgment-free `session.json` health record into each run dir: convergence (iterations + rejections), decision profile (surfaced/answered/assumed by priority, incl. the assumed-P0 count), clarity delta, cost per settled decision + scope spend, and an editor-liveness word-count block. No human rating, additive and soft-fail (`session.py` builds it, `run_phase._write_session_record` wires it). New `[outcomes] ledger_path` in `.studio/integrations.toml`: when set, `finalize` appends the run's outcome record to that local ledger (dedup by repo+run_id, soft-fail), collapsing the manual `export-outcomes` → `import-outcomes` step for a single-machine setup; unrated runs are now included so the ledger and `stats` see every session. `stats` gains a "Session health" block (five auto-measured signals: assumed-P0 rate, convergence, clarity gain, tokens per settled decision, editor liveness) and a `session_health` key under `--json`
- Run outcome capture + cross-repo sharing. `rate` gains optional `--shipped {yes,no,partial}` / `--impact {none,minor,major}` / `--changed "<line>"` flags that record what a run led to downstream under an `outcome` block in `rating.json`. `stats` opens with an "Outcomes (did it ship / what changed)" section (ship rate, impact mix, recent notes), folding this repo's rated runs and a cross-repo ledger; `--json` gains an `outcomes` key. New `export-outcomes` emits rated runs as portable JSONL; `import-outcomes` merges them into a central `knowledge/outcomes.jsonl` ledger (dedup by repo+run_id) so evidence from other repos reaches `stats` here
- CI: ruff + pytest gate on every PR (`.github/workflows/ci.yml`): the first automated lint/test check. Ruff config lives in `studio/pyproject.toml` `[tool.ruff]`
- Real mutation testing. `mutmut` is now a dev dependency (`pyproject` `[project.optional-dependencies] dev`), configured in `studio/setup.cfg` `[mutmut]` and run by a new weekly/on-demand CI workflow (`.github/workflows/mutation.yml`). The implementation loop's `require_mutation_check` gate now runs a real tool instead of only being attested: `LoopConfig` gains a `gate.mutation_command` field (default `mutmut run`), surfaced in `runtime_knobs`, and the `implementation-loop.js` writer step invokes it and reports the result (falling back to hand-mutation if mutmut is absent). The weekly CI run is the machine backstop
- Write for humans, in code as well as prose. `CODING_PRINCIPLES` gains §7 "Write Code for Humans" (explicit descriptive names, explicit over clever, one obvious thing per line) alongside the existing §6 for docs/comments/commits. §2 and the Contrarian Mandate are sharpened so "simplify" means fewer moving parts, never terser code: cut concepts, not characters. Reaches installing repos through the `CLAUDE.md` sentinel injection
- Quality ratings & cross-run stats: the diagnostics + fine-tuning feedback loop. `rate` records a human 1-5 quality score + note per run (`rating.json`, the human counterpart to the agent verdict); `stats` is the first cross-run dashboard, aggregating every run's `run.json`/`rating.json`/`decisions.json` plus `.studio/usage.log` into verdict/approval rate, rating avg + lowest-rated targets, token/cost efficiency, decision priority mix, and usage (`--phase`, `--json`). `finalize` ends with an auto rate-prompt (TTY-interactive or copy-paste nudge; `--no-rate-prompt` to suppress)
- Slack / n8n run-digest integration: first `studio/integrations/` subpackage (`slack_digest.py`). Posts a finalized run's status/verdict/summary to a Slack Incoming Webhook (Block Kit) and/or n8n Webhook node (flat JSON), stdlib `urllib` only. New `notify` subcommand; auto-fires on `finalize` when enabled (default-disabled, soft-fail). Config in `.studio/integrations.toml`; webhook secrets resolved strictly from env vars (`*_env` keys, no literal fallback)
- CI: Phase-1 PR triage gate (`.github/workflows/pr-triage.yml`)
- Contrarian editor mandate (always on): every deliverable run's contrarian now carries a built-in bias toward removal, merge, and simplification on top of flaw-hunting. The advocate piles it on; the contrarian carves out the essence. Shared `CONTRARIAN_MANDATE` injected across single-phase, flat, and scoped studio prompts; phase contrarians reframed as editors. Off in `--mode questions` (there the contrarian judges question relevance, never cuts genuinely-open questions)
- Open-Questions Pre-Flight (Step 0): every deliverable run opens by surfacing what is genuinely unsettled, pausing on P0 blockers, and recording answers before the iteration loop, so no run silently assumes; later passes keep raising new questions as they surface. Reuses existing decision/clarity machinery
- Project-overridable single-phase personas via `.studio/personas.toml`: `persona_overrides.py` per-phase shallow-merges advocate/contrarian/notes/implementer/integrator overrides over the shipped `PHASE_DETAILS` defaults; setup wizard gains a `persona_customization` step (`CURRENT_SETUP_VERSION` 2) that authors the file and can sniff the project stack (`Cargo.toml`/`package.json`/`*.csproj`) to suggest a fitting persona
- `/offload` slash command: analyzes CLAUDE.md for content safe to move to companion docs, with section classification, pointer strength scoring, canary token verification, and reconciliation against existing docs (`offload.py`, 23 tests)
- `/detest` slash command: audits test suites against AI-TDD methodology, finds anti-patterns, fixes them
- `/unstale` Agent 5: project tracking audit (GitHub Issues + local tracking files) with permission-gated destructive actions
- Stack-agnostic `/unstale`: the command now self-detects the project stack (Rust/Unity/Node/Python/Go) from marker files instead of assuming the Studio Python layout, so it works in any installed repo. Optional per-repo `.studio/unstale.toml` override pins exact snapshot commands and audit globs; authored by a new setup wizard `unstale_config` step (`CURRENT_SETUP_VERSION` 3) via `suggest_unstale_from_stack`
- `ai_engineer` role in manifest: Staff AI Engineer specializing in prompt architecture & agent optimization
- `web_product` role in manifest: Director of Product (Web Platforms & Creator Tools): opportunity framing (ICP/JTBD), build-vs-fork-vs-buy with licensing implications, MVI-gated roadmaps. Completes the `web_*` role set so downstream packs that list it survive updates (#35)
- `/studio-setup` slash command + `setup` CLI subcommand: post-install wizard for role pack selection, role customization, scope tuning, and cleanup settings with incremental versioned steps (`setup.py`, 43 tests)
- `docs/CODING_PRINCIPLES.md`: standalone Karpathy-inspired principles file, shipped with cross-repo installs
- Cross-repo install now injects coding principles into target's `CLAUDE.md` via sentinel markers (`<!-- STUDIO:CODING_PRINCIPLES:BEGIN/END -->`), with idempotent update support (6 tests)
- Karpathy AI principles integrated into agent instructions: Think-Before-Coding (alignment scope), Simplicity-First, Surgical-Changes (depth/polish scopes), Goal-Driven-Execution with verification checkpoints. Think-First Checkpoint requires advocates to state their understanding before analysis; contrarians verify framing before critiquing content
- `No Merge Conflicts` CI workflow (`.github/workflows/no-merge-conflicts.yml`) to satisfy branch ruleset

### Fixed
- `check-install`/`update` now read Studio source from the **default branch** (`main`), not whatever branch the upstream source checkout happens to be parked on (or its uncommitted edits). Consuming repos resolve their upstream to a local working tree and read its files directly, so a source repo left on a feature branch used to leak that work-in-progress into other projects' update checks — they compared against the branch, and once they'd copied it, reported a false "up to date." The check now materializes the default branch's committed tree in a throwaway worktree, reads from there, and notes which branch it bypassed; `update` copies from `main` while still recording the durable upstream path in `VERSION`. Falls back to reading the working tree as-is when the source isn't a git repo or is already on `main` and clean
- `/studio-update` now recovers when a project's installed snapshot is too old or broken to run. Previously, if the snapshot's `run_phase.py` failed to start (a `ModuleNotFoundError`/`ImportError` from a past install bug or a snapshot predating a module current code imports), the command surfaced a raw Python traceback and the user was stuck. The command now recognizes an outright run failure and switches to running `check-install`/`update` from the upstream Studio repo (path read from `.studio/VERSION` `source_path`), whose `update` re-copies a working snapshot in and repairs it
- `update` now refreshes the coding-principles block in a project's `CLAUDE.md`. That block is injected once at install time between sentinel markers and was never a manifest file, so a checksum-only `check-install` never noticed when Studio's principles moved ahead (e.g. the new "Talk to Humans" principle) and reported "up to date" while the block sat behind. `check-install` now compares the installed block against the current template and flags it; `update` re-injects it in place, leaving the rest of `CLAUDE.md` — your own project notes above and below the markers — untouched
- `record-metrics --agent` accepted `polish` (a scope name) as an agent type while omitting `implementer` (the real agent in market/design/tech phases): corrected in the CLI and its `API.md` reference. Also retargeted the `CROSS_REPO_CHECK_MVI` doc, which described a never-shipped `studio check` command with output it doesn't print, to the actual `check-install` behavior
- `update` no longer silently overwrites your local edits to slash commands or workflows. It already protected the Studio source files; now it also tracks the installed `.claude/commands/*` and `.claude/workflows/*`, so `check-install` flags an edit you've made to one of them and `update` stops before overwriting it (pass `--force` to overwrite anyway)
- `check-install`/`update` stale-snapshot detection (#20): run through the installed snapshot, both compared it against its own manifest and always reported "up to date", silently blocking updates. Now resolves the live upstream from `VERSION.source_path`, warning loudly when it can't
- Installer omitted the `integrations` subpackage: `init`/`update` shipped without `integrations/__init__.py` + `slack_digest.py`, breaking every command in installed projects
- Slack digest body now includes the run summary + final-doc pointer, prefers a plain-language `digest.md` over the dense `summary.md`, and renders markdown as Slack `mrkdwn`
- Stack-neutral phase personas: removed the hardcoded "Three.js Technical Architect / WebGL" tech persona and "Steam hook" market wording from `PHASE_DETAILS` so runs in any codebase (Rust, Unity, etc.) get a fitting default
- Clarity reset is now phase-independent: the fresh-run check compares the current objective against the one stored in the project-level `clarity.json`, so a prior objective under one phase no longer leaks stale topics into a new objective under another phase. A corrupt/unparseable `clarity.json` is now treated as absent (self-heals) instead of crashing `prepare`
- Rerun context injection is gated on a phase-local objective match, so a project-wide same-objective decision can't pull rejection feedback from an unrelated previous run
- `persona_overrides.py` added to cross-repo install `SOURCE_FILES` (was missing, would `ImportError` on target installs)
- `inject-context` now resolves custom scope names via canonical positional aliases (alignment→0, depth→1, polish→2)
- `prepare` now resets stale clarity and skips rerun context when the new run has a different objective than the previous one: prevents orchestrator agents from inheriting irrelevant topic scores and rejection feedback
- `_resolve_scopes` now falls back to shipped `config/scopes.toml` when no `.studio/scopes.toml` override exists: scoped runs work out of the box

### Changed
- Extracted two modules out of `run_phase.py`: `config_loading.py` (the single shared `tomllib`/`tomli` loader, now imported by every config reader instead of each carrying its own copy) and `stats.py` (pure cross-run aggregation, formatting, and outcome roll-up). A deferred plan for the rest of the split lives in `studio/docs/RUN_PHASE_SPLIT_PLAN.md`
- Decision-point format now has a single owner: `decision_points.py` holds the canonical `DECISION_BLOCK_TEMPLATE` and `DECISION_BLOCK_EXAMPLE` constants, imported by the instruction generators (`run_phase.build_instruction_doc`, `scopes.py`) so what agents emit and what the parser reads can't drift apart
- Windsurf/Cascade path retired: Claude Code is the one supported assistant path; the Windsurf bridge docs were removed and the remaining docs updated to match
- CLAUDE.md slimmed: the full CLI command list and module/config catalog now live in `API.md` and `ARCHITECTURE.md`, with CLAUDE.md pointing there instead of duplicating them
- Clarity module now mandatory: direct import replaces lazy-load, always active in every studio run
- `clarity.py` added to cross-repo install `SOURCE_FILES`
- New `empty_snapshot()` factory bootstraps clarity on first run

---

## 2026-03-22

### Added
- `/unstale` slash command: comprehensive staleness audit across docs, code comments, memory, cross-references
- `/studio-update` slash command: one-step update of installed Studio source and slash commands
- Agent metrics tracking: per-agent token/duration tracking via `record-metrics`/`show-metrics` CLI

### Fixed
- Decision points now surface per-agent in S1 (not batched at scope end)
- EAFP pattern in run_phase, eliminated double-write, added argparse choices validation

---

## 2026-03-20

### Fixed
- Iterative scoped debate now actually works: rejected roles loop correctly within scope budgets

---

## 2026-03-19

### Added
- Per-topic Clarity Score: adaptive question density based on answered decisions (M3)
- Project-local role customization via `.studio/roles/*.json` overlays (M4)
- Cross-repo install: `studio init` ships slash commands + source into any project (M5)
- Cleanup loose files: legacy artifacts outside run directories now cleaned up

### Fixed
- All decision points pause: per-agent, not per-scope; no more silent P1/P2 pass-through
- Corrupt manifest handling, documented lazy import patterns
- Codebase audit: dead code, stale docs, vestigial naming cleaned up
- `token_budget` → `scope_stats` rename completed across all docs

---

## 2026-03-18

### Added
- Question-surfacing mode (`--mode questions`): pre-flight decision collection before full runs
- Decision Point Protocol: P0/P1/P2 inline decision surfacing with orchestrator pause-and-ask (M1 + M2)
- Cross-repo install: `studio init` deploys slash commands + source (M5)

### Fixed
- Subagents now read instructions.md for Decision Point Protocol
- Parser matches both decision point format variants
- Inline Decision Point Protocol in agent prompts with dedup guard

---

## 2026-03-14

### Added
- Three-tier scoped debate: alignment → depth → polish with output budgets and debate modes
- Optimized studio debate: rolling briefs, scoped reads, collapsed S3 into single consolidated agent
- MVI (Minimum Viable Interaction) methodology: codified and enforced by Product, Engineering, and Design contrarians
- `test_engineer` role with AI-TDD methodology and auto-injection via manifest role dependencies

### Fixed
- Test integrity findings from studio self-evaluation
- Quality checks consolidated into single-pass loop

---

## 2026-03-07

### Added
- Claude Code integration: slash commands, run_phase.py as sole entrypoint
- Windsurf as peer variant (M5 migration complete)
- Cross-repo artifact routing with auto-scaffold (`.studio/output/`)
- Multi-model support

### Fixed
- Broken doc cross-references after Windsurf file moves
- Simplified cross-repo code

---

## 2026-03-01

### Added
- Budget-based artifact cleanup (900MB threshold)
- TTL-based cleanup (30-day retention)
- Storage management tooling

---

## 2026-02-28

### Fixed: Critical Reliability Improvements
- Concurrent-run protection: collision detection before directory creation prevents silent data corruption from simultaneous `prepare` commands
- File-size limit (1MB) for document validation: graceful failure with actionable messages instead of performance cliffs
- Added `tests/test_integration.py`: end-to-end workflow tests across scopes, rerun, validation

### Added: Clarity & Discoverability
- Actionable error messages with fix suggestions (scopes config, common issues)
- Contextual post-prepare / post-finalize hints suggesting next steps
- Interactive setup wizard for scopes configuration (later superseded by `setup.py`)
- Performance benchmarks (`tests/test_benchmarks.py`)

### Changed
- Repository restructured: modules moved under `studio/`
- Documentation alignment pass

---

## 2026-02-27: Concentric-Iteration Strategy

### Added
- **Scope-based iteration allocation**: TOML-configured (`.studio/scopes.toml`) proportional iteration budgets, sequential high→medium→low execution (~20-30% token savings)
- **Failure context injection** (`rerun.py`): automatic rerun detection, rejection-reason extraction, context injection into advocate prompts (role-aware for studio phase)
- **Phase-appropriate validation** (`validate` CLI): document validation (completeness, consistency, format, verdict) and code validation (pytest/mypy/ruff/black), config-driven via `.studio/validation.toml`

### Changed
- Scope-based iteration enabled by default when config exists; `--no-scopes` to disable
- No breaking changes: all features opt-in or with graceful fallbacks

---

## 2025-12-20 to 2025-12-28

### Added
- Initial Studio implementation: instruction generator for structured advocate/contrarian debates (originally CrewAI-based, later rewritten to stdlib-only)
- Four phases: market, design, tech, studio
- Role system with manifest-driven disciplines
- Windsurf/Cascade agent support
- Scoped iteration system

---

## Version Numbering

Studio follows [Semantic Versioning](https://semver.org/): **MAJOR** for breaking changes, **MINOR** for backward-compatible features, **PATCH** for backward-compatible fixes. Dated sections above predate strict version tagging.
