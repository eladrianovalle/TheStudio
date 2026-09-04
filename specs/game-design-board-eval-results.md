# The Game Design Board as Studio's Live Working Surface — Verification Results

**Spec:** [`game-design-board.md`](./game-design-board.md). The pass criterion below was copied from
that spec before anything was measured. Don't edit it to match what happened — if it turned out to be
the wrong criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> This works if and only if, in a repo that declares a design board, the agent
(a) makes the free structural call and names the region it will open *before* any content read,
(b) sources every claim about the game to a region it read in that turn, and (c) re-reads the
destination region in the same turn before every write, with no write occurring that the designer
did not see proposed first.

## What happened
| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | FILL_ME | FILL_ME | FILL_ME | FILL_ME |
| With the feature | FILL_ME | FILL_ME | FILL_ME | FILL_ME |

The baseline row should read "no". If the criterion was already met with the feature off, stop and
say so: a feature that fixes a problem you could never trigger has not been shown to do anything.

**Before trusting either row, read `find-before-you-grep-eval-results.md`.** Four of its five runs
were void, and both failure modes generalise: a baseline is only a baseline if the behaviour under
test cannot reach the agent by another route (a skill, a hook, an MCP server, CLAUDE.md), and a
treatment is only a treatment if the file carrying it actually loads.

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
