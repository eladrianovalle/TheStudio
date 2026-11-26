# Verification Skills — Verification Results

**Spec:** [`verify-skill.md`](./verify-skill.md). The pass criterion below was copied from that spec before
anything was measured. Don't edit it to match what happened — if it turned out to be the wrong
criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> This feature works if and only if R, F and M all hold:
> - **R: replay, both arms real.** Build two branches in the adopter from the base of the
>   phone-speaker unit, plus the observe adoption (steps 3-4). Only the treatment arm gets the verify
>   skill and the pointer line. The unit's writer diff goes on top of each, so the editor's
>   `base..writer` diff is exactly the unit's. Render the editor prompt with
>   `node .claude/workflows/tests/editor-prompt.mjs render`, criteria verbatim from the unit's editor
>   record, and run it headless with forge's flags 3 times per arm, passing `--allowedTools
>   'Bash(<observe_command> *)'` on the command line. `--disable-slash-commands` stays on, so only
>   the pointer channel is tested: the worst case. R holds when the treatment arm grades the
>   phone-speaker criterion `pass` or `fail` in at least 2 of 3 runs, with evidence naming an
>   absolute capture path a feature-map recipe wrote at that commit, and the control arm grades it
>   `unverifiable` in at least 2 of 3. If the remote phone-sounds unit's base and writer commits
>   can be recovered from the adopter's worktrees, it is a second positive case with the same arms,
>   runs and thresholds. If they can't, the results file says so. **Negative case:** a
>   treatment-arm replay of the designer-decision criterion grades it `unverifiable` in at least 2
>   of 3. If the control arm also verifies a positive case, R fails: the observe entry did the work,
>   not the map, and the results file says that.
> - **F: real use.** By `verification_due`, at least one real adopter `/forge` editor transcript, not
>   a replay, opens one of its `features/*.md` and cites, in a `pass` or `fail` verdict, an
>   absolute capture path that file's recipe wrote. Checked from the adopter's transcripts under
>   `~/.claude/projects/`. For each qualifying transcript the results file records whether the
>   editor reached the map through the `CLAUDE.md` pointer or through `observe --help`, judged by
>   which Read or Bash call came first. No qualifying unit by the due date is a fail unless the
>   owner moves the date on the record.
> - **M: maintenance finds planted drift.** `git clone --bare` the adopter into scratch, clone that
>   bare repo, commit one wrong recipe command (an old URL parameter name) to the clone's `main`,
>   and push it to the bare origin. Hand-run `/maintain-verification-skill` from the clone. M holds
>   when the reply names that feature as drift, the fix touches only the skill directory, the fix
>   was re-driven live, and the outcome is `blocked` at step 6, because `gh` can't reach a
>   non-GitHub origin.

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
