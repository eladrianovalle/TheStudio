# Pre-committed Verification for Prompt-Shaped Features — Verification Results

**Spec:** [`prompt-feature-verification.md`](./prompt-feature-verification.md). The pass criterion
below was copied from that spec before anything was measured. Don't edit it to match what happened —
if it turned out to be the wrong criterion, say so under "What this doesn't prove."

Every `FILL_ME` marks data that does not exist yet. Replacing one is the act of reporting. Deleting
one without replacing it — dropping a row or a section — is the failure these pre-written headings
exist to catch.

## Pass criterion (written before the build)
> This feature works if and only if the next prompt-shaped spec written after it
> carries a pass criterion committed *before* its build, and its evidence file is filled in — with a
> non-empty "What this doesn't prove" — before anyone describes that feature as working.

## What happened
| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | FILL_ME | FILL_ME | FILL_ME | FILL_ME |
| With the feature | FILL_ME | FILL_ME | FILL_ME | FILL_ME |

The baseline row should read "no". If the criterion was already met with the feature off, stop and
say so: a feature that fixes a problem you could never trigger has not been shown to do anything.

## What this doesn't prove
Required — this section is the point of the file.
- Did the criterion pass *as written*, un-rewritten after the fact? Name every number that moved the
  wrong way, cost included.
- What could a reader wrongly conclude from that table? At minimum: the sample size, the conditions
  you did not test, and the alternative explanation you can't rule out. "Nothing" is not an answer;
  if you can't name a limit, you haven't looked yet.

FILL_ME

## Verdict
One of **criterion met** / **criterion not met** / **inconclusive, and why**.

FILL_ME
