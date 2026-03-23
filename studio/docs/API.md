# API Reference (run_phase.py)

Studio exposes exactly one supported interface: `run_phase.py`. This script prepares instructions, validates artifacts, and keeps indexes/logs up to date so runs stay reproducible across any AI assistant (Claude Code, Windsurf/Cascade, etc.). This document describes the command-line contract, JSON schema, and file formats you can rely on when integrating Studio into other repositories or tooling.

---

## 1. Commands

```bash
python /path/to/studio/run_phase.py <command> [options]
```

Supported commands:

| Command | Description |
| --- | --- |
| `prepare` | Creates a new run directory, instructions.md, and updates the active output index. |
| `finalize` | Validates artifacts, updates `run.json`, refreshes the active index, and appends to the active run log. |
| `cleanup` | Manually enforces run retention budgets (age + total size). |
| `validate` | Runs validators for a prepared/finalized run using validation config. |
| `record-decisions` | Records answered decisions into a run's `decisions.json`. |
| `check-decisions` | Parses decision points from a single agent output file. |
| `extract-decisions` | Extracts decision points from all agent files in a run directory. |
| `inject-context` | Generates the context block for the next agent in a scoped run. |
| `show-clarity` | Displays current project clarity scores. |
| `set-clarity` | Overrides a topic's clarity score. |
| `recompute-clarity` | Recomputes clarity from a run's decisions. |
| `record-metrics` | Records token usage for a single agent invocation into `metrics.json`. |
| `show-metrics` | Displays aggregated agent token usage for a run (by scope, role, per-agent). |
| `init` | Installs Studio into a target project directory. |
| `check-install` | Checks if installed Studio is up to date. |
| `update` | Updates installed Studio from source. |

---

### 1.1 `prepare` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--phase {market,design,tech,studio}` | ✅ | – | Studio phase to run. Controls artifact checklist and instruction copy. |
| `--text "..."` | ✅ | – | Idea, objective, or question you want Studio to tackle. |
| `--max-iterations N` | ❌ | `3` | How many Advocate↔Contrarian loops the assistant should run before stopping. |
| `--budget "$0-20/mo"` | ❌ | `$0-20/mo` | Advisory note printed in instructions (not enforced). Primarily used by `studio` phase. |
| `--role-pack PACK` | ❌ | Manifest default | Studio-only: selects a curated pod from `role_packs/`. |
| `--roles [+role|-role ...]` | ❌ | `None` | Studio-only: include/exclude roles relative to the selected pack. Supports `--roles +product +engineering +qa` and repeated flags (`--roles=+product --roles=+engineering --roles=+qa`). Use `-role` only when you explicitly need to remove a role. |
| `--scopes PATH` | ❌ | `.studio/scopes.toml` if present | Optional scopes config for iteration budget allocation. |
| `--no-scopes` | ❌ | `False` | Disable scope-based allocation for this run. |
| `--skip-cleanup` | ❌ | `False` | Skip automatic retention cleanup before preparing the run. |
| `--cleanup-dry-run` | ❌ | `False` | Preview cleanup candidates without deleting files. |

**Output files (under the active output root):**
- Studio-local execution: `<studio>/output/<phase>/run_<phase>_<timestamp>/`
- External-repo execution: `<origin_repo>/.studio/output/<phase>/run_<phase>_<timestamp>/`

Inside each run directory:
- `instructions.md`
- `run.json` (see schema below)
- Empty placeholders for artifacts:
  - Non-studio phases → `advocate_<n>.md`, `contrarian_<n>.md`, `summary.md` (plus `implementation.md` for tech phase)
  - Studio phase → `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md`, `integrator.md`, `summary.md`

`prepare` also regenerates `<active_output_root>/index.md` so downstream repos can discover pending runs immediately.

---

### 1.2 `finalize` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--phase {market,design,tech,studio}` | ✅ | – | Phase associated with the run. |
| `--run-id run_<phase>_<timestamp>` | ✅ | – | Identifier printed by `prepare`. |
| `--status STATUS` | ❌ | `COMPLETED` | Free-form label (“completed”, “abandoned”, etc.). |
| `--verdict VERDICT` | ❌ | – | `APPROVED`, `REJECTED`, `N/A`, or any label you prefer. |
| `--iterations-run N` | ❌ | auto-count | Override if the assistant ran extra loops or skipped iterations. |
| `--hours FLOAT` | ❌ | `None` | Time spent; stored in `run.json` + `run_log.md`. |
| `--cost FLOAT` | ❌ | `None` | Monetary cost in USD (typically `0`). |
| `--summary PATH` | ❌ | auto-detected | Provide a custom summary path if you store it elsewhere. |

`finalize` enforces the artifact checklist (see Section 3). Missing files raise a `FileNotFoundError` describing the gaps.

---

### 1.3 `record-metrics` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--run-dir PATH` | Yes | – | Path to the run directory. |
| `--agent {advocate,contrarian,integrator,polish}` | Yes | – | Agent type being recorded. |
| `--total-tokens N` | Yes | – | Total tokens consumed by the agent. |
| `--tool-uses N` | No | `0` | Number of tool uses. |
| `--duration-ms N` | No | `0` | Wall-clock duration in milliseconds. |
| `--role NAME` | No | `None` | Role name (for studio phase). |
| `--scope {alignment,depth,polish,flat}` | No | `None` | Scope the agent ran in. |

Appends an entry to `{run_dir}/metrics.json`. Called by the orchestrator after each Agent tool returns, using values from the `<usage>` block in the tool result.

---

### 1.4 `show-metrics` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--run-dir PATH` | Yes | – | Path to the run directory. |

Displays a formatted summary of all recorded metrics: total tokens, tool uses, duration, breakdowns by scope and role, and per-agent detail.

---

## 2. Environment Variables

| Variable | Description |
| --- | --- |
| `STUDIO_ROOT` | Optional override pointing to the Studio repo. If unset, `run_phase.py` uses its own directory. |
| `STUDIO_ARTIFACT_ROOT` | Optional override for where artifacts/logs are written. If unset, Studio writes to repo-local `.studio/` when run outside Studio, otherwise Studio root `output/` + `knowledge/`. |
| `STUDIO_SKIP_CLEANUP` | Optional flag (`1/true/yes/on`) to skip automatic cleanup before `prepare`. |
| `STUDIO_CLEANUP_DRY_RUN` | Optional flag (`1/true/yes/on`) to preview cleanup deletions without removing files. |

Set it once to avoid hard-coding absolute paths in other repos:

```bash
export STUDIO_ROOT="/path/to/studio"
python $STUDIO_ROOT/run_phase.py prepare --phase market --text "..."
```

Pin artifact location explicitly when running from shared environments:

```bash
export STUDIO_ARTIFACT_ROOT="/absolute/path/to/target/repo"
python $STUDIO_ROOT/run_phase.py prepare --phase studio --text "..."
```

No API keys or third-party credentials are required.

---

## 3. Artifact Checklist

| Phase | Required files |
| --- | --- |
| `market`, `design` | `advocate_<n>.md`, `contrarian_<n>.md`, `summary.md` |
| `tech` | `advocate_<n>.md`, `contrarian_<n>.md`, `summary.md`, `implementation.md` (with tests) |
| `studio` | `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md`, `integrator.md` (with duel sections), `summary.md` |

`finalize` ensures these files exist inside the run directory. You can add extra context (screenshots, spreadsheets, etc.) so long as they live in the same folder.

---

## 4. `run.json` Schema

Every run directory contains a `run.json` created by `prepare` and updated by `finalize`.

| Field | Type | Description |
| --- | --- | --- |
| `run_id` | string | `run_<phase>_<timestamp>` identifier. |
| `phase` | string | `market`, `design`, `tech`, or `studio`. |
| `input` | string | Text supplied via `--text`. |
| `budget_cap` | string | Only meaningful for `studio` phase. Empty otherwise. |
| `max_iterations` | int | Copied from `--max-iterations`. |
| `created_iso` | string | UTC timestamp (`YYYY-MM-DDTHH:MM:SS`). |
| `created_display` | string | Human-readable timestamp (`YYYY-MM-DD HH:MM`). |
| `status` | string | `PENDING` until finalized. |
| `summary_path` | string | Absolute path to `summary.md`. Auto-filled if blank. |
| `verdict` | string | Populated during finalize. |
| `iterations_run` | int or null | Auto-counted from artifacts unless overridden. |
| `hours` | float or null | Optional metadata set by finalize. |
| `cost` | float or null | Optional metadata set by finalize. |
| `output_type` | string | `"deliverables"` or `"questions"` (from `--mode`). |
| `studio_roles` | object or null | Studio-only metadata: `{ "pack": str, "overrides": list[str], "invited": list[str], "completed": list[str], "missing": list[str] }`. |
| `scopes` | object or null | Scope config snapshot: `{ "config_path": str, "scopes": [...], "total_iterations": int }`. |
| `storage` | object | Storage stats at prepare time: `{ "total_size_mb": float, "file_count": int, "oldest_artifact_days": float, "cleanup_suggested": bool }`. |
| `updated_iso` | string (optional) | Added by finalize to record the last change timestamp. |
| `scope_stats` | object or null | Per-scope output stats from finalize: `{ "<scope>": { "files": int, "total_chars": int, "total_words": int, "avg_words": int } }`. |
| `quality` | object or null | Quality check results from finalize: `{ "checks_run": int, "warnings": list[str], "errors": list[str] }`. |
| `metrics` | object or null | Agent token usage aggregated from `metrics.json` at finalize: `{ "agents": int, "total_tokens": int, "total_duration_ms": int, "total_tool_uses": int, "by_scope": { ... }, "by_role": { ... } }`. |

You can safely parse this JSON for dashboards, scripts, or audits.

---

## 5. `instructions.md` Structure

Generated instructions follow a consistent layout:

1. **Header** — phase, run directory, input text, iteration cap, creation timestamp, budget, and (for Studio) role pack + overrides.
2. **Artifacts list** — file destinations. Studio instructions highlight per-role filenames.
3. **Agent Roles** — Advocate, Contrarian, Implementer (non-studio) or Integrator (studio).
4. **Iteration Loop** — numbered steps for Advocate/Contrarian exchanges. Studio loop points to the Integrator duel hand-off after approval.
5. **Role Menu** (Studio only) — table describing each invited role, deliverables, file naming, and links to `docs/role_prompts/*.md`.
6. **Integrator Duel** (Studio only) — explains `### Integrator Advocate`, `### Integrator Contrarian (VERDICT)`, and `### Integrated Plan` sections inside `integrator.md`.
7. **Summary & Packaging** — reminders to fill out `summary.md` and run the finalize command.

The assistant should read this file to know where to save each artifact.

---

## 6. Active `index.md`

Markdown table of every run. Columns:

| Column | Meaning |
| --- | --- |
| `Run ID` | Hyperlinks back to the run folder via relative paths. |
| `Phase` | Same as `run.json["phase"]`. |
| `Created (UTC)` | Value from `created_display`. |
| `Status` | `PENDING`, `COMPLETED`, etc. |
| `Input` | Sanitized version of the `--text` argument. |
| `Summary` | Auto-linked if `summary_path` exists, otherwise `_pending_`. |

Path depends on artifact root:
- Studio-local: `<studio>/output/index.md`
- External-repo: `<repo>/.studio/output/index.md`

Any automation that needs to list past runs should read this file or regenerate it by calling `run_phase.rebuild_index()`.

---

## 7. Active `run_log.md`

Append-only markdown log created by finalize. Each entry looks like:

```
## run_market_20251223_170045 (market) – COMPLETED
- Created: 2025-12-23 17:00
- Verdict: APPROVED
- Iterations: 2
- Hours: 0.8 | Cost: 0
- Summary: [summary](/absolute/path/to/summary.md)
```

Use it to brief stakeholders or link into downstream repos’ release notes.

Path depends on artifact root:
- Studio-local: `<studio>/knowledge/run_log.md`
- External-repo: `<repo>/.studio/knowledge/run_log.md`

---

## 8. Programmatic Usage (Optional)

While the CLI is the supported interface, you can import `run_phase.py` if you need tighter automation:

```python
import importlib.util
from pathlib import Path

script = Path(os.environ.get('STUDIO_ROOT', '/path/to/studio') + "/run_phase.py")
spec = importlib.util.spec_from_file_location("run_phase", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

run_id = module.prepare_run(module.SimpleNamespace(
    phase="market",
    text="Describe the idea",
    budget="$0-20/mo",
    max_iterations=3,
))

module.finalize_run(module.SimpleNamespace(
    phase="market",
    run_id=run_id,
    status="COMPLETED",
    summary=None,
    verdict="APPROVED",
    iterations_run=None,
    hours=0.5,
    cost=0,
))
```

Stick to the CLI whenever possible so scripts remain simple and any assistant can quote the same commands your teammates run manually.

---

## 9. Related Documents

- [README.md](../../README.md) – big-picture overview and testing notes.
- [CLAUDE_CODE_USAGE.md](./CLAUDE_CODE_USAGE.md) – Claude Code slash commands and workflow.
- [windsurf/USAGE.md](./windsurf/USAGE.md) – Windsurf/Cascade-specific workflow.
- [STUDIO_BRIDGE_TEMPLATE.md](./STUDIO_BRIDGE_TEMPLATE.md) – copy into every dependent repo.
- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) – repo-level onboarding checklist and helper scripts.

These docs, together with `run_phase.py`, define the entire Studio API surface.
