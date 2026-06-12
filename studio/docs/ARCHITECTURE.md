# Studio Architecture

Studio is no longer a long-running runtime or CrewAI service. The entire system revolves around producing structured instructions, having an AI assistant (Claude Code, Windsurf/Cascade, or any capable agent) execute them, and packaging artifacts so every project can reuse the results.

---

## 1. High-Level Flow

```
run_phase.py prepare
        ↓
<active_output_root>/<phase>/run_<phase>_<timestamp>/instructions.md
        ↓
AI assistant executes Advocate ↔ Contrarian loops
        ↓
Artifacts saved back into the run folder
        ↓
run_phase.py finalize
        ↓
<active_output_root>/index.md + <active_knowledge_root>/run_log.md updated
```

All intelligence lives inside the assistant’s execution. Studio’s job is to keep the prompts, roles, artifacts, and logs organized.

---

## 2. Core Components

| Component | Purpose |
| --- | --- |
| `run_phase.py` | CLI entrypoint: `prepare`, `finalize`, `validate`, `cleanup`, clarity, install, decision, metrics, setup, and offload subcommands. |
| `run_phase_roles.py` | Loads `studio.manifest.json`, applies role packs with dependency injection, applies project-local overrides, and normalizes per-role filenames. |
| `role_overrides.py` | Project-local role customization: loads `.studio/roles/*.json` overlays, validates structure, shallow-merges with manifest roles. |
| `persona_overrides.py` | Project-local single-phase persona overrides: loads `.studio/personas.toml`, per-phase shallow-merges over the shipped `PHASE_DETAILS` defaults. |
| `decision_points.py` | Inline decision point parsing (P0/P1/P2 blockquote format), formatting, `decisions.md` generation, run directory scanning. |
| `clarity.py` | Per-topic Clarity Score tracking from answered decisions. Controls agent question density and adapts to context scope. |
| `question_mode.py` | Pre-flight question surfacing (`--mode questions`): generates decision-collection instructions for advocate/contrarian. |
| `scopes.py` | Three-tier scope configuration: alignment → depth → polish, with output budgets and debate modes. |
| `cleanup.py` | TTL-based (30 days) and budget-based (900 MB) run artifact cleanup, plus loose file removal for legacy artifacts outside run directories. |
| `rerun.py` | Detects rejection context from prior runs and generates rerun instructions. |
| `verdict.py` | Extracts APPROVED/REJECTED/UNKNOWN verdict from agent output. |
| `install.py` | Cross-repo installer: `init`/`check-install`/`update` copies source + slash commands into any project. |
| `offload.py` | CLAUDE.md analyzer: classifies sections, detects embedded constraints, scores pointer strength, generates offload reports, manages canary tokens. |
| `setup.py` | Setup wizard: project configuration after install. Tracks setup state in `.studio/SETUP.json`, generates role overrides, scopes, and cleanup config with incremental versioned steps. |
| `validators/` | `DocumentValidator` and `CodeValidator` for post-run quality checks. |
| `studio.manifest.json` | Declarative description of phase-level personas, Studio role definitions, and role dependencies. |
| `role_packs/*.json` | Curated sets of Studio roles (e.g., `studio_core`). Operators pick a pack, then add/remove roles with CLI flags. |
| `config/scopes.toml` | Default scope configuration for studio phase runs. |
| `.studio/roles/*.json` | Project-local role overrides. Shallow-merge with manifest roles (override keys replace base, unspecified keys inherit). |
| `.studio/personas.toml` | Project-local single-phase persona overrides. Per-phase shallow-merge over the shipped `PHASE_DETAILS` defaults (loaded by `persona_overrides.py`, authored by the setup wizard). |
| `.studio/unstale.toml` | Optional per-repo override for the `/unstale` audit (`[snapshot]` commands + `[audit]` globs). Read by the `/unstale` command; absent it self-detects the stack. Authored by the setup wizard. |
| `docs/role_prompts/*.md` | Long-form prompts for each role. Instructions link to these files rather than inlining pages of text. |
| Active output root (`output/` or `.studio/output/`) | Run folders containing instructions, advocate/contrarian artifacts, integrator plans, summaries, and metadata. |
| Active knowledge log (`knowledge/run_log.md` or `.studio/knowledge/run_log.md`) | Append-only log of finalized runs for easy reference across repos. |

No other services, runtimes, or APIs exist.

---

## 3. Prepare Command Path

1. Operator runs `python run_phase.py prepare --phase ...`.
2. `run_phase.py` loads the manifest and, for Studio phase:
   - Determines which role pack to use (default or `--role-pack`).
   - Applies `--roles` overrides through `run_phase_roles.resolve_role_list`.
     - Examples: `--roles +product +engineering +qa` or repeated flags `--roles=+product --roles=+engineering --roles=+qa`.
   - Builds `RoleDetails` objects with titles, deliverables, prompt links, and escalation cues.
3. `run_phase.py` writes:
   - `instructions.md` including header, artifact checklist, Agent Roles, Iteration Loop, **Role Menu**, and **Integrator Duel** guidance.
   - `run.json` with metadata plus `studio_roles = {pack, overrides, invited}` when applicable.
   - Empty artifact placeholders (per-role filenames for Studio).
4. The active index (`<active_output_root>/index.md`) is regenerated immediately so other repos know a run is pending.

---

## 4. Execute via AI Assistant

The assistant reads `instructions.md`, the bridge doc, and any prompt docs linked from the Role Menu.

### Simple Phases (market, design, tech)

Advocate → Contrarian loop until `VERDICT: APPROVED` or max iterations exhausted. Then implementation (tech) or summary.

### Studio Phase — Three-Tier Scoped Debate (Default)

Studio runs use a scoped flow configured in `config/scopes.toml`:

1. **Alignment** (all roles, parallel, ~500 words each): Directional check — approach, fatal flaws, high-level tradeoffs. Catches bad directions cheaply before deep dives.
2. **Depth** (per-role, sequential, no word cap): Full deliverables per discipline. Starts focused because alignment context is available.
3. **Polish** (all roles, parallel, ~300 words, 1 pass): Cross-discipline gut-check. Flag remaining conflicts, no new proposals.
4. **Integrator duel**: Synthesize all scope artifacts into `integrator.md` with `### Integrator Advocate`, `### Integrator Contrarian`, `### Integrated Plan`.

File naming encodes scope: `advocate--marketing--S1-01.md` (alignment), `advocate--engineering--S2-02.md` (depth iteration 2), `advocate--qa--S3-01.md` (polish).

Use `--no-scopes` for flat mode (all roles at full depth, original behavior).

### Scope Configuration

`scopes.py` provides `ScopeConfig` with fields: `name`, `focus`, `max_iterations`, `output_budget` (word cap, optional), `debate_mode` (`"all_roles"` or `"per_role"`). The `generate_scope_instructions()` function embeds scope guidance into `instructions.md`.

No automation runs outside the assistant; the instructions are simply executed as a structured conversation.

---

## 5. Finalize Command Path

1. Operator runs `python run_phase.py finalize --phase ... --run-id ...`.
2. `run_phase.py` looks up `run.json`, ensures `summary.md` exists, and calls `_validate_artifacts`.
3. `_validate_artifacts` logic:
   - Non-Studio phases: glob `advocate_<n>.md` / `contrarian_<n>.md` / `implementation.md`.
   - Studio phase: iterate through the invited roles stored in `run.json["studio_roles"]["invited"]`, using `collect_role_artifacts` to confirm both advocate and contrarian files exist. Missing roles are recorded.
   - Verify `integrator.md` and `summary.md`.
   - **Quality checks** (single-pass, warnings only): verdict presence, rubber-stamp detection (<200 chars), format validation, and scope stats tracking per scope. Results stored in `run.json["quality"]` and `run.json["scope_stats"]`.
   - **Agent metrics aggregation**: if `metrics.json` exists (recorded by the orchestrator during the run), summarize into `run.json["metrics"]` with totals and breakdowns by scope and role.
4. Finalize updates `run.json` with status, verdict, hours, cost, iterations, quality checks, scope stats, agent metrics, and for Studio: `completed` + `missing` role lists.
5. The active index/log (`<active_output_root>/index.md` and `<active_knowledge_root>/run_log.md`) are refreshed, giving downstream repos searchable entries with summary links.

---

## 6. Role Packs & Manifest

- **Manifest** defines the authoritative personas. Each role entry includes:
  - `title`
  - `advocate_focus` / `contrarian_focus`
  - `deliverables`
  - `escalate_on`
  - `prompt_doc` (Markdown file inside `docs/role_prompts/`)
- **Role packs** enforce consistent combinations. Example `studio_core` includes marketing, product, design, art, engineering, test_engineer, and QA.
- **Role dependencies** are declared in `defaults.role_dependencies` (e.g., `engineering → test_engineer`). After resolving overrides, `resolve_role_list` injects co-required roles immediately after their trigger role — unless the operator explicitly removed them with `-role`. This guarantees that test integrity is always debated when engineering is present.
- Operators select a pack via `--role-pack` and tweak attendance with `--roles` additions/removals. This keeps instructions concise while maintaining a single source of truth.
- **Methodology enforcement**: Product, Engineering, and Design roles enforce MVI (Minimum Viable Interaction) — every milestone must end in something usable. Engineering and Test Engineer enforce AI-TDD. See `docs/MVI_METHODOLOGY.md` and `docs/AI_TDD_METHODOLOGY.md`.

---

## 7. Files & Artifacts

```
<active_output_root>/
  <phase>/
    run_<phase>_<timestamp>/
      instructions.md
      run.json
      advocate_<n>.md / contrarian_<n>.md / implementation.md (non-studio)
      advocate--<role>--<n>.md / contrarian--<role>--<n>.md / integrator.md (studio, flat)
      advocate--<role>--S1-<n>.md / S2-<n>.md / S3-<n>.md (studio, scoped)
      summary.md
```

Indexes:
- `<active_output_root>/index.md` – table view
- `<active_knowledge_root>/run_log.md` – chronological log with verdicts, hours, and summary links

---

## 8. Extending Studio

| Need | How to Extend |
| --- | --- |
| New Studio role | Update `studio.manifest.json` + add a prompt doc + include it in a role pack. |
| Alternate role pack per repo | Check `role_packs/*.json` into the shared repo; downstream bridge docs specify which pack to use via CLI flags. |
| New phase | Add entries to `PHASE_DETAILS` in `run_phase.py`, define deliverables, and update docs/tests accordingly. |
| Automation | Wrap `run_phase.py prepare/finalize` in repo-specific scripts, shell aliases, or assistant-specific commands. |

No direct imports or service layers are required—just CLI calls and Markdown artifacts.

---

## 9. Source of Truth

1. Code: `run_phase.py`, `run_phase_roles.py`, manifest, role packs.
2. Docs: README, CLAUDE_CODE_USAGE, WINDSURF_USAGE, WINDSURF_QUICKREF, STUDIO_BRIDGE_TEMPLATE, API, INTEGRATION_GUIDE, AGENTS_REFERENCE, ARCHITECTURE (this file).
3. Outputs: `<active_output_root>/index.md`, `<active_knowledge_root>/run_log.md`.

Whenever the workflow changes, update all of the above in one commit. Studio deliberately has no hidden runtime — everything is visible, reproducible, and assistant-agnostic.
