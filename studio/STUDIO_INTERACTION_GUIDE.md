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
```

Outputs:
- `output/<phase>/run_<phase>_<timestamp>/instructions.md`
- `run.json` metadata seeded with status = `PENDING`
- `output/index.md` entry pointing at the new run folder

### Step 2 – Execute inside Windsurf

1. Paste `instructions.md` into Cascade.
2. Follow the loop spelled out inside the file:
   - Save Advocate responses to `advocate_<n>.md`.
   - Save Contrarian responses to `contrarian_<n>.md` (skip for studio phase).
   - After approval (or immediately for studio phase), write the implementation/integrator deliverable.
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

---

## 3. Artifact Expectations

| Phase | Required files | Notes |
| --- | --- | --- |
| `market`, `design`, `tech` | `advocate_<n>.md`, `contrarian_<n>.md`, `implementation.md`, `summary.md` | Implementation file is created **after** the first APPROVED verdict. |
| `studio` | `advocate_1.md`, `contrarian_1.md`, `integrator.md`, `summary.md` | Studio phase runs exactly one Advocate → Contrarian pass before the Integrator consolidates. |

Additional files are welcome (screenshots, charts, etc.) as long as they live inside the run folder.

---

## 4. Role Manifests & Custom Experts

Even though Studio no longer instantiates crews directly, you can still describe preferred experts for each repo via `studio.manifest.json`. Cascade should read this file before improvising prompts so the correct personas show up in its answers.

Example (drop next to your bridge doc):

```jsonc
{
  "phases": {
    "market": {
      "advocate": {
        "role": "LiveOps Growth Hacker",
        "goal": "Steel-man the pitch for retention-first F2P loops."
      },
      "contrarian": {
        "role": "Monetization Skeptic",
        "goal": "Find pricing/burn traps before we spend a dollar."
      }
    },
    "studio": {
      "integrator": {
        "role": "Principal Tools PM",
        "goal": "Ship the cheapest Cascade workflow that still scales."
      }
    }
  }
}
```

Treat the manifest as configuration Cascade must ingest (mention it in your prompts or command palette entries).

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
