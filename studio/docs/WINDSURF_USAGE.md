# Using Studio from Windsurf/Cascade (Cascade-Only Workflow)

Studio no longer exposes a CLI runtime, LiteLLM proxy, or direct Python API. Every interaction now flows through a simple helper script (`run_phase.py`) plus Windsurf/Cascade chat. This guide shows how to prepare runs, execute them via Cascade, and keep artifacts tidy so any repo can continue the work later.

---

## 1. Prerequisites

- Keep Studio cloned at a predictable path (examples below use `/Users/orcpunk/Repos/_TheGameStudio/studio`). If your path differs, either:
  - Pass the absolute path when calling `python /path/to/run_phase.py …`, or
  - Export `STUDIO_ROOT="/absolute/path/to/studio"` so the script picks it up automatically.
- Each dependent repo must include a bridge doc (copy `docs/STUDIO_BRIDGE_TEMPLATE.md`) that:
  - Lists project canon (docs/data Cascade must read before running Studio).
  - States exactly where Studio lives.
  - Includes a prompt stub referencing the bridge doc, canon list, and run folder expectations.
- (Optional but recommended) Configure Windsurf command palette entries for the prepare/finalize commands so you can trigger them without typing full paths.

No API keys or Python dependencies are needed—the actual agent reasoning happens inside Windsurf/Cascade.

---

## 2. Three-Step Workflow

### Step A – Prepare

Run from any repo/terminal:

```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  prepare --phase <market|design|tech|studio> \
  --text "Describe the idea, objective, or question" \
  --max-iterations 3 \
  --budget "$0-20/mo"     # studio phase only
```

What you get:
- `output/<phase>/run_<phase>_<timestamp>/instructions.md`
- `run.json` metadata (status=PENDING, timestamps, iteration cap, etc.)
- `output/index.md` refreshed with the new run

Copy the emitted `run_id` and folder path—Cascade will reference them verbatim.

### Step B – Execute inside Windsurf/Cascade

1. Paste `instructions.md` into chat (include the absolute path and mention the bridge doc/canon).
2. Follow the loop described in the instructions:
   - Save Advocate output to `advocate_<n>.md`.
   - Save Contrarian output to `contrarian_<n>.md` (studio phase skips contrarian loops after the first pass).
   - Once approved (or immediately for studio phase), complete `implementation.md` or `integrator.md`.
   - Write `summary.md` capturing the inputs, iterations, verdict, and next actions.
3. Keep Cascade aware of the run folder path so future prompts can reopen the artifacts without re-searching.

### Step C – Finalize

```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  finalize --phase <phase> \
  --run-id run_<phase>_<timestamp> \
  --status completed \
  --verdict APPROVED \
  --hours 0.8 \
  --cost 0 \
  --iterations-run 2     # optional override
```

`finalize` will:
- Verify required artifacts exist (advocate/contrarian files, implementation/integrator, summary).
- Count iterations automatically if you omit `--iterations-run`.
- Update `run.json`, `output/index.md`, and `knowledge/run_log.md`.
- Abort with a clear checklist if something is missing—fix the files and re-run finalize.

---

## 3. Command Palette Shortcuts (Optional)

1. Press **⌘⇧P** / **Ctrl+Shift+P** → “Cascade: Configure Command Palette Actions”.
2. Add entries like:

```json
{
  "title": "Studio: Prepare Run",
  "description": "Generate instructions for a Studio phase",
  "inputs": [
    { "name": "phase", "placeholder": "market/design/tech/studio" },
    { "name": "idea_or_objective", "placeholder": "What should Studio work on?" },
    { "name": "max_iterations", "placeholder": "Adv↔Con loops (default 3)", "default": "3" }
  ],
  "command": "python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py prepare --phase {{phase}} --text \"{{idea_or_objective}}\" --max-iterations {{max_iterations}}"
}
```

Add a second entry mirroring `run_phase.py finalize …` so finishing runs is one palette action away. If you rely on `STUDIO_ROOT`, prepend `export STUDIO_ROOT=/path && …` inside the command value.

---

## 4. Conversation Templates

When chatting with Cascade, always mention:
1. The bridge doc (e.g., “See docs/studio-bridge.md for canon.”).
2. The prepared run folder path + instructions.
3. The goal/phases to cover.

Example prompts:
- “Use Studio market phase on: **A 3D stealth horror roguelike**. Instructions: `/Users/.../output/market/run_market_20251223_170045/instructions.md`. Save artifacts in that folder, then summarize verdict.”
- “Run Studio design phase using canon from docs/studio-bridge.md. Run folder prepared already—check `run_design_20251223_171210`.”
- “Do a Studio self-critique (studio phase). Manifest + canon listed in this repo’s bridge doc; run folder instructions attached below.”

---

## 5. Artifact Checklist

| Phase | Files | Notes |
| --- | --- | --- |
| Market / Design / Tech | `advocate_<n>.md`, `contrarian_<n>.md`, `implementation.md`, `summary.md` | Implementation is produced after the first APPROVED verdict. |
| Studio | `advocate_1.md`, `contrarian_1.md`, `integrator.md`, `summary.md` | Exact loop is Advocate → Contrarian → Integrator (no implementation file). |

You can add extra context files (screenshots, charts, code samples) as long as they live inside the run folder.

---

## 6. Example End-to-End Session

1. Prepare:
   ```bash
   python run_phase.py prepare --phase market --text "A cozy farming sim with time travel"
   ```
2. Cascade executes:
   - Advocate 1 saved to `advocate_1.md`.
   - Contrarian 1 saved to `contrarian_1.md` (verdict: APPROVED).
   - Implementation checklist completed in `implementation.md`.
   - `summary.md` written with next steps.
3. Finalize:
   ```bash
   python run_phase.py finalize --phase market --run-id run_market_20251223_170045 --status completed --verdict APPROVED --hours 0.8 --cost 0
   ```
4. Reference the run:
   - Bridge doc in the originating repo links to `output/market/run_market_20251223_170045/summary.md`.
   - Later phases can reopen the same folder or spawn a new run with updated goals.

---

## 7. Troubleshooting

| Issue | Fix |
| --- | --- |
| `finalize` complains about missing files | Ensure Advocate/Contrarian/Implementation (or Integrator) + `summary.md` exist in the run directory named in the error. |
| Wrong directory written | Set `STUDIO_ROOT` before running prepare/finalize or pass absolute paths. |
| Need to rerun with new brief | Run `prepare` again; multiple runs per phase are encouraged. Use `output/index.md` to keep them straight. |
| Cascade forgets canon | Update the bridge doc prompt stub to explicitly say “See docs/studio-bridge.md for canon + workflow.” Mention it in every prompt. |

---

## 8. Related Docs

- [README.md](../README.md) – overall vision + quick start.
- [STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md) – detailed workflow reference.
- [STUDIO_BRIDGE_TEMPLATE.md](./STUDIO_BRIDGE_TEMPLATE.md) – copy into dependent repos.
- [API.md](./API.md) – schema for `run_phase.py` arguments, metadata files, and output index.

Keep all of these documents aligned whenever the workflow changes—Studio has no other entrypoint anymore.*** End Patch
