# Studio Phase Run (Multi-Role)

Execute a multi-role advocate/contrarian debate across disciplines (marketing, product, design, art, engineering, QA, etc.).

## Arguments

- `$ARGUMENTS` — Required. Format: `--text "your idea or objective"`
- Optional: `--role-pack <name>` (default: studio_core), `--roles +role -role`, `--max-iterations N` (default 3)

## Instructions

You are executing a Studio multi-role phase run. Follow these steps exactly:

### Step 1: Prepare

Run the prepare command to create a run directory and instructions:

Determine the Studio root path. If this repo contains a `studio/run_phase.py`, use that. Otherwise check `$STUDIO_ROOT`. Then run:

```bash
python "$STUDIO_ROOT/run_phase.py" prepare --phase studio $ARGUMENTS --no-scopes
```

If running from a repo that is NOT the Studio repo itself, artifacts will automatically land in the current repo under `.studio/output/`. A bridge doc will be created on first use.

Note the run_id and run directory path from the output.

### Step 2: Read Instructions and Role Menu

Read the generated `instructions.md` file. Pay attention to:
- The **Role Menu** table listing each invited role with its advocate/contrarian focuses and deliverables
- The file naming convention: `advocate--<role>--<NN>.md` and `contrarian--<role>--<NN>.md`
- The integrator duel section

### Step 3: Process Each Role Sequentially

For each role listed in the Role Menu (process them in order):

#### a. Role Advocate

Use the Agent tool to spawn a subagent:

> You are the **{role_title} Advocate** for this Studio run.
>
> **Focus:** {advocate_focus from Role Menu}
>
> **Input/objective:** {the user's text}
>
> **Required deliverables:**
> {deliverables list from Role Menu}
>
> {If this role has a prompt doc, read it at `studio/{prompt_doc}` for detailed guidance.}
>
> {If iteration > 1: "Previous contrarian feedback to address:" + rejection reasons}
>
> Write a thorough advocate proposal covering all required deliverables. Save to `{run_dir}/advocate--{role}--{NN}.md`.

#### b. Role Contrarian

Use the Agent tool to spawn a SEPARATE subagent:

> You are the **{role_title} Contrarian** for this Studio run.
>
> **Focus:** {contrarian_focus from Role Menu}
>
> Read the advocate's proposal at `{run_dir}/advocate--{role}--{NN}.md`.
>
> Critically evaluate against your focus area. Check for:
> - Fatal flaws in the proposal
> - Unrealistic assumptions
> - Missing considerations specific to your domain
> - Risks that haven't been addressed
>
> **Escalation triggers** (flag immediately if found): {escalate_on from Role Menu}
>
> End with exactly `VERDICT: APPROVED` or `VERDICT: REJECTED`.
> If REJECTED, list specific numbered reasons.
>
> Save to `{run_dir}/contrarian--{role}--{NN}.md`.

#### c. Check Verdict

Read the contrarian output. If `VERDICT: REJECTED` and iterations remain for this role, loop back to (a) with rejection feedback. If `VERDICT: APPROVED`, move to the next role.

### Step 4: Integrator Duel (after all roles complete)

Once all roles have been processed, create `{run_dir}/integrator.md` using separate Agent invocations:

#### a. Integrator Advocate

Use the Agent tool:

> You are the **Integrator Advocate** — a Systems Integrator & Ops Lead.
>
> Read ALL approved advocate and contrarian files from the run directory to understand what each discipline proposed and what concerns were raised.
>
> Synthesize a unified plan that:
> - Merges insights from all roles into a coherent roadmap
> - Sequences work by priority and dependency
> - Identifies cross-functional dependencies
> - Proposes concrete next steps with owners
>
> Write your synthesis as `### Integrator Advocate` in `{run_dir}/integrator.md`.

#### b. Integrator Contrarian

Use a SEPARATE Agent:

> You are the **Integrator Contrarian** — a Director of Live Service Operations.
>
> Read `{run_dir}/integrator.md` (the Integrator Advocate section).
>
> Critique the integrated plan for:
> - Feasibility and resource constraints
> - Operational risk and maintenance burden
> - Sequencing issues and dependency conflicts
> - Missing stakeholders or unresolved tensions between roles
>
> End with `VERDICT: APPROVED` or `VERDICT: REJECTED` with numbered reasons.
> If REJECTED, the integrator gets one revision (max 2 total integrator iterations).
>
> Append your review as `### Integrator Contrarian` in `{run_dir}/integrator.md`.

#### c. Integrated Plan

After the integrator duel resolves (approved or max iterations), append a `### Integrated Plan` section to `{run_dir}/integrator.md` that synthesizes both perspectives into the final roadmap with next steps.

### Step 5: Summary

Write `{run_dir}/summary.md` covering:
- Original input/objective
- Which roles participated and their verdicts
- Key recommendations from each discipline
- The integrated plan highlights
- Concrete next actions

### Step 6: Finalize

```bash
python "$STUDIO_ROOT/run_phase.py" finalize --phase studio --run-id {run_id} --status completed --verdict {APPROVED|REJECTED}
```

## Key Rules

- **Each role's Advocate and Contrarian MUST be separate Agent invocations** — no shared context.
- **Process roles sequentially** — later roles can benefit from reading earlier roles' outputs if relevant.
- **Integrator Advocate and Contrarian are also separate agents.**
- The contrarian reads ONLY the advocate's written file for that role.
- File naming: `advocate--marketing--01.md`, `contrarian--engineering--02.md`, etc.
- The integrator reads ALL role artifacts to synthesize.
