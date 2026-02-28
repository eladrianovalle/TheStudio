# The Studio (Cascade Edition)

Studio is now a **single-purpose instruction generator** for Windsurf/Cascade. Instead of hosting its own runtime, the repo prepares structured advocate/contrarian debates that you execute inside Cascade chat, then packages the results so every project can reference them later.

Key goals:

1. **Cascade-only workflow** – no Gemini, LiteLLM, or CLI runtime required.
2. **Deterministic packaging** – every phase run creates a folder with instructions, iteration transcripts, summary, and metadata.
3. **Cross-project visibility** – `output/index.md` and `knowledge/run_log.md` stay up to date so any repo can pick up the latest context.

---

## 🧱 Studio Role Packs & Role Menu

- **Manifest (`studio.manifest.json`)** defines every discipline (title, focuses, prompt doc, deliverables, escalation cues).
- **Role packs (`role_packs/*.json`)** are curated pod presets (e.g., `studio_core` = marketing + product + design + art + engineering + QA). Downstream repos do *not* fork them; they only supply `--roles +foo -bar`.
- **Instructions** now include a Role Menu table linking to prompt docs and file names (e.g., `advocate--design--02.md`).
- **Finalize** validates that each invited role produced both advocate/contrarian artifacts and records missing pods inside `run.json["studio_roles"]["missing"]`.
- **Integrator duel** is captured inside `integrator.md` with `### Integrator Advocate`, `### Integrator Contrarian (VERDICT)`, and `### Integrated Plan`.

When in doubt, run:
```bash
python run_phase.py prepare --phase studio --text "..." --role-pack studio_core
```
and adjust attendees via `--roles +qa -marketing`.

## 🧪 Test-Driven Development Discipline

**All tech phase implementations must follow test-driven discipline:**

- Define testable requirements in the advocate phase
- Write test specifications before implementation
- Write test code that initially fails
- Implement code to pass the tests
- Include verification instructions

Tech implementations without tests are incomplete. See **[docs/TEST_DRIVEN_GUIDE.md](./studio/docs/TEST_DRIVEN_GUIDE.md)** for the complete workflow, examples, and quality standards.

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

1. **Clone** this repo somewhere long-lived.
2. **(Optional)** Set `STUDIO_ROOT` if needed:
   ```bash
   export STUDIO_ROOT="/absolute/path/to/studio"
   ```
3. **Prepare a run** from any other repo or terminal:
   ```bash
   python $STUDIO_ROOT/run_phase.py \
     prepare --phase market \
     --text "A cozy farming sim with time travel"
   ```
   Output:
   - `output/market/run_market_20251223_170045/instructions.md`
   - `run.json` metadata + empty artifact placeholders
   - `output/index.md` updated with the new run ID
4. **(Studio phase only)** If you want multiple disciplines in the room, add:
   ```bash
   python $STUDIO_ROOT/run_phase.py \
     prepare --phase studio \
     --text "Self-critique Studio" \
     --role-pack studio_core --roles +qa -marketing
   ```
   - `--role-pack` pulls a preset pod from `role_packs/`.
   - `--roles` lets you include/exclude roles (`+role`/`-role`) without editing instructions.
   - Instructions will list a **Role Menu** with per-role file targets like `advocate--design--01.md`.
5. **Execute inside Windsurf/Cascade**:
   - Paste the instructions into chat.
   - For each iteration, save files exactly where the instructions specify (`advocate_1.md`, `contrarian_1.md`, etc.).
   - Generate `summary.md` (and `implementation.md` for non-studio phases).
6. **Finalize** once artifacts are in place:
   ```bash
   python $STUDIO_ROOT/run_phase.py \
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
7. **Validate** (optional but recommended):
   ```bash
   python $STUDIO_ROOT/run_phase.py \
     validate --phase market \
     --run-id run_market_20251223_170045
   ```
   Validates document quality and code (if implementation phase).

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
  studio/
    run_studio_20251223_230322/
      instructions.md
      advocate--marketing--01.md
      contrarian--marketing--01.md
      ... (per-role files)
      integrator.md
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
| `studio_roles` | Studio-only metadata: `{pack, overrides, invited, completed, missing}`. |

Use these files as the single source of truth when referencing decisions or continuing work.

---

## 🎯 New: Concentric-Iteration Strategy (v2.0)

Studio now implements a **concentric-iteration strategy** (narrowing scope across iterations) with patterns inspired by agent-gauntlet:

1. **Time-to-live:** runs older than **30 days** are purged before creating new ones.
2. **Storage budget:** total run storage under a given `STUDIO_ROOT` is capped at **900 MB**. When the cap is exceeded, the oldest remaining runs are deleted until usage falls below the limit.

Controls live in `config/studio_settings.toml`:

```toml
[cleanup]
ttl_days = 30
size_limit_mb = 900
```

During `python run_phase.py prepare …`, cleanup runs automatically (unless you pass `--skip-cleanup`). Helpful flags/env vars:

| Option | Purpose |
| --- | --- |
| `--skip-cleanup` / `STUDIO_SKIP_CLEANUP=1` | Bypass the cleanup pass (rare; only when experimenting). |
| `--cleanup-dry-run` / `STUDIO_CLEANUP_DRY_RUN=1` | Log what would be deleted without touching files. |
| `python run_phase.py cleanup [--dry-run]` | Manually invoke cleanup on demand (e.g., cron, CI). |

Every invocation prints how many runs were scanned, which ones were deleted (TTL vs. budget), and total bytes reclaimed so you can monitor behavior. If you need a different TTL/size cap per repo, check the TOML file in with project-specific values.

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
