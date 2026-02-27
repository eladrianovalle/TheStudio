# Studio Interaction Guide

Single source of truth for running Studio via Windsurf/Cascade. The legacy CLI, LiteLLM runtime, and direct Python APIs have been removed—everything now flows through `run_phase.py` plus Cascade chat.

---

## 1. What’s Required

1. **Studio root** – keep this repo cloned at a predictable path (default assumed: `/Users/orcpunk/Repos/_TheGameStudio/studio`). If you move it, export `STUDIO_ROOT` so the helper script knows where to write output:
   ```bash
   export STUDIO_ROOT="/absolute/path/to/studio"
   ```
2. **Bridge doc per dependent repo** – copy [`docs/STUDIO_BRIDGE_TEMPLATE.md`](./docs/STUDIO_BRIDGE_TEMPLATE.md) into every project that relies on Studio (e.g., `docs/studio-bridge.md`). Fill in:
   - Studio location (and `STUDIO_ROOT` if overridden).
   - Canonical docs Cascade must read before each run.
   - Prompt stub instructing Cascade to reference the bridge doc + canon and to echo the run folder path created by `run_phase.py`.
3. **Optional shortcuts** – add command palette entries or shell aliases that wrap the `run_phase.py prepare/finalize` commands (examples in `docs/WINDSURF_USAGE.md`).

No additional dependencies or API keys are required because the agents execute inside Windsurf.

---

## 2. Standard Cascade Workflow

### Step 1 – Prepare

```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  prepare --phase <market|design|tech|studio> \
  --text "Describe the objective or idea" \
  --max-iterations 3 \
  --budget "$0-20/mo"            # studio phase only
  --role-pack studio_core        # studio phase optional
  --roles +qa -marketing         # studio phase optional overrides
  --scopes .studio/scopes.toml   # optional: scope-based iteration allocation
  --skip-cleanup                 # optional: bypass cleanup
  --cleanup-dry-run              # optional: preview cleanup deletions
```

Outputs:
- `output/<phase>/run_<phase>_<timestamp>/instructions.md`
- `run.json` metadata seeded with status = `PENDING`
- `output/index.md` entry pointing at the new run folder

### Step 2 – Execute inside Windsurf

1. Paste `instructions.md` into Cascade.
2. Follow the loop spelled out inside the file:
   - Save Advocate responses to `advocate_<n>.md` (non-studio) or per-role files like `advocate--design--02.md`.
   - Save Contrarian responses to `contrarian_<n>.md` (non-studio) or `contrarian--design--02.md`.
   - After approval:
     - Non-studio → write `implementation.md`.
     - Studio → run the Integrator duel sections inside `integrator.md` (`### Integrator Advocate`, `### Integrator Contrarian`, `### Integrated Plan`).
   - Summarize the entire session inside `summary.md`.
3. Mention the run folder path frequently so later instructions can reopen it.

### Step 3 – Finalize

```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  finalize --phase <phase> \
  --run-id run_<phase>_<timestamp> \
  --status completed \
  --verdict APPROVED \
  --hours 0.8 \
  --cost 0 \
  --iterations-run 2         # optional override
```

`finalize` will refuse to run if required artifacts are missing. Once it succeeds you can reference:
- `output/index.md` – sortable table of every run.
- `knowledge/run_log.md` – long-form history with summary links.

### Step 4 – Validate (Optional)

```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  validate --phase <phase> \
  --run-id run_<phase>_<timestamp> \
  --config .studio/validation.toml  # optional: custom config
```

Validates run outputs:
- **Discussion phase**: Document completeness, consistency, format, verdict
- **Implementation phase**: Code checks (pytest, mypy, ruff)

See **[docs/VALIDATION_GUIDE.md](./docs/VALIDATION_GUIDE.md)** for detailed usage.

---

## 3.5 Automatic Cleanup Policy

To keep repositories lean, Studio enforces dual cleanup rules every time you run `prepare` (and via the dedicated command below):

1. **Time-to-live:** delete runs older than 30 days.
2. **Size cap:** keep total storage under 900 MB; if exceeded, delete the oldest remaining runs until under budget.

Configuration lives in `config/studio_settings.toml` with defaults:

```toml
[cleanup]
ttl_days = 30
size_limit_mb = 900
```

Useful flags/env vars:

| Flag / Env | What it does |
| --- | --- |
| `--skip-cleanup` / `STUDIO_SKIP_CLEANUP=1` | Skip cleanup for a single invocation (use sparingly). |
| `--cleanup-dry-run` / `STUDIO_CLEANUP_DRY_RUN=1` | Print which runs would be removed without deleting them. |
| `python run_phase.py cleanup [--dry-run]` | Run cleanup manually (ideal for cron/CI). |

Every cleanup pass logs the number of scanned runs, deletions grouped by reason (TTL vs. budget), and total bytes reclaimed so you can monitor it during Cascade sessions.

---

## 3. Artifact Expectations

| Phase | Required files | Notes |
| --- | --- | --- |
| `market`, `design`, `tech` | `advocate_<n>.md`, `contrarian_<n>.md`, `implementation.md`, `summary.md` | Implementation file is created **after** the first APPROVED verdict. |
| `studio` | `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md`, `integrator.md`, `summary.md` | Each invited role (from the Role Menu) produces its own advocate/contrarian loop. Integrator runs a capped duel inside `integrator.md`. |

Additional files are welcome (screenshots, charts, etc.) as long as they live inside the run folder.

---

## 5. Role Manifests, Packs & Custom Experts

- `studio.manifest.json` now defines per-role personas (title, focuses, deliverables, `docs/role_prompts/...`).
- `role_packs/*.json` contain curated sets (e.g., `studio_core`). Downstream repos use `--role-pack` plus `--roles +foo -bar` rather than editing packs directly.
- Instructions list a **Role Menu** so Cascade knows which artifacts to write and where to find extended prompts.
- Finalize records which roles completed/missed deliverables inside `run.json["studio_roles"]`.

When introducing a new discipline:
1. Extend `studio.manifest.json`.
2. Add/update prompt docs under `docs/role_prompts/`.
3. Update/introduce a `role_packs/*.json` entry.
4. Mention the manifest + pack in downstream bridge docs so Cascade reloads them before each run.

---

## 5. Troubleshooting & Tips

- **Missing artifacts on finalize:** ensure `summary.md` and the iteration files exist. `finalize` prints the exact checklist it enforces.
- **Wrong output directory:** set/export `STUDIO_ROOT` before calling `run_phase.py` or add `--env STUDIO_ROOT=/path` when using Cascade command palette entries.
- **Keeping context fresh:** every repo should log notable runs at the bottom of its bridge doc (date, run_id, takeaway). Cascade can then reopen the folder immediately.
- **Iterating quickly:** rerun `prepare` whenever the brief changes meaningfully; multiple runs per phase are fine. `output/index.md` keeps them organized.

---

## 6. Documentation Contract

1. README + this guide must be updated for every workflow change.
2. Dependent bridge docs must be updated in lockstep.
3. When referencing Studio in conversation with Cascade, cite:
   ```
   See docs/studio-bridge.md for canon + workflow.
   Prepare via run_phase.py, then paste instructions.md back here.
   ```

Staying disciplined here keeps every repo interoperable without guessing which workflow is active.

## 4. Artifact Expectations

| Phase | Required files | Notes |
| --- | --- | --- |
| `market`, `design`, `tech` | `advocate_<n>.md`, `contrarian_<n>.md`, `implementation.md`, `summary.md` | Implementation file is created **after** the first APPROVED verdict. |
| `studio` | `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md`, `integrator.md`, `summary.md` | Each invited role (from the Role Menu) produces its own advocate/contrarian loop. Integrator runs a capped duel inside `integrator.md`. |

Additional files are welcome (screenshots, charts, etc.) as long as they live inside the run folder.

---

## 4. Role Manifests, Packs & Custom Experts

- `studio.manifest.json` now defines per-role personas (title, focuses, deliverables, `docs/role_prompts/...`).
- `role_packs/*.json` contain curated sets (e.g., `studio_core`). Downstream repos use `--role-pack` plus `--roles +foo -bar` rather than editing packs directly.
- Instructions list a **Role Menu** so Cascade knows which artifacts to write and where to find extended prompts.
- Finalize records which roles completed/missed deliverables inside `run.json["studio_roles"]`.

When introducing a new discipline:
1. Extend `studio.manifest.json`.
2. Add/update prompt docs under `docs/role_prompts/`.
3. Update/introduce a `role_packs/*.json` entry.
4. Mention the manifest + pack in downstream bridge docs so Cascade reloads them before each run.

---

## 5. Troubleshooting & Tips

- **Missing artifacts on finalize:** ensure `summary.md` and the iteration files exist. `finalize` prints the exact checklist it enforces.
- **Wrong output directory:** set/export `STUDIO_ROOT` before calling `run_phase.py` or add `--env STUDIO_ROOT=/path` when using Cascade command palette entries.
- **Keeping context fresh:** every repo should log notable runs at the bottom of its bridge doc (date, run_id, takeaway). Cascade can then reopen the folder immediately.
- **Iterating quickly:** rerun `prepare` whenever the brief changes meaningfully; multiple runs per phase are fine. `output/index.md` keeps them organized.

---

## 6. Documentation Contract

1. README + this guide must be updated for every workflow change.
2. Dependent bridge docs must be updated in lockstep.
3. When referencing Studio in conversation with Cascade, cite:
   ```
   See docs/studio-bridge.md for canon + workflow.
   Prepare via run_phase.py, then paste instructions.md back here.
   ```

Staying disciplined here keeps every repo interoperable without guessing which workflow is active.
