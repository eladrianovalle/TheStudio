# API Reference (run_phase.py)

The Studio project now exposes exactly one supported interface: `run_phase.py`. This script prepares instructions, validates artifacts, and keeps indexes/logs up to date so Windsurf/Cascade runs stay reproducible. This document describes the command-line contract, JSON schema, and file formats you can rely on when integrating Studio into other repositories or tooling.

---

## 1. Commands

```bash
python /path/to/studio/run_phase.py <command> [options]
```

Only two commands exist:

| Command | Description |
| --- | --- |
| `prepare` | Creates a new run directory, instructions.md, and updates `output/index.md`. |
| `finalize` | Validates artifacts, updates `run.json`, refreshes the index, and appends to `knowledge/run_log.md`. |

---

### 1.1 `prepare` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--phase {market,design,tech,studio}` | ✅ | – | Studio phase to run. Controls artifact checklist and instruction copy. |
| `--text "..."` | ✅ | – | Idea, objective, or question you want Studio to tackle. |
| `--max-iterations N` | ❌ | `3` | How many Advocate↔Contrarian loops Cascade should run before stopping. |
| `--budget "$0-20/mo"` | ❌ | `$0-20/mo` | Only used by the `studio` phase to remind Cascade of spending limits. |
| `--role-pack PACK` | ❌ | Manifest default | Studio-only: selects a curated pod from `role_packs/`. |
| `--roles [+role|-role ...]` | ❌ | `None` | Studio-only: include/exclude roles relative to the selected pack. |

**Output files (all under `output/<phase>/run_<phase>_<timestamp>/`):**
- `instructions.md`
- `run.json` (see schema below)
- Empty placeholders for artifacts:
  - Non-studio phases → `advocate_<n>.md`, `contrarian_<n>.md`, `implementation.md`, `summary.md`
  - Studio phase → `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md`, `integrator.md`, `summary.md`

`prepare` also regenerates `output/index.md` so downstream repos can discover the pending run immediately.

---

### 1.2 `finalize` arguments

| Flag | Required | Default | Description |
| --- | --- | --- | --- |
| `--phase {market,design,tech,studio}` | ✅ | – | Phase associated with the run. |
| `--run-id run_<phase>_<timestamp>` | ✅ | – | Identifier printed by `prepare`. |
| `--status STATUS` | ❌ | `COMPLETED` | Free-form label (“completed”, “abandoned”, etc.). |
| `--verdict VERDICT` | ❌ | – | `APPROVED`, `REJECTED`, `N/A`, or any label you prefer. |
| `--iterations-run N` | ❌ | auto-count | Override if Cascade ran extra loops or skipped iterations. |
| `--hours FLOAT` | ❌ | `None` | Time spent; stored in `run.json` + `run_log.md`. |
| `--cost FLOAT` | ❌ | `None` | Monetary cost in USD (typically `0`). |
| `--summary PATH` | ❌ | auto-detected | Provide a custom summary path if you store it elsewhere. |

`finalize` enforces the artifact checklist (see Section 3). Missing files raise a `FileNotFoundError` describing the gaps.

---

## 2. Environment Variables

| Variable | Description |
| --- | --- |
| `STUDIO_ROOT` | Optional override pointing to the Studio repo. If unset, `run_phase.py` uses its own directory. |

Set it once to avoid hard-coding absolute paths in other repos:

```bash
export STUDIO_ROOT="/Users/orcpunk/Repos/_TheGameStudio/studio"
python $STUDIO_ROOT/run_phase.py prepare --phase market --text "..."
```

No API keys, LiteLLM settings, or third-party credentials are required anymore.

---

## 3. Artifact Checklist

| Phase | Required files |
| --- | --- |
| `market`, `design`, `tech` | `advocate_<n>.md`, `contrarian_<n>.md`, `implementation.md`, `summary.md` |
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
| `studio_roles` | object or null | Studio-only metadata: `{ "pack": str, "overrides": list[str], "invited": list[str], "completed": list[str], "missing": list[str] }`. |
| `updated_iso` | string (optional) | Added by finalize to record the last change timestamp. |

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

Cascade should paste this file into chat verbatim so it knows where to save each artifact.

---

## 6. `output/index.md`

Markdown table of every run. Columns:

| Column | Meaning |
| --- | --- |
| `Run ID` | Hyperlinks back to the run folder via relative paths. |
| `Phase` | Same as `run.json["phase"]`. |
| `Created (UTC)` | Value from `created_display`. |
| `Status` | `PENDING`, `COMPLETED`, etc. |
| `Input` | Sanitized version of the `--text` argument. |
| `Summary` | Auto-linked if `summary_path` exists, otherwise `_pending_`. |

Any automation that needs to list past runs should read this file or regenerate it by calling `run_phase.rebuild_index()`.

---

## 7. `knowledge/run_log.md`

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

---

## 8. Programmatic Usage (Optional)

While the CLI is the supported interface, you can import `run_phase.py` if you need tighter automation:

```python
import importlib.util
from pathlib import Path

script = Path("/Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py")
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

Stick to the CLI whenever possible so scripts remain simple and Cascade can quote the same commands your teammates run manually.

---

## 9. Related Documents

- [README.md](../README.md) – big-picture overview and testing notes.
- [STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md) – canonical user workflow.
- [WINDSURF_USAGE.md](./WINDSURF_USAGE.md) – conversational prompts + palette shortcuts.
- [STUDIO_BRIDGE_TEMPLATE.md](./STUDIO_BRIDGE_TEMPLATE.md) – copy into every dependent repo.
- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) – repo-level onboarding checklist and helper scripts.

These docs, together with `run_phase.py`, define the entire Studio API surface. Anything that reintroduces a direct runtime must update all of them in lockstep.
