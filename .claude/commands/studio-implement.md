# Studio Implement (Writer/Editor Loop)

Build one MVI unit through the implementation writer/editor loop: a writer agent builds a
complete, usable unit and commits its passing state; a fresh editor agent (carrying the
`CONTRARIAN_MANDATE`) cuts/refines it, reverting if an edit breaks green; then it's delivered.
See `studio/docs/IMPLEMENTATION_LOOP_SPEC.md` for the full design.

This command is the **authorized, unequivocal trigger** for the loop. Invoking it is explicit
opt-in to run the `implementation-loop` workflow (which spawns multiple agents). When the user
asks in natural language to "implement X with the loop" / "run the writer-editor loop on X",
treat that as an invocation of this command.

## Arguments

- `$ARGUMENTS` — Required. Free-text description of the ONE unit to build. Should describe a
  complete, usable interaction (MVI), not a partial component.
- Optional `--branch <name>` — branch to run on (default: derive `impl/<unit_id>`).
- Optional `--test "<cmd>"` — override the inferred test command.
- Optional `--plan` — echo the parsed plan and STOP (dry run); do not run the loop.

## Instructions

Run behavior is **echo-plan-then-run**: print the plan, then immediately run the loop (no
separate confirmation step — the slash invocation is the authorization). `--plan` is the only
thing that stops before running.

### Step 1 — Parse the request into a unit object

From `$ARGUMENTS`, construct the workflow `args`:

- `unit_id` — a short snake_case slug derived from the request (e.g. `profile_create_view`).
- `title` — a one-line MVI-framed statement of the usable outcome ("X can do Y …"). If the
  request describes a partial component ("add a data model", "define the schema"), reframe it as
  the smallest usable interaction, or stop and say it isn't an MVI unit.
- `instructions` — concrete build steps: what files to create/modify, what tests to write. Keep
  it to this one unit; no speculative scope.
- `test_command` — infer from the repo's stack unless `--test` is given. Detect from marker files:
  - Python (`pyproject.toml`/`pytest`): `python -m pytest <path> -q` (in this repo: `cd studio && python -m pytest tests/<file> -q`).
  - Node (`package.json`): `npm test` or the project's test script.
  - Rust (`Cargo.toml`): `cargo test`.
  - Unity / other: ask if you cannot infer a runnable command.
  - If you cannot infer one, fall back to the config knob `test_command` from `python -m impl_loop` (Step 4).
- `static_check` — `ruff check <path>` for Python; the project linter otherwise; omit if none.

### Step 2 — Pick the target branch (safety)

The loop edits files in place and makes a real `git commit`, and the writer + editor stages must
share one working tree. So:

```bash
git rev-parse --abbrev-ref HEAD
```

- If `--branch` was given, check it out (create if missing).
- Else if on `main`/`master`, create and switch to `impl/<unit_id>`.
- Else use the current branch (it's already a feature branch).

If the working tree is dirty, stop and tell the user to commit/stash first — the loop's revert
relies on a clean base.

### Step 3 — Echo the plan

Print a short block, then proceed (unless `--plan`):

```
/studio-implement
  unit_id:  <slug>
  title:    <MVI outcome>
  branch:   <branch>
  tests:    <test_command>
  builds:   <1-line of what files/behavior>
```

If `--plan`, stop here.

### Step 4 — Load config knobs, then run the loop

First read the loop config so the run honors `implementation_loop.toml` (run from the `studio/`
package dir):

```bash
python -m impl_loop   # prints knobs JSON, e.g. {"editor_enabled": true, "read_scope": "touched+importers", "output_budget": 400, ...}
```

Then call the **Workflow** tool **by `scriptPath`** (NOT `name` — see Gotchas), merging the
config knobs into the unit args:

```
Workflow({ scriptPath: "<repo>/.claude/workflows/implementation-loop.js", args: {
  unit_id, title, instructions, static_check,
  test_command,            // per-unit inferred; if none, use the knob test_command
  editor_enabled, read_scope, output_budget,           // from `python -m impl_loop`
  static_checks, require_mutation_check                // from `python -m impl_loop`
}})
```

How the workflow consumes each knob: `editor_enabled=false` → skip the editor pass;
`read_scope`/`output_budget` → shape the editor prompt; `require_mutation_check=false` → writer
skips the mutation check; `static_checks=[]` → writer skips the static check and the entry gate
doesn't require it. So passing all knobs makes `implementation_loop.toml` fully live.

The workflow runs in the background and notifies on completion. Do not re-run it or poll;
wait for the completion notification.

#### Gotchas (learned the hard way — do not regress these)

- **Invoke by `scriptPath`, never `name`.** `Workflow({name})` resolves a FROZEN registry snapshot
  captured early in the session; it ignores on-disk edits to the workflow file. `scriptPath` (the
  absolute path to `.claude/workflows/implementation-loop.js`) reads the live file.
- **`args` reaches the workflow as a JSON string**, not an object — the workflow `JSON.parse`s it.
  Pass args as a normal object here; just don't be surprised the workflow normalizes a string.
- If `editor_enabled` is false (config `mandate = "off"`), the loop skips the editor pass and
  delivers the writer's version (`editorRan: false`).

### Step 5 — Report the result

The workflow returns `{ delivered, flagged, editorRan, finalVersion, writer, editor }`. Summarize
for the user:

- **What was built** + final test status (`editor.tests` / `writer.tests`).
- **What the editor changed** (`editor.edits`) — the cuts/merges/restructures, or "nothing to cut".
- **MVI verdict** (`editor.mvi_verdict`) — and call out explicitly if the editor *overturned* the
  writer's `mvi_claimed` (unit not actually usable → it's flagged, not silently shipped).
- **Reverted?** (`editor.reverted`) — if an edit broke green and was rolled back to `writer_sha`.
- Point to the handoff records under `.studio/output/impl_loop/<unit_id>/`.

If `flagged` is true, make clear the unit did NOT pass the full gate (delivered for inspection,
not as a clean green/usable unit).
