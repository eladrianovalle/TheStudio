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

Measured 2026-10-29 with `studio/finish_check_tally.py --since 2026-09-29`, run from this repo so its
own transcripts are left out. The instrument is Claude Code's own transcripts: every blocked stop is
in there as a hook-feedback record, followed by whatever the assistant did before the person's next
prompt. The rollout reached every install on 2026-09-29, so the window is the month after it, on the
author's machine. The spec's own instrument (a payload log inside the hook) was cut in the build and
turned out not to be needed.

A block counts as followed by a concrete change when the turn after it used an editing tool,
delegated to an agent, or ran a shell command that writes something: a commit, a push, a pull
request, a redirect, a file move. A read-only command counts as a tool call but not as a change,
which is stricter than the criterion's "a command run".

| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | Not run | 0 | no, by construction | With the hook off the turn ends at the first stop and nothing follows it, so there is no following turn to grade. The global registration of the same hook that would have voided the comparison is gone: on 2026-10-29 the user-level settings file carries one Stop hook, the worktree-pruning one. |
| With the feature | The tally over every transcript outside this repo | 1,048 blocked stops in 55 project directories | yes | 401 of 1,048 blocks were followed by a concrete change, 485 by any tool call, 563 by no tool call at all. Of the 1,019 windows of 30 consecutive blocks, 866 meet the criterion. The first window after the rollout has 13, the latest 10, the worst 3. |

The 55 directories are the eleven installs' main checkouts, which hold almost all of the blocks, plus
throwaway worktrees and review sandboxes with between one and ten blocks each. "Consecutive" is by
timestamp across all of them, since the criterion says "repos", plural.

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

**The criterion passed as written, but it never said which 30.** It is met by the first 30 blocks
after the rollout, by the latest 30, and by 866 of the 1,019 windows. It is not met by 153 of them,
and the worst run of 30 produced 3 changes. A reader who picked that run would call the feature a
tax, and the spec gives them no grounds to be overruled.

**The numbers that moved the wrong way, cost first.** 563 of the 1,048 blocks, more than half, were
followed by no tool call: the assistant re-read its message and stopped again. Those turns cost
137,165 output tokens between them, and that is the smaller half of the bill. Each one is also a full
model round trip re-reading the whole context, which the transcripts do not price and this file does
not count. The hook's cost is one such round trip on every turn in every install, paid whether or not
anything follows.

**There is no baseline, and the shape of the feature means there cannot be one of the kind the
spec asked for.** The spec wanted the same sessions with the hook off. With the hook off a turn
simply ends, so "what follows the block" has no counterpart. This measurement therefore shows that
work happens after a block. It does not show that the work would otherwise have stayed undone: the
person might have asked for it in their next prompt, or the assistant might have been about to do it
anyway and was interrupted a second earlier than it would have stopped.

**The grading is mechanical and never reads what was written.** A write after a block is counted
as a concrete change whether it was the deferred work the hook exists for, or a tidy-up the block
provoked, or a commit the assistant was going to make regardless. The regex for writing shell
commands is a judgment too, and a turn the person cut off part-way counts as no change.

**The sample is one machine, one person, one month.** All eleven installs belong to the author, so
the repos, the habits, and the prompting style are one person's. The assistant can also read the
block for what it is, since the paragraph says "automatic, not the user speaking"; nothing here
measures whether it would behave the same if it could not.

## Verdict

One of **criterion met** / **criterion not met** / **inconclusive, and why**.

**Criterion met.** Roughly 4 in 10 blocked stops are followed by a concrete change, against a bar
of 8 in 30, and the bar is cleared by the first window after the rollout and by the latest one. The
cost is the other 6 in 10, and it is paid on every turn.
