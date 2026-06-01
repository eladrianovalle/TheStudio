# Studio Setup Wizard

Configure this project's Studio installation — role packs, role/phase-persona customization, scope tuning, cleanup settings.

## Arguments

- `$ARGUMENTS` — Optional. Pass `--status` to check current config, or `--defaults` to apply all defaults without prompts.

## Instructions

You are running the Studio setup wizard. This walks the user through configuring their Studio installation. Follow these steps exactly:

**Studio path:** Use `.studio/source/run_phase.py` for all commands below. If that file does not exist but `studio/run_phase.py` does, use `studio/run_phase.py` instead (you are in the Studio source repo).

### Step 0: Check Arguments

If the user passed `--defaults`, apply defaults and stop:

```bash
python ".studio/source/run_phase.py" setup --target . --defaults
```

Report what was applied and stop.

If the user passed `--status`, show status and stop:

```bash
python ".studio/source/run_phase.py" setup --target . --status
```

### Step 1: Verify Installation

Check that `.studio/VERSION` exists in this project. If not, tell the user:

> Studio isn't installed in this project. Run `python .studio/source/run_phase.py init --target .` first, or install from the Studio source repo.

And stop.

### Step 2: Check Current Setup Status

```bash
python ".studio/source/run_phase.py" setup --target . --status
```

If all steps are already configured, tell the user their setup is complete. Ask if they want to reconfigure anything. If not, stop.

If steps are pending, tell the user which ones need configuration and proceed.

### Step 3: Role Pack Selection

Read the available role packs:

```bash
ls ".studio/source/role_packs/"
```

Read each pack file to get names, descriptions, and roles. Present them as a numbered list:

```
Available role packs:
1. studio_core (7 roles) — Default pod: marketing, product, design, art, engineering, test_engineer, qa
2. studio_core_with_ml (9 roles) — Core + ML and PMM
3. pictorly_execution (5 roles) — Focused: product, design, engineering, test_engineer, qa
4. orcpunk_web (3 roles) — Web-focused: web_engineering, web_test_engineer, web_qa
```

Ask the user: **"Which role pack fits your project? (pick a number, or type a pack name)"**

After they choose, read the full role catalog from the manifest:

```bash
python -c "import json; m=json.load(open('.studio/source/studio.manifest.json')); [print(f'  {k}: {v[\"title\"]}') for k,v in m['roles'].items()]"
```

Ask: **"Want to add (+) or remove (-) any individual roles? (e.g., '+ml -art', or 'none')"**

Apply the choice:

```bash
python ".studio/source/run_phase.py" setup --target . --role-pack <name> --roles <overrides>
```

### Step 4: Role Customization (Optional)

Ask: **"Do you want to customize any role's focus areas or deliverables? Most users skip this — the defaults are solid."**

If the user says no/skip, apply empty customization to mark the step complete:

```bash
python ".studio/source/run_phase.py" setup --target . --answers '{"role_customizations": {}}'
```

If yes, for each role the user wants to customize:

1. Read the role's current definition from the manifest and show it:
   - Title
   - Advocate focus
   - Contrarian focus
   - Deliverables
   - Escalation triggers

2. Ask what they want to change. Valid fields: `title`, `advocate_focus`, `contrarian_focus`, `deliverables`, `escalate_on`.

3. Build a JSON answers file with the customizations and apply:

```bash
python ".studio/source/run_phase.py" setup --target . --answers '<json with role_customizations>'
```

### Step 5: Phase Persona Customization (Optional)

The single-phase advocate / contrarian / implementer / integrator personas ship as
stack-neutral defaults (e.g. tech advocate = "Technical Architect"). A project can
tailor them per phase — writing `.studio/personas.toml` — so a Rust repo gets a
"Rust Systems Architect" instead.

Ask: **"Do you want to tailor the phase personas to your tech stack? Most users skip this — the neutral defaults are fine."**

If the user says no/skip, apply empty customization to mark the step complete (no file written, neutral defaults stand):

```bash
python ".studio/source/run_phase.py" setup --target . --answers '{"persona_customizations": {}}'
```

If yes, for each phase the user wants to customize (`market`, `design`, `tech`, `studio`):

1. Valid string keys per phase: `advocate`, `contrarian`, `notes`. `integrator` is allowed **only** under `studio`. A nested `implementer` table (keys `title`, `deliverables`) is allowed for `market`/`design`/`tech` only — not `studio`.

2. Build a JSON answers file with the customizations and apply:

```bash
python ".studio/source/run_phase.py" setup --target . --answers '<json with persona_customizations>'
```

### Step 6: Scope Tuning

Show the default scope configuration:

```
Default scopes (three-tier debate):
  alignment: 2 iterations, 500-word cap, all roles in parallel
  depth:     3 iterations, no word cap, roles debate sequentially
  polish:    1 iteration,  300-word cap, all roles in parallel
```

Ask: **"Want to adjust iteration counts or word budgets? The defaults work well for most projects. (yes/no)"**

If no, apply defaults:

```bash
python ".studio/source/run_phase.py" setup --target . --answers '{"scopes": "defaults"}'
```

If yes, walk through each scope asking about:
- `max_iterations` — how many advocate/contrarian rounds
- `output_budget` — word cap per agent output (optional)
- `debate_mode` — "all_roles" (parallel) or "per_role" (sequential)

Build the scopes config and apply via answers JSON.

### Step 7: Cleanup Settings

Show the defaults:

```
Artifact cleanup defaults:
  TTL: 30 days (runs older than this are automatically deleted)
  Size limit: 900 MB (oldest runs deleted when exceeded)
```

Ask: **"Want to change artifact retention settings? (yes/no)"**

If no, apply defaults:

```bash
python ".studio/source/run_phase.py" setup --target . --answers '{"cleanup": {"ttl_days": 30, "size_limit_mb": 900}}'
```

If yes, ask for TTL (days) and size limit (MB), then apply.

### Step 8: Summary

Show the final configuration:

```bash
python ".studio/source/run_phase.py" setup --target . --status
```

Tell the user:

> Setup complete! You can re-run `/studio-setup` anytime to reconfigure, or `/studio-setup --status` to check your current config.

## Key Rules

- **Always show defaults** and explain what each setting does before asking
- **Accept "defaults" or "skip"** for any step — never force the user through every question
- **One step at a time** — don't dump all questions at once
- **Apply each step immediately** via CLI — don't batch them. This way partial completion is preserved if the user stops mid-wizard
- **Never skip a pending step silently** — always at least mention it and offer the default
- When showing roles, include their title so the user knows what each one does
