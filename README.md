# The Game Studio

Studio is an **instruction generator** for structured advocate/contrarian debates. It prepares run directories with instructions that an AI assistant (Claude Code, Windsurf/Cascade, or any capable agent) executes, then packages the results as versioned artifacts.

Key goals:

1. **Assistant-agnostic workflow** — no runtime, no API keys; any capable AI assistant can execute the generated instructions.
2. **Deterministic packaging** — every phase run creates a folder with instructions, iteration transcripts, summary, and metadata.
3. **Cross-project visibility** — every artifact root gets its own `output/index.md` and `knowledge/run_log.md` so any repo can pick up the latest context.

---

## Role Packs & Role Menu

- **Manifest (`studio.manifest.json`)** defines every discipline (title, focuses, prompt doc, deliverables, escalation cues).
- **Role packs (`role_packs/*.json`)** are curated pod presets (e.g., `studio_core` = marketing + product + design + art + engineering + QA). Downstream repos do *not* fork them; they supply `--roles` overrides (typically `+product +engineering +qa`, with optional `-role` removals when needed).
- **Instructions** now include a Role Menu table linking to prompt docs and file names (e.g., `advocate--design--02.md`).
- **Finalize** validates that each invited role produced both advocate/contrarian artifacts and records missing pods inside `run.json["studio_roles"]["missing"]`.
- **Integrator duel** is captured inside `integrator.md` with `### Integrator Advocate`, `### Integrator Contrarian (VERDICT)`, and `### Integrated Plan`.

When in doubt, run:
```bash
python run_phase.py prepare --phase studio --text "..." --role-pack studio_core
```
and add attendees via `--roles +product +engineering +qa`.

## Test-Driven Development Discipline

**All tech phase implementations must follow test-driven discipline:**

- Define testable requirements in the advocate phase
- Write test specifications before implementation
- Write test code that initially fails
- Implement code to pass the tests
- Include verification instructions

Tech implementations without tests are incomplete. See **[docs/TEST_DRIVEN_GUIDE.md](./studio/docs/TEST_DRIVEN_GUIDE.md)** for the complete workflow, examples, and quality standards.

## What's in the box?

| Path | Purpose |
| --- | --- |
| `run_phase.py` | Primary CLI entrypoint. Creates instructions + folders (`prepare`) and finalizes runs after the assistant finishes (`finalize`). Also `validate` and `cleanup`. |
| `output/` or `.studio/output/` | Auto-generated artifacts grouped by phase (`<artifact_root>/output/<phase>/run_<phase>_<timestamp>/…`). |
| `knowledge/run_log.md` or `.studio/knowledge/run_log.md` | Chronological feed of finalized runs with verdict, hours, cost, and summary links. |
| `docs/` | Guides, bridge templates, and architecture notes. |
| `studio.manifest.json` (optional) | Example of per-repo role overrides for advocates/contrarians. |

---

## Zero-Setup Quick Start

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
   - `.studio/output/market/run_market_20251223_170045/instructions.md` (when run outside Studio)
   - `run.json` metadata + empty artifact placeholders
   - `.studio/output/index.md` updated with the new run ID
4. **(Studio phase only)** If you want multiple disciplines in the room, add:
   ```bash
   python $STUDIO_ROOT/run_phase.py \
     prepare --phase studio \
     --text "Self-critique Studio" \
     --role-pack studio_core --roles +product +engineering +qa
   ```
   - `--role-pack` pulls a preset pod from `role_packs/`.
   - `--roles` lets you include/exclude roles (`+role`/`-role`) without editing instructions.
   - You can pass role overrides either as `--roles +product +engineering +qa` or repeated `--roles=+product --roles=+engineering --roles=+qa`.
   - Instructions will list a **Role Menu** with per-role file targets like `advocate--design--01.md`.
5. **Execute with your AI assistant**:
   - Paste the instructions into your assistant (Claude Code, Windsurf/Cascade, etc.).
   - For each iteration, save files exactly where the instructions specify (`advocate_1.md`, `contrarian_1.md`, etc.).
   - Generate `summary.md` (and `implementation.md` for tech phase, `integrator.md` for studio phase).
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
   - Refresh `<active_output_root>/index.md`.
   - Append an entry to `<active_knowledge_root>/run_log.md`.
7. **Validate** (optional but recommended):
   ```bash
   python $STUDIO_ROOT/run_phase.py \
     validate --phase market \
     --run-id run_market_20251223_170045
   ```
   Validates document quality and code (if tech phase).

That's the whole loop.

---

## Artifact Root Behavior (Cross-Repo Safety)

- If you run `run_phase.py` **inside this Studio repo**, artifacts stay in `studio/output` and `studio/knowledge`.
- If you run it from a **different repo**, artifacts now default to that repo under:
  - `.studio/output/<phase>/run_*`
  - `.studio/knowledge/run_log.md`
- You can override artifact placement explicitly with:
  ```bash
  export STUDIO_ARTIFACT_ROOT="/absolute/path/to/host-repo"
  ```

This keeps generated docs/working files with the repo that requested the run, while still using centralized Studio prompts and role packs.

---

## Standard Workflow (per phase)

1. **Bridge doc first** — copy `docs/STUDIO_BRIDGE_TEMPLATE.md` into each dependent repo (e.g., `docs/studio-bridge.md`) and fill in:
   - Where Studio lives.
   - Canonical project docs the assistant must load.
   - Prompt template referencing the bridge doc, canon, objectives, and run folder.
2. **Prepare** with `run_phase.py`.
3. **Assistant executes** Advocate → Contrarian loops using the generated instructions.
4. **Finalize** to lock the run and log it.
5. **Link back** to the run folder inside your project issue, PR, or design doc.

All automation, scripting, or CI integrations should call `run_phase.py` rather than importing Python modules.

## Run Directory Anatomy

```
.studio/output/                         # when run from another repo
  market/
    run_market_20251223_170045/
      instructions.md
      advocate_1.md
      contrarian_1.md
      implementation.md   # tech phase; optional for market/design
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

When you run from inside the Studio repo, the same structure appears under `studio/output/` and `studio/knowledge/`.

Use these files as the single source of truth when referencing decisions or continuing work.

---

## Cleanup & Storage

Studio enforces dual cleanup rules automatically on every `prepare` call:

1. **Time-to-live:** runs older than **30 days** are purged.
2. **Storage budget:** total run storage is capped at **900 MB**. When exceeded, oldest runs are deleted until under budget.

Controls live in `config/studio_settings.toml`:

```toml
[cleanup]
ttl_days = 30
size_limit_mb = 900
```

```bash
# Preview what would be deleted
python run_phase.py cleanup --dry-run

# Execute cleanup
python run_phase.py cleanup
```

| Option | Purpose |
| --- | --- |
| `--skip-cleanup` / `STUDIO_SKIP_CLEANUP=1` | Bypass the cleanup pass. |
| `--cleanup-dry-run` / `STUDIO_CLEANUP_DRY_RUN=1` | Log what would be deleted without touching files. |

See **[docs/STORAGE_MANAGEMENT.md](./studio/docs/STORAGE_MANAGEMENT.md)** for details.

---

## Documentation Contract

Whenever you change the workflow:

1. Update **this README**.
2. Update **STUDIO_INTERACTION_GUIDE.md**.
3. Update every affected **bridge doc** in downstream repos.

No change is "done" until all three are in sync.

Reference material:

- [STUDIO_INTERACTION_GUIDE.md](./studio/STUDIO_INTERACTION_GUIDE.md) — hands-on instructions and troubleshooting.
- [docs/INDEX.md](./studio/docs/INDEX.md) — full documentation index.
- [docs/STUDIO_BRIDGE_TEMPLATE.md](./studio/docs/STUDIO_BRIDGE_TEMPLATE.md) — copy into other repos before running Studio.
- [docs/ARCHITECTURE.md](./studio/docs/ARCHITECTURE.md) — system design and extensibility.

---

## Testing & Dev Notes

- Run tests (from `studio/` directory):
  ```bash
  cd studio && python -m pytest tests/ -v
  ```
- Python dependencies are minimal: stdlib only, plus `tomli` on Python 3.10 (see `pyproject.toml`).

---

## Migration Status

Studio is being adapted to support Claude Code as a native execution peer alongside Windsurf. See **[STUDIO_MIGRATION_PLAN.md](./STUDIO_MIGRATION_PLAN.md)** for the active plan and progress.

---

## License

MIT — reuse freely across your projects.
