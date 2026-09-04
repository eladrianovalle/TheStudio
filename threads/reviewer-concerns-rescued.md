---
type: thread
status: active
slug: reviewer-concerns-rescued
created: 2026-09-04
updated: 2026-09-04
---

# Reviewer concerns rescued from worktrees

`/forge`'s editor writes a `reviewer-concerns.md` when it finds something real it cannot safely fix
in the edit — critique that would otherwise be lost when a change gets reverted. Those files land in
`.studio/output/impl_loop/<unit>/`, which is **gitignored**, inside a per-unit worktree. So every one
of them was a single `git worktree remove` from being destroyed, and six had accumulated.

Copied here verbatim on 2026-09-04, during a branch cleanup that would otherwise have deleted them.
Status notes are mine; the concern text is the editor's, unedited.

**The lesson, worth acting on separately:** a `/forge` concern that survives its own unit has nowhere
durable to live. Landing it in a gitignored directory inside a disposable worktree means the loop's
one mechanism for not losing critique loses it by default.

---

## From `_TheGameStudio-wt-static-checks/.studio/output/impl_loop/wizard_writes_static_commands/reviewer-concerns.md`

**Status 2026-09-04: still live.** This is unit 3 of `specs/detected-static-check-command.md`. Criteria 1 and 3 are verified; criterion 2 needs the two stale consumer repos updated.

### Reviewer Concerns — wizard_writes_static_commands

#### 1. Every already-configured Python consumer repo's `/forge` now refuses at load

**Concern.** `_bare_static_check_name_message`'s own docstring
(`studio/impl_loop.py:339`) states the condition as fact:

> Studio itself planted these: `/studio-setup` in a Python repo wrote
> `static_checks = ["ruff"]` and never overwrites what it wrote, so a config file out
> there says a name where the loop now expects a command.

This unit fixes what the wizard writes *from now on*. It does nothing for the files the
wizard already wrote. `apply_implementation_loop_config` leaves an existing
`.studio/implementation_loop.toml` untouched by design, so in every consumer repo that
already ran the wizard against a Python stack, the next `/forge` raises `LoopConfigError`
instead of running. The refusal message names the file and the exact replacement line, so
it is recoverable — but it is recoverable by hand, once per repo, and nothing schedules
that work.

**Why unresolved.** `out_of_unit_scope`. The unit's own acceptance criteria say so:
"Out of scope: any change to detection or the refusal, and any edit to a consuming repo's
config file." Refusing rather than auto-upgrading is the approved decision in
`specs/detected-static-check-command.md`, not an oversight; the gap is that the approved
plan has two build units and no rollout step.

**Follow-up.** Add a third item to the spec's Build Plan — a cross-repo sweep that
rewrites the `static_checks` line in each installed repo's
`.studio/implementation_loop.toml` — or file it as an issue against the cross-repo push
procedure, so the first person to hit the refusal is not surprised by it.

---

## From `_TheGameStudio-wt-static-checks/.studio/output/impl_loop/due_date_rule/reviewer-concerns.md`

**Status 2026-09-04: RESOLVED.** The fuse was defused today — `find-before-you-grep` is `status: shipped` on real evidence (PR #150), not by moving the date.

### Reviewer Concerns — due_date_rule

#### 1. The rule's only live subject goes red on 2026-10-01, in somebody else's PR

**Concern.** `specs/find-before-you-grep.md` now carries
`verification_due: 2026-09-30   # 30 days from approval`, and it is the only spec in the
repo that rule 6 actually looks at — every other case is synthetic. Its evidence file
`specs/find-before-you-grep-eval-results.md` is still four `FILL_ME` placeholders (lines
20, 21, 34, 39). Today is 2026-08-31, so the suite is green. On 2026-10-01 rule 6b fires
and `test_every_spec_satisfies_the_convention` turns red for whoever pushes next,
regardless of what they touched.

This is the feature working exactly as designed, not a bug — the spec's Key Decisions
defend it, and unit 1's acceptance criteria only ask for green today. It is recorded here
because nothing else in the repo is tracking the date, and the person who trips it will
have had no hand in setting it.

**Why unresolved.** Out of unit scope. Clearing it means actually running the
find-before-you-grep evaluation and writing down what was observed — real work, not an
edit to this unit's diff — and this unit is explicitly scoped to the rule plus the one
backfill that keeps the suite green.

**Follow-up.** Before 2026-09-30, take one of the two exits rule 6b names: fill in
`specs/find-before-you-grep-eval-results.md` with what was observed and flip the spec to
`status: shipped`, or move `verification_due` to when the evidence is realistically
expected. Moving it is a legitimate exit — the point is that it is a visible line in a
diff somebody can question.

---

## From `_TheGameStudio-wt/impl-findings/.studio/output/impl_loop/findings_extracted_at_finalize/reviewer-concerns.md`

**Status 2026-09-04: unverified.** The claim is that `specs/contrarian-finding-verifier.md` promises a `finding_id` no code writes. Check `save_findings_json`'s keys before acting.

### Reviewer Concerns — findings_extracted_at_finalize

Real problems found during the editor pass that could not be safely fixed in it.

#### 1. The spec's contract promises a `finding_id` that no code writes or reads

**Concern.** `specs/contrarian-finding-verifier.md` states, in the same Contract bullet this unit
edited:

> `findings.json` is a list of `Finding` records keyed by a stable `finding_id` (`source_file` + index).

There is no `finding_id`. `save_findings_json` writes exactly seven keys — `confidence`, `flaw`,
`quote`, `impact`, `source_file`, `verdict`, `verified_confidence` — and the verifier matches a
verdict back to a finding by its **position in the list**, not by any id:

- `verifier.select_rows_for_run` emits `{"index": i, "quote": f.quote}`
- `verifier.apply_verdicts_to_run` reads `verdict_record["index"]` and indexes straight into the list

So the approved spec describes a keying scheme the shipped code never had. Anyone building the next
consumer (stats, dedup) off that sentence would write code against a field that does not exist.

**Why unresolved.** Out of this unit's scope. The mismatch predates the unit — it arrived with Unit 1,
when `findings.json` was first defined — and this unit only added a sentence about *who writes the
file*. Fixing it means either adding a field to the record schema (a contract change touching the
verifier's write-back and its tests) or amending an approved spec. Neither belongs in a change whose
job was to call the extractor at finalize.

**Suggested follow-up.** Correct the spec sentence rather than the code: positional keying is what the
verifier actually wants, and this unit just made it safer by guaranteeing the file is written once and
never re-extracted, so positions stay stable between selection and write-back. Replace the bullet with
something like "an ordered list of `Finding` records, keyed by position — the index the verifier
round-trips." If a stable id is genuinely wanted later, that is its own spec pass.

---

## From `_TheGameStudio-wt/impl-gates/.studio/output/impl_loop/detected_gate_defaults/reviewer-concerns.md`

**Status 2026-09-04: likely resolved by PR #143**, which made `static_checks` hold commands rather than names — the concern was that the detected linter's name was computed then thrown away. Worth confirming.

### Reviewer concerns — detected_gate_defaults

Real problems found in the editor pass that could not safely be fixed in it.

#### 1. The detected linter's name is computed and then thrown away

**Concern.** Detection now works out which linter a repo has — `_node_profile` returns
`static_checks=("eslint",)`, `PROFILES["python"]` returns `("ruff",)` — but nothing downstream uses
the name. The workflow only reads the array as a yes/no:

> `static_checks` (config array) gates WHETHER static checking is required; `static_check`
> (per-unit command string, used in writerPrompt) is WHAT runs.
> — `.claude/workflows/implementation-loop.js:311`

and the command itself is still guessed by the agent:

> `static_check`: `ruff check <path>` for Python; the project linter otherwise; omit if none.
> — `.claude/commands/forge.md:111`

So in a Node repo the gate is correctly marked "static check required" while the command that runs
is whatever /forge decides to write, with `ruff check <path>` as the only concrete example in front
of it. That is the same wrong-reason failure this unit removed for the test command, one level down
and one step later.

**Why it is unresolved:** out_of_unit_scope. No acceptance criterion covers `static_check`, and
fixing it means editing the JS workflow and `forge.md`, neither of which this unit's tests exercise.

**Smallest follow-up:** have `resolve_profile` emit the static-check *command* next to the name
(`npx eslint`, `ruff check`) and have /forge pass it as `static_check` instead of authoring one, so
the two halves of the duality stop being able to disagree.

---

## From `_TheGameStudio-wt/impl-hook/.studio/output/impl_loop/nudge_hook_survives_update/reviewer-concerns.md`

**Status 2026-09-04: code fixed (#128), installed base done.** The nudge is live in all 10 repos as of 2026-08-14.

### Reviewer Concerns — nudge_hook_survives_update

Raised by the editor pass. The code fix itself is sound and complete; this is the part
the fix alone does not close.

#### 1. The repos that lost the hook won't get it back on their own

**Concern.** The CHANGELOG entry for this fix states the problem exactly:

> So every update that did any real work deleted the hook it had written milliseconds
> earlier. That is why `_Cerebro` drifted 185 commits behind with the anti-drift feature
> installed.

That is a statement about the installed base, not just about the code. Any consuming repo
that has ever run an `update` which did real work has had its update-check hook deleted.
Merging this fix repairs the code path, but it does not reach back into those repos and
reinstall anything.

The result is a chicken-and-egg gap: a repo only picks up this fix by running `update`,
and the thing whose job was to tell it to run `update` is the hook that got deleted. The
repos most affected — the ones that update often enough to have hit the re-install path —
are exactly the ones now running with no nudge at all.

**Why it wasn't resolved in this pass.** `out_of_unit_scope`. This unit is a one-argument
fix in `studio/install.py` plus its regression tests. Closing the gap is an operational
push across the consuming repos, not a code change, and nothing in this unit's diff or
test scope can verify it.

**Smallest follow-up.** After this merges, run `python studio/run_phase.py update --target
<repo>` once against each of the consuming repos on record (the roster in project memory
lists 10), and confirm the hook is present afterwards by grepping each target's
`.claude/settings.local.json` for the `check-updates` command — check the file, not the
installer's report, since the installer reported success throughout the whole period the
bug was live.

---

## From `_TheGameStudio-wt/impl-wizard/.studio/output/impl_loop/wizard_writes_loop_config/reviewer-concerns.md`

**Status 2026-09-04: still live, and it is [issue #133](https://github.com/eladrianovalle/TheStudio/issues/133)'s concern 2** — the wizard cannot tell its own file from a hand-written one. Concern 1 of that issue shipped in #139; the issue body still needs narrowing.

### Reviewer Concerns — wizard_writes_loop_config

Two real problems the editor pass could not safely fix. Neither blocks the unit: every acceptance
criterion passes and the suite is green.

#### 1. The wizard cannot tell its own file from one you wrote, so a stale gate never refreshes

**The concern.** `apply_implementation_loop_config` decides everything on one question: `if
config_path.exists()`. The file it wrote itself last run and the file you hand-wrote look identical
on the next run, so a repo whose stack has moved on keeps the commands detected the first time,
forever. Concretely: a Node repo with no lint script gets `static_checks = []` written; you add
eslint later; detection would now say `["eslint"]`, but the file says `[]` and the wizard reports
`Forge gates: your own .studio/implementation_loop.toml (left alone)` — which is not true, since the
wizard wrote it.

Two things soften this. The header the step writes into the file says a `[gate]` key you delete
falls back to detection, so the escape hatch is documented where you would find it. And the same
`exists()` check is what keeps Orkid Garden's hand-written override alive, which matters more than
freshness.

**Why unresolved:** load_bearing. That early return is on the do-not-touch list, and criterion 3
compares Orkid Garden's file byte-for-byte after the step runs.

**Follow-up:** have the step write a single marker line into the files it generates (a
`# generated by /studio-setup` first line), and on a later run refresh only a file that still
carries the marker *and* still matches what the step would write today. Anything edited by hand
loses the marker on the first save and is never touched again. Keep the status row honest: "written
by setup" versus "your own".

#### 2. In the Studio source repo the wizard writes to a path `/forge` will not read

**The concern.** `impl_loop._project_artifact_root` maps an installed snapshot
(`<repo>/.studio/source`) back to `<repo>`, and otherwise falls back to the source root itself —
which is the `studio/` package directory, not the repo root. So in this repository `/forge` looks
for its override at `studio/.studio/implementation_loop.toml`, while `/studio-setup --target .`
writes `<repo>/.studio/implementation_loop.toml`. Dogfooding the new step here leaves an inert file
that looks live.

Consuming repos — the whole audience for this feature — are unaffected: the installed layout
resolves correctly, and every test covers that layout.

**Why unresolved:** out_of_unit_scope. The mismatch lives in `_project_artifact_root`, shipped by
the previous unit, and it deliberately does not import `run_phase` so that `impl_loop.py` stays
standalone in `.studio/source/`. Changing where `/forge` resolves its config is a change to the
loop's config chain, not to the wizard step.

**Follow-up:** in `_project_artifact_root`, add the Studio-source-repo case the same way the
installed case is handled — when the root is a package directory named `studio` whose parent holds
the repo, return the parent — and cover it with a test in `test_impl_loop.py`.
