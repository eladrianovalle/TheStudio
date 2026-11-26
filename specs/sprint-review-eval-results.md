# Sprint Review — Verification Results

**Spec:** [`sprint-review.md`](./sprint-review.md). The pass criterion below was copied from that spec before
anything was measured. Don't edit it to match what happened — if it turned out to be the wrong
criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> `/sprint-review` works if and only if both of these hold.
> (1) In a fixture repository with Studio installed and four finished, still-`approved` specs — one
> built only on an unmerged branch, one merged by squash — a `/sprint-review` run in which the human
> answers yes to two, hold (giving a criterion) to one, and nothing to the unmerged one, opens exactly
> one pull request, ready for review, holding exactly one commit whose changed files are exactly the
> two yes'd specs, the held spec and the held spec's results file; the two yes'd specs say
> `status: shipped` with both shipped fields filled; the held spec has one `## Verification` section
> carrying the human's criterion word for word and a `verification_due` 30 days out; and the unmerged
> spec is unchanged — in 3 of 3 runs.
> (2) In the same fixture before any batch, 5 of 5 fresh sessions opened with "What should I work on
> next?" change no spec's `status` and name `/sprint-review` to the human.

## What happened
| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | FILL_ME | FILL_ME | FILL_ME | FILL_ME |
| With the feature | FILL_ME | FILL_ME | FILL_ME | FILL_ME |

The baseline row should read "no". If the criterion was already met with the feature off, stop and
say so: a feature that fixes a problem you could never trigger has not been shown to do anything.
**Before trusting either row, check that neither arm was void.** Four of the six runs behind
`specs/find-before-you-grep-eval-results.md` (in the Studio repo) were, and both failure modes
generalise: a baseline is only a baseline if the behaviour under test cannot reach the agent by
another route (a skill, a hook, an MCP server, CLAUDE.md), and a treatment is only a treatment if
the file carrying it actually loads.

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
