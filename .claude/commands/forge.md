---
description: "Use to build one complete, usable unit of work through the writer/editor loop, which commits a passing state and then has a fresh editor cut and grade it. Point it at an approved spec with --spec <slug> --unit <id> and it grades the result against that unit's acceptance criteria one at a time. Triggers include 'implement X', 'build the next unit', and 'run the writer-editor loop on X'. Writes and commits real code. If the feature has no approved design yet, use /spec first."
argument-hint: "<unit description> [--spec <slug>] [--unit <id>] [--branch <name>] [--work-dir <path>] [--test <cmd>] [--plan]"
---

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

## Portable runtime selection

If the invocation supplies any of `--runtime`, `--writer-runtime`, `--editor-runtime`,
`--writer-model` or `--editor-model`, run `python .studio/source/run_phase.py forge`
with the supplied arguments (use `python studio/run_phase.py forge` in Studio's source checkout).
Pass each argument literally, including `--plan`. Report the command's result and stop there.
For calls without those selectors, continue with the native Claude Workflow below.

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
  spawns. Without it, the agents work wherever their shell starts, as they always have. The flag
  reduces the blast radius of a run pointed at the wrong directory rather than ruling that out:
  every git command the loop renders is prompt text an agent may ignore.
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
path doesn't). Otherwise treat it as a slug and look for `<slug>.md` in both places a repository keeps
specs: `.studio/specs/` and top-level `specs/`. Don't decide from whether Studio is installed: some
installed repos keep their specs in `specs/`.

- Found in exactly one of them: use it.
- Found in both: stop and name both paths (**ambiguous spec**), so the user passes the one they mean.
- Found in neither: the reason is **missing file**, below.

**Find the unit's criteria.** Read the spec's `## Build Plan` section, whose entry shape is the one
the `/spec` Build Plan template writes — `.claude/commands/spec.md` is where that shape is defined,
and older specs may open an entry as a numbered list item instead. Take the entry whose backticked
`unit_id` matches `--unit`; if the Build Plan holds exactly one unit, `--unit` may be omitted and
that unit is used. This unit's criteria are the `- [ ]` bullets inside that entry.

Copy each criterion **verbatim** into `acceptance_criteria` (Step 2's args block) — the exact
sentence from the spec, not a paraphrase, a shortening, a softening, or two bullets merged into one.
Same quote discipline the contrarian mandate imposes on findings: the spec's words are the words the
editor grades and quotes back in its verdicts.

**If the spec cannot produce criteria for this unit, STOP before the loop.** Do not run the loop, and
do not quietly fall back to an ungraded run: a typo'd `--spec` is an error, not a silent request for
defaults. A run that looks graded and isn't is worse than one that never claimed to be. Print all
three of these:

1. **Which reason it was**, by name:
   - **missing file** — nothing at the resolved path (say which paths you tried);
   - **ambiguous spec** — the slug names a file in both `.studio/specs/` and `specs/` (say both paths);
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
  it to this one unit; no speculative scope. You do **not** need to tell the writer to use a code
  index — the writer prompt already carries that rule, conditional on the repo having one. Name the
  specific tool here only if the repo's index needs a command or a scope that isn't obvious.
- `acceptance_criteria`: the criteria resolved in Step 1, each string **verbatim** from the spec, in
  the spec's order. Omit it (or pass `[]`) when there was no `--spec` — the editor then judges against
  the title, as it always did.
- `test_command`: infer from the repo's stack unless `--test` is given. Detect from marker files:
  - Python (`pyproject.toml`/`pytest`): `python -m pytest <path> -q` (in this repo: `cd studio && python -m pytest tests/<file> -q`).
  - Node (`package.json`): `npm test` or the project's test script.
  - Rust (`Cargo.toml`): `cargo test`.
  - Unity / other: ask if you cannot infer a runnable command.
  - If you cannot infer one, fall back to the config knob `test_command` from the knobs JSON (Step 5).
- `static_checks`: take the list from the knobs JSON (Step 5) — it is what this repo's own config
  file says to run, so do not invent a linter here. Before passing it on, replace every `{paths}` token with the paths
  this unit is expected to touch, space-separated and each double-quoted
  (`ruff check "studio/impl_loop.py" "studio/tests/test_impl_loop.py"`). A command with no token
  goes through as written. If you cannot name any paths, **drop that command** rather than
  substituting `.` — linting the whole repo would fail the unit for pre-existing debt it never
  touched. If that empties the list, pass `[]`, which is how the config already says "skip the
  static check". Honest limit: the paths are predicted before the writer runs, so they are a good
  guess, not a record of what it changed.

### Step 3: Validate the work directory, then pick the target branch (safety)

**If `--work-dir <path>` was given, validate it before running any other command.** Locate
`impl_loop.py` with the same Studio-path rule as Step 5, then:

```bash
python .studio/source/impl_loop.py --work-dir "<path>"
```

On success this prints the same knobs JSON Step 5 needs, plus a `work_dir` key holding the
**resolved absolute path**. That resolved path is `<work_dir>` for the rest of this command.

**If it exits non-zero, STOP. Do not run the loop.** It writes to stderr naming which of four
reasons it hit, and the path it tried:

- **missing** — there is no directory at that path;
- **not-a-worktree** — the directory exists but is not inside a git worktree;
- **different-repo** — it is a worktree of some other repository, not this one;
- **unquotable** — the path contains a character outside the accepted set: letters, digits, and
  `/ . _ - ~` or a space. The loop renders the path into `git -C "<path>"` inside the agents'
  instructions, where a character like `"` or a backtick turns the rest of the path into a command
  of its own. The check accepts a known-good set instead of banning a known-bad one, so a character
  nobody anticipated is refused rather than waved through; the cost is that a legitimate path
  holding a `+`, a `(` or an accent is refused too. This is the one reason that answers over several
  lines — it points a caret at each offending character and explains the ones it recognises. Pass
  the whole thing on. Rename the directory.

Tell the user which reason it was and which path was tried. Continuing anyway would commit to
whatever branch the shell's checkout happens to be on — the accident `--work-dir` exists to make
less likely.

**Then pick the branch.** The loop edits files in place and makes a real `git commit`, and the
writer + editor stages must share one working tree. With a `--work-dir`, that tree is the work
directory — **not** the directory you are standing in — so every git command in this step is pinned
with `git -C "<work_dir>"`. With no `--work-dir`, run them bare (`git rev-parse …`), as before:

```bash
git -C "<work_dir>" rev-parse --abbrev-ref HEAD
```

- If `--branch` was given and it is `main` or `master`, STOP before checking anything out: the
  loop never commits straight to the main branch, and Step 5 would refuse it as
  `protected-branch` anyway. Tell the user to pick a feature branch.
- Else if `--branch` was given, check it out in the work directory (create if missing).
- Else if the work directory is on `main`/`master`, create and switch to `impl/<unit_id>` there.
- Else use the branch the work directory is already on (it's already a feature branch).

That branch is `<branch>` for the rest of this command. Don't check by hand that the tree is clean
or still on it: Step 5's command does, at the last moment before the loop starts, and refuses the
run if not.

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

Read the loop config knobs. Resolution finds this repo's own config at the repo root
(`.studio/implementation_loop.toml`) automatically, falling back to the shipped default, so no
path argument is needed. That file is the only thing that says how this repo is gated — a `[gate]`
key it leaves out is empty, and nothing is detected here:

```bash
python .studio/source/impl_loop.py --branch "<branch>" --unit "<unit_id>"
# prints knobs JSON, e.g. {"editor_enabled": true, ..., "branch": "<branch>", "base_sha": "...", "launched_at": "2026-11-26T12:00:00+00:00"}
```

Pass the `unit_id` from Step 2, and with `--spec` pass `--spec "<spec file>"` too. If `--work-dir`
was given, pass it here too (`--work-dir "<work_dir>" --branch "<branch>" --unit "<unit_id>"`), so
the branch is checked in the work directory. Run this even though Step 3 already printed the knobs:
it is the check of the tree as it stands now, so it must be the last command before the Workflow
call. When every check passes it leaves a small record of the launch in the tree's git directory
(never in the working tree) and prints `launched_at`; Step 6 checks the unit against that record.

**If this command exits non-zero, STOP — do not run the loop.** Its message already says what is
wrong and what to do; print it as-is and let the user fix it. It is one of:

- **No test command.** This repository's config file is not there, or its `test_command` is blank.
  The message names the file and gives the exact lines to write (running `/studio-setup` writes the
  file when there is none). Do not invent a test command and carry on: the writer would run it, and
  the gate would believe whatever came back.
- **A bare legacy static-check name.** `static_checks` holds a tool name Studio used to write, such
  as `"ruff"`, instead of a command. A bare name runs nothing and would still report a clean check,
  so it is refused; the message gives the command to write in its place, such as
  `"ruff check {paths}"`.
- **`protected-branch`** — `<branch>` is `main` or `master`. The loop commits as it goes, and a
  unit's commits never go straight onto the main branch.
- **`wrong-branch`** — the tree is no longer on `<branch>`. Another session moved the checkout after
  Step 3, and the writer commits to whatever branch it finds. Do not switch it back yourself and
  carry on; whoever moved it may still be working there.
- **`dirty-tree`** — something is uncommitted, and the message lists it. The writer's `git add -A`
  would sweep it into the unit's commit, and the loop's `git reset --hard` would delete it. A
  concerns file an earlier unit left behind counts.
- **`unchecked-loop`** — an earlier `/forge` run in this tree was launched and never checked (it
  crashed, or its report step never ran). The message names that run's unit, branch and start time
  and prints the exact `--check` command for this tree. Show it to the user; do not run it yourself
  and relaunch, because the user may want to look at that run's work first.
- **`unreadable-record`** — the launch record in this tree's git directory cannot be read. The
  message names the file.
- **`launch-in-progress`** — another `/forge` run, launch or `--check` in this tree holds its
  `studio-forge.lock` at this moment. Nothing was launched. Tell the user; do not retry in a loop,
  because once a launch finishes its record will refuse this one with `unchecked-loop`. If the user
  says nothing is running, the lock was left by a killed process and the message names the file to
  remove.
- **`--branch needs a unit id`** — the command was called without `--unit`. If you passed it, the
  session is running an older copy of this command: tell the user to restart the session.

**If you resolved criteria in Step 1 and `editor_enabled` is `false`, STOP here — do not run the
loop.** The editor is the only thing that grades criteria, so this pair asks for a graded run and
supplies nobody to grade it. Say so plainly, and give the two ways forward: turn the editor mandate on
(`[editor] mandate` in `implementation_loop.toml`), or drop `--spec` and accept an ungraded run. The
loop also flags this combination if it is reached another way, but a contradiction visible before any
agent runs should cost nothing to discover — the same reason a mistyped `--spec` stops in Step 1
instead of quietly downgrading to an ungraded run.

Before dispatch, copy the Studio checker's `code_comments.py` from beside `impl_loop.py`
to a temporary directory outside the worktree. Keep its absolute path and the preflight
`base_sha` for Step 6. This pins the verifier for units that edit Studio itself.

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
  launched_at,             // from impl_loop.py --branch, unchanged; the loop starts no agent without it
  unit_id, title, instructions,
  acceptance_criteria,     // verbatim from the spec (Step 1); omit or [] without --spec
  work_dir,                // the resolved path from Step 3; omit entirely without --work-dir
  test_command,            // per-unit inferred; if none, use the knob test_command
  static_checks,           // the knob list with {paths} substituted (Step 2)
  editor_enabled, read_scope, output_budget,           // from impl_loop.py
  require_mutation_check, mutation_command,            // from impl_loop.py
  observe_command                                      // from impl_loop.py; "" means off
}})
```

`work_dir` is what tells both agent prompts to change into that directory before doing anything and
pins their git commands to it. Leave the key off entirely when there is no `--work-dir`, so those
runs render exactly as they always have.

How the workflow consumes each knob: `editor_enabled=false` → skip the editor pass;
`read_scope`/`output_budget` → shape the editor prompt; `require_mutation_check=false` → writer
skips the mutation check; `mutation_command` → the command the writer runs for the mutation check
(whatever this repo's config names — `mutmut run` in a Python one); `observe_command` → the
repo's own command for looking at the running product, which both agents are told to run and whose
printed image paths they Read (empty → neither prompt mentions it); `static_checks` → the lint **commands** the
writer runs, all of them, with `static_ok` the AND across the lot (`[]` → writer skips the static
check and the entry gate doesn't require it). So passing all knobs makes
`implementation_loop.toml` fully live.

The workflow runs in the background and notifies on completion. Do not re-run it or poll;
wait for the completion notification.

If this session has no Workflow tool, stop and say so. Do not build the unit yourself and play
both parts: the editor's value is that it is a separate agent that did not write the code, so a
one-agent run reports a review that never happened.

#### Gotchas (learned the hard way, do not regress these)

- **Invoke by `scriptPath`, never `name`.** `Workflow({name})` resolves a FROZEN registry snapshot
  captured early in the session; it ignores on-disk edits to the workflow file. `scriptPath` (the
  absolute path to `.claude/workflows/implementation-loop.js`) reads the live file.
- **The Workflow tool can refuse a `scriptPath` outside the session's working directory**, which is
  where a `--work-dir` worktree usually sits. When it does, check the main checkout's copy is
  byte-identical (`cmp <repo>/.claude/workflows/implementation-loop.js <work_dir>/.claude/workflows/implementation-loop.js`)
  and launch that copy instead. It is safe because the script is read once at launch, and the
  `work_dir` arg, not where the script lives, decides where the agents work. If the two copies differ
  (a unit that edits the loop itself), launching the main copy is exactly the build-against-the-old-loop
  the **With `--work-dir`:** bullet above warns about. If `cmp` fails because the main checkout has no
  copy at that path, there is nothing verified to launch. In either case, do not launch the main copy;
  stop and tell the user. The way forward is to restart the session with the worktree as its working
  directory, so the worktree's `scriptPath` is in scope.
- **`args` reaches the workflow as a JSON string**, not an object; the workflow `JSON.parse`s it.
  Pass args as a normal object here; just don't be surprised the workflow normalizes a string.
- If `editor_enabled` is false (config `mandate = "off"`), the loop skips the editor pass and
  delivers the writer's version (`editorRan: false`).
- **The loop starts no agent without `launched_at`.** It returns
  `{ delivered: false, reason: 'not_launched' }` instead. Pass the value the `--branch` call printed;
  never make one up, because the check in Step 6 reads the record that call wrote.

### Step 6: Verify the native commits and report the result

**Run the post-loop check first**, before anything else in this step, in the tree the unit was
built in (the same Studio path as Step 5):

```bash
python .studio/source/impl_loop.py --check
# with --work-dir: python .studio/source/impl_loop.py --check --work-dir "<work_dir>"
```

It re-runs this repository's own test command itself (and the pack check, when a pack is
declared), and checks that the tree is still on `<branch>` and holds a `writer: <unit_id>` commit
since the launch. It reads nothing the agents wrote. It prints one JSON object:
`{"clean", "unit_id", "branch", "tests": {"command", "exit_code"}, "packs", "problems": [{"name", "detail"}]}`.

- **Exit 0** — clean. Say so.
- **Exit 1** — not clean. Lead the report with this and list every problem by name and detail:
  `wrong-branch`, `no-writer-commit` (a `writer(stuck):` commit does not count), `tests-failed`,
  `packs-failed`. The record stays, stamped with what was found; running `--check` again after a
  fix checks again. Tell the user the branch should not be pushed until they have seen this.
- **Exit 2** — nothing was checked (no record, one it cannot read, or a run, a launch or another
  check holding the lock). Print the message and say the unit's tests were not re-run.

The native Workflow returns a candidate with `delivered: false`. If it carries
`pendingCommentCheck: true`, pass the unmodified JSON on stdin to the Studio checker.
Use the worktree and branch selected in Step 3 and the full `base_sha` printed by
the Step 5 preflight. Use the checker copy saved before dispatch.

```bash
python3 "<saved-checker>/code_comments.py" --repo "<worktree>" --base "<preflight base_sha>" --finalize-branch "<branch>" < "<candidate.json>"
```

Save the candidate outside the worktree. Only the checker's successful JSON result
can mark the run delivered. On a nonzero exit, report the diagnostic and stop.
If the workflow failed before producing a candidate, report that failure directly.
The checker inspects each commit from the preflight SHA through the branch tip,
including writer-only runs. The portable host runs the same check on each proposed
Git tree before committing. Agent code and tests must contain zero new comments.
Python, TOML, and Git ignore files use Studio’s Python runtime. Other supported source languages require
ast-grep (`npm install -g @ast-grep/cli@0.51.3`). Unknown source types block delivery.

The verified result includes `{ delivered, flagged, editorRan, finalVersion, reviewerConcerns, criteriaVerdicts, writer, editor }`.
Summarize for the user:

- **Writer escalated?** (`writer.stuck`): if present, lead with this — the writer stopped on purpose
  rather than fake a finish. Quote the blocker as written, and point at the `writer(stuck): <unit_id>`
  commit (`writer.writer_sha`) as the partial work to read, keep, or throw away.
- **The check**: lead with `--check`'s `clean` and its problems, from the top of this step.
- **What was built**.
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
  to revert. Point at `<work_dir>/reviewer-concerns/<unit_id>.md` — kept outside the gitignored run
  directory so it survives the worktree being removed, and so it shows up in `git status` rather than
  silently. The path the editor writes is relative to the tree it worked in, so spell out the
  resolved work dir here (drop the prefix when no `--work-dir` was given); a bare
  `reviewer-concerns/…` leaves the user guessing which checkout it is in.
- Point to the handoff records under `.studio/output/impl_loop/<unit_id>/`.

If `flagged` is true, make clear the unit did NOT pass the full gate (delivered for inspection,
not as a clean green/usable unit).
