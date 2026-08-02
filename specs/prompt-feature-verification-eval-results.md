# Pre-committed Verification for Prompt-Shaped Features — Verification Results

**Spec:** [`prompt-feature-verification.md`](./prompt-feature-verification.md). The pass criterion
below was copied from that spec before anything was measured. Don't edit it to match what happened —
if it turned out to be the wrong criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> This feature works if and only if the next prompt-shaped spec written after it
> carries a pass criterion committed *before* its build, and its evidence file is filled in — with a
> non-empty "What this doesn't prove" — before anyone describes that feature as working.

## What happened
| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | The prompt-shaped features that shipped in the two weeks before this convention existed: the design-phase slop blacklist + Goodwill Reservoir (#69), the gstack prompt borrowings — quote-to-promote, the named-scar anchor, the lone-critical override (#65), and the contrarian editor mandate + Open-Questions Pre-Flight | 3 PRs | **no** | None carried a pass criterion, and no evidence file existed in the repo before this convention created its own. `git log --diff-filter=A -- 'specs/*-eval-results.md'` returns exactly two files, both dated on or after 2026-07-28 |
| With the feature | `specs/forge-work-dir.md` — the next prompt-shaped spec written after the convention shipped | 1 | **yes** | Its `## Verification` section was present in the spec's first commit (`b4448ce`, 2026-07-30). The evidence file was opened empty at approval (`bad3d45`), and `git merge-base --is-ancestor` confirms both landed before the first build commit (`940de25`). It was filled from two controlled runs and the status flipped to `shipped` in the same commit (`96c7ded`, PR #107), so nothing described the feature as working while the file was still blank |

The baseline row should read "no". If the criterion was already met with the feature off, stop and
say so: a feature that fixes a problem you could never trigger has not been shown to do anything.

The baseline reads "no", and not by a narrow margin: the practice did not exist in any form. This is
a process convention rather than a runtime behavior, so the two arms are historical rather than
simultaneous — the baseline is what the repo actually did before 2026-07-28, not a control run.

## What this doesn't prove
Required — this section is the point of the file.
- Did the criterion pass *as written*, un-rewritten after the fact? Name every number that moved the
  wrong way, cost included.
- What could a reader wrongly conclude from that table? At minimum: the sample size, the conditions
  you did not test, and the alternative explanation you can't rule out. "Nothing" is not an answer;
  if you can't name a limit, you haven't looked yet.

The criterion passed **as written**. It was not rewritten after the fact — the wording above is
byte-identical to the one committed in `ec911eb` on 2026-07-28, before the build. Nothing measured
moved the wrong way, because this convention costs no tokens and no runtime; its whole cost is the
authoring effort of one section and one file. The limits are elsewhere, and they are substantial:

- **The sample is one spec.** Exactly one prompt-shaped spec has been written since the convention
  landed. One instance cannot distinguish a convention that works from a coincidence, and the
  criterion as written was satisfiable by a single compliant example — which is a weakness in the
  criterion, not just in the data.
- **The alternative explanation I cannot rule out, and it is the strong one:** the same author wrote
  both the convention and the spec that complied with it, 48 hours apart, in a repo where the
  convention was the most recent thing discussed. Compliance that close to authorship measures
  salience, not durability. The real test is a prompt-shaped spec written months later, by someone
  who did not write the rule and is not thinking about it. That test has not happened.
- **The reporter is the participant.** I did the work being graded and then graded it. No independent
  reader checked whether `forge-work-dir`'s evidence file is honest or merely present, and the
  convention has no mechanism that would produce one.
- **This file is itself a counterexample to the convention's reach.** The feature shipped 2026-07-28
  and this evidence file sat blank until 2026-08-02 — five days during which the convention was in
  force and its own results were unrecorded. It never technically broke the rule, because
  `test_spec_verification.py` only refuses a spec claiming `status: shipped`, and this spec stayed at
  `approved`. That is the hole: **the enforcement binds only those who claim completion, so the way
  around it is to never claim it.** The file was filled because a human asked, not because anything
  compelled it. A reader should not conclude from the table above that the convention enforces
  itself; it enforces a *claim*, which is a narrower thing.
- **The criterion measures process compliance, not outcome.** It asks whether the next spec carried a
  criterion and filled its file. It never asks whether doing so caught a defect that would otherwise
  have shipped. A convention can be complied with perfectly and still find nothing, and this result
  would look identical either way.
- **Filler still passes.** As the spec recorded when it was written: "N/A" under every heading
  satisfies all four rules. That remains undetectable in principle, and nothing here changes it.

## Verdict
One of **criterion met** / **criterion not met** / **inconclusive, and why**.

**Criterion met**, as written, on a sample of one.

The next prompt-shaped spec after this one carried a pass criterion committed before its build, its
evidence file was opened empty at approval and filled from real runs, its "What this doesn't prove"
is non-empty and genuinely self-critical — it names a probe that could pass while the thing it
measures is broken — and the feature was not described as working until that file was filled.

What this earns is narrow, and the honest reading is that the *convention* passed while the
*enforcement* did not get tested. The one case where enforcement would have mattered is this file:
it stayed blank for five days under a rule that only fires on a completion claim never made. If a
second prompt-shaped spec ships with an unfilled results file, the trigger the spec set for itself
has been reached, and the choice it named — enforce the stop condition properly or delete the tier —
should be made then rather than argued again from scratch. The obvious way to close the hole is to
stop letting `approved` be a resting place for a feature already in use, but that is a change to
propose, not a conclusion this evidence supports.
