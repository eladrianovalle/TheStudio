# Claude Code Usage Guide

Run Studio phase debates natively in Claude Code using slash commands.

## Quick Start

```
/run-phase --phase market --text "A cozy farming sim with social deduction mechanics"
```

This triggers the full advocate/contrarian loop:
1. Prepares a run directory with instructions
2. Runs the **Open-Questions Pre-Flight** (Step 0) — surfaces what is genuinely unsettled, pauses on P0 blockers, records the answers
3. Spawns an Advocate agent to build the case
4. Spawns a separate Contrarian agent to stress-test it
5. Iterates until APPROVED or max iterations exhausted
6. Generates implementation deliverables (if approved)
7. Writes summary and finalizes the run

The **Contrarian is an editor by default**: alongside flaws and edge cases it carries an always-on mandate to cut, merge, and simplify — the advocate adds, the contrarian carves out the essence. (This mandate is off in `--mode questions`, where the contrarian instead judges whether each surfaced question is *relevant* and must not drop genuinely-open questions.)

## Available Phases

| Phase | Advocate | Contrarian | Output |
|-------|----------|------------|--------|
| `market` | Market Growth Strategist | Reality Check & Editor | Audience profile, competitor analysis, GTM plan |
| `design` | Lead Systems Designer | Scope-Creep Police & Editor | Core loop, progression, mechanics, UX |
| `tech` | Technical Architect | Senior SRE & Editor | Architecture, stack, tests, implementation |

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

### Pause-and-Ask (Collaborative Decisions)

During any run, agents may flag decision points — questions where your input changes the outcome. The orchestrator detects these and pauses to ask you:

- **P0 (Blocking):** The run pauses and presents the decision with options. You answer before agents continue. Your answers become hard constraints for all subsequent agents.
- **P1 (Important):** Shown as "FYI — agent assumes X for: [question]." You can override or accept the assumption.
- **P2 (Context):** Logged silently to `decisions.md` — no interruption.

All your decisions accumulate in `{run_dir}/decisions.md` throughout the run. Later agents read this file and treat settled decisions as constraints they cannot re-litigate.

**Example flow:**
1. Advocate writes proposal, flags P0: "Real-time or turn-based?"
2. Orchestrator pauses: "Blocking Decision: Real-time or turn-based? Options: (a) Real-time (b) Turn-based"
3. You answer: "Turn-based"
4. Contrarian reads `decisions.md`, treats turn-based as a constraint
5. Subsequent iterations build on your decision

This works in both single-phase (`/run-phase`) and multi-role (`/run-studio-phase`) runs. In scoped runs:
- **S1 (Alignment):** Decisions checked after each agent (advocate/contrarian), surfaced immediately
- **S2 (Depth):** Decisions checked per-role (sequential), earlier role decisions inform later roles
- **S3 (Polish) + Integrator:** Receive all accumulated decisions as constraints

### Clarity Scores (Adaptive Question Density)

As decisions accumulate, Studio tracks **per-topic clarity scores** — a confidence metric that controls how aggressively agents surface new decision points.

| Score | Status | Agent behavior |
|-------|--------|----------------|
| 0.0–0.4 | Needs work | Actively surface decision points on this topic |
| 0.4–0.7 | Settling | Only flag genuine new gaps |
| 0.7–1.0 | Settled | Treat as constraint, do not re-litigate |

Scores are computed from: decisions answered / total decisions surfaced, with a mild penalty for contrarian challenges. They persist across runs in `.studio/clarity.json`.

**Viewing and overriding clarity:**
```bash
# Show current project clarity
python studio/run_phase.py show-clarity

# Override a topic score (if the system has it wrong)
python studio/run_phase.py set-clarity --topic core_loop_design --score 0.9

# Reset an override (back to computed score)
python studio/run_phase.py set-clarity --topic core_loop_design --reset

# Recompute from a specific run's decisions
python studio/run_phase.py recompute-clarity --phase studio --run-id run_studio_20260319_143000
```

**Context-adaptive scoping:** Studio detects whether you're analyzing something broad ("a cozy farming sim") or narrow ("build the inventory system") and tracks clarity accordingly. Broad runs produce more topics; narrow runs focus on what that feature needs.

**Natural scope progression:** Clarity maps to scoped debate tiers:
- **S1 Alignment** (low clarity) → many decision points
- **S2 Depth** (medium-high clarity) → fewer, only genuine gaps
- **S3 Polish** (high clarity) → rare, mostly confirmations

### Agent Metrics (Token Tracking)

Studio tracks per-agent token usage throughout each run. After every agent completes, the orchestrator records the `total_tokens`, `tool_uses`, and `duration_ms` from the Agent tool result into `{run_dir}/metrics.json`.

**Viewing metrics mid-run or after:**
```bash
python studio/run_phase.py show-metrics --run-dir <path>
```

Example output:
```
Agent Metrics — run_studio_20260322_143000
  Agents spawned:  6
  Total tokens:    82,400
  Total tool uses: 95
  Total duration:  312s (5.2m)

  By scope:
    alignment     4 agents    20,700 tokens (25%)
    depth         2 agents    61,700 tokens (75%)

  By role:
    engineering       2 agents    45,000 tokens (55%)
    marketing         2 agents    18,700 tokens (23%)
    product           2 agents    18,700 tokens (23%)
```

At finalize, metrics are aggregated into `run.json["metrics"]` for permanent record-keeping. This lets you compare token efficiency across runs — are alignment scopes catching issues cheaply? Are certain roles disproportionately expensive?

---

### Quality Ratings & Cross-Run Stats

The agent **verdict** (APPROVED/REJECTED) tells you what the debate concluded — not whether the run was actually *useful to you*. To gauge how well Studio is doing and improve it as you use it, record your own judgment and look across runs.

**Rate a run** (1 = poor, 5 = excellent) after you've reviewed its output:
```bash
python studio/run_phase.py rate --run-dir <path> --score 4 --note "solid market read, weak on monetization"
```
This writes `{run_dir}/rating.json` — the human counterpart to the agent verdict. Re-running `rate` overwrites the prior score (e.g. after a rerun improves things).

**You don't have to remember to do it.** Rating is auto-prompted at the end of a run:
- The `/run-phase` and `/run-studio-phase` flows close with a "rate this run" step — the assistant asks you for a 1–5 + optional note and records it (skippable; it won't nag).
- Running `finalize` yourself in a terminal prompts interactively (`Rate this run 1-5 (Enter to skip)`). When `finalize` runs non-interactively (automation, or the assistant via a non-TTY shell), it instead prints a copy-paste `rate` command rather than blocking on stdin. Suppress either with `finalize --no-rate-prompt`.

**View the cross-run dashboard:**
```bash
python studio/run_phase.py stats                # all runs
python studio/run_phase.py stats --phase studio # one phase
python studio/run_phase.py stats --json         # machine-readable
```

Example output:
```
Studio Cross-Run Stats
Total runs: 12
  By phase:  design=3, market=4, studio=4, tech=1
  By status: COMPLETED=11, PENDING=1

Verdicts (agent):
  APPROVED=8  REJECTED=3  UNKNOWN=1
  Approval rate: 73% (of decided runs)

Quality ratings (human):
  Rated 9/12 runs — avg 3.6/5
  By phase: design=4.0, market=3.5, studio=3.3, tech=2.0
  Lowest-rated (improvement targets):
    2/5  run_tech_20260601_120000 — missed netcode tradeoffs

Efficiency:
  Tokens: 612,000 across 11 runs (avg 55,636/run)

Decision points:
  41 total — P0=6 P1=18 P2=17
  Answered: 33/41 (80%)

Usage (prepare log):
  12 prepares — design=3, market=4, studio=4, tech=1
  Modes: deliverables=10, questions=2
  Scoped: 4 / Flat: 8
```

**The fine-tuning loop:** `stats` surfaces *where* the system underperforms (low-rated phases, runs you flagged, expensive scopes, unanswered decisions). Use those signals to adjust the knobs that actually shape runs — phase/role personas (`.studio/personas.toml`, `.studio/roles/*.json`), scope budgets (`.studio/scopes.toml`), and clarity thresholds — then re-rate to confirm the change helped. There's no model to train; calibration is judgment-driven, and the ratings are the evidence.

---

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

### Project-Local Role Overrides

Customize base manifest roles per-project by placing JSON files in `.studio/roles/<role_name>.json`:

```json
// .studio/roles/engineering.json
{
  "advocate_focus": "Focus on Next.js App Router and static export architecture.",
  "deliverables": ["Route structure validation", "Static export compatibility report"]
}
```

Override keys replace the base; unspecified keys inherit from the manifest. Valid keys: `title`, `advocate_focus`, `contrarian_focus`, `prompt_doc`, `deliverables`, `escalate_on`. Applied overrides are logged in `run.json` under `studio_roles.role_overrides_applied`.

---

## Utility Slash Commands

In addition to phase runners, these slash commands are available:

| Command | Purpose |
|---------|---------|
| `/unstale` | Comprehensive staleness audit — aligns all docs, code comments, memory, and project tracking to current reality. Stack-agnostic: self-detects Rust/Unity/Node/Python/Go from marker files, or reads `.studio/unstale.toml` to pin exact snapshot commands and audit globs. |
| `/detest` | Audits the repo's test suite against AI-TDD methodology — finds anti-patterns, fixes them. |
| `/offload` | Analyzes CLAUDE.md for content safe to move to companion docs, with canary token verification. |
| `/studio-update` | One-step update of installed Studio source and slash commands. |
| `/studio-setup` | Configure project's Studio installation — role packs, role/phase-persona customization (`.studio/personas.toml`), unstale audit config (`.studio/unstale.toml`), scope tuning, cleanup settings. |
