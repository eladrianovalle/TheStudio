# Studio

Studio is a discipline layer for AI coding agents. It runs structured advocate/contrarian debates on your decisions, keeps agents focused and honest while they implement, and ships slash commands that automate the chores around all of it: auditing tests, un-staling docs, slimming context files, and keeping installs current.

Under the hood it's an **instruction generator**. It prepares run directories with instructions an AI assistant (Claude Code is the supported path) executes, then packages the results as versioned artifacts. **No runtime. No API keys. No dependencies beyond Python stdlib.** All the intelligence lives in the assistant's execution.

---

## Quick Start

```bash
# 1. Clone this repo
git clone <repo-url> && cd TheGameStudio

# 2. Run a single-phase debate (market, design, or tech)
python studio/run_phase.py prepare --phase market --text "A cozy farming sim with time travel"

# 3. Hand the generated instructions.md to your AI assistant
#    It will produce advocate_1.md, contrarian_1.md, summary.md

# 4. Finalize the run
python studio/run_phase.py finalize --phase market --run-id <run_id> --status completed --verdict APPROVED
```

**With Claude Code**, use slash commands instead:
```
/run-phase --phase market --text "A cozy farming sim with time travel"
/run-phase --phase design --text "A cozy farming sim" --mode questions
/run-studio-phase --text "Evaluate our multiplayer architecture" --roles +engineering +qa
```

**Install into any project** (slash commands + source, no env vars needed):
```bash
python studio/run_phase.py init --target /path/to/your-project
# Then from that project: /run-phase and /run-studio-phase just work
```

---

## Slash Commands

Slash commands are the main way you use Studio day to day. `init` installs them into any project, so they work natively wherever your code lives.

**Run debates**
| Command | What it does |
|---------|--------------|
| `/run-phase` | Single-phase advocate/contrarian debate (market, design, or tech) |
| `/run-studio-phase` | Multi-role debate across disciplines (alignment → depth → polish) |
| `/spec` | Map a feature's architecture into an approved source-of-truth spec (plain language + technical + diagram) before you build it |

**Build**
| Command | What it does |
|---------|--------------|
| `/forge` | Build one MVI unit through the writer/editor loop, gated on tests-green; when the unit carries acceptance criteria, the editor grades them one at a time |
| `/smoke` | Stand up a live, running version so you can hand-test it (stack-agnostic) |

**Keep the project honest**
| Command | What it does |
|---------|--------------|
| `/detest` | Audit your test suite against AI-TDD methodology and fix the violations |
| `/unstale` | Find and fix stale docs, wrong counts, and dead links (stack-agnostic) |
| `/offload` | Slim a bloated CLAUDE.md by moving reference content into companion docs |

**Maintain the install**
| Command | What it does |
|---------|--------------|
| `/studio-setup` | Configure roles, personas, scopes, and cleanup after install |
| `/studio-update` | Pull the latest Studio source and commands into an installed project |

Every command works from any project once you've run `init`. See [CLAUDE_CODE_USAGE.md](./studio/docs/CLAUDE_CODE_USAGE.md) for full arguments.

---

## The Discipline Layer

Studio isn't only a debate runner. It's a way to hold AI agents to a standard. Install it and these travel with your project:

- **Coding principles**: seven rules that counter common LLM failure modes, from "think before coding" and "make surgical changes" to writing both docs and code for a human reader. `init` injects them into your project's CLAUDE.md. See [CLAUDE.md](./CLAUDE.md#coding-principles).
- **MVI (Minimum Viable Interaction)**: every increment ends in something usable. "Build a skateboard, not a wheel." The Product, Engineering, and Design contrarians enforce it. See [MVI_METHODOLOGY.md](./studio/docs/MVI_METHODOLOGY.md).
- **AI-TDD**: scenario-first tests, humans own the assertions, and mutation verification proves the tests actually bite. The Test Engineer role enforces it. See [AI_TDD_METHODOLOGY.md](./studio/docs/AI_TDD_METHODOLOGY.md).

---

## How It Works

```
prepare ──→ instructions.md ──→ AI assistant executes ──→ finalize
   │                                    │                      │
   │  Creates run directory,            │  Advocate argues      │  Logs results,
   │  role menu, personas,              │  for the idea.        │  updates indexes,
   │  iteration rules                   │  Contrarian attacks   │  runs quality checks
   │                                    │  it. Loop until       │
   │                                    │  VERDICT: APPROVED    │
```

### Collaborative by Design

Agents don't run autonomously to completion. When they hit gaps or forks, they **flag decision points** inline, and the orchestrator pauses to ask you:

- **P0 (Blocking):** Run pauses. You answer before agents continue.
- **P1 (Important):** Agent states an assumption. You can override.
- **P2 (Context):** Logged for reference, no interruption.

Your decisions accumulate in `decisions.md` and become hard constraints for all subsequent agents. **Clarity Scores** track per-topic confidence and automatically reduce question density as topics settle: early runs produce many questions, later runs focus only on genuine new gaps.

### Four Phases

| Phase | What It Does | Output |
|-------|-------------|--------|
| `market` | Viability analysis: audience, competition, GTM | `advocate_N.md`, `contrarian_N.md`, `summary.md` |
| `design` | Game design: core loop, mechanics, scope | Same |
| `tech` | Technical architecture: stack, performance, ops | Same + `implementation.md` with tests |
| `studio` | Multi-role debate: all disciplines in the room | Per-role files + `integrator.md` |

---

## Multi-Role Studio Runs

The `studio` phase brings multiple disciplines into a structured debate. The default `studio_core` pack includes 7 roles:

| Role | Advocate Focus | Contrarian Focus |
|------|---------------|-----------------|
| **Marketing** | Viral hook, audience segmentation, GTM | TAM realism, UA cost scrutiny |
| **Product** | Roadmap sequencing, staffing, success metrics | Priority tradeoffs, ownership gaps |
| **Design** | Experience pillars, core loop | Scope control, UX clarity |
| **Art** | Visual north star, references | Production feasibility, tooling readiness |
| **Engineering** | Architecture, integrations, performance | Ops toil, technical risk |
| **Test Engineer** | Scenario-first test design, mutation verification | Self-mocking tests, hallucinated assertions |
| **QA** | Validation strategy, telemetry | Coverage gaps, environment readiness |

### Role Dependencies

Engineering automatically brings Test Engineer into the room (`engineering → test_engineer`). Override with `-test_engineer` if explicitly unwanted.

### Three-Tier Scoped Debate (Default)

Studio runs use a scoped debate flow to manage token usage and debate quality:

```
┌─ ALIGNMENT ─────────────────────────────────┐
│ All roles in parallel. ~500 words each.     │
│ "Should we go this way at all?"             │
│ Catches fatal flaws cheaply.                │
├─ DEPTH ─────────────────────────────────────┤
│ Each role sequentially. Full deliverables.  │
│ "How exactly should we do this?"            │
│ Starts focused thanks to alignment context. │
├─ POLISH ────────────────────────────────────┤
│ All roles in parallel. ~300 words each.     │
│ "Anything still broken across disciplines?" │
│ Final cross-check before integrator.        │
├─ INTEGRATOR ────────────────────────────────┤
│ Synthesize all roles into unified roadmap.  │
│ Own advocate/contrarian duel.               │
└─────────────────────────────────────────────┘
```

Use `--no-scopes` for flat mode (all roles at full depth, no tiers).

Scope configuration lives in `config/scopes.toml` and can be overridden per-project.

---

## CLI Reference

```bash
# Prepare a run
python studio/run_phase.py prepare --phase <market|design|tech|studio> --text "description"

# Prepare in question-surfacing mode (pre-flight decision collection)
python studio/run_phase.py prepare --phase design --text "description" --mode questions

# Prepare with role pack and overrides
python studio/run_phase.py prepare --phase studio --text "..." \
  --role-pack studio_core --roles +product +engineering +qa

# Finalize a completed run
python studio/run_phase.py finalize --phase <phase> --run-id <run_id> \
  --status completed --verdict APPROVED

# Validate document quality and code
python studio/run_phase.py validate --phase <phase> --run-id <run_id>

# Decision management
python studio/run_phase.py check-decisions --file path/to/advocate_1.md
python studio/run_phase.py record-decisions --run-dir <run_dir> --decisions-file answers.json
python studio/run_phase.py extract-decisions --run-dir <run_dir>
python studio/run_phase.py inject-context --run-dir <run_dir> --scope alignment --role marketing --stance advocate

# Clarity scores
python studio/run_phase.py show-clarity
python studio/run_phase.py set-clarity --topic core_loop_design --score 0.9
python studio/run_phase.py set-clarity --topic core_loop_design --reset
python studio/run_phase.py recompute-clarity --phase studio --run-id <run_id>

# Agent metrics (token tracking per agent)
python studio/run_phase.py record-metrics --run-dir <path> --agent advocate --total-tokens 5000 --role marketing --scope alignment
python studio/run_phase.py show-metrics --run-dir <path>

# Quality ratings & cross-run stats (diagnostics + fine-tuning feedback loop)
python studio/run_phase.py rate --run-dir <path> --score 4 --note "solid market read"  # human 1-5 quality score
python studio/run_phase.py rate --run-dir <path> --score 5 --shipped yes --impact major --changed "shipped the lobby MVP"  # record the run's outcome
python studio/run_phase.py stats                  # cross-run dashboard: outcomes, verdicts, ratings, tokens, decisions, usage
python studio/run_phase.py stats --phase studio   # filter to one phase
python studio/run_phase.py stats --json           # machine-readable aggregate (includes an outcomes key)

# Cross-repo outcome sharing (feed other repos' results into this repo's stats)
python studio/run_phase.py export-outcomes --out outcomes.jsonl  # export this repo's rated runs
python studio/run_phase.py import-outcomes --from outcomes.jsonl # merge into the central ledger (dedup by repo+run_id)

# Cross-repo install
python studio/run_phase.py init --target /path/to/project
python studio/run_phase.py check-install --target /path/to/project
python studio/run_phase.py update --target /path/to/project          # add --force to overwrite files you've edited locally

# Preview / execute storage cleanup
python studio/run_phase.py cleanup --dry-run
python studio/run_phase.py cleanup

# Setup wizard (configure roles, scopes, cleanup after install)
python studio/run_phase.py setup --target . --status
python studio/run_phase.py setup --target . --defaults

# Offload analysis (analyze CLAUDE.md for offload opportunities)
python studio/run_phase.py offload --target .
python studio/run_phase.py offload --target . --apply

# Outbound run digest (Slack / n8n webhooks — see studio/docs/INTEGRATIONS.md)
python studio/run_phase.py notify --run-dir <run_dir>            # post digest to enabled webhooks
python studio/run_phase.py notify --run-dir <run_dir> --dry-run  # print payloads without posting
```

---

## Cross-Repo Usage

**Recommended:** Install Studio into your project. This copies slash commands and source so `/run-phase` and `/run-studio-phase` work natively with full pause-and-ask support:

```bash
python studio/run_phase.py init --target ~/my-game-project
# Then from my-game-project: /run-phase --phase tech --text "Build lobby system"
```

**Alternative:** Set `STUDIO_ROOT` and run manually:

```bash
export STUDIO_ROOT="/path/to/TheGameStudio/studio"
cd ~/my-game-project
python $STUDIO_ROOT/run_phase.py prepare --phase tech --text "Build lobby system"
# Artifacts land in ./my-game-project/.studio/output/tech/run_tech_<timestamp>/
```

First run auto-scaffolds `.studio/` and creates a bridge doc. Override with `--artifact-root` or `STUDIO_ARTIFACT_ROOT` env var. Priority: flag > env > cwd detection.

Keep installed copies current: `python studio/run_phase.py check-install --target <path>` and `update --target <path>`. `init`/`update` also install a per-user SessionStart hook that quietly nudges you to run `/studio-update` when your installed Studio falls behind upstream — once per update, silent otherwise, offline-safe, and never able to break a session. Opt out with `--no-hook` or an empty `.studio/update-check.off`. See [CLAUDE_CODE_USAGE.md](./studio/docs/CLAUDE_CODE_USAGE.md#staying-up-to-date-automatic-nudge). If you develop Studio and consume it elsewhere, set `[update] auto_pull_source = true` in your source repo's `.studio/update.toml` (or pass `update --pull-source`) and `update` will safely fast-forward your source checkout when it's cleanly behind — so it stops nagging you to `git pull` it by hand.

---

## Run Directory Anatomy

```
.studio/output/
  market/
    run_market_20260314_034202/
      instructions.md          # Generated prompts and personas
      advocate_1.md            # Advocate's proposal
      contrarian_1.md          # Contrarian's critique + VERDICT
      summary.md               # Run summary
      run.json                 # Metadata, quality checks, token budget
  studio/
    run_studio_20260314_034202/
      instructions.md
      advocate--marketing--S1-01.md    # Alignment scope
      contrarian--marketing--S1-01.md
      advocate--engineering--S2-01.md  # Depth scope
      contrarian--engineering--S2-01.md
      advocate--qa--S3-01.md           # Polish scope
      contrarian--qa--S3-01.md
      integrator.md                    # Integrated roadmap
      decisions.json                   # Accumulated decision points + answers
      decisions.md                     # Human-readable settled decisions
      clarity.json                     # Per-topic clarity scores
      metrics.json                     # Per-agent token usage (recorded during run)
      rating.json                      # Human 1-5 quality score (written by `rate`)
      summary.md
      run.json
```

### run.json Metadata

| Key | Meaning |
|-----|---------|
| `run_id` | Unique identifier (`run_<phase>_<timestamp>`) |
| `phase` | `market`, `design`, `tech`, or `studio` |
| `status` / `verdict` | `COMPLETED` + `APPROVED`/`REJECTED` after finalize |
| `studio_roles` | `{pack, overrides, invited, completed, missing}` |
| `quality` | Finalize-time quality checks: `{checks_run, warnings, errors}` |
| `scope_stats` | Per-scope output stats: `{files, total_chars, avg_words}` |
| `metrics` | Agent token usage: `{agents, total_tokens, total_duration_ms, by_scope, by_role}` |

---

## MVI (Minimum Viable Interaction)

Every task, sprint, and milestone must end in something **usable**, not a partial component that becomes useful later.

> "Build a skateboard, not a wheel." Each increment is rideable.

- **Tasks** produce an interactable result, not isolated backend/frontend pieces
- **Sprints** end with a working flow, not a layer of the stack
- **Milestones** are demonstrable without caveats like "once we also finish X"
- **Roadmaps** are sequences of increasingly capable MVIs. If cancelled at any point, something usable exists

Product, Engineering, and Design contrarians enforce MVI. See [MVI_METHODOLOGY.md](./studio/docs/MVI_METHODOLOGY.md).

---

## AI-TDD Discipline

All tech phase implementations follow AI-assisted test-driven development:

- **Scenario-first**: Generate Given-When-Then scenarios before any test code
- **Context boundary**: Declare exact stack, ban incompatible frameworks
- **Assertion ownership**: AI writes setup and boilerplate; humans own assertions
- **Mutation verification**: Deliberately break production code to verify tests catch it
- **Anti-pattern detection**: Reject self-mocking tests, hallucinated assertions, implementation-coupled tests

The **Test Engineer** role enforces these in every run that includes engineering. See [AI_TDD_METHODOLOGY.md](./studio/docs/AI_TDD_METHODOLOGY.md).

---

## Quality Checks

Finalize runs quality checks on every advocate/contrarian artifact (warnings only, never blocks):

- **Verdict presence**: Warns if contrarian files lack `VERDICT: APPROVED/REJECTED`
- **Rubber-stamp detection**: Flags files under 200 characters
- **Format validation**: Checks markdown structure, title presence, list formatting
- **Scope stats tracking**: Measures output per scope (chars, words, file count)

Results are stored in `run.json["quality"]` and `run.json["scope_stats"]`.

---

## Cleanup & Storage

Automatic on every `prepare` call:

- **TTL**: Runs older than 30 days are purged
- **Budget**: Total storage capped at 900MB; oldest runs deleted first

Configure in `config/studio_settings.toml`. Use `--skip-cleanup` to bypass.

---

## Project Structure

```
studio/
  run_phase.py              # CLI entrypoint: prepare, finalize, validate, cleanup, decision, clarity, metrics, rate, stats, export/import-outcomes, install, setup, offload, notify
  stats.py                  # Pure cross-run aggregation + formatting + outcome/session-health roll-up (backs `stats`)
  session.py                # Pure builder for the session.json health record finalize writes per run
  config_loading.py         # Shared TOML loader (tomllib/tomli fallback), used by every config reader
  run_phase_roles.py        # Role system: manifest, packs, dependencies, file naming
  role_overrides.py         # Project-local role customization (.studio/roles/*.json)
  persona_overrides.py      # Project-local phase persona overrides (.studio/personas.toml)
  scopes.py                 # Three-tier scope allocation + CONTRARIAN_MANDATE (contrarian editor/evidence-gate)
  design_mandate.py         # Design-phase critique guide: AI-slop blacklist + Goodwill Reservoir (design phase only)
  decision_points.py        # Inline decision point parsing, formatting, persistence
  findings.py               # Contrarian FINDING-block parsing → findings.json (sibling of decision_points)
  verifier.py               # Independent finding verifier: re-check Medium findings from only the quote, write back
  clarity.py                # Per-topic Clarity Score tracking and question density control
  question_mode.py          # Pre-flight question surfacing (--mode questions)
  install.py                # Cross-repo installer (init/check/update)
  setup.py                  # Setup wizard: project config after install (roles, scopes, cleanup)
  offload.py                # CLAUDE.md analyzer: section classification, pointer scoring, canary tokens
  cleanup.py                # TTL + budget-based artifact cleanup + loose file removal
  rerun.py                  # Rejection context injection for iterate-on-failure
  verdict.py                # APPROVED/REJECTED extraction
  impl_loop.py              # Implementation writer/editor loop config (LoopConfig + python -m impl_loop)
  integrations/             # Outbound run-digest webhooks (slack_digest.py → Slack/n8n)
  validators/               # DocumentValidator + CodeValidator
  studio.manifest.json      # Role definitions (14 disciplines)
  role_packs/*.json          # Curated role sets (studio_core, etc.)
  config/scopes.toml         # Default scope configuration
  config/studio_settings.toml # Cleanup settings
  config/implementation_loop.toml # Implementation writer/editor loop defaults
  docs/                     # Guides, role prompts, architecture
  tests/                    # 851 tests (pytest)
```

---

## Testing

```bash
cd studio && python -m pytest tests/ -v
```

851 tests covering: prepare/finalize lifecycle, role resolution with dependency injection, TTL/budget cleanup with boundary conditions, loose file cleanup, scope allocation, rerun detection, fresh-run/cross-phase context reset, verdict extraction, document validation, code validation, decision point parsing, contrarian FINDING-block parsing and the independent finding verifier, the design-phase critique guide (AI-slop blacklist + Goodwill Reservoir) gating, delta-based stats trend alerts, doc-parity (CLI/config docs vs source), the spec-verification convention (a prompt-shaped spec may not be called shipped while its evidence file is unfilled, or has one of its headings dropped or left unanswered), clarity scoring, role overrides, phase persona overrides, cross-repo artifact routing, install/update workflows (incl. stale-snapshot resolution), CLAUDE.md principles injection, agent metrics tracking, quality ratings and cross-run stats, run outcome capture and cross-repo outcome export/import, session-health records and ledger auto-append, CLAUDE.md offload analysis, unstale audit configuration, smoke test configuration, setup wizard configuration, and Slack/n8n run-digest webhooks.

Python 3.10+ required. stdlib only, plus `tomli` on Python 3.10 (see `pyproject.toml`).

---

## Documentation

- [CLAUDE_CODE_USAGE.md](./studio/docs/CLAUDE_CODE_USAGE.md): slash commands, decision points, clarity scores, question mode
- [ARCHITECTURE.md](./studio/docs/ARCHITECTURE.md): system design and extensibility
- [AGENTS_REFERENCE.md](./studio/docs/AGENTS_REFERENCE.md): role definitions and debate flow
- [MVI_METHODOLOGY.md](./studio/docs/MVI_METHODOLOGY.md): Minimum Viable Interaction methodology
- [AI_TDD_METHODOLOGY.md](./studio/docs/AI_TDD_METHODOLOGY.md): AI-assisted testing methodology
- [TEST_DRIVEN_GUIDE.md](./studio/docs/TEST_DRIVEN_GUIDE.md): tech phase TDD workflow
- [INTEGRATION_GUIDE.md](./studio/docs/INTEGRATION_GUIDE.md): cross-repo setup
- [INTEGRATIONS.md](./studio/docs/INTEGRATIONS.md): outbound Slack/n8n run-digest webhooks
- [STUDIO_BRIDGE_TEMPLATE.md](./studio/docs/STUDIO_BRIDGE_TEMPLATE.md): template for downstream repos

---

## License

MIT. Reuse freely across your projects.
