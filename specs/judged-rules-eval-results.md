# Judged Rules — Verification Results

**Spec:** [`judged-rules.md`](./judged-rules.md). The pass criterion below was copied from that spec before
anything was measured. Don't edit it to match what happened — if it turned out to be the wrong
criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> This feature works if and only if both baseline measurements are recorded with no void case and no unruled row, and in the transcripts of those two runs no case editor reads a file or runs a command outside its own tree, uses a tool or command that answers from a code index, was shown the measuring command in its session context, or says it may be looking at a test, a planted change or an evaluation.

## What happened
| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline (feature off) | None. Before this spec nothing measured the editor, so there is no run to hold the criterion against. | 0 | no | The only record was 628 of 642 criterion verdicts passing, counted on 2026-11-18, with no known right answer for any of them. |
| With the feature | `/measure-editor` headless from the baseline worktree, `claude -p --setting-sources project,local --strict-mcp-config --permission-mode auto --allowedTools Workflow`, on cases fingerprint `e54988c2…`: runs `wf_bedbc1e0-022` and `wf_eb4aaf92-736`, 18 case editors each | 2 | no, by one command | Both runs recorded with no void case, and every row was ruled (4 rulings, against about 8 expected per run). Across the 36 editor transcripts: no code-index tool or command, no `/measure-editor` in any editor's context, and no editor saying it might be looking at a test, a planted change or an evaluation. One breach: in `wf_bedbc1e0-022` willow's editor ran `python studio/impl_loop.py --work-dir` on the baseline worktree's path to try the "different repository" refusal it was reviewing. The tool asked git which repository that directory belongs to and printed one refusal line. No file there was read, and willow's verdict in that run rested on two criteria it called unverifiable. |

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

- **The criterion did not pass as written.** One command in 36 editor sessions reached outside its tree. The owner accepted the run on 2026-11-24 because the command returned nothing about any case, and recorded the breach here rather than rewording the criterion.
- **Every editor could see the measuring worktree.** Each session's context showed the working directory `_TheGameStudio-editor-baseline`, the branch `measure/editor-baseline`, the untracked `studio/evals/forge_editor/results.json`, and recent commit subjects such as "Make the editor benchmark's cases hold up to an audit". The breach above came from that path. No editor said it noticed, but the instrument cannot rule out that the context changed how an editor worked. Running the measurement from a neutral directory would remove it.
- **The results.** Run `wf_bedbc1e0-022` caught 5 of 12 defects, missed 7, and raised 1 false alarm on 6 clean cases (willow). Run `wf_eb4aaf92-736` caught 6, missed 6, and raised none. After rulings the runs differ on two cases: spruce, missed then repaired, and willow, false alarm then passed. The mark is set from them at `max_missed` 7 and `max_false_alarms` 1, the worse of the two runs. It catches the editor getting worse; it is not a target, and the owner wants the catch rate raised.
- **Where the misses are.** The editor missed all 4 defects that no criterion states, in both runs. It caught 5 to 6 of the 8 that a criterion states. Planted defects were caught 4 and 5 times out of 6; defects from the repository's real review history, once out of 6 in each run.
- **Sample size.** Two runs of 12 defect and 6 clean cases cannot show a small change. Six clean cases make the false-alarm tolerance mostly noise.
- **Rulings.** All four rulings were proposed by the agent that built the cases and approved by the owner. Two rows, alder in both runs, count as caught on a written concern that named the defect, not a repair.
- **Cost.** The workflow reported about 0.92 and 0.89 million tokens per run, in about 4 minutes each. That figure leaves out cache reads, which the spec's 25 to 31 million estimate includes, so the two are not compared here.
- **Checks made by script, not by reading every line.** Paths outside the tree, index commands, the measuring command and words of suspicion were searched for by script across all 36 transcripts, and every hit was read. A wider test command that went red was searched for the same way and none was found. An editor phrasing a suspicion in words the search did not cover would have been missed.

## Verdict
One of **criterion met** / **criterion not met** / **inconclusive, and why**.

**Criterion not met** as written, by one harmless command in one of 36 editor sessions. The owner accepted both runs as the baseline and set the mark on 2026-11-24.
