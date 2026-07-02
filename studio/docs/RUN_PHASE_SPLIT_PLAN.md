# Splitting `run_phase.py`: deferred decomposition plan

`run_phase.py` is the largest file in the repo. Two low-risk extractions have
already landed: `config_loading.py` (the shared TOML loader) and `stats.py` (the
pure cross-run aggregation/formatting). This document is the plan for the rest,
written so it can be executed later with all tests green at every step. It was
produced by a Fable 5 review pass; treat it as a guide, re-measure line numbers
before you start (they drift as the file changes).

## Current structure map

| Concern | Contents |
|---|---|
| imports + TOML fallback | now `config_loading.py` (done) |
| cleanup glue | `get_storage_stats` |
| constants | `PHASE_DETAILS`, `INDEX_HEADER`, env-var names, `SUBCOMMANDS` |
| path / root resolution | `_resolve_env_path`, `_is_within`, `get_studio_root`, `_entrypoint`, `_phase_from_run_id`, `set_artifact_root` + `_artifact_root_override` state, `_installed_repo_root`, `_find_installed_root_upwards`, `get_artifact_root`, `get_output_root`, `get_knowledge_log_path`, `get_outcomes_ledger_path`, `_project_name` |
| io + index | `utc_now`, `sanitize_cell`, `write_json`, `load_json`, `collect_runs`, `write_index` |
| finalize helpers | `_find_previous_run_dir`, `_is_same_objective`, `_norm_objective`, `_objective_changed`, `_ensure_summary_path`, `_validate_artifacts`, `_append_run_log` |
| instruction templating | `build_instruction_doc` (~400 lines) |
| prepare helpers | `_resolve_studio_roles`, `_resolve_scopes`, `_build_run_meta`, `_ensure_bridge_doc`, `_scaffold_external_repo` |
| run lifecycle | `prepare_run`, `finalize_run`, `_maybe_notify`, `rebuild_index` |
| CLI | `_normalize_*`, `parse_cli_args`, `_add_artifact_root_arg`, `build_parser` (~430 lines) |
| validate | `validate_run` |
| decisions | `record_decisions`, `_decision_to_dict`, `check_decisions`, `extract_decisions` |
| metrics/rating/stats I/O | `record_metrics`, `show_metrics`, `record_rating`, `show_stats`, outcome export/import (pure half now in `stats.py`) |
| context assembly | `inject_context` |
| thin command wrappers | `notify`, `show_clarity`, `set_clarity`, `recompute_clarity` |
| install/setup/offload dispatch | `_do_init`, `_do_check_install`, `_do_update`, `_do_setup`, `do_offload` |
| dispatch | `_dispatch`, `main` |

Key fact that makes this safe: **no production module imports `run_phase`** (only
tests do). So `run_phase` can re-export moved names and cycles are impossible
from the production side.

## Target modules (beyond config_loading + stats)

- **`paths.py`**: root resolution. Public: `get_studio_root`, `get_artifact_root`,
  `get_output_root`, `get_knowledge_log_path`, `get_outcomes_ledger_path`,
  `set_artifact_root`, `_project_name`, `ARTIFACT_ROOT_ENV`. Also lets `impl_loop.py`
  stop mirroring the artifact-root logic (follow-up, not part of the split).
- **`phases.py`**: `PHASE_DETAILS` + `_phase_from_run_id`. Tiny data module both
  the CLI and `build_instruction_doc` read, so keeping it separate breaks any
  instructions↔CLI cycle.
- **`instructions.py`**: `build_instruction_doc` + `inject_context` (same concern:
  assembling agent-facing markdown). Depends on `phases`, `paths`, `scopes`,
  `question_mode`, `rerun`, `decision_points`, `clarity`.
- **`run_index.py`**: `INDEX_HEADER`, `sanitize_cell`, `collect_runs`,
  `write_index`, `rebuild_index` (+ the small io helpers `utc_now`/`write_json`/
  `load_json`, or put those in `config_loading`).
- **`lifecycle.py`**: `prepare_run` + helpers, `finalize_run` + helpers,
  `validate_run`. ~900 lines; split into `prepare.py`/`finalize.py` if that feels
  heavy.
- **Stays in `run_phase.py`** (~700 lines): CLI wiring, cleanup glue, the thin
  command wrappers, and a backward-compat re-export block.

## Extraction order (each step independently green)

1. **`paths.py`**: leaf, no internal deps.
2. **`phases.py`**: pure data.
3. **`run_index.py`**: depends on paths only.
4. **`instructions.py`**: depends on paths + phases (do those first).
5. **`lifecycle.py`**: depends on everything above; last.

Run the full suite after each step (`cd studio && python -m pytest tests/ -q`);
667+ passing is the bar.

## Traps

- **Monkeypatch surface.** Tests patch `run_phase._artifact_root_override`
  directly and `run_phase.sys.stdin`. Once the override state lives in `paths.py`,
  patching the attribute on `run_phase` does nothing. Update those sites to patch
  `paths._artifact_root_override` (or call `run_phase.set_artifact_root(None)`,
  which delegates). This is the single most likely silent-failure point.
- **Re-exports are load-bearing.** Several test files do `from run_phase import
  <name>` for moved names. Keep an explicit re-export block; don't rely on `*`.
- **Artifact-root vs studio-root (PR #38).** Every project-local config read must
  use `get_artifact_root()` (the consuming repo), never `get_studio_root()` (the
  installed snapshot). Preserve the on-purpose branch comments in
  `get_artifact_root` verbatim; don't "simplify" the two roots into one.
- **Prompt/parse contract.** `build_instruction_doc` embeds copy-pasteable CLI
  hints and the decision-point blockquote format (now sourced from
  `decision_points.DECISION_BLOCK_EXAMPLE`). Those strings must move unchanged.
- **Mutable module state.** `_artifact_root_override` and `_artifact_root_warned`
  must each live in exactly one module after the move.
