# Studio Phase Run (Multi-Role)

Execute a multi-role advocate/contrarian debate across disciplines using a three-tier scoped debate: alignment → depth → polish.

## Arguments

- `$ARGUMENTS` — Required. Format: `--text "your idea or objective"`
- Optional: `--role-pack <name>` (default: studio_core), `--roles +role -role`, `--max-iterations N` (default 6 across all scopes)
- Optional: `--no-scopes` to use flat mode (all roles at full depth, no tiers)

## Instructions

You are executing a Studio multi-role phase run. Follow these steps exactly:

### Step 1: Prepare

Determine the Studio root path. If this repo contains a `studio/run_phase.py`, use that. Otherwise check `$STUDIO_ROOT`. Then run:

```bash
python "$STUDIO_ROOT/run_phase.py" prepare --phase studio $ARGUMENTS
```

If running from a repo that is NOT the Studio repo itself, artifacts will automatically land in the current repo under `.studio/output/`.

Note the run_id and run directory path from the output.

### Step 2: Read Instructions and Role Menu

Read the generated `instructions.md` file. Pay attention to:
- The **Role Menu** table listing each invited role
- The **Scope-Based Iteration Plan** (if scopes are enabled)
- File naming convention

### Decision Point Handling (applies to ALL scopes)

**MANDATORY — DO NOT SKIP:** After EVERY agent (advocate or contrarian) saves its output:

1. **Extract decision points** — Run this command (do NOT manually scan files):
   ```bash
   python "$STUDIO_ROOT/run_phase.py" extract-decisions --run-dir {run_dir}
   ```

2. **If the output is non-empty**, you MUST pause and present ALL decision points to the user. Do not spawn the next agent until the user has responded. Present each as:
   - **Decision [priority]:** [question]
   - Unblocks: [context]
   - Options: [options if present]

3. **Wait for the user to answer ALL decisions.** Then record in one batch:
   ```bash
   python "$STUDIO_ROOT/run_phase.py" record-decisions --run-dir {run_dir} --decisions-file {tmp_json_path}
   ```
   JSON format: `[{"priority": "P0", "question": "...", "answer": "...", "unblocks": "...", "source_file": "[filename]", "answered_by": "user"}, ...]`

   After recording, show updated clarity scores: `python "$STUDIO_ROOT/run_phase.py" show-clarity`
   Display the scores to the user — they can override with `set-clarity --topic <slug> --score <0.0-1.0>`.

4. **Context injection** — Before spawning each agent, generate its context block:
   ```bash
   python "$STUDIO_ROOT/run_phase.py" inject-context --run-dir {run_dir} --scope {scope} --role {role} --stance {stance}
   ```
   Append the output to the agent prompt. This automatically includes settled decisions, clarity summary, prior-scope file lists, and scope-specific instructions. No manual assembly needed.

5. **Settled context** — If `{run_dir}/decisions.md` exists, the `inject-context` command includes this automatically. If NOT using `inject-context`, ALL subsequent agent prompts must include:
   > Read `{run_dir}/decisions.md` for settled constraints. Treat these as hard constraints — do not re-litigate.

### Step 3: Execute Scoped Debate

If `instructions.md` contains a **Scope-Based Iteration Plan**, follow the three-tier flow below. If `--no-scopes` was used, skip to the **Flat Mode** section at the bottom.

---

#### Scope 1: ALIGNMENT (all roles, short, parallel)

**Goal:** Directional alignment. "Should we go this way at all?"

For each role in the Role Menu, generate context and spawn advocate + contrarian **in parallel** (all roles simultaneously):

**Before each agent**, generate its context:
```bash
python "$STUDIO_ROOT/run_phase.py" inject-context --run-dir {run_dir} --scope alignment --role {role} --stance advocate
```

**Advocate prompt:**
> You are the **{role_title} Advocate** for this Studio run.
>
> {Paste the inject-context output here — it contains scope guidance, word cap, decision point protocol, and settled decisions.}
>
> Save to `{run_dir}/advocate--{role}--S1-01.md`.

**Contrarian** — generate context with `--stance contrarian`, then spawn a SEPARATE agent:
> You are the **{role_title} Contrarian** for this Studio run.
>
> {Paste the inject-context output here.}
>
> Read the advocate's alignment stance at `{run_dir}/advocate--{role}--S1-01.md`.
>
> End with `VERDICT: APPROVED` or `VERDICT: REJECTED` with numbered reasons.
> Save to `{run_dir}/contrarian--{role}--S1-01.md`.

**After all S1 agents complete (before proceeding to S2):**
1. Run `python "$STUDIO_ROOT/run_phase.py" extract-decisions --run-dir {run_dir} --scope S1`
2. If non-empty, present ALL decision points to user at once — group by role for clarity
3. Record all user answers to `decisions.md` via `record-decisions`
4. Recompute clarity: `python "$STUDIO_ROOT/run_phase.py" recompute-clarity --phase studio --run-id {run_id}`

**After all roles complete:** Read all contrarian verdicts.
- If all APPROVED → proceed to Scope 2 with alignment context
- If any REJECTED → note the rejection reasons. Proceed to Scope 2 anyway (the depth pass will address them), but include rejection context in each rejected role's depth prompt
- If `max_iterations` for alignment scope allows iteration 2, loop rejected roles only (still with 500-word cap)

---

#### Scope 2: DEPTH (per-role, sequential, with briefs and scoped reads)

**Goal:** Detailed analysis per discipline. "How exactly should we do this?"

Process each role **sequentially** (later roles benefit from earlier outputs).

**Token optimization — summarize-then-delegate:** After every 2-3 completed roles, write a condensed 1-page brief (`{run_dir}/S2-brief.md`) summarizing key decisions, concerns, and conditions from completed S2 roles. Update this brief as more roles complete. Later roles read the brief instead of all individual files.

**Scoped reads — each role only reads what's relevant:**

| Role | Must read (S2 files) | Brief sufficient |
|------|---------------------|-----------------|
| Product | (runs first) | S1 alignment only |
| Marketing | Product S2 | S1 alignment |
| Design | Product S2, Marketing S2 | S1 alignment |
| Art | Design S2 | Brief for others |
| Engineering | Design S2, Art S2 | Brief for others |
| Test Engineer | Engineering S2, Design S2 | Brief for others |
| QA | Engineering S2, Test Engineer S2 | Brief for others |

Adjust based on the specific proposal — if a role clearly depends on another's output, add it.

**Before each S2 agent**, generate its context:
```bash
python "$STUDIO_ROOT/run_phase.py" inject-context --run-dir {run_dir} --scope depth --role {role} --stance advocate
```

**Advocate prompt:**
> You are the **{role_title} Advocate** for this Studio run.
>
> {Paste the inject-context output here — it contains scope guidance, deliverables, decision point protocol, settled decisions, clarity context, and prior-scope file lists.}
>
> **Context from prior Depth roles (SCOPED — read only these):**
> - {List specific S2 files this role needs per the dependency map}
> - Condensed brief of all other roles: `{run_dir}/S2-brief.md`
>
> {If this role has a prompt doc, read it at `studio/{prompt_doc}` for detailed guidance.}
>
> Write a thorough proposal covering all required deliverables. No word cap — this is the full analysis.
> Save to `{run_dir}/advocate--{role}--S2-01.md`.

**Contrarian** — generate context with `--stance contrarian`, then spawn a SEPARATE agent:
> You are the **{role_title} Contrarian** for this Studio run.
>
> {Paste the inject-context output here.}
>
> Read the advocate's depth proposal at `{run_dir}/advocate--{role}--S2-{NN}.md`.
>
> **Scoped reads (only these — do NOT read all S2 files):**
> - {1-2 S2 files most relevant per dependency map}
> - Condensed brief: `{run_dir}/S2-brief.md`
>
> Critically evaluate against your focus area with full rigor. Check for:
> - Fatal flaws, unrealistic assumptions, missing considerations
> - Whether alignment-scope concerns were actually addressed
> - Risks that haven't been mitigated
>
> **Escalation triggers** (flag immediately): {escalate_on from Role Menu}
>
> End with `VERDICT: APPROVED` or `VERDICT: REJECTED` with numbered reasons.
> Save to `{run_dir}/contrarian--{role}--S2-{NN}.md`.

**Check decision points** — After each S2 advocate and contrarian saves output, run:
```bash
python "$STUDIO_ROOT/run_phase.py" extract-decisions --run-dir {run_dir} --scope S2
```
If non-empty, follow the Decision Point Handling protocol above. Since S2 is sequential, decisions from earlier roles inform later roles.

**Brief update cadence — MANDATORY:** After every 2-3 roles complete:
1. Run `python "$STUDIO_ROOT/run_phase.py" extract-decisions --run-dir {run_dir}` to gather all decisions
2. Write/update `{run_dir}/S2-brief.md` with key decisions and conditions from completed roles
3. Include a "Settled Decisions" summary referencing `decisions.md`. Keep under 1 page.
4. Run `python "$STUDIO_ROOT/run_phase.py" recompute-clarity --phase studio --run-id {run_id}` to update clarity scores

**Loop:** If REJECTED and iterations remain (up to 3), feed rejection back to advocate. If APPROVED, move to next role.

---

#### Scope 3: POLISH (single consolidated agent)

**Goal:** Cross-discipline gut-check. "Anything still broken across disciplines?"

After all Scope 2 roles are approved, run **one consolidated agent** — not per-role pairs.

**Consolidated polish prompt (ONE agent):**
> You are the **Cross-Discipline Polish Reviewer** for this Studio run.
>
> Read these files:
> - Condensed S2 brief: `{run_dir}/S2-brief.md`
> - All S2 contrarian files: `{run_dir}/contrarian--*--S2-*.md` (for conditions attached to each approval)
>
> Produce a single document covering:
> 1. **Unresolved cross-discipline conflicts** — where one role's decision contradicts another's
> 2. **Conditions that overlap or conflict** — where two contrarians demanded incompatible things
> 3. **Gaps between roles** — concerns that fell between disciplines and no one owns
> 4. **Consolidated open items** — deduplicated list of all conditions, grouped by priority
>
> {If `{run_dir}/decisions.md` exists: "**Settled decisions:** Read `{run_dir}/decisions.md`. These are user-confirmed constraints. Flag in your review if any cross-discipline conflict involves a settled decision."}
>
> Do NOT introduce new proposals or repeat S2 analysis.
> **Keep under 800 words.** End with `VERDICT: APPROVED` or `VERDICT: REJECTED` with numbered reasons.
> Save to `{run_dir}/polish--consolidated--S3-01.md`.

**No iteration** — single pass. If REJECTED, note concerns for integrator but proceed.

---

### Step 4: Integrator Duel (after Scope 3)

Same as standard integrator flow. Create `{run_dir}/integrator.md`:

#### a. Integrator Advocate

> You are the **Integrator Advocate** — a Systems Integrator & Ops Lead.
>
> Read these artifacts (briefs over full files):
> - S2 condensed brief: `{run_dir}/S2-brief.md` (primary context)
> - S3 consolidated polish: `{run_dir}/polish--consolidated--S3-01.md` (cross-discipline conflicts and open items)
> - S1 alignment verdicts: skim `{run_dir}/*--S1-*.md` for rejected roles and key flags
>
> You do NOT need to read every individual S2 advocate/contrarian file — the brief and polish doc contain the distilled decisions.
>
> {If `{run_dir}/decisions.md` exists: "**Settled decisions:** Read `{run_dir}/decisions.md` — incorporate all settled constraints into your unified plan."}
>
> Synthesize a unified plan. Write as `### Integrator Advocate` in `{run_dir}/integrator.md`.

#### b. Integrator Contrarian

> You are the **Integrator Contrarian** — Director of Live Service Operations.
>
> Read `{run_dir}/integrator.md`. Critique for feasibility, sequencing, and missing concerns.
> End with `VERDICT: APPROVED` or `VERDICT: REJECTED`.
> Append as `### Integrator Contrarian` in `{run_dir}/integrator.md`.

#### c. Integrated Plan

Append `### Integrated Plan` to `{run_dir}/integrator.md`.

### Step 5: Summary

Write `{run_dir}/summary.md` covering:
- Original input/objective
- Scope progression (what was caught at each tier)
- Which roles participated and their verdicts per scope
- The integrated plan highlights
- Concrete next actions

### Step 6: Finalize

```bash
python "$STUDIO_ROOT/run_phase.py" finalize --phase studio --run-id {run_id} --status completed --verdict {APPROVED|REJECTED}
```

---

## Flat Mode (--no-scopes)

When `--no-scopes` is used, fall back to the original single-tier flow:

For each role sequentially:
1. Spawn advocate agent (full depth, no word cap)
   - Include the Decision Point Protocol inline (format example + P0/P1/P2 levels)
   - Include settled decisions context if `{run_dir}/decisions.md` exists
2. Spawn SEPARATE contrarian agent
   - Include the Decision Point Protocol inline (format + "flag unsettled assumptions")
   - Include settled decisions context if `{run_dir}/decisions.md` exists
3. **Check decision points** — follow the Decision Point Handling protocol after each advocate and contrarian output
4. If REJECTED and iterations remain, loop
5. If APPROVED, next role

Then run integrator duel and summary as above.

## Key Rules

- **Advocate and Contrarian MUST be separate Agent invocations** — no shared context.
- **Scope 1 runs all roles in parallel** — short enough to parallelize.
- **Scope 2 runs roles sequentially** with scoped reads and rolling briefs (`S2-brief.md`).
- **Scope 3 is a single consolidated agent** — one cross-discipline check, not per-role pairs.
- **Briefs over full reads** — later roles and integrator read `S2-brief.md` instead of all individual files.
- **Word caps are instruction-enforced** — include them in the agent prompt, not as runtime truncation.
- **Decision points are checked after every agent** — S1 batches (parallel), S2 checks per-role (sequential), S3 and integrator receive all accumulated decisions.
- **`decisions.md` is the single source of truth** for settled constraints, accumulating throughout the run.
- File naming: `advocate--marketing--S1-01.md`, `contrarian--engineering--S2-02.md`, `polish--consolidated--S3-01.md`
