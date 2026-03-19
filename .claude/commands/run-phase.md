# Studio Phase Run

Execute a structured advocate/contrarian debate for game development decisions.

## Arguments

- `$ARGUMENTS` — Required. Format: `--phase <market|design|tech> --text "your idea or objective"`
- Optional: `--max-iterations N` (default 3)

## Instructions

You are executing a Studio phase run. Follow these steps exactly:

### Step 1: Prepare

Run the prepare command to create a run directory and instructions:

Determine the Studio root path. If this repo contains a `studio/run_phase.py`, use that. Otherwise check `$STUDIO_ROOT`. Then run:

```bash
python "$STUDIO_ROOT/run_phase.py" prepare $ARGUMENTS
```

If running from a repo that is NOT the Studio repo itself, artifacts will automatically land in the current repo under `.studio/output/`. A bridge doc will be created on first use.

Note the run_id and run directory path from the output.

### Step 2: Read Instructions

Read the generated `instructions.md` file in the run directory. It contains the phase-specific advocate/contrarian personas, iteration rules, and deliverable requirements.

### Step 3: Execute Advocate/Contrarian Loop

For each iteration (up to max_iterations):

**a. Advocate** — Use the Agent tool to spawn a subagent with this prompt:

> You are the **Advocate** for this Studio run. Your role: {advocate role from instructions.md}.
>
> Input/objective: {the user's text}
>
> {If iteration > 1, include: "Previous contrarian feedback to address:" followed by the rejection reasons from the prior contrarian output.}
>
> {If `{run_dir}/decisions.md` exists: "Read `{run_dir}/decisions.md` for settled constraints from prior iterations. Treat these as hard constraints — do not re-litigate."}
>
> Write a thorough advocate proposal. Structure it with clear sections, concrete recommendations, and actionable details. Save your output to `{run_dir}/advocate_{N}.md`.

**b. Check advocate decision points** — Read the advocate's output file (`{run_dir}/advocate_{N}.md`). Look for decision point blockquotes matching this pattern:

> **DECISION [P0]:** [question]
> **Unblocks:** [context]
> **Options:** (a) ... (b) ...

Handle by priority:

- **P0 (blocking):** Present ALL P0 decisions to the user at once. Format each as:

  **Blocking Decision:** [question]
  Unblocks: [context]
  Options: [options if present]

  Wait for the user to answer each P0 decision. Then record ALL decisions from this agent in one batch — write a JSON file with all decisions and their answers, then run:
  ```bash
  python "$STUDIO_ROOT/run_phase.py" record-decisions --run-dir {run_dir} --decisions-file {tmp_json_path}
  ```
  The JSON file format: `[{"priority": "P0", "question": "...", "answer": "...", "unblocks": "...", "source_file": "advocate_{N}.md", "answered_by": "user"}, ...]`

  Alternatively, for a single decision: `python "$STUDIO_ROOT/run_phase.py" record-decisions --run-dir {run_dir} --question "[question]" --answer "[answer]" --priority P0 --source "advocate_{N}.md" --unblocks "[context]" --answered-by user`

- **P1 (important):** Show to the user as FYI: "The advocate is assuming [stated assumption/first option] for: [question]. Override? (press Enter to accept)". Include in the batch JSON with `"answered_by": "user"` (if overridden) or `"answered_by": "assumption"` (if accepted).

- **P2 (context):** No user interaction. Include in the batch JSON with `"answered_by": "logged"`.

**c. Contrarian** — Use the Agent tool to spawn a SEPARATE subagent with this prompt:

> You are the **Contrarian** for this Studio run. Your role: {contrarian role from instructions.md}.
>
> {If `{run_dir}/decisions.md` exists: "Read `{run_dir}/decisions.md` first. Treat settled decisions as hard constraints — do not re-litigate them. Focus your critique on everything else."}
>
> Read the advocate's proposal at `{run_dir}/advocate_{N}.md`.
>
> Critically evaluate the proposal. Look for fatal flaws, unrealistic assumptions, missing considerations, and risks. Be rigorous but fair.
>
> End your response with exactly `VERDICT: APPROVED` or `VERDICT: REJECTED`.
> If REJECTED, list specific numbered reasons that must be addressed.
>
> Save your output to `{run_dir}/contrarian_{N}.md`.

**d. Check contrarian decision points** — Same process as step (b) but for `{run_dir}/contrarian_{N}.md`. Contrarians rarely flag new decisions, but when they do (e.g., "the advocate assumed X but that's actually unsettled"), handle identically.

**e. Check verdict** — Read the contrarian output. If `VERDICT: APPROVED`, proceed to Step 4. If `VERDICT: REJECTED` and iterations remain, loop back to (a) with the rejection feedback.

### Step 4: Implementation (if approved)

For market/design/tech phases, after approval the instructions.md lists an Implementer role with specific deliverables. Generate the implementation and save to `{run_dir}/implementation.md`.

### Step 5: Summary

Write a summary of the entire run (inputs, iterations, verdict, key recommendations, next actions) and save to `{run_dir}/summary.md`.

### Step 6: Finalize

```bash
python "$STUDIO_ROOT/run_phase.py" finalize --phase {phase} --run-id {run_id} --status completed --verdict {APPROVED|REJECTED}
```

## Key Rules

- **Advocate and Contrarian MUST be separate Agent invocations** — this prevents the contrarian from being influenced by having generated the advocate's arguments.
- The contrarian must ONLY read the advocate's written file, not share context.
- Each iteration produces exactly one `advocate_N.md` and one `contrarian_N.md`.
- Stop iterating when APPROVED or when max iterations are exhausted.
- **All P0 decisions from a single agent are presented to the user at once** — do not ask one at a time.
- **`decisions.md` accumulates across the full run** — decisions settled in iteration 1 carry forward as constraints for all subsequent iterations.
