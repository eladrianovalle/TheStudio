# Shipped Finish-Check Stop Hook — Verification Results

**Spec:** [`shipped-finish-check.md`](./shipped-finish-check.md). The pass criterion below was copied
from that spec before anything was measured. Don't edit it to match what happened — if it turned out
to be the wrong criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)

> This feature works if and only if, across 30 consecutive blocked stops in repos
> other than the Studio source repo, **at least 8 produce a concrete change to the working tree or to
> a tracked artifact** — a file edited, a command run, an issue or PR created, a decision recorded —
> in the turn that follows the block. Anything less and the hook is a tax that buys a reworded message.

## What happened

| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | FILL_ME | FILL_ME | FILL_ME | FILL_ME |
| With the feature | FILL_ME | FILL_ME | FILL_ME | FILL_ME |

"Feature off" here means `.studio/finish-check.off` in place and the update re-run. The baseline row should read "no". If work deferred at a stop got finished anyway with the hook off,
stop and say so: a hook that catches what something else already catches has not been shown to do
anything.

**Before trusting either row, check that neither arm was void.** A baseline is only a baseline if the
behaviour under test cannot reach the agent another way — and here that is a real hazard, because a
global `Stop` registration of this same hook covers every project on the author's machine. If it is
still installed, the "hook off" arm is not off. Confirm it is gone before the first measured stop, and
say in the Notes column how you confirmed it.

## What this doesn't prove

Required — this section is the point of the file.
- Did the criterion pass *as written*, un-rewritten after the fact? Name every number that moved the
  wrong way, cost included — one extra model round-trip per turn is the price, and it should appear
  here as a figure rather than an aside.
- What could a reader wrongly conclude from that table? At minimum: how many distinct repos and
  sessions the 30 stops came from, whether one long session dominated, who judged "a concrete change"
  and whether they knew which arm they were reading.

FILL_ME

## Verdict

One of **criterion met** / **criterion not met** / **inconclusive, and why**.

FILL_ME
