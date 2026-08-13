# API Reference (run_phase.py)

Studio exposes exactly one supported interface: `run_phase.py`. This script prepares instructions, validates artifacts, and keeps indexes/logs up to date so runs stay reproducible (Claude Code is the supported assistant path). This document describes the command-line contract, JSON schema, and file formats you can rely on when integrating Studio into other repositories or tooling.

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
| `stats` | Cross-run diagnostics dashboard: shipped features read from spec frontmatter, verdict/approval rate, decision priority mix + answer rate, session health, and prepare-usage counts. Supports `--phase`, `--json`, `--artifact-root`. |
| `offload` | Analyzes CLAUDE.md for content safe to offload to companion docs. Classifies sections, scores pointer strength, generates reports. |
| `init` | Installs Studio into a target project directory. Also installs a per-user SessionStart hook (in `.claude/settings.local.json`) that quietly checks, once per session, whether your installed Studio is behind upstream and nudges you to run `/studio-update`. Pass `--no-hook` to skip installing it. |
| `check-updates` | The lightweight check the SessionStart hook runs (you rarely call it by hand). Compares the commit your Studio was installed from against the source's current `origin/main` HEAD; if they differ, it prints a one-line "an update is available" nudge, otherwise it's silent. Network is a bounded, best-effort `git fetch` at most once per 24h (cached in `.studio/update-check.json`), so it's near-instant on repeat sessions and safe offline. It nudges once per new upstream commit, never changes files, and always exits 0 (a session-start hook must never fail your session). Opt out durably by creating an empty `.studio/update-check.off` file. Only works on the machine that ran `studio init` (the one with the Studio source); a teammate who merely cloned the repo gets a silent no-op. |
| `check-install` | Checks whether the installed Studio is up to date, and shows any files you've edited locally that an `update` would overwrite: both the Studio source and the installed slash commands and workflows. Also guards against a stale *source*: it does a quick, best-effort `git fetch` of the Studio source and, if the source's own checkout is behind its remote (`origin/main`), refuses to report "up to date" (exits non-zero) and compares against `origin/main` instead — so "up to date" can't silently mean "up to date with an out-of-date source." Pass `--no-fetch` to skip the network and compare against already-fetched refs. |
| `update` | Updates the installed Studio from source. If you've edited any installed file locally, it stops instead of overwriting your work; pass `--force` to overwrite anyway. This covers the Studio source as well as the installed slash commands and workflows. If the Studio *source* is behind its own remote, `update` won't falsely no-op: it reinstalls from `origin/main` and reminds you to run `git -C <source> pull` to catch your source up. By default it never pulls your source for you — but you can opt in: pass `--pull-source` (or set `[update] auto_pull_source = true` in the *source* repo's `.studio/update.toml`, once, to cover every consumer on that machine) and `update` will fast-forward your source checkout itself when it's cleanly behind, so the nag stops recurring. The pull is strictly safe — fast-forward only, and only when the source is clean, on its default branch, and simply behind (never a merge, force, or a dirty/diverged/feature-branch checkout; any of those falls back to the reinstall-from-origin + manual-pull hint). `--no-fetch` skips that source-staleness network check. It also refreshes the SessionStart update-check hook (pass `--no-hook` to remove it instead). |
| `setup` | Configure Studio for a project: role pack selection, role + phase-persona customization (`.studio/personas.toml`), unstale audit config (`.studio/unstale.toml`), smoke profile (`.studio/smoke.toml`), cleanup settings. Supports `--target`, `--status`, `--defaults`, `--answers`, `--role-pack`, `--roles`. |
| `notify` | Posts a run digest to enabled Slack/n8n webhooks (config in `.studio/integrations.toml`). Auto-fires on `finalize` when a target is enabled (soft-fail). Supports `--run-dir`, `--dry-run`, `--artifact-root`. |

---

### 1.1 `prepare` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--phase {market,design,tech,studio}` | ✅ | - | Studio phase to run. Controls artifact checklist and instruction copy. |
| `--text "..."` | ✅ | - | Idea, objective, or question you want Studio to tackle. |
| `--max-iterations N` | ❌ | `3` | How many Advocate↔Contrarian loops the assistant should run before stopping. |
| `--budget "$0-20/mo"` | ❌ | `$0-20/mo` | Advisory note printed in instructions (not enforced). Primarily used by `studio` phase. |
| `--role-pack PACK` | ❌ | Manifest default | Studio-only: selects a curated pod from `role_packs/`. |
| `--roles [+role|-role ...]` | ❌ | `None` | Studio-only: include/exclude roles relative to the selected pack. Supports `--roles +product +engineering +qa` and repeated flags (`--roles=+product --roles=+engineering --roles=+qa`). Use `-role` only when you explicitly need to remove a role. |
| `--scopes PATH` | ❌ | `.studio/scopes.toml` if present | Optional scopes config for iteration budget allocation. |
| `--no-scopes` | ❌ | `False` | Disable scope-based allocation for this run. |
| `--skip-cleanup` | ❌ | `False` | Skip automatic retention cleanup before preparing the run. |
| `--mode` | ❌ | `deliverables` | Output mode: `deliverables` (default) produces specs; `questions` surfaces open questions. |
| `--artifact-root` | ❌ | None | Override where artifacts are written. Defaults to cwd (external repo) or Studio root. |
| `--cleanup-dry-run` | ❌ | `False` | Preview cleanup candidates without deleting files. |
| `--json` | ❌ | `False` | Emit a machine-readable `{run_id, run_dir, instructions, phase, ...}` object as the final line of stdout, instead of the prose summary and tips. |

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
| `--phase {market,design,tech,studio}` | ❌ | derived from `--run-id` | Phase associated with the run. Redundant with `--run-id`, which already encodes it, so it's optional. |
| `--run-id run_<phase>_<timestamp>` | ✅ | - | Identifier printed by `prepare`. |
| `--status STATUS` | ❌ | `COMPLETED` | Free-form label (“completed”, “abandoned”, etc.). |
| `--verdict VERDICT` | ❌ | - | `APPROVED`, `REJECTED`, `N/A`, or any label you prefer. |
| `--iterations-run N` | ❌ | auto-count | Override if the assistant ran extra loops or skipped iterations. |
| `--summary PATH` | ❌ | auto-detected | Provide a custom summary path if you store it elsewhere. |
| `--artifact-root` | ❌ | None | Override where artifacts are written. Defaults to cwd (external repo) or Studio root. |

`finalize` enforces the artifact checklist (see Section 3). Missing files raise a `FileNotFoundError` describing the gaps. It asks you for nothing: there is no rating prompt and no nudge, at a terminal or anywhere else.

`finalize` writes `session.json` into the run directory — the automatic, judgment-free session-health record (schema in Section 4.1) — soft-fail, so a failure there prints a warning but never breaks finalize.

The `[outcomes] ledger_path` key that used to make `finalize` append an outcome record to a local JSONL ledger is **gone**, along with the `rate`, `export-outcomes`, and `import-outcomes` commands. Outcome data now comes from the `shipped_impact` / `shipped_changed` lines in a spec's frontmatter, which `stats` reads directly. A leftover `[outcomes]` table in `.studio/integrations.toml` is ignored; existing `rating.json` and `outcomes.jsonl` files are simply no longer read.

---

### 1.3 `stats` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--phase {market,design,tech,studio}` | No | `None` | Filter the dashboard to a single phase. |
| `--json` | No | `false` | Emit the aggregated stats dict as JSON instead of the text dashboard. |
| `--artifact-root PATH` | No | auto | Override artifact root (where `output/` and `.studio/usage.log` live). |

Reads every run's `run.json`, `session.json`, and `decisions.json` under the output root, plus `.studio/usage.log` and the specs directory, and aggregates: total/by-phase/by-status run counts, verdict distribution + approval rate, decision priority mix + answer rate, session health, and prepare-usage counts. Pure aggregation and formatting live in `stats.py` (`aggregate_stats()`, `format_stats()`, `summarize_shipped_specs()`).

The dashboard's **"Shipped features (from specs/)"** block counts the specs whose frontmatter says `status: shipped`, tallies their `shipped_impact` (`none`/`minor`/`major`), and lists the most recent eight `shipped_changed` lines. The specs directory is `specs/` in the Studio repo and `.studio/specs/` in a repo that installed Studio (`run_phase.get_specs_dir()`); `*-eval-results.md` files are skipped. Nothing here is typed into a command — a feature appears the moment someone flips its spec to `shipped`, which the spec-verification test refuses unless both lines are filled in.

A repo with no spec at `shipped` prints the one-line empty state instead (`No shipped features recorded yet …`). With `--json`, the emitted dict gains a `shipped_specs` key holding the same summary (`records`, the `impact` tally, and `recent_changed`).

The dashboard also renders a **"Session health"** block, computed from each run's `session.json` (see Section 4.1) by `stats.summarize_session_health`. It reports three auto-measured signals over the finalized sessions on record: assumed-P0 rate (P0s guessed instead of asked), convergence (median iterations + rejection rate), and clarity gain per session. With enough sessions it splits earlier vs. recent to show the trend. With `--json`, the emitted dict gains a `session_health` key holding this summary.

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
| `studio` | `integrator.md` (with duel sections), `summary.md`, plus per-role agent files. In the default scoped mode those are `advocate--<role>--S1-<nn>.md` / `S2-` / `S3-` (alignment / depth / polish) and the matching `contrarian--` files; with `--no-scopes` they are `advocate--<role>--<n>.md` and `contrarian--<role>--<n>.md`. |

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
| `output_type` | string | `"deliverables"` or `"questions"` (from `--mode`). |
| `studio_roles` | object or null | Studio-only metadata: `{ "pack": str, "overrides": list[str], "invited": list[str], "completed": list[str], "missing": list[str] }`. |
| `scopes` | object or null | Scope config snapshot: `{ "config_path": str, "scopes": [...], "total_iterations": int }`. |
| `storage` | object | Storage stats at prepare time: `{ "total_size_mb": float, "file_count": int, "oldest_artifact_days": float, "cleanup_suggested": bool }`. |
| `updated_iso` | string (optional) | Added by finalize to record the last change timestamp. |
| `scope_stats` | object or null | Per-scope output stats from finalize: `{ "<scope>": { "files": int, "total_chars": int, "total_words": int, "avg_words": int } }`. |
| `quality` | object or null | Quality check results from finalize: `{ "checks_run": int, "warnings": list[str], "errors": list[str] }`. |

You can safely parse this JSON for dashboards, scripts, or audits.

---

### 4.1 `session.json` Schema

`finalize` also writes a `session.json` into each run directory: an automatic, judgment-free **session-health** record. A Studio run is a planning session whose specs get built later, so its quality can't be judged at finalize; what *can* be measured is whether the debate converged, surfaced and settled the right questions, and reduced uncertainty. Every field is derived from files the run already produced (no human input). The record is built by `session.build_session_record` and written soft-fail, so a failure here never breaks finalize.

| Field | Type | Description |
| --- | --- | --- |
| `run_id` | string | Run identifier. |
| `repo` | string | Project name the run belongs to. |
| `phase` | string | `market`, `design`, `tech`, or `studio`. |
| `mode` | string | `deliverables` or `questions`. |
| `finalized_iso` | string | UTC timestamp of finalize. |
| `verdict` | string | Final verdict (`APPROVED`, `REJECTED`, …). |
| `convergence` | object | `{ "iterations": int, "max_iterations": int, "rejections": int }`: iterations to verdict and how many REJECTED verdicts preceded it. |
| `decisions` | object | `{ "surfaced": {"P0": int, "P1": int, "P2": int}, "answered_by_user": int, "answered_by_assumption": int, "unanswered": int, "p0_assumed": int }`. `p0_assumed` is the key signal: blocking questions the session guessed on rather than asking. |
| `clarity` | object | `{ "mean_before": float or null, "mean_after": float or null, "topics_touched": int }`: the de-risking delta. |

See `docs/SESSION_ANALYTICS_PLAN.md` for the design and the three health signals `stats` derives from these records.

---

## 5. `instructions.md` Structure

Generated instructions follow a consistent layout:

1. **Header**: phase, run directory, input text, iteration cap, creation timestamp, budget, and (for Studio) role pack + overrides.
2. **Artifacts list**: file destinations. Studio instructions highlight per-role filenames.
3. **Agent Roles**: Advocate, Contrarian, Implementer (non-studio) or Integrator (studio).
4. **Iteration Loop**: numbered steps for Advocate/Contrarian exchanges. Studio loop points to the Integrator duel hand-off after approval.
5. **Role Menu** (Studio only): table describing each invited role, deliverables, file naming, and a link to each role's `prompt_doc` when set (optional, project-supplied; `-` otherwise).
6. **Integrator Duel** (Studio only): explains `### Integrator Advocate`, `### Integrator Contrarian (VERDICT)`, and `### Integrated Plan` sections inside `integrator.md`.
7. **Summary & Packaging**: reminders to fill out `summary.md` and run the finalize command.

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
))
```

Stick to the CLI whenever possible so scripts remain simple and any assistant can quote the same commands your teammates run manually.

---

## 9. Related Documents

- [README.md](../../README.md): big-picture overview and testing notes.
- [CLAUDE_CODE_USAGE.md](./CLAUDE_CODE_USAGE.md): Claude Code slash commands and workflow.
- [STUDIO_BRIDGE_TEMPLATE.md](./STUDIO_BRIDGE_TEMPLATE.md): copy into every dependent repo.
- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md): repo-level onboarding checklist and helper scripts.

These docs, together with `run_phase.py`, define the entire Studio API surface.
