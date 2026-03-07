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
python "$STUDIO_ROOT/run_phase.py" prepare $ARGUMENTS --no-scopes
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
> Write a thorough advocate proposal. Structure it with clear sections, concrete recommendations, and actionable details. Save your output to `{run_dir}/advocate_{N}.md`.

**b. Contrarian** — Use the Agent tool to spawn a SEPARATE subagent with this prompt:

> You are the **Contrarian** for this Studio run. Your role: {contrarian role from instructions.md}.
>
> Read the advocate's proposal at `{run_dir}/advocate_{N}.md`.
>
> Critically evaluate the proposal. Look for fatal flaws, unrealistic assumptions, missing considerations, and risks. Be rigorous but fair.
>
> End your response with exactly `VERDICT: APPROVED` or `VERDICT: REJECTED`.
> If REJECTED, list specific numbered reasons that must be addressed.
>
> Save your output to `{run_dir}/contrarian_{N}.md`.

**c. Check verdict** — Read the contrarian output. If `VERDICT: APPROVED`, proceed to Step 4. If `VERDICT: REJECTED` and iterations remain, loop back to (a) with the rejection feedback.

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
