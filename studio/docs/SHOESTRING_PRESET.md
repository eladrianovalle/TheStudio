# Studio “Shoestring” Preset

This preset is the canonical zero-cost workflow for running Studio entirely through Cascade, ensuring every run is prepared, executed, and packaged consistently—even when you trigger it from other repos.

## Goals

- Keep monthly spend under **$20** (ideally $0 by using Windsurf/Cascade + optional local Ollama).
- Limit hands-on time to **<10 hours/week**.
- Ensure every run is executed by Cascade (no CLI) and captured under `output/{phase}/run_*`.

---

## 1. One-Time Setup

1. **Install dependencies (inside `studio/`):**
   ```bash
   pip install uv
   crewai install
   ```
2. **Configure environment (`studio/.env`):**
   ```env
   GEMINI_API_KEY=your_key_here   # or GROQ_API_KEY / OPENAI_API_KEY
   STUDIO_MODEL=groq/llama-3.3-70b-versatile  # example
   ```
3. **Expose helper script anywhere:**
   ```bash
   alias studio-run="python $STUDIO_ROOT/run_phase.py"
   ```
4. **Optional local fallback:** install and start Ollama if you want fully offline execution.

---

## 2. Standard Workflow (Per Run)

1. **Prepare the run** (from any repo):
   ```bash
   studio-run prepare \
     --phase market \
     --text "A bite-sized puzzle roguelike for web"
   ```
   - Creates `output/market/run_market_<timestamp>/` with `instructions.md`.
   - Updates `output/index.md`.

2. **Execute via Cascade:**
   - Paste the instructions block into Windsurf chat.
   - Run Advocate/Contrarian/Implementer steps manually and save outputs inside the run folder.

3. **Finalize / package:**
   ```bash
   studio-run finalize \
     --phase market \
     --run-id run_market_<timestamp> \
     --status completed \
     --verdict APPROVED \
     --hours 0.8 --cost 0
   ```
   - Validates artifacts, auto-counts iterations, records metadata, updates `output/index.md`, and appends an entry to `knowledge/run_log.md`.

---

## 3. Troubleshooting

| Issue | Cause | Fix |
| --- | --- | --- |
| `Missing advocate outputs` error on finalize | Files saved elsewhere or wrong name | Ensure Cascade writes `advocate_1.md` etc. in the run directory |
| CLI complains about missing API key | Env not loaded | Verify `.env` values and the shell environment calling `run_phase.py` |
| Cascade forgets to save artifacts | Manual oversight | Use the instruction checklist; each step points to the exact file path |
| Index doesn’t reflect new run | `finalize` not executed | Always finish with `run_phase.py finalize ...` |

---

## 4. Recommended Cascade Prompts

### Market Phase
```
Use the Studio market Advocate to steel-man this idea:
{{ instructions from run folder }}
```
Follow with Contrarian prompt referencing the Advocate output; iterate if REJECTED, then run Implementer checklist.

### Design / Tech
Use the same pattern, swapping the phase-specific instructions from `instructions.md`.

### Studio Phase (Self-Critique)
Simply run Advocate → Contrarian → Integrator once (no verdict loop). Save outputs as instructed.

---

## 5. Consumption & Insight Sharing

- `output/index.md` lists all runs with links to summaries.
- `knowledge/run_log.md` holds timestamped entries for stand-ups or cross-project sharing.
- Encourage teammates to consult the index before starting new requests to avoid duplicating work.

---

## 6. Optional Work Status & Next Ideas

**Recently completed**
1. `run_phase.py` prepares/finalizes runs end-to-end (instructions, validation, indexing, knowledge log).
2. Regression tests (`tests/test_run_phase.py`) cover prepare/finalize happy paths plus validation failures.
3. Windsurf-friendly command snippets documented here and in `docs/WINDSURF_USAGE.md`.
4. Knowledge log + output index automatically updated on every finalize to keep insights discoverable.

**Ideas still on deck**
1. Surface `run_phase.py prepare` as a Windsurf command palette action / snippet library entry.
2. Auto-digest latest `output/index.md` entries into Slack/Notion for async sharing.
3. Lightweight dashboard that visualizes run metadata (phase, verdicts, hours/cost).

Track any new follow-ups at the bottom of this section so optional efforts stay visible.

---

By enforcing this preset, every Studio run—regardless of which repo triggered it—remains zero-cost, fully traceable, and reusable across the workspace.
