# Studio Migration Plan

Status: **In Progress — Milestone 5 (Windsurf as Peer Variant)**

## Goal
Create a shared-core Studio with Claude Code and Windsurf as equal execution peers. Fix bugs, remove dead weight, build test foundation, then implement Claude Code native execution.

## Milestones

### M0: Stabilize (bugs + dead weight removal) — COMPLETE
- [x] T0.1 Fix division-by-zero in budget status display (removed budget commands entirely)
- [x] T0.2 Fix `collect_runs` crash on corrupted run.json (added try/except)
- [x] T0.3 Fix `write_index`/`_append_run_log` crash on missing keys (switched to .get())
- [x] T0.4 Fix rerun detection (now checks previous run dir via `_find_previous_run_dir`)
- [x] T0.5 Fix lexicographic sort of contrarian files (numeric sort via `_parse_iter_number`)
- [x] T0.6 Add tomllib fallback for Python 3.10 (try/except import with tomli)
- [x] T0.7 Delete `src/studio/` — extracted `verdict.py` to `studio/verdict.py`
- [x] T0.8 Delete `studio_cli.py`
- [x] T0.9 Delete token tracker (`token_tracker.py`, `analyze_tokens.py`, related docs)
- [x] T0.10 Remove budget tracker from `run_phase.py` (deleted `studio_budget_tracker.py`, removed all budget subcommands and integration)
- [x] T0.11 Remove dead code (redundant imports, token metadata, double-break logic)
- [x] T0.12 Remove `inject_context_into_prompt` from `rerun.py` + tests
- [x] T0.13 Replace custom TOML parser in `cleanup.py` with tomllib
- [x] T0.14 Delete stale docs (QUICKSTART, SHOESTRING_PRESET, CLUTTER_MANAGEMENT_PLAN, V2_1_IMPROVEMENTS, TOKEN_TRACKING, TOKEN_TRACKING_SUMMARY)
- [x] T0.15 Clean INDEX.md (complete rewrite, removed all CrewAI/Gemini refs)
- [x] T0.16 Fix doc contradictions (scopes auto-load, tech artifacts, "no CLI" claim, Cascade-only branding, stale artifact links)
- [x] T0.17 Consolidate redundant doc content (assistant-agnostic language, removed duplicate cleanup/workflow sections, fixed artifact tables)

### M1: Test Foundation — COMPLETE
- [x] T1.1 Create `tests/conftest.py` with shared fixtures
- [x] T1.2 Unit tests for `run_phase_roles.py` (35 tests)
- [x] T1.3 Unit tests for rerun critical paths (3 studio-phase tests added)
- [x] T1.4 Fix placeholder tests (refactored to shared fixtures)
- [x] T1.5 E2E test (CLI subprocess, 6 tests)
- [x] T1.6 Remove/relax flaky benchmark assertions (test file deleted with budget tracker)
- [x] T1.7 Validator blind spot tests (5 tests added)
- **Result: 127 tests passing**

### M2: Extract Shared Core — COMPLETE
- [x] T2.1 Extract `parse_verdict()` utility (already done as `verdict.py` in M0)
- [x] T2.2 Make instruction generation backend-agnostic (removed "Cascade" from titles, docstrings, parser)
- [x] T2.3 Refactor `prepare_run` into composable functions (`_resolve_studio_roles`, `_resolve_scopes`, `_build_run_meta`)
- [x] T2.4 Define execution interface contracts (`execution_contract.py` with `RunContext`, `RunArtifacts`, lifecycle docs)
- **Result: 132 tests passing**

### M3: Claude Code MVP (single-phase) — COMPLETE
- [x] T3.1 Create `.claude/commands/run-phase.md` (slash command with $ARGUMENTS)
- [x] T3.2 Agent-based advocate/contrarian separation (separate Agent invocations documented in command)
- [x] T3.3 Create `docs/CLAUDE_CODE_USAGE.md` (usage guide with flow diagrams)
- [x] T3.4 Update CLAUDE.md (added /run-phase section, reorganized commands)
- [x] T3.5 Test market + tech phases end-to-end (9 tests: slash command validation, market E2E, tech E2E, rerun flow)
- **Result: 141 tests passing**

### M4: Multi-role Studio Phase — COMPLETE
- [x] T4.1 Create `.claude/commands/run-studio-phase.md` (slash command with per-role agent instructions)
- [x] T4.2 Sequential role processing with agent spawning (command documents role-by-role flow)
- [x] T4.3 Integrator duel via separate agents (Integrator Advocate + Contrarian as separate Agent calls)
- [x] T4.4 Test full studio phase with studio_core pack (11 tests: command validation, role menu, full workflow, integrator duel)
- **Result: 152 tests passing**

### M5: Windsurf as Peer Variant
- [ ] T5.1 Move Windsurf docs into `docs/windsurf/`
- [ ] T5.2 Agent-neutral README
- [ ] T5.3 Configurable assistant name in instruction generation
- [ ] T5.4 Agent-agnostic bridge template
