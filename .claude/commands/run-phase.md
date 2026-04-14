# Studio Phase Run

Execute a structured advocate/contrarian debate for game development decisions.

## Arguments

- `$ARGUMENTS` — Required. Format: `--phase <market|design|tech> --text "your idea or objective"`
- Optional: `--max-iterations N` (default 3)

## Instructions

You are executing a Studio phase run. Follow these steps exactly:

### Step 1: Prepare

Run the prepare command to create a run directory and instructions:

**Studio path:** Use `.studio/source/run_phase.py` for all commands below. If that file does not exist but `studio/run_phase.py` does, use `studio/run_phase.py` instead (you are in the Studio source repo).

```bash
python ".studio/source/run_phase.py" prepare $ARGUMENTS
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
> {If `{run_dir}/clarity.json` exists, run `python ".studio/source/run_phase.py" show-clarity` and include the output here. Tell the agent: "**Clarity context:** Topics marked Settled are constraints — do not re-litigate. For topics marked Needs work, actively surface decision points. For Settling topics, only flag genuine new gaps."}
>
> **Decision Point Protocol:** When you encounter a gap, ambiguity, or fork that could meaningfully change your approach, flag it inline using this exact blockquote format:
>
> ```
> > **DECISION [P0]:** Should the mechanic be real-time or turn-based?
> > **Unblocks:** Core loop design — fundamentally different gameplay
> > **Options:** (a) Real-time (b) Turn-based
> ```
>
> Priority levels:
> - **P0 (Blocking):** Cannot proceed without an answer. The orchestrator will pause and ask the user.
> - **P1 (Important):** State your assumption and continue, but flag it so the user can override.
> - **P2 (Context):** Nice-to-know, logged for completeness.
>
> Surface decision points as you encounter them. Prefer fewer, high-quality P0/P1 flags over many P2s. Each must name what it unblocks.
>
> Write a thorough advocate proposal. Structure it with clear sections, concrete recommendations, and actionable details. Save your output to `{run_dir}/advocate_{N}.md`.

**b. Record metrics and extract decision points — MANDATORY, DO NOT SKIP**

First, record the agent's token usage from the `<usage>` block in the Agent tool result:
```bash
python ".studio/source/run_phase.py" record-metrics --run-dir {run_dir} --agent advocate --total-tokens {N} --tool-uses {N} --duration-ms {N}
```

Then extract decision points:
```bash
python ".studio/source/run_phase.py" extract-decisions --run-dir {run_dir}
```

**If the output is non-empty (any decision points found), you MUST pause and present them ALL to the user before proceeding.** Do not continue to the contrarian until the user has responded.

Present each decision to the user:

  **Decision [priority]:** [question]
  Unblocks: [context]
  Options: [options if present]

Wait for the user to answer ALL decisions. Then record them in one batch — write a JSON file and run:
```bash
python ".studio/source/run_phase.py" record-decisions --run-dir {run_dir} --decisions-file {tmp_json_path}
```
JSON format: `[{"priority": "P0", "question": "...", "answer": "...", "unblocks": "...", "source_file": "advocate_{N}.md", "answered_by": "user"}, ...]`

After recording, show updated clarity scores to the user:
```bash
python ".studio/source/run_phase.py" show-clarity
```
This displays per-topic confidence scores so the user can see which areas are settling and which still need work. If a topic score seems wrong, the user can override: `python ".studio/source/run_phase.py" set-clarity --topic <slug> --score <0.0-1.0>`.

**c. Contrarian** — Use the Agent tool to spawn a SEPARATE subagent with this prompt:

> You are the **Contrarian** for this Studio run. Your role: {contrarian role from instructions.md}.
>
> {If `{run_dir}/decisions.md` exists: "Read `{run_dir}/decisions.md` first. Treat settled decisions as hard constraints — do not re-litigate them. Focus your critique on everything else."}
>
> {If clarity data exists, include the same clarity context from the advocate prompt above — settled topics are constraints, unsettled topics should be explored.}
>
> Read the advocate's proposal at `{run_dir}/advocate_{N}.md`.
>
> **Decision points:** If the advocate assumed something that is actually unsettled, flag it using this blockquote format:
> `> **DECISION [P0]:** [question]`
> `> **Unblocks:** [what this decision affects]`
> `> **Options:** (a) ... (b) ...`
> Your primary job is critique — decision points are secondary, only when assumptions are genuinely unsettled.
>
> Critically evaluate the proposal. Look for fatal flaws, unrealistic assumptions, missing considerations, and risks. Be rigorous but fair.
>
> End your response with exactly `VERDICT: APPROVED` or `VERDICT: REJECTED`.
> If REJECTED, list specific numbered reasons that must be addressed.
>
> Save your output to `{run_dir}/contrarian_{N}.md`.

**d. Record contrarian metrics and extract decision points** — Record the contrarian's token usage:
```bash
python ".studio/source/run_phase.py" record-metrics --run-dir {run_dir} --agent contrarian --total-tokens {N} --tool-uses {N} --duration-ms {N}
```
Then run `python ".studio/source/run_phase.py" extract-decisions --run-dir {run_dir}` again. If new decision points appear (from the contrarian), present them to the user and record as in step (b).

**e. Check verdict** — Read the contrarian output. If `VERDICT: APPROVED`, proceed to Step 4. If `VERDICT: REJECTED` and iterations remain, loop back to (a) with the rejection feedback.

### Step 4: Implementation (if approved)

For market/design/tech phases, after approval the instructions.md lists an Implementer role with specific deliverables. Generate the implementation and save to `{run_dir}/implementation.md`.

### Step 5: Summary

Write a summary of the entire run (inputs, iterations, verdict, key recommendations, next actions) and save to `{run_dir}/summary.md`.

### Step 6: Finalize

```bash
python ".studio/source/run_phase.py" finalize --phase {phase} --run-id {run_id} --status completed --verdict {APPROVED|REJECTED}
```

## Key Rules

- **Advocate and Contrarian MUST be separate Agent invocations** — this prevents the contrarian from being influenced by having generated the advocate's arguments.
- The contrarian must ONLY read the advocate's written file, not share context.
- Each iteration produces exactly one `advocate_N.md` and one `contrarian_N.md`.
- Stop iterating when APPROVED or when max iterations are exhausted.
- **All P0 decisions from a single agent are presented to the user at once** — do not ask one at a time.
- **`decisions.md` accumulates across the full run** — decisions settled in iteration 1 carry forward as constraints for all subsequent iterations.
