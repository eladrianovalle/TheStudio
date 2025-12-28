# Studio Architecture (Cascade Edition)

Studio is no longer a long-running runtime or CrewAI service. The entire system now revolves around producing structured instructions, running them inside Windsurf/Cascade, and packaging artifacts so every project can reuse the results. This document explains how the pieces fit together in the Cascade-only world.

---

## 1. High-Level Flow

```
run_phase.py prepare
        ↓
output/<phase>/run_<phase>_<timestamp>/instructions.md
        ↓
Windsurf/Cascade executes Advocate ↔ Contrarian loops
        ↓
Artifacts saved back into the run folder
        ↓
run_phase.py finalize
        ↓
output/index.md + knowledge/run_log.md updated
```

All intelligence lives inside Cascade conversations. Studio’s job is to keep the prompts, roles, artifacts, and logs organized.

---

## 2. Core Components

| Component | Purpose |
| --- | --- |
| `run_phase.py` | CLI entrypoint for `prepare` and `finalize`. Generates instructions, enforces artifact checklists, and keeps indexes current. |
| `run_phase_roles.py` | Helper module that loads `studio.manifest.json`, applies role packs, and normalizes per-role filenames. |
| `studio.manifest.json` | Declarative description of phase-level personas plus Studio role definitions (title, focuses, deliverables, prompt doc, escalation cues). |
| `role_packs/*.json` | Curated sets of Studio roles (e.g., `studio_core`). Operators pick a pack, then add/remove roles with CLI flags. |
| `docs/role_prompts/*.md` | Long-form prompts for each role. Instructions link to these files rather than inlining pages of text. |
| `output/` | Run folders containing instructions, advocate/contrarian artifacts, integrator plans, summaries, and metadata. |
| `knowledge/run_log.md` | Append-only log of finalized runs for easy reference across repos. |

No other services, runtimes, or APIs exist.

---

## 3. Prepare Command Path

1. Operator runs `python run_phase.py prepare --phase ...`.
2. `run_phase.py` loads the manifest and, for Studio phase:
   - Determines which role pack to use (default or `--role-pack`).
   - Applies `--roles +foo -bar` overrides through `run_phase_roles.resolve_role_list`.
   - Builds `RoleDetails` objects with titles, deliverables, prompt links, and escalation cues.
3. `run_phase.py` writes:
   - `instructions.md` including header, artifact checklist, Agent Roles, Iteration Loop, **Role Menu**, and **Integrator Duel** guidance.
   - `run.json` with metadata plus `studio_roles = {pack, overrides, invited}` when applicable.
   - Empty artifact placeholders (per-role filenames for Studio).
4. `output/index.md` is regenerated immediately so other repos know a run is pending.

---

## 4. Execute Inside Cascade

Cascade reads `instructions.md`, the bridge doc, and any prompt docs linked from the Role Menu. Operators ensure:

- Every invited role produces matching `advocate--<role>--NN.md` and `contrarian--<role>--NN.md` files until the role’s contrarian issues `VERDICT: APPROVED`.
- For Studio, once all necessary contrarians approve, the Integrator performs a capped duel inside `integrator.md` with three sections:
  1. `### Integrator Advocate`
  2. `### Integrator Contrarian (VERDICT: …)`
  3. `### Integrated Plan`
- All summaries land in `summary.md`.

No automation runs outside of Cascade; the instructions are simply executed as a structured conversation.

---

## 5. Finalize Command Path

1. Operator runs `python run_phase.py finalize --phase ... --run-id ...`.
2. `run_phase.py` looks up `run.json`, ensures `summary.md` exists, and calls `_validate_artifacts`.
3. `_validate_artifacts` logic:
   - Non-Studio phases: glob `advocate_<n>.md` / `contrarian_<n>.md` / `implementation.md`.
   - Studio phase: iterate through the invited roles stored in `run.json["studio_roles"]["invited"]`, using `collect_role_artifacts` to confirm both advocate and contrarian files exist. Missing roles are recorded.
   - Verify `integrator.md` and `summary.md`.
4. Finalize updates `run.json` with status, verdict, hours, cost, iterations, and for Studio: `completed` + `missing` role lists.
5. `output/index.md` and `knowledge/run_log.md` are refreshed, giving downstream repos searchable entries with summary links.

---

## 6. Role Packs & Manifest

- **Manifest** defines the authoritative personas. Each role entry includes:
  - `title`
  - `advocate_focus` / `contrarian_focus`
  - `deliverables`
  - `escalate_on`
  - `prompt_doc` (Markdown file inside `docs/role_prompts/`)
- **Role packs** enforce consistent combinations. Example `studio_core` includes marketing, product, design, art, engineering, and QA.
- Operators select a pack via `--role-pack` and tweak attendance with `--roles +qa -marketing`. This keeps instructions concise while maintaining a single source of truth.

---

## 7. Files & Artifacts

```
output/
  <phase>/
    run_<phase>_<timestamp>/
      instructions.md
      run.json
      advocate_<n>.md / contrarian_<n>.md / implementation.md (non-studio)
      advocate--<role>--<n>.md / contrarian--<role>--<n>.md / integrator.md (studio)
      summary.md
```

Indexes:
- `output/index.md` – table view
- `knowledge/run_log.md` – chronological log with verdicts, hours, and summary links

---

## 8. Extending Studio

| Need | How to Extend |
| --- | --- |
| New Studio role | Update `studio.manifest.json` + add a prompt doc + include it in a role pack. |
| Alternate role pack per repo | Check `role_packs/*.json` into the shared repo; downstream bridge docs specify which pack to use via CLI flags. |
| New phase | Add entries to `PHASE_DETAILS` in `run_phase.py`, define deliverables, and update docs/tests accordingly. |
| Automation | Wrap `run_phase.py prepare/finalize` in repo-specific scripts or Windsurf command palette entries. |

No direct imports or service layers are required—just CLI calls and Markdown artifacts.

---

## 9. Source of Truth

1. Code: `run_phase.py`, `run_phase_roles.py`, manifest, role packs.
2. Docs: README, STUDIO_INTERACTION_GUIDE, WINDSURF_USAGE, WINDSURF_QUICKREF, STUDIO_BRIDGE_TEMPLATE, API, INTEGRATION_GUIDE, AGENTS_REFERENCE, ARCHITECTURE (this file).
3. Outputs: `output/index.md`, `knowledge/run_log.md`.

Whenever the workflow changes, update all of the above in one commit. Studio deliberately has no hidden runtime—everything is visible, reproducible, and Cascade-first.
