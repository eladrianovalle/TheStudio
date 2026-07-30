# Forge (Writer/Editor Loop)

Build one MVI unit through the implementation writer/editor loop: a writer agent builds a
complete, usable unit and commits its passing state; a fresh editor agent (carrying the
`CONTRARIAN_MANDATE`) cuts/refines it, reverting if an edit breaks green; then it's delivered.
Point it at an approved spec with `--spec` and the editor also grades the unit against that spec's
acceptance criteria, one at a time. See `studio/docs/IMPLEMENTATION_LOOP_SPEC.md` for the full design.

This command is the **authorized, unequivocal trigger** for the loop. Invoking it is explicit
opt-in to run the `implementation-loop` workflow (which spawns multiple agents). When the user
asks in natural language to "implement X with the loop" / "run the writer-editor loop on X",
treat that as an invocation of this command.

## Arguments

- `$ARGUMENTS`: Required. Free-text description of the ONE unit to build. Should describe a
  complete, usable interaction (MVI), not a partial component.
- Optional `--spec <slug-or-path>`: an approved spec (written by `/spec`) whose Build Plan carries
  this unit's acceptance criteria. Given this, the editor grades the built unit against those
  criteria one by one instead of against the title alone. Without it, nothing changes.
- Optional `--unit <unit_id>`: which unit of that spec's Build Plan to build. Only meaningful with
  `--spec`, and optional when the Build Plan has exactly one unit.
- Optional `--branch <name>`: branch to run on (default: derive `impl/<unit_id>`).
- Optional `--work-dir <path>`: the directory the loop's agents build in. Must be a git worktree
  of this repository; it is validated in Step 3 and a bad path stops the run before any agent
  spawns. Without it, the agents work wherever their shell starts, as they always have.
- Optional `--test "<cmd>"`: override the inferred test command.
- Optional `--plan`: echo the parsed plan and STOP (dry run); do not run the loop.

## Instructions

Run behavior is **echo-plan-then-run**: print the plan, then immediately run the loop (no
separate confirmation step; the slash invocation is the authorization). `--plan` is the only
thing that stops before running.

### Step 1: Resolve `--spec` into acceptance criteria

If no `--spec` was given, skip this whole step and go to Step 2 — behavior is exactly as it has
always been, with one addition to the plan echo (Step 4).

**Find the spec file.** If `--spec` names a file that exists, use it (try appending `.md` if the bare
path doesn't). Otherwise treat it as a slug and resolve it with the **same repo-shape signal this
command already uses** to locate `impl_loop.py` in Step 5 — one detection rule in this file, not two:

- Studio installed under `.studio/source` (you are in a consuming repo): `.studio/specs/<slug>.md`.
- No such install but a root `studio/` dir is present (you are in the Studio source repo):
  `specs/<slug>.md`.

**Find the unit's criteria.** Read the spec's `## Build Plan` section. It is a numbered list of
units, each entry opening with a backticked `unit_id`. Take the entry whose `unit_id` matches
`--unit`; if the Build Plan holds exactly one unit, `--unit` may be omitted and that unit is used.
This unit's criteria are the `- [ ]` bullets under that entry's `**Acceptance criteria:**` line.

Copy each criterion **verbatim** into `acceptance_criteria` (Step 2's args block) — the exact
sentence from the spec, not a paraphrase, a shortening, a softening, or two bullets merged into one.
Same quote discipline the contrarian mandate imposes on findings: the spec's words are the words the
editor grades and quotes back in its verdicts.

**If the spec cannot produce criteria for this unit, STOP before the loop.** Do not run the loop, and
do not quietly fall back to an ungraded run: a typo'd `--spec` is an error, not a silent request for
defaults. A run that looks graded and isn't is worse than one that never claimed to be. Print all
three of these:

1. **Which reason it was**, by name:
   - **missing file** — nothing at the resolved path (say which path you tried);
   - **no Build Plan** — the file exists but has no `## Build Plan` section;
   - **unknown unit** — no Build Plan entry's `unit_id` matches `--unit`;
   - **ambiguous unit** — more than one entry matches, or the Build Plan has several units and no
     `--unit` was given;
   - **empty criteria list** — the entry matched but carries no acceptance-criteria bullets.
2. **The `unit_id`s found** in that spec's Build Plan. If the file or the section is missing there was
   nothing to list, so say that instead of printing an empty list.
3. **The two ways forward:** add acceptance criteria for this unit to the spec (the `/spec` Build Plan
   template gives the shape), or re-run **without `--spec`** to build it ungraded against the title.

**A `status: draft` spec pauses; it does not stop.** Check the spec's frontmatter `status:`. If it is
anything other than `approved`, surface a **P1 decision point** and wait for the user's answer before
running the loop — don't hard-stop, and never proceed silently:

```
> **DECISION [P1]:** Build against `<path>`, which is `status: <value>` rather than approved?
> **Unblocks:** Whether these criteria are the agreed definition of done — approval is what makes a
> spec the source of truth, and grading against unapproved criteria bakes in whatever is still moving.
> **Options:** (a) proceed with these criteria as-is (b) approve the spec first, then re-run
> (c) run without `--spec` and judge against the title
```

### Step 2: Parse the request into a unit object

From `$ARGUMENTS`, construct the workflow `args`:

- `unit_id`: a short snake_case slug derived from the request (e.g. `profile_create_view`). With
  `--spec`, use the Build Plan's `unit_id` exactly as written — the spec entry and the run's handoff
  directory stay keyed on the same handle.
- `title`: a one-line MVI-framed statement of the usable outcome ("X can do Y …"). If the
  request describes a partial component ("add a data model", "define the schema"), reframe it as
  the smallest usable interaction, or stop and say it isn't an MVI unit.
- `instructions`: concrete build steps: what files to create/modify, what tests to write. Keep
  it to this one unit; no speculative scope.
- `acceptance_criteria`: the criteria resolved in Step 1, each string **verbatim** from the spec, in
  the spec's order. Omit it (or pass `[]`) when there was no `--spec` — the editor then judges against
  the title, as it always did.
- `test_command`: infer from the repo's stack unless `--test` is given. Detect from marker files:
  - Python (`pyproject.toml`/`pytest`): `python -m pytest <path> -q` (in this repo: `cd studio && python -m pytest tests/<file> -q`).
  - Node (`package.json`): `npm test` or the project's test script.
  - Rust (`Cargo.toml`): `cargo test`.
  - Unity / other: ask if you cannot infer a runnable command.
  - If you cannot infer one, fall back to the config knob `test_command` from the knobs JSON (Step 5).
- `static_check`: `ruff check <path>` for Python; the project linter otherwise; omit if none.

### Step 3: Validate the work directory, then pick the target branch (safety)

**If `--work-dir <path>` was given, validate it before running any other command.** Locate
`impl_loop.py` with the same Studio-path rule as Step 5, then:

```bash
python .studio/source/impl_loop.py --work-dir "<path>"
```

On success this prints the same knobs JSON Step 5 needs, plus a `work_dir` key holding the
**resolved absolute path**. That resolved path is `<work_dir>` for the rest of this command. Keep
the JSON — Step 5 reuses it instead of running the command again.

**If it exits non-zero, STOP. Do not run the loop.** It writes one line to stderr naming which of
three reasons it hit, and the path it tried:

- **missing** — there is no directory at that path;
- **not-a-worktree** — the directory exists but is not inside a git worktree;
- **different-repo** — it is a worktree of some other repository, not this one.

Tell the user which reason it was and which path was tried. Continuing anyway would commit to
whatever branch the shell's checkout happens to be on — the accident `--work-dir` exists to prevent.

**Then pick the branch.** The loop edits files in place and makes a real `git commit`, and the
writer + editor stages must share one working tree. With a `--work-dir`, that tree is the work
directory — **not** the directory you are standing in — so every git command in this step is pinned
with `git -C "<work_dir>"`. With no `--work-dir`, run them bare (`git rev-parse …`), as before:

```bash
git -C "<work_dir>" rev-parse --abbrev-ref HEAD
git -C "<work_dir>" status --porcelain
```

- If `--branch` was given, check it out in the work directory (create if missing).
- Else if the work directory is on `main`/`master`, create and switch to `impl/<unit_id>` there.
- Else use the branch the work directory is already on (it's already a feature branch).

If that working tree is dirty — the `status --porcelain` above printed anything — stop and tell the
user to commit or stash **in the work directory**; the loop's revert relies on a clean base.

### Step 4: Echo the plan

Print a short block, then proceed (unless `--plan`):

```
/forge
  unit_id:  <slug>
  title:    <MVI outcome>
  branch:   <branch>
  work dir: <resolved work_dir>   (omit this line when no --work-dir was given)
  tests:    <test_command>
  builds:   <1-line of what files/behavior>
  spec:     specs/<slug>.md (status: approved) — unit <unit_id>
  criteria:
    1. <criterion, verbatim>
    2. <criterion, verbatim>
```

Print every resolved criterion in full, verbatim. This is the anti-hallucination anchor: it is the
one place a softened or invented criterion is visible before any code is written, and `--plan` makes
the check free.

With no `--spec`, drop the `spec:` line and make `criteria:` a single line naming what's on offer —
count the `*.md` files in `specs/` (or `.studio/specs/` in a consuming repo):

```
  criteria: none (no --spec; N spec(s) available — pass --spec <slug> to grade against approved criteria)
```

Non-blocking, and **silent** in a repo with no specs: if that directory is missing or holds no specs,
omit the `criteria:` line entirely rather than printing a zero.

If `--plan`, stop here.

### Step 5: Load config knobs, then run the loop

**Studio path:** use `.studio/source/impl_loop.py` for the command below. If that file does not
exist but `studio/impl_loop.py` does, use that instead (you are in the Studio source repo).

Read the loop config knobs. Resolution finds a project override at the repo root
(`.studio/implementation_loop.toml`) automatically, falling back to the shipped default →
built-in defaults, so no path argument is needed:

```bash
python .studio/source/impl_loop.py
# prints knobs JSON, e.g. {"editor_enabled": true, "read_scope": "touched+importers", "output_budget": 400, ...}
```

If `--work-dir` was given you already ran this in Step 3 (with the flag) and it produced the same
JSON. Reuse that output; don't run it a second time.

**If you resolved criteria in Step 1 and `editor_enabled` is `false`, STOP here — do not run the
loop.** The editor is the only thing that grades criteria, so this pair asks for a graded run and
supplies nobody to grade it. Say so plainly, and give the two ways forward: turn the editor mandate on
(`[editor] mandate` in `implementation_loop.toml`), or drop `--spec` and accept an ungraded run. The
loop also flags this combination if it is reached another way, but a contradiction visible before any
agent runs should cost nothing to discover — the same reason a mistyped `--spec` stops in Step 1
instead of quietly downgrading to an ungraded run.

Then call the **Workflow** tool **by `scriptPath`** (NOT `name`; see Gotchas), pointing at the
workflow copy that belongs to the tree being built, and merging the config knobs into the unit args:

- **With `--work-dir`:** `scriptPath` is `<work_dir>/.claude/workflows/implementation-loop.js`.
  Resolve it inside the work directory, never the directory you are standing in — a unit that edits
  the loop itself would otherwise build against the main checkout's copy while its commits land in
  the work directory.
- **Without `--work-dir`:** `scriptPath` is `<repo>/.claude/workflows/implementation-loop.js`, as
  before.

```
Workflow({ scriptPath: "<work_dir or repo>/.claude/workflows/implementation-loop.js", args: {
  unit_id, title, instructions, static_check,
  acceptance_criteria,     // verbatim from the spec (Step 1); omit or [] without --spec
  work_dir,                // the resolved path from Step 3; omit entirely without --work-dir
  test_command,            // per-unit inferred; if none, use the knob test_command
  editor_enabled, read_scope, output_budget,           // from impl_loop.py
  static_checks, require_mutation_check, mutation_command  // from impl_loop.py
}})
```

`work_dir` is what tells both agent prompts to change into that directory before doing anything and
pins their git commands to it. Leave the key off entirely when there is no `--work-dir`, so those
runs render exactly as they always have.

How the workflow consumes each knob: `editor_enabled=false` → skip the editor pass;
`read_scope`/`output_budget` → shape the editor prompt; `require_mutation_check=false` → writer
skips the mutation check; `mutation_command` → the command the writer runs for the mutation check
(default `mutmut run`); `static_checks=[]` → writer skips the static check and the entry gate
doesn't require it. So passing all knobs makes `implementation_loop.toml` fully live.

The workflow runs in the background and notifies on completion. Do not re-run it or poll;
wait for the completion notification.

#### Gotchas (learned the hard way, do not regress these)

- **Invoke by `scriptPath`, never `name`.** `Workflow({name})` resolves a FROZEN registry snapshot
  captured early in the session; it ignores on-disk edits to the workflow file. `scriptPath` (the
  absolute path to `.claude/workflows/implementation-loop.js`) reads the live file.
- **`args` reaches the workflow as a JSON string**, not an object; the workflow `JSON.parse`s it.
  Pass args as a normal object here; just don't be surprised the workflow normalizes a string.
- If `editor_enabled` is false (config `mandate = "off"`), the loop skips the editor pass and
  delivers the writer's version (`editorRan: false`).

### Step 6: Report the result

The workflow returns `{ delivered, flagged, editorRan, finalVersion, reviewerConcerns, criteriaVerdicts, writer, editor }`.
Summarize for the user:

- **Writer escalated?** (`writer.stuck`): if present, lead with this — the writer stopped on purpose
  rather than fake a finish. Quote the blocker as written, and point at the `writer(stuck): <unit_id>`
  commit (`writer.writer_sha`) as the partial work to read, keep, or throw away.
- **What was built** + final test status (`editor.tests` / `writer.tests`).
- **What the editor changed** (`editor.edits`): the cuts/merges/restructures, or "nothing to cut".
- **MVI verdict** (`editor.mvi_verdict`): call out explicitly if the editor *overturned* the
  writer's `mvi_claimed` (unit not actually usable → it's flagged, not silently shipped). With
  criteria, the verdict is both questions at once: usable as a complete interaction **and** every
  criterion passing.
- **Acceptance criteria** (`criteriaVerdicts`): if the unit carried criteria, list every one with its
  grade — `pass`, `fail`, or `unverifiable` — and the evidence the editor actually checked (a test and
  its result, a `file:line` it read, a command it ran). Lead with the ones that didn't pass, and
  don't round `unverifiable` up to a pass: it means nobody confirmed it, which is why the unit is
  flagged. A failed criterion is **flagged, not blocked** — nothing was reverted and there is no
  retry, so say plainly that it's now the user's call whether to build the gap next or accept it.
  On a run with no `--spec` there are no verdicts; say the verdict was judged against the title.
- **Reverted?** (`editor.reverted`): if an edit broke green and was rolled back to `writer_sha`.
- **Reviewer concerns** (`reviewerConcerns`): if non-empty, list them — these are real problems the
  editor found but couldn't fix this pass (would break green, is load-bearing, or out of unit scope).
  They are NOT blockers on delivery, but they are the loop's most useful output when the editor had
  to revert. Point at `.studio/output/impl_loop/<unit_id>/reviewer-concerns.md`.
- Point to the handoff records under `.studio/output/impl_loop/<unit_id>/`.

If `flagged` is true, make clear the unit did NOT pass the full gate (delivered for inspection,
not as a clean green/usable unit).
