# The Game Studio

Studio is an **instruction generator** for structured advocate/contrarian debates. It prepares run directories with instructions that an AI assistant (Claude Code, Windsurf/Cascade, or any capable agent) executes, then packages the results as versioned artifacts.

**No runtime. No API keys. No dependencies beyond Python stdlib.** All intelligence lives in the assistant's execution — Studio just keeps the prompts, roles, artifacts, and logs organized.

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
/run-studio-phase --text "Evaluate our multiplayer architecture" --roles +engineering +qa
```

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

### Four Phases

| Phase | What It Does | Output |
|-------|-------------|--------|
| `market` | Viability analysis — audience, competition, GTM | `advocate_N.md`, `contrarian_N.md`, `summary.md` |
| `design` | Game design — core loop, mechanics, scope | Same |
| `tech` | Technical architecture — stack, performance, ops | Same + `implementation.md` with tests |
| `studio` | Multi-role debate — all disciplines in the room | Per-role files + `integrator.md` |

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

# Prepare with role pack and overrides
python studio/run_phase.py prepare --phase studio --text "..." \
  --role-pack studio_core --roles +product +engineering +qa

# Finalize a completed run
python studio/run_phase.py finalize --phase <phase> --run-id <run_id> \
  --status completed --verdict APPROVED

# Validate document quality and code
python studio/run_phase.py validate --phase <phase> --run-id <run_id>

# Preview / execute storage cleanup
python studio/run_phase.py cleanup --dry-run
python studio/run_phase.py cleanup
```

---

## Cross-Repo Usage

Run Studio from any repo — artifacts stay with the calling repo:

```bash
export STUDIO_ROOT="/path/to/TheGameStudio/studio"
cd ~/my-game-project
python $STUDIO_ROOT/run_phase.py prepare --phase tech --text "Build lobby system"
# Artifacts land in ./my-game-project/.studio/output/tech/run_tech_<timestamp>/
```

First run auto-scaffolds `.studio/` and creates a bridge doc. Override with `--artifact-root` or `STUDIO_ARTIFACT_ROOT` env var. Priority: flag > env > cwd detection.

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
| `token_budget` | Per-scope output stats: `{files, total_chars, avg_words}` |

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
- **Token budget tracking**: Measures output per scope (chars, words, file count)

Results are stored in `run.json["quality"]` and `run.json["token_budget"]`.

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
  run_phase.py              # CLI entrypoint: prepare, finalize, validate, cleanup
  run_phase_roles.py        # Role system: manifest, packs, dependencies, file naming
  scopes.py                 # Three-tier scope allocation (alignment/depth/polish)
  cleanup.py                # TTL + budget-based artifact cleanup
  rerun.py                  # Rejection context injection for iterate-on-failure
  verdict.py                # APPROVED/REJECTED extraction
  validators/               # DocumentValidator + CodeValidator
  studio.manifest.json      # Role definitions (9 disciplines)
  role_packs/*.json          # Curated role sets (studio_core, etc.)
  config/scopes.toml         # Default scope configuration
  config/studio_settings.toml # Cleanup settings
  docs/                     # Guides, role prompts, architecture
  tests/                    # 204 tests (pytest)
```

---

## Testing

```bash
cd studio && python -m pytest tests/ -v
```

204 tests covering: prepare/finalize lifecycle, role resolution with dependency injection, TTL/budget cleanup with boundary conditions, scope allocation, rerun detection, verdict extraction, document validation, code validation, and cross-repo artifact routing.

Python 3.10+ required. stdlib only, plus `tomli` on Python 3.10 (see `pyproject.toml`).

---

## Documentation

- [ARCHITECTURE.md](./studio/docs/ARCHITECTURE.md) — system design and extensibility
- [AGENTS_REFERENCE.md](./studio/docs/AGENTS_REFERENCE.md) — role definitions and debate flow
- [AI_TDD_METHODOLOGY.md](./studio/docs/AI_TDD_METHODOLOGY.md) — AI-assisted testing methodology
- [TEST_DRIVEN_GUIDE.md](./studio/docs/TEST_DRIVEN_GUIDE.md) — tech phase TDD workflow
- [INTEGRATION_GUIDE.md](./studio/docs/INTEGRATION_GUIDE.md) — cross-repo setup
- [STUDIO_BRIDGE_TEMPLATE.md](./studio/docs/STUDIO_BRIDGE_TEMPLATE.md) — template for downstream repos

---

## License

MIT — reuse freely across your projects.
