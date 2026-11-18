# Finish-Check Without the Error Notice — Verification Results

**Spec:** [`finish-check-context-channel.md`](./finish-check-context-channel.md). The pass criterion below was copied from that spec before
anything was measured. Don't edit it to match what happened — if it turned out to be the wrong
criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> This feature works if and only if, over at least 150 context-channel finish-checks whose final message was at least 600 characters (from projects that also have a frozen block baseline), the share followed by a concrete change is at least 0.80 times the block-channel rate weighted by each project's share of those context checks.

## Frozen baseline (written 2026-11-18, before the hook changed)
Block channel, final message at least 600 characters. Run on 2026-11-18:
`python studio/finish_check_tally.py --since 2026-11-01 --exclude <Studio source checkout> --channel block --min-final-chars 600`.
530 checks from 2026-11-04 to 2026-11-18, 166 followed by a concrete change (0.313 pooled). Claude Code deletes
transcripts 30 days after their last write, so these numbers are never re-read from disk. Installs are labelled rather than named because this repository is public; the
mapping to transcript directories is kept outside it. Weight each row by that install's
context-check count when comparing.

| Install | Checks | Followed by a concrete change |
|---|---|---|
| Install A | 180 | 50 |
| Install B | 84 | 30 |
| Install C | 69 | 29 |
| Install D | 60 | 8 |
| Install E | 50 | 18 |
| Install F | 50 | 20 |
| Install G | 18 | 4 |
| Install H | 9 | 6 |
| Install I | 6 | 1 |
| Install J | 3 | 0 |
| a temporary test project | 1 | 0 |

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
