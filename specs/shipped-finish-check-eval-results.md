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

Measured 2026-11-11 with `studio/finish_check_tally.py --since 2026-09-29`, with this repo's own
transcripts excluded. The instrument is Claude Code's own transcripts: every blocked stop is in there
as a hook-feedback record, followed by whatever the assistant did before the person's next prompt.
The rollout reached every install on 2026-09-29. Claude Code deletes a transcript file 30 days
after its last write, so a long-running session keeps records older than that. The surviving record
on the author's machine runs from 2026-10-05 to 2026-11-11; an earlier run of
the same tally on 2026-10-29 saw blocks back to the rollout day and was discarded because its
grading over-counted (see below). The spec's own instrument (a payload log inside the hook) was cut
in the build and turned out not to be needed.

A block counts as followed by a concrete change when the turn after it used an editing tool or ran a
shell command that writes something: a commit, a push, a pull request, a redirect into a file, a file
move. A read-only command counts as a tool call but not as a change, which is stricter than the
criterion's "a command run". Handing work to a subagent is reported on its own line and not counted
as a change, because what the subagent did is in a transcript this tally does not read.

| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | Not run | 0 | no, by construction | With the hook off the turn ends at the first stop and nothing follows it, so there is no following turn to grade. The global registration of the same hook that would have voided the comparison is gone: on 2026-10-29 the user-level settings file carries one Stop hook, the worktree-pruning one. |
| With the feature | The tally over every surviving transcript outside this repo | 912 blocked stops in 10 project directories | yes | 288 of 912 blocks were followed by a concrete change, 409 by any tool call, 503 by no tool call at all; 10 more delegated to a subagent and changed nothing themselves. Of the 883 windows of 30 consecutive blocks, 601 meet the criterion. The earliest surviving window has 12, the latest 15, the worst 3. |

The 10 directories are installs' main checkouts; the throwaway worktrees and review sandboxes that
the 2026-10-29 run also saw have been deleted since, transcripts included. "Consecutive" is by
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

**The criterion passed as written, but it never said which 30.** It is met by the earliest
surviving 30 blocks, by the latest 30, and by 601 of the 883 windows. It is not met by 282 of them,
roughly a third, and the worst run of 30 produced 3 changes. A reader who picked that run would call
the feature a tax, and the spec gives them no grounds to be overruled.

**The first grading over-counted, and the population moved under it.** The 2026-10-29 run counted
any `>` in a shell command as a write, so `2>&1` and `>/dev/null` on read-only commands, and a `>`
inside a quoted argument, all became "concrete changes"; it also counted handing work to a subagent
as a change. That run reported 401 of 1,048 and 866 of 1,019 windows. The grading here fixes both,
but the same transcripts could not be re-graded, because Claude Code had deleted the first week of
them by then. So the two runs are not the same population measured twice, and the drop from roughly
4 in 10 to roughly 3 in 10 is the correction and the rotation together, in a split nobody can
recover. The numbers above are the ones the shipped tool reproduces.

**The numbers that moved the wrong way, cost first.** 503 of the 912 blocks, more than half, were
followed by no tool call: the assistant re-read its message and stopped again. Those turns cost
105,154 output tokens between them, and that is the smaller half of the bill. Each one is also a full
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
provoked, or a commit the assistant was going to make regardless. The rules for which shell
commands write are a judgment too: an unquoted `[[ $n > 3 ]]`, or an apostrophe in an unquoted
comment that throws off the quote stripping, still reads as a write, and `>| file` does not. None
looked common enough to move the count, and none was measured. A turn the person cut off part-way
counts as no change.

**The sample is one machine, one person, five weeks.** All the installs belong to the author, so
the repos, the habits, and the prompting style are one person's. The assistant can also read the
block for what it is, since the paragraph says "automatic, not the user speaking"; nothing here
measures whether it would behave the same if it could not.

## Verdict

One of **criterion met** / **criterion not met** / **inconclusive, and why**.

**Criterion met.** Roughly 3 in 10 blocked stops are followed by a concrete change, against a bar
of 8 in 30, and the bar is cleared by the earliest surviving window and by the latest one, though not
by a third of the windows in between. The cost is the other 7 in 10, and it is paid on every turn.
