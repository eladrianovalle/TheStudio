# Claude Code Usage Guide

Run Studio phase debates natively in Claude Code using slash commands.

## Quick Start

```
/run-phase --phase market --text "A cozy farming sim with social deduction mechanics"
```

This triggers the full advocate/contrarian loop:
1. Prepares a run directory with instructions
2. Spawns an Advocate agent to build the case
3. Spawns a separate Contrarian agent to stress-test it
4. Iterates until APPROVED or max iterations exhausted
5. Generates implementation deliverables (if approved)
6. Writes summary and finalizes the run

## Available Phases

| Phase | Advocate | Contrarian | Output |
|-------|----------|------------|--------|
| `market` | Market Growth Strategist | Reality Check | Audience profile, competitor analysis, GTM plan |
| `design` | Lead Systems Designer | Scope-Creep Police | Core loop, progression, mechanics, UX |
| `tech` | Technical Architect | Senior SRE | Architecture, stack, tests, implementation |

## Options

```
/run-phase --phase tech --text "Build multiplayer lobby system" --max-iterations 5
/run-phase --phase design --text "A cozy farming sim" --mode questions
```

- `--phase` — Required. One of: market, design, tech
- `--text` — Required. The idea or objective to debate
- `--max-iterations N` — Cap on advocate/contrarian rounds (default: 3)
- `--mode` — Output mode: `deliverables` (default) or `questions`

## How It Works

The key architectural decision: **advocate and contrarian run as separate Agent subprocesses**. This matters because:

- The advocate builds the strongest possible case without knowing what the contrarian will attack
- The contrarian reads only the advocate's written output, with no shared context from generating the proposal
- This produces genuinely adversarial review, not self-critique

### Iteration Flow

```
Iteration 1:
  Agent(Advocate) → writes advocate_1.md
  Agent(Contrarian) → reads advocate_1.md → writes contrarian_1.md

  If VERDICT: REJECTED and iterations remain:

Iteration 2:
  Agent(Advocate) → reads rejection reasons → writes advocate_2.md
  Agent(Contrarian) → reads advocate_2.md → writes contrarian_2.md

  If VERDICT: APPROVED:
    → Implementation phase
    → Summary
    → Finalize
```

### Rerun Detection

If a previous run in the same phase was REJECTED, the prepare step automatically injects that rejection context into the new run's instructions. The advocate sees what failed last time and must address those concerns.

## Decision Point Protocol

All runs (except question mode) now include inline decision point surfacing. As agents produce their output, they flag decisions that need human input using a standard blockquote format:

```markdown
> **DECISION [P0]:** Should the mechanic be real-time or turn-based?
> **Unblocks:** Core loop design — fundamentally different gameplay
> **Options:** (a) Real-time (b) Turn-based
```

### Priority levels

| Priority | Meaning | Agent behavior |
|----------|---------|----------------|
| **P0** | Blocking | Orchestrator pauses for human input before continuing |
| **P1** | Important | Agent states an assumption and continues; human can override later |
| **P2** | Context | Logged only — useful for future reference but not blocking |

Decision points are automatically injected into `instructions.md` during `prepare`. After a run completes, you can extract all surfaced decisions from agent output files using `decision_points.extract_decisions_from_run()`, which produces a consolidated `decisions.md` grouped by priority.

---

## Pre-flight Decision Collection (`--mode questions`)

Use `--mode questions` as a pre-flight reconnaissance step — a "what don't I know yet?" workflow before committing to a full deliverables run. This is especially useful when an idea is too early for specs and you need to identify the key decisions first.

```
/run-phase --phase design --text "A cozy farming sim with social deduction" --mode questions
/run-studio-phase --text "Add AI critique engine" --roles +product +design --mode questions
```

### What changes in question mode

| Aspect | Deliverables mode (default) | Question mode |
|--------|----------------------------|---------------|
| Advocate output | Proposals, specs, plans | Prioritised question list (P0/P1/P2) |
| Contrarian output | Critique + VERDICT | Challenge priorities, surface missing questions + VERDICT |
| Integrator (studio) | Roadmap via duel | Consolidated, deduplicated question set grouped by theme |
| Implementation step | Yes (after approval) | No — output is the question set itself |
| Rerun context | Injected from prior rejections | Skipped (questions aren't responses to rejections) |

### How questions are structured

Advocates produce 5-15 numbered questions, each tagged:
- **[P0]** — Blocking: cannot start work without an answer
- **[P1]** — Important: answer shapes the approach significantly
- **[P2]** — Nice-to-know: refines quality but work can begin without it

Each question must name the specific decision it unblocks. Anti-generic guardrails prevent questions that are answerable from the input text or that request missing data rather than exposing hidden assumptions.

Contrarians must challenge at least 30% of questions on priority level, surface 2+ unstated assumptions, and identify 2+ missing questions.

### When to use question mode

- Early-stage ideas where you're not sure what you're building yet
- Before a full deliverables run, to identify what decisions and information are missing
- When a deliverables run keeps getting REJECTED because the input is too vague
- To generate a structured brief that feeds into a subsequent deliverables run

**Tip:** Run question mode first to surface P0 decisions, resolve them, then run a full deliverables phase. The deliverables run will still surface new decision points inline as agents encounter them.

### Metadata

Question-mode runs set `"output_type": "questions"` in `run.json`. The `DocumentValidator.validate_question_mode()` method validates question-mode artifacts (checks for >= 3 question-form lines, no verdict tokens, non-empty content).

Usage is logged to `.studio/usage.log` with the mode field for observability.

## Cross-Repo Usage

Studio can be invoked from any external repository. Artifacts land in the calling repo, not in Studio.

### Setup

1. Set `STUDIO_ROOT` in your shell profile or `.env`:
   ```bash
   export STUDIO_ROOT="/absolute/path/to/TheGameStudio/studio"
   ```

2. Run any Studio command from your repo. On first use, Studio auto-creates:
   - `.studio/output/` and `.studio/knowledge/` directories
   - `docs/studio-bridge.md` — pre-filled with your `STUDIO_ROOT` path

3. Optionally copy slash commands for convenience:
   ```bash
   mkdir -p .claude/commands
   # See studio/docs/BRIDGE_COMMANDS_TEMPLATE.md for command templates
   ```

### Explicit artifact routing

Use `--artifact-root` to force artifacts to a specific location:
```bash
python "$STUDIO_ROOT/run_phase.py" prepare --phase market --text "..." --artifact-root /path/to/target
```

Or set `STUDIO_ARTIFACT_ROOT` as an environment variable.

Priority: `--artifact-root` flag > `STUDIO_ARTIFACT_ROOT` env > cwd-based detection.

## Artifacts

When running from the Studio repo, outputs go to `studio/output/<phase>/run_<phase>_<timestamp>/`.
When running from an external repo, outputs go to `<repo>/.studio/output/<phase>/run_<phase>_<timestamp>/`.

```
run_market_20260307_143022/
  instructions.md    # Generated by prepare
  run.json           # Run metadata
  advocate_1.md      # Advocate proposal
  contrarian_1.md    # Contrarian review + verdict
  advocate_2.md      # Revised proposal (if rejected)
  contrarian_2.md    # Second review (if needed)
  implementation.md  # Deliverables (after approval)
  summary.md         # Run summary
```

## Manual Steps

If you prefer manual control over the process:

```bash
# 1. Prepare
python "$STUDIO_ROOT/run_phase.py" prepare --phase market --text "your idea"

# 2. Execute advocate/contrarian manually (read instructions.md for prompts)

# 3. Finalize
python "$STUDIO_ROOT/run_phase.py" finalize --phase market --run-id run_market_... --status completed --verdict APPROVED
```

## Studio Phase (Multi-Role)

For multi-role studio phase runs with role packs and integrator duels:

```
/run-studio-phase --text "Add AI critique engine" --roles +marketing +engineering
```

Options:
- `--text` — Required. The objective for the multi-role debate
- `--role-pack <name>` — Pod preset (default: studio_core)
- `--roles +role -role` — Include/exclude roles from the pack
- `--max-iterations N` — Cap per-role advocate/contrarian rounds (default: 3)
- `--mode` — Output mode: `deliverables` (default) or `questions` (see Question Mode above)

Each role is processed sequentially with separate Advocate and Contrarian agents. After all roles complete, an Integrator duel synthesizes the cross-functional plan. See the [command file](../../.claude/commands/run-studio-phase.md) for full details.
