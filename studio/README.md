# The Game Studio (Cascade Edition)

Studio is now a **single-purpose instruction generator** for Windsurf/Cascade. Instead of hosting its own runtime, the repo prepares structured advocate/contrarian debates that you execute inside Cascade chat, then packages the results so every project can reference them later.

Key goals:

1. **Cascade-only workflow** – no Gemini, LiteLLM, or CLI runtime required.
2. **Deterministic packaging** – every phase run creates a folder with instructions, iteration transcripts, summary, and metadata.
3. **Cross-project visibility** – `output/index.md` and `knowledge/run_log.md` stay up to date so any repo can pick up the latest context.

---

## ✨ What’s in the box?

| Path | Purpose |
| --- | --- |
| `run_phase.py` | Primary entrypoint. Creates instructions + folders (`prepare`) and finalizes runs after Cascade finishes (`finalize`). |
| `output/` | Auto-generated artifacts grouped by phase: `output/<phase>/run_<phase>_<timestamp>/…`. |
| `knowledge/run_log.md` | Chronological feed of finalized runs with verdict, hours, cost, and summary links. |
| `docs/` | Guides for Cascade usage, bridge templates, presets, and architecture notes. |
| `studio.manifest.json` (optional) | Example of per-repo role overrides for advocates/contrarians. |

There is **no** CLI, LiteLLM proxy, Gemini integration, or Python API entrypoint anymore. Everything routes through `run_phase.py` + Cascade chat.

---

## 🚀 Zero-Setup Quick Start

1. **Clone** this repo somewhere long-lived (e.g., `/Users/orcpunk/Repos/_TheGameStudio/studio`).
2. **(Optional)** Set `STUDIO_ROOT` if you keep the repo elsewhere:
   ```bash
   export STUDIO_ROOT="/absolute/path/to/studio"
   ```
3. **Prepare a run** from any other repo or terminal:
   ```bash
   python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
     prepare --phase market \
     --text "A cozy farming sim with time travel"
   ```
   Output:
   - `output/market/run_market_20251223_170045/instructions.md`
   - `run.json` metadata + empty artifact placeholders
   - `output/index.md` updated with the new run ID
4. **Execute inside Windsurf/Cascade**:
   - Paste the instructions into chat.
   - For each iteration, save files exactly where the instructions specify (`advocate_1.md`, `contrarian_1.md`, etc.).
   - Generate `summary.md` (and `implementation.md` for non-studio phases).
5. **Finalize** once artifacts are in place:
   ```bash
   python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
     finalize --phase market \
     --run-id run_market_20251223_170045 \
     --status completed --verdict APPROVED \
     --hours 0.75 --cost 0
   ```
   Finalize will:
   - Validate required artifacts are present.
   - Count iterations automatically.
   - Refresh `output/index.md`.
   - Append an entry to `knowledge/run_log.md`.

That’s the whole loop.

---

## 🧭 Standard Workflow (per phase)

1. **Bridge doc first** – copy `docs/STUDIO_BRIDGE_TEMPLATE.md` into each dependent repo (e.g., `docs/studio-bridge.md`) and fill in:
   - Where Studio lives.
   - Canonical project docs Cascade must load.
   - Prompt template instructing Cascade to mention the bridge doc, canon, objectives, and run folder.
2. **Prepare** with `run_phase.py` (include `--max-iterations` or `--budget` for studio phase if needed).
3. **Cascade executes** Advocate → Contrarian loops using the generated instructions.
4. **Finalize** to lock the run and log it.
5. **Link back** to the run folder inside your project issue, PR, or design doc.

All automation, scripting, or CI integrations should call `run_phase.py` rather than importing Python modules.

---

## 🗂️ Run Directory Anatomy

```
output/
  market/
    run_market_20251223_170045/
      instructions.md
      advocate_1.md
      contrarian_1.md
      implementation.md   # non-studio phases
      summary.md
      run.json
```

`run.json` fields:

| Key | Meaning |
| --- | --- |
| `run_id` | Unique identifier (`run_<phase>_<timestamp>`). |
| `phase` | `market`, `design`, `tech`, or `studio`. |
| `input` | Text supplied via `--text`. |
| `max_iterations` | Cap provided at prepare time. |
| `status` / `verdict` | Filled in when finalized. |
| `iterations_run`, `hours`, `cost` | Auto-tracked or provided on finalize. |
| `summary_path` | Resolved path to `summary.md` (auto-set if blank). |

Use these files as the single source of truth when referencing decisions or continuing work.

---

## 📑 Documentation Contract

Whenever you change the workflow:

1. Update **this README**.
2. Update **STUDIO_INTERACTION_GUIDE.md**.
3. Update every affected **bridge doc** in downstream repos.

No change is “done” until all three are in sync.

Reference material:

- [STUDIO_INTERACTION_GUIDE.md](./STUDIO_INTERACTION_GUIDE.md) – hands-on instructions, manifest notes, troubleshooting.
- [docs/WINDSURF_USAGE.md](./docs/WINDSURF_USAGE.md) – verbose walkthrough for Cascade usage + command palette integrations.
- [WINDSURF_QUICKREF.md](./WINDSURF_QUICKREF.md) – one-page reminder for Cascade prompts.
- [docs/STUDIO_BRIDGE_TEMPLATE.md](./docs/STUDIO_BRIDGE_TEMPLATE.md) – copy into other repos before letting Cascade touch Studio.
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) – agent roles/tasks reference (still accurate but now invoked manually through Cascade).

---

## 🛠️ Testing & Dev Notes

- Run tests (currently only the `run_phase` suite):
  ```bash
  pytest tests/test_run_phase.py
  ```
- Python dependencies are intentionally empty in `pyproject.toml`; the helper script only needs the standard library.
- Removed modules (`studio.crew`, `studio.iteration`, `studio.health`, `studio.telemetry`, CLI, etc.) now raise a `StudioRuntimeRemoved` exception if imported. Do not rely on them.

---

## 🤝 Support & Contributions

- Keep `run_phase.py` small, deterministic, and bash-friendly so Cascade can quote it verbatim.
- If you need custom behavior (new phases, deliverable templates, manifest defaults), update `PHASE_DETAILS` in `run_phase.py` and the related docs simultaneously.
- When adding data to `output/` or `knowledge/`, ensure paths remain relative to `STUDIO_ROOT` so other repos can reference them safely.

---

## 📄 License

MIT – reuse freely across your projects. The only requirement is to keep the Cascade-first workflow intact so every repo can share the same expectations. Anything that reintroduces a direct runtime must ship with a brand-new doc pass keeping this README and the interaction guide aligned.
