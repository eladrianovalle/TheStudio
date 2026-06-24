# Changelog

All notable changes to TheGameStudio are documented here.

---

## [Unreleased]

### Added
- Contrarian editor mandate (always on) — every deliverable run's contrarian now carries a built-in bias toward removal, merge, and simplification on top of flaw-hunting. The advocate piles it on; the contrarian carves out the essence. Shared `CONTRARIAN_MANDATE` injected across single-phase, flat, and scoped studio prompts; phase contrarians reframed as editors. Off in `--mode questions` (there the contrarian judges question relevance, never cuts genuinely-open questions)
- Open-Questions Pre-Flight (Step 0) — every deliverable run opens by surfacing what is genuinely unsettled, pausing on P0 blockers, and recording answers before the iteration loop, so no run silently assumes; later passes keep raising new questions as they surface. Reuses existing decision/clarity machinery
- Project-overridable single-phase personas via `.studio/personas.toml` — `persona_overrides.py` per-phase shallow-merges advocate/contrarian/notes/implementer/integrator overrides over the shipped `PHASE_DETAILS` defaults; setup wizard gains a `persona_customization` step (`CURRENT_SETUP_VERSION` 2) that authors the file and can sniff the project stack (`Cargo.toml`/`package.json`/`*.csproj`) to suggest a fitting persona
- `/offload` slash command — analyzes CLAUDE.md for content safe to move to companion docs, with section classification, pointer strength scoring, canary token verification, and reconciliation against existing docs (`offload.py`, 23 tests)
- `/detest` slash command — audits test suites against AI-TDD methodology, finds anti-patterns, fixes them
- `/unstale` Agent 5 — project tracking audit (GitHub Issues + local tracking files) with permission-gated destructive actions
- Stack-agnostic `/unstale` — the command now self-detects the project stack (Rust/Unity/Node/Python/Go) from marker files instead of assuming the Studio Python layout, so it works in any installed repo. Optional per-repo `.studio/unstale.toml` override pins exact snapshot commands and audit globs; authored by a new setup wizard `unstale_config` step (`CURRENT_SETUP_VERSION` 3) via `suggest_unstale_from_stack`
- `ai_engineer` role in manifest — Staff AI Engineer specializing in prompt architecture & agent optimization
- `/studio-setup` slash command + `setup` CLI subcommand — post-install wizard for role pack selection, role customization, scope tuning, and cleanup settings with incremental versioned steps (`setup.py`, 43 tests)
- `docs/CODING_PRINCIPLES.md` — standalone Karpathy-inspired principles file, shipped with cross-repo installs
- Cross-repo install now injects coding principles into target's `CLAUDE.md` via sentinel markers (`<!-- STUDIO:CODING_PRINCIPLES:BEGIN/END -->`), with idempotent update support (6 tests)

### Fixed
- Stack-neutral phase personas — removed the hardcoded "Three.js Technical Architect / WebGL" tech persona and "Steam hook" market wording from `PHASE_DETAILS` so runs in any codebase (Rust, Unity, etc.) get a fitting default
- Clarity reset is now phase-independent — the fresh-run check compares the current objective against the one stored in the project-level `clarity.json`, so a prior objective under one phase no longer leaks stale topics into a new objective under another phase. A corrupt/unparseable `clarity.json` is now treated as absent (self-heals) instead of crashing `prepare`
- Rerun context injection is gated on a phase-local objective match, so a project-wide same-objective decision can't pull rejection feedback from an unrelated previous run
- `persona_overrides.py` added to cross-repo install `SOURCE_FILES` (was missing — would `ImportError` on target installs)
- `inject-context` now resolves custom scope names via canonical positional aliases (alignment→0, depth→1, polish→2)
- `prepare` now resets stale clarity and skips rerun context when the new run has a different objective than the previous one — prevents orchestrator agents from inheriting irrelevant topic scores and rejection feedback
- `_resolve_scopes` now falls back to shipped `config/scopes.toml` when no `.studio/scopes.toml` override exists — scoped runs work out of the box

### Added
- Karpathy AI principles integrated into agent instructions — Think-Before-Coding (alignment scope), Simplicity-First, Surgical-Changes (depth/polish scopes), Goal-Driven-Execution with verification checkpoints. Think-First Checkpoint requires advocates to state their understanding before analysis; contrarians verify framing before critiquing content.
- `No Merge Conflicts` CI workflow (`.github/workflows/no-merge-conflicts.yml`) to satisfy branch ruleset

### Changed
- Clarity module now mandatory — direct import replaces lazy-load, always active in every studio run
- `clarity.py` added to cross-repo install `SOURCE_FILES`
- New `empty_snapshot()` factory bootstraps clarity on first run

---

## 2026-03-22

### Added
- `/unstale` slash command — comprehensive staleness audit across docs, code comments, memory, cross-references
- `/studio-update` slash command — one-step update of installed Studio source and slash commands
- Agent metrics tracking — per-agent token/duration tracking via `record-metrics`/`show-metrics` CLI

### Fixed
- Decision points now surface per-agent in S1 (not batched at scope end)
- EAFP pattern in run_phase, eliminated double-write, added argparse choices validation

---

## 2026-03-20

### Fixed
- Iterative scoped debate now actually works — rejected roles loop correctly within scope budgets

---

## 2026-03-19

### Added
- Per-topic Clarity Score — adaptive question density based on answered decisions (M3)
- Project-local role customization via `.studio/roles/*.json` overlays (M4)
- Cross-repo install — `studio init` ships slash commands + source into any project (M5)
- Cleanup loose files — legacy artifacts outside run directories now cleaned up

### Fixed
- All decision points pause — per-agent, not per-scope; no more silent P1/P2 pass-through
- Corrupt manifest handling, documented lazy import patterns
- Codebase audit — dead code, stale docs, vestigial naming cleaned up
- `token_budget` → `scope_stats` rename completed across all docs

---

## 2026-03-18

### Added
- Question-surfacing mode (`--mode questions`) — pre-flight decision collection before full runs
- Decision Point Protocol — P0/P1/P2 inline decision surfacing with orchestrator pause-and-ask (M1 + M2)
- Cross-repo install — `studio init` deploys slash commands + source (M5)

### Fixed
- Subagents now read instructions.md for Decision Point Protocol
- Parser matches both decision point format variants
- Inline Decision Point Protocol in agent prompts with dedup guard

---

## 2026-03-14

### Added
- Three-tier scoped debate — alignment → depth → polish with output budgets and debate modes
- Optimized studio debate — rolling briefs, scoped reads, collapsed S3 into single consolidated agent
- MVI (Minimum Viable Interaction) methodology — codified and enforced by Product, Engineering, and Design contrarians
- `test_engineer` role with AI-TDD methodology and auto-injection via manifest role dependencies

### Fixed
- Test integrity findings from studio self-evaluation
- Quality checks consolidated into single-pass loop

---

## 2026-03-07

### Added
- Claude Code integration — slash commands, run_phase.py as sole entrypoint
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

## 2026-02-27 — 2026-02-28

### Changed
- Repository restructured — modules moved under `studio/`
- Documentation alignment pass

---

## 2025-12-20 — 2025-12-28

### Added
- Initial Studio implementation — instruction generator for structured advocate/contrarian debates
- Four phases: market, design, tech, studio
- Role system with manifest-driven disciplines
- Windsurf/Cascade agent support
- Scoped iteration system
