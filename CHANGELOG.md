# Changelog

All notable changes to TheGameStudio are documented here.

---

## [Unreleased]

### Added
- `/offload` slash command — analyzes CLAUDE.md for content safe to move to companion docs, with section classification, pointer strength scoring, canary token verification, and reconciliation against existing docs (`offload.py`, 23 tests)
- `/detest` slash command — audits test suites against AI-TDD methodology, finds anti-patterns, fixes them
- `/unstale` Agent 5 — project tracking audit (GitHub Issues + local tracking files) with permission-gated destructive actions
- `ai_engineer` role in manifest — Staff AI Engineer specializing in prompt architecture & agent optimization

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
