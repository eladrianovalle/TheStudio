# Studio Architecture

Studio is no longer a long-running runtime or CrewAI service. The entire system revolves around producing structured instructions, having an AI assistant (Claude Code is the supported path) execute them, and packaging artifacts so every project can reuse the results.

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
| `run_phase.py` | CLI entrypoint: `prepare`, `finalize`, `validate`, `cleanup`, clarity, install, decision, `stats`, setup, offload, and `notify` subcommands. |
| `run_phase_roles.py` | Loads `studio.manifest.json`, applies role packs with dependency injection, applies project-local overrides, and normalizes per-role filenames. |
| `role_overrides.py` | Project-local role customization: loads `.studio/roles/*.json` overlays, validates structure, shallow-merges with manifest roles. |
| `persona_overrides.py` | Project-local single-phase persona overrides: loads `.studio/personas.toml`, per-phase shallow-merges over the shipped `PHASE_DETAILS` defaults. |
| `decision_points.py` | Inline decision point parsing (P0/P1/P2 blockquote format), formatting, `decisions.md` generation, run directory scanning. |
| `findings.py` | Contrarian finding parsing: the machine-readable `FINDING` blockquote format (owns `FINDING_BLOCK_TEMPLATE`, injected into contrarian prompts by `scopes.py`), parsed into `findings.json` — which `finalize` writes at the end of a run, and only when the file isn't already there, so the verifier's write-back survives a re-finalize. Sibling of `decision_points.py` — a `Finding` mirrors a decision point. |
| `verifier.py` | Independent finding-verifier core: selects Medium-confidence findings, applies a verdict, and writes the adjusted confidence back into `findings.json`. Pure, gate-tested logic behind the `.claude/workflows/finding-verifier.js` Workflow, whose fresh agent re-checks each finding from ONLY its quote — never the contrarian's reasoning (the anti-anchoring firewall). |
| `clarity.py` | Per-topic Clarity Score tracking from answered decisions. Controls agent question density and adapts to context scope. |
| `question_mode.py` | Pre-flight question surfacing (`--mode questions`): generates decision-collection instructions for advocate/contrarian. |
| `scopes.py` | Three-tier scope configuration: alignment → depth → polish, with output budgets and debate modes. Also home to `CONTRARIAN_MANDATE` (the shared contrarian editor + evidence-gate identity injected into every deliverable contrarian prompt). |
| `design_mandate.py` | `DESIGN_CRITIQUE_GUIDE`: the game-adapted AI-slop blacklist, the "would a designer be embarrassed?" self-gate, and the Goodwill Reservoir UX score. Injected into **design-phase** instructions only (`run_phase.build_instruction_doc`). Prompt-data sibling of `scopes.py`. |
| `cleanup.py` | TTL-based (30 days) and budget-based (900 MB) run artifact cleanup, plus loose file removal for legacy artifacts outside run directories. |
| `rerun.py` | Detects rejection context from prior runs and generates rerun instructions. |
| `verdict.py` | Extracts APPROVED/REJECTED/UNKNOWN verdict from agent output. |
| `stats.py` | Pure cross-run aggregation, formatting, and the shipped-features roll-up (`aggregate_stats`, `format_stats`, `summarize_shipped_specs`, `summarize_session_health`, `_parse_usage_log`). Also owns `parse_frontmatter`, the single reader of a spec's leading `---` block — `tests/test_spec_verification.py` calls it today, the dashboard next, so the two can't disagree about what a spec says. Backs the `stats` command; moved out of `run_phase.py` so the number-crunching has no I/O. |
| `session.py` | Pure builder for the automatic `session.json` health record (`build_session_record` + `_summarize_decisions`). Mirrors `stats.py`: data-in/data-out, no I/O; `run_phase` finalize reads the run dir and hands the pieces in. Every field is counted from a file the run already produced, so nothing in the record waits on a human. |
| `config_loading.py` | The single shared TOML loader: picks `tomllib` (3.11+) or the `tomli` fallback (3.10) with one consistent error message. Imported by `run_phase.py`, `scopes.py`, `cleanup.py`, `persona_overrides.py`, `impl_loop.py`, and `integrations/slack_digest.py` so no module carries its own copy. |
| `impl_loop.py` | Implementation writer/editor loop config: `LoopConfig` + `load_loop_config()`. Projects the resolved config into runtime knobs (editor on/off, read scope, output budget, mutation/static gates) for the `implementation-loop.js` Workflow, read by running the module as a script (`python .studio/source/impl_loop.py`, or `python studio/impl_loop.py` in this repo). |
| `install.py` | Cross-repo installer: `init`/`check-install`/`update` copies source + slash commands into any project. Injects coding principles into target's `CLAUDE.md` via sentinel markers. |
| `offload.py` | CLAUDE.md analyzer: classifies sections, detects embedded constraints, scores pointer strength, generates offload reports, manages canary tokens. |
| `setup.py` | Setup wizard: project configuration after install. Tracks setup state in `.studio/SETUP.json` and authors the per-repo config files with incremental versioned steps: role overrides, phase personas (`.studio/personas.toml`), cleanup, the `/unstale` audit override (`.studio/unstale.toml`), and the `/smoke` profile (`.studio/smoke.toml`). |
| `validators/` | `DocumentValidator` and `CodeValidator` for post-run quality checks. |
| `integrations/slack_digest.py` | Outbound run-digest notifier. Posts a finalized run's status/verdict/summary to a Slack Incoming Webhook (Block Kit) and/or an n8n Webhook node (flat JSON), stdlib `urllib` only. Config from `.studio/integrations.toml`; fires via the `notify` subcommand and auto-fires on `finalize` (soft-fail). |
| `studio.manifest.json` | Declarative description of phase-level personas, Studio role definitions, and role dependencies. |
| `role_packs/*.json` | Curated sets of Studio roles (e.g., `studio_core`). Operators pick a pack, then add/remove roles with CLI flags. |
| `config/scopes.toml` | Default scope configuration for studio phase runs. A project override at `.studio/scopes.toml` is read *instead of* this file, not merged into it. |
| `config/studio_settings.toml` | Shipped retention/cleanup settings (`[cleanup]` thresholds) read by `cleanup.py`. There is no `.studio/` override path for these; edit the shipped file. |
| `config/implementation_loop.toml` | Shipped defaults for the implementation writer/editor loop (`[loop]`, `[gate]` incl. `mutation_command`, `[editor]`). A project override at `.studio/implementation_loop.toml` is read *instead of* this file; keys it omits fall back to `LoopConfig`'s built-in defaults, not to this file's values. Loaded by `impl_loop.py`. |
| `setup.cfg` | `[mutmut]` config for mutation testing: the tool the `require_mutation_check` gate and the weekly mutation CI run. Lists which pure-logic modules to mutate and the pytest runner. |
| `.studio/roles/*.json` | Project-local role overrides. Shallow-merge with manifest roles (override keys replace base, unspecified keys inherit). |
| `.studio/personas.toml` | Project-local single-phase persona overrides. Per-phase shallow-merge over the shipped `PHASE_DETAILS` defaults (loaded by `persona_overrides.py`, authored by the setup wizard). |
| `.studio/update.toml` | Optional per-repo update behavior. `[update] auto_pull_source = true` in the **source** repo's copy lets `update` fast-forward your Studio source checkout when it is cleanly behind origin (see `install.py`). |
| `.studio/unstale.toml` | Optional per-repo override for the `/unstale` audit (`[snapshot]` commands + `[audit]` globs). Read by the `/unstale` command; absent it self-detects the stack. Authored by the setup wizard. |
| `.studio/smoke.toml` | Optional per-repo profile for the `/smoke` command: a single `[smoke]` table pinning how to stand up a live version to hand-test (`kind`, `setup`/`build`/`launch`, `url`, `ready_probe`/`ready_log`, `golden_path`, `teardown`). Read by the `/smoke` command; absent it self-detects the stack. Authored by the setup wizard. |
| `.studio/integrations.toml` | Optional outbound-webhook config for run digests. `[slack]` and `[n8n]` tables, each with `enabled` and `webhook_url_env` (env var holding the secret URL); `[n8n]` also takes optional `auth_header`/`auth_value_env` for Header Auth. Loaded by `integrations/slack_digest.py`. The old `[outcomes] ledger_path` key is gone — outcome data now comes from spec frontmatter — and a leftover `[outcomes]` table is ignored. |
| Role `prompt_doc` (optional) | Per-role pointer to a long-form prompt doc, surfaced as a link in the Role Menu. Studio ships none. Projects supply their own and set the path via a `.studio/roles/*.json` override; unset renders as `-`. |
| Active output root (`output/` or `.studio/output/`) | Run folders containing instructions, advocate/contrarian artifacts, integrator plans, summaries, and metadata. |
| Active knowledge log (`knowledge/run_log.md` or `.studio/knowledge/run_log.md`) | Append-only log of finalized runs for easy reference across repos. |

No other services, runtimes, or APIs exist.

### Where Artifacts Land

`get_artifact_root()` in `run_phase.py` answers one question — *is this Studio's own repo, or a
project that installed Studio?* — and the run folder, the knowledge log, the specs directory, and
the project-local `.studio/*.toml` config all hang off the answer. An explicit `--artifact-root`
or the `STUDIO_ARTIFACT_ROOT` environment variable beats every case below. With neither set, these
four are tried in order:

1. **cwd is inside `studio/` itself** — either the source tree or an installed snapshot at
   `<repo>/.studio/source`. A snapshot resolves to the consuming repo root, never to the snapshot
   directory; the source tree resolves to `studio/`.
2. **cwd is elsewhere in the source repo** — `studio/` is not a snapshot and cwd sits somewhere
   under its parent, which only Studio's own repo can satisfy. The artifact root is `studio/`, so
   a run from the repo root files its work in `studio/output/`. This case has to come before the
   two consumer checks below: the source repo keeps its own bare `.studio/` for `update.toml` and
   `usage.log`, and those checks would otherwise read it as somebody else's project.
3. **A `.studio/VERSION` above cwd** — the marker `init` leaves in a repo it installed into. The
   search walks *up*, so a call from a monorepo subdirectory still lands on the real repo root.
4. **A bare `.studio/` in cwd** — a repo that was scaffolded but never `init`'d, so it has no
   `VERSION`. This one checks cwd only.

The last two look mergeable and are not. An installed repo is found by walking up for `VERSION`;
a merely scaffolded one is found only by looking at cwd. Collapse them and a scaffolded parent
directory would start capturing runs from every child.

If nothing matches, Studio falls back to cwd and warns once — a genuine first run in a fresh repo.
Downstream, everything keys off whether the artifact root *is* `studio/`. When it is, runs land in
`studio/output/` and no bridge doc is written, because a bridge doc exists to point a separate
project back at Studio. Otherwise runs land in `<repo>/.studio/output/` and the first run
scaffolds that repo's `.studio/` and its `docs/studio-bridge.md`.

`get_specs_dir()` hangs off the same answer with one twist worth knowing: in the source repo the
artifact root is `studio/`, but `specs/` sits *beside* it, so that branch climbs one level to the
repo root. Everywhere else it is `<repo>/.studio/specs`. This is where `stats` reads the shipped
features it reports.

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

### Studio Phase: Three-Tier Scoped Debate (Default)

Studio runs use a scoped flow configured in `config/scopes.toml`:

1. **Alignment** (all roles, parallel, ~500 words each): Directional check on approach, fatal flaws, and high-level tradeoffs. Catches bad directions cheaply before deep dives.
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
4. Finalize updates `run.json` with status, verdict, iterations, quality checks, scope stats, and for Studio: `completed` + `missing` role lists.
5. The active index/log (`<active_output_root>/index.md` and `<active_knowledge_root>/run_log.md`) are refreshed, giving downstream repos searchable entries with summary links.
6. One additive, soft-fail side effect (never gates finalize): `run_phase._write_session_record` writes the automatic `session.json` health record into the run dir (built by `session.build_session_record`). Finalize asks the reader for nothing.

---

## 6. Role Packs & Manifest

- **Manifest** defines the authoritative personas. Each role entry includes:
  - `title`
  - `advocate_focus` / `contrarian_focus`
  - `deliverables`
  - `escalate_on`
  - `prompt_doc` (optional pointer to a project-supplied Markdown file; Studio ships none)
- **Role packs** enforce consistent combinations. Example `studio_core` includes marketing, product, design, art, engineering, test_engineer, and QA.
- **Role dependencies** are declared in `defaults.role_dependencies` (e.g., `engineering → test_engineer`). After resolving overrides, `resolve_role_list` injects co-required roles immediately after their trigger role, unless the operator explicitly removed them with `-role`. This guarantees that test integrity is always debated when engineering is present.
- Operators select a pack via `--role-pack` and tweak attendance with `--roles` additions/removals. This keeps instructions concise while maintaining a single source of truth.
- **Methodology enforcement**: Product, Engineering, and Design roles enforce MVI (Minimum Viable Interaction): every milestone must end in something usable. Engineering and Test Engineer enforce AI-TDD. See `docs/MVI_METHODOLOGY.md` and `docs/AI_TDD_METHODOLOGY.md`.

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
- `<active_output_root>/index.md`: table view
- `<active_knowledge_root>/run_log.md`: chronological log with verdicts, iterations, and summary links

---

## 8. Extending Studio

| Need | How to Extend |
| --- | --- |
| New Studio role | Update `studio.manifest.json` + add a prompt doc + include it in a role pack. |
| Alternate role pack per repo | Check `role_packs/*.json` into the shared repo; downstream bridge docs specify which pack to use via CLI flags. |
| New phase | Add entries to `PHASE_DETAILS` in `run_phase.py`, define deliverables, and update docs/tests accordingly. |
| Automation | Wrap `run_phase.py prepare/finalize` in repo-specific scripts, shell aliases, or assistant-specific commands. |

No direct imports or service layers are required: just CLI calls and Markdown artifacts.

---

## 9. Source of Truth

1. Code: `run_phase.py`, `run_phase_roles.py`, manifest, role packs.
2. Docs: README, CLAUDE_CODE_USAGE, STUDIO_BRIDGE_TEMPLATE, API, INTEGRATION_GUIDE, AGENTS_REFERENCE, ARCHITECTURE (this file), CODING_PRINCIPLES, MVI_METHODOLOGY, AI_TDD_METHODOLOGY, SCOPES_GUIDE, VALIDATION_GUIDE, TEST_DRIVEN_GUIDE, STORAGE_MANAGEMENT.
3. Outputs: `<active_output_root>/index.md`, `<active_knowledge_root>/run_log.md`.

Whenever the workflow changes, update all of the above in one commit. Studio deliberately has no hidden runtime: everything is visible, reproducible, and assistant-agnostic.
