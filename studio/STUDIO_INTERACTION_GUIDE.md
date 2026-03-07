# Studio Interaction Guide

Single source of truth for running Studio. The legacy CLI runtime and direct Python APIs have been removed — everything flows through `run_phase.py` plus your AI assistant (Claude Code, Windsurf/Cascade, or any capable agent).

---

## 1. What's Required

1. **Studio root** — keep this repo cloned at a predictable path. If you move it, export `STUDIO_ROOT` so the helper script can find manifests, role packs, and defaults:
   ```bash
   export STUDIO_ROOT="/absolute/path/to/studio"
   ```
   Optional when running from external repos:
   ```bash
   export STUDIO_ARTIFACT_ROOT="/absolute/path/to/your-project"
   ```
   If unset, Studio defaults artifact writes to the current working directory (outside Studio) under `.studio/`.
2. **Bridge doc per dependent repo** — copy [`docs/STUDIO_BRIDGE_TEMPLATE.md`](./docs/STUDIO_BRIDGE_TEMPLATE.md) into every project that relies on Studio (e.g., `docs/studio-bridge.md`). Fill in:
   - Studio location (and `STUDIO_ROOT` if overridden).
   - Canonical docs the assistant must read before each run.
   - Prompt stub referencing the bridge doc + canon and echoing the run folder path created by `run_phase.py`.
3. **Optional shortcuts** — add command palette entries or shell aliases that wrap the `run_phase.py prepare/finalize` commands (examples in `docs/WINDSURF_USAGE.md`).

No additional dependencies or API keys are required — the agents execute inside your AI assistant.

---

## 2. Standard Workflow

### Step 1 — Prepare

```bash
python $STUDIO_ROOT/run_phase.py \
  prepare --phase <market|design|tech|studio> \
  --text "Describe the objective or idea" \
  --max-iterations 3 \
  --budget "$0-20/mo"            # note for the operator (not enforced)
  --role-pack studio_core        # studio phase optional
  --roles +product +engineering +qa   # studio phase optional overrides
  --scopes custom-scopes.toml    # optional: override default scopes
  --no-scopes                    # optional: disable scopes entirely
  --skip-cleanup                 # optional: bypass cleanup
  --cleanup-dry-run              # optional: preview cleanup deletions
```

`--roles` supports both styles:
- `--roles +product +engineering +qa`
- `--roles=+product --roles=+engineering --roles=+qa`

You can still remove roles with `-role` tokens when needed.

**Note**: If `.studio/scopes.toml` exists, scope-based iteration is used by default. Pass `--no-scopes` to disable.

Outputs:
- `<artifact_root>/output/<phase>/run_<phase>_<timestamp>/instructions.md` when running in Studio
- `<artifact_root>/.studio/output/<phase>/run_<phase>_<timestamp>/instructions.md` when running outside Studio
- `run.json` metadata seeded with status = `PENDING`
- `<active_output_root>/index.md` entry pointing at the new run folder

### Step 2 — Execute

1. Paste `instructions.md` into your AI assistant.
2. Follow the loop spelled out inside the file:
   - Save Advocate responses to `advocate_<n>.md` (non-studio) or per-role files like `advocate--design--02.md`.
   - Save Contrarian responses to `contrarian_<n>.md` (non-studio) or `contrarian--design--02.md`.
   - After approval:
     - Tech phase → write `implementation.md` (with tests).
     - Market/Design → `implementation.md` is optional (discussion phases).
     - Studio → run the Integrator duel sections inside `integrator.md` (`### Integrator Advocate`, `### Integrator Contrarian`, `### Integrated Plan`).
   - Summarize the entire session inside `summary.md`.
3. Mention the run folder path frequently so later instructions can reopen it.

### Step 3 — Finalize

```bash
python $STUDIO_ROOT/run_phase.py \
  finalize --phase <phase> \
  --run-id run_<phase>_<timestamp> \
  --status completed \
  --verdict APPROVED \
  --hours 0.8 \
  --cost 0 \
  --iterations-run 2         # optional override
```

`finalize` will refuse to run if required artifacts are missing. Once it succeeds you can reference:
- `<active_output_root>/index.md` — sortable table of every run.
- `<active_knowledge_root>/run_log.md` — long-form history with summary links.

### Step 4 — Validate (Optional)

```bash
python $STUDIO_ROOT/run_phase.py \
  validate --phase <phase> \
  --run-id run_<phase>_<timestamp> \
  --config .studio/validation.toml  # optional: custom config
```

Validates run outputs:
- **Discussion phase**: Document completeness, consistency, format, verdict
- **Implementation phase**: Code checks (pytest, mypy, ruff)

See **[docs/VALIDATION_GUIDE.md](./docs/VALIDATION_GUIDE.md)** for detailed usage.

---

## 3. Automatic Cleanup Policy

Studio enforces dual cleanup rules every time you run `prepare` (and via the dedicated `cleanup` command):

1. **Time-to-live:** delete runs older than 30 days.
2. **Size cap:** keep total storage under 900 MB; if exceeded, delete the oldest remaining runs until under budget.

Configuration lives in `config/studio_settings.toml`. See **[docs/STORAGE_MANAGEMENT.md](./docs/STORAGE_MANAGEMENT.md)** for details and flags.

---

## 4. Artifact Expectations

| Phase | Required files | Notes |
| --- | --- | --- |
| `market`, `design` | `advocate_<n>.md`, `contrarian_<n>.md`, `summary.md` | Discussion phases — `implementation.md` is optional. |
| `tech` | `advocate_<n>.md`, `contrarian_<n>.md`, `summary.md` | **Test-driven discipline required.** `implementation.md` should include test specs, test code, and implementation code. See [TEST_DRIVEN_GUIDE.md](./docs/TEST_DRIVEN_GUIDE.md). |
| `studio` | `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md`, `integrator.md`, `summary.md` | Each invited role (from the Role Menu) produces its own advocate/contrarian loop. Integrator runs a capped duel inside `integrator.md`. |

Additional files are welcome (screenshots, charts, etc.) as long as they live inside the run folder.

### Test-Driven Development for Tech Phase

**All tech implementations must follow test-driven discipline:**
1. Define testable requirements in advocate phase
2. Write test specifications before implementation
3. Write test code that initially fails
4. Implement code to pass tests
5. Include verification instructions

See **[docs/TEST_DRIVEN_GUIDE.md](./docs/TEST_DRIVEN_GUIDE.md)** for complete workflow and examples.

---

## 5. Role Manifests, Packs & Custom Experts

- `studio.manifest.json` defines per-role personas (title, focuses, deliverables, `docs/role_prompts/...`).
- `role_packs/*.json` contain curated sets (e.g., `studio_core`). Downstream repos use `--role-pack` plus `--roles` overrides rather than editing packs directly.
- Instructions list a **Role Menu** so the assistant knows which artifacts to write and where to find extended prompts.
- Finalize records which roles completed/missed deliverables inside `run.json["studio_roles"]`.

When introducing a new discipline:
1. Extend `studio.manifest.json`.
2. Add/update prompt docs under `docs/role_prompts/`.
3. Update/introduce a `role_packs/*.json` entry.
4. Mention the manifest + pack in downstream bridge docs.

---

## 6. Troubleshooting & Tips

- **Missing artifacts on finalize:** ensure `summary.md` and the iteration files exist. `finalize` prints the exact checklist it enforces.
- **Wrong output directory:** set/export `STUDIO_ARTIFACT_ROOT` for explicit placement, or run from the target repo root so Studio writes to `<repo>/.studio`.
- **Keeping context fresh:** every repo should log notable runs at the bottom of its bridge doc (date, run_id, takeaway). The assistant can then reopen the folder immediately.
- **Iterating quickly:** rerun `prepare` whenever the brief changes meaningfully; multiple runs per phase are fine. Use `.studio/output/index.md` (external repo) or `output/index.md` (Studio repo) to keep them organized.

---

## 7. Documentation Contract

1. README + this guide must be updated for every workflow change.
2. Dependent bridge docs must be updated in lockstep.
3. When referencing Studio in conversation with your assistant, cite:
   ```
   See docs/studio-bridge.md for canon + workflow.
   Prepare via run_phase.py, then paste instructions.md back here.
   ```

Staying disciplined here keeps every repo interoperable without guessing which workflow is active.
