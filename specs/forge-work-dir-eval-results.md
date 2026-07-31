# /forge can build in a git worktree — Verification Results

**Spec:** [`forge-work-dir.md`](./forge-work-dir.md). The pass criterion below was copied from that spec before
anything was measured. Don't edit it to match what happened — if it turned out to be the wrong
criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> This feature works if and only if a `/forge` run with `--work-dir` pointed at a
> real worktree produces every commit it makes on the worktree's branch, leaves the main checkout's
> `HEAD` and working tree unchanged, and runs its tests against the worktree's code — all four
> observed in a single live run, not inferred from the rendered prompts.

## What happened
| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | `worktree_probe_baseline` — a 14-line disposable probe unit built by the loop with **no** `work_dir`, from the main checkout on scratch branch `eval/baseline-no-workdir`, while the `wd` worktree existed | 1 | **no** | Writer commit `1fd7634` landed **in the main checkout** (`git rev-parse --show-toplevel` returned `/Users/orcpunk/Repos/_TheGameStudio`). The probe file was created in the main checkout and **not** in the worktree. The worktree's `HEAD` never moved — `907b847` before and after. The old behavior, reproduced deliberately. |
| With the feature | `worktree_probe_feature` — the same probe unit, `work_dir=/Users/orcpunk/Repos/_TheGameStudio-wt/wd`, editor pass on | 1 | **yes** | All four parts read from git and from the test's own output, not from the agents' reports: (1) the only commit, `9e05f0d`, is on the worktree's branch `eval/feature-with-workdir`; (2) main's `HEAD` is identical before and after (`6898ce6998d0…`); (3) main's working tree is clean, 0 changed files, and the probe file did **not** appear there; (4) the probe printed `worktree probe ran in: /Users/orcpunk/Repos/_TheGameStudio-wt/wd`. |

The baseline row should read "no". If the criterion was already met with the feature off, stop and
say so: a feature that fixes a problem you could never trigger has not been shown to do anything.

## What this doesn't prove
Required — this section is the point of the file.

The criterion passed **as written**, un-rewritten after the fact, and nothing measured moved the
wrong way. But it is one run per arm, and the limits below are real:

- **"Every commit" was tested against exactly one commit.** The editor found nothing worth cutting in
  a 14-line probe, so it made no commit of its own and the feature arm produced a single writer
  commit. That an editor's commit — or a revert — also lands in the worktree is **not** established
  here. Those paths are covered only by unit tests on the rendered prompts, which is precisely the
  kind of inference this criterion was written to refuse.
- **The probe measures where the *test* ran, not where git committed.** The loop's own editor raised
  this during the run and it is correct: `repo_root` derives from `Path(__file__)`. Under the exact
  failure this project has already hit — tests in the worktree, an unpinned git writing to the
  primary checkout — the probe would print the worktree path and pass while the commit went
  elsewhere. Criteria 1-3 survive that because they were checked against `git` in both checkouts;
  criterion 4 rests on the probe alone and would not catch a split like that.
- **The arms were not identical in shape.** The baseline ran writer-only (`editor_enabled: false`) to
  halve its cost; the feature arm ran the full loop. One misplaced commit is enough to establish the
  old behavior, but a strict A/B would run both the same way.
- **One machine, one repository, one worktree layout.** Nothing here speaks to a worktree on another
  filesystem, a path that would hit the `unquotable` refusal, or a repo whose `.git` is a file rather
  than a directory.
- **The alternative explanation I cannot rule out:** that the agents in the feature arm happened to
  behave, rather than were made to. A single obedient run and a run that could not have disobeyed
  look the same from outside. Repetition is what would separate them, and there has been none.
- **This does not show that an agent obeys the `cd` in general** — only that in this run, commits and
  tests landed in the right tree. Every git command remains prompt text an agent may ignore, and
  validation is one-shot at t0 while agents run for an hour. The feature reduces the blast radius;
  nothing observed here makes the accident impossible.
- **The most convincing baseline evidence is not in the table.** Earlier the same day an unpinned run
  committed onto `main` for real, because no `work_dir` was set and the operator changed branches
  mid-run. That was an accident, not a controlled arm, which is why the table reports the reproduced
  baseline instead — but it is why the criterion is worded the way it is.

## Verdict
**Criterion met.** In a single live run with `--work-dir`, every commit the loop made was on the
worktree's branch, the main checkout's `HEAD` and working tree were unchanged, and the tests ran
against the worktree's code — each verified from git and from the test's own output rather than
inferred from the rendered prompts. The deliberately-run baseline failed the same criterion in the
expected way.

Read the limits above before treating this as more than it is: one run per arm, one commit in the
arm that mattered, and no claim that an agent will always obey.
