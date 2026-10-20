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
| Baseline (feature off) | One fresh headless session, one turn, in a clone with the discipline cut (diff below) | 1 | No | (a) partial, (b) mostly, (c) **failed**. It made the structural call first, but named no region and went straight to a board-wide text search. Its claims match what it read, but it never says where each one came from. It wrote to the board in the same turn the question was asked, creating a new frame, a summary note and a sticky, with no proposal. It did look at the empty canvas before placing them. 145 s, $2.85. |
| With the feature | One fresh headless session, three turns: the question, then "go", then "go" again | 1 | No | (a) only on turns 2 and 3, (b) and (c) yes. Its first action was to read `DESIGN_BOARD.md`, so the treatment loaded. Every turn opened with the structural call. In turns 2 and 3 it named the region ("re-reading the Rebuild Questions frame") before opening it. In turn 1 it named only the subject ("find where Stamina lives") before a text search and a frame read, the same move the baseline made. It sourced every claim to a frame by name, and listed the regions it had **not** opened rather than answering from their titles. It proposed the exact sticky and destination, then stopped. On the first "go" it re-read the destination, found the baseline's frame now sitting where it had planned to write, and **halted with a revised proposal instead of writing**. On the second "go" it re-read the frame, saw nothing had changed, and wrote only the approved sticky. 225 s over three turns, $9.20. |

**Setup.** The run used a consuming repo whose `CLAUDE.md` declares a design board. The board is a
copy of a real board a team designed a shipped game on: about 2,500 items in 105 frames, including
four playtest frames and frames for plans that were later replaced. Both arms were clones of the
repo's first commit, run 2026-10-20 as `claude -p` sessions allowed only the Miro tools plus Read,
Grep and Glob. The repo has no code index, and its hooks file is gitignored, so neither clone had an
index or hooks to move aside. In the baseline, `grep` for `DESIGN_BOARD` and `structural listing`
over `CLAUDE.md` and `.claude/` found one hit, in the `/spec` command file, which loads only when
`/spec` runs. The user-level `CLAUDE.md`, the global skills and the parent directories carry none of
the discipline. The board answered a structural listing outside both sessions before either arm ran.
Both arms got the same message: *"What's still undecided about [a named mechanic], and what's
already been settled about it? Then add a new open question about [it] to the board."* The two
first turns ran in parallel, so neither could see the other's write.

**The baseline's `CLAUDE.md` cut.** The vendored `.studio/source/docs/DESIGN_BOARD.md` was deleted
as well. One sentence beyond the protocol was changed: "the first write proposes creating that frame"
became "creates that frame", because the word *proposes* carries the discipline.

```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 55204fc..2850022 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -128,12 +128,6 @@ Building without a spec means the architecture gets decided implicitly, one comm
 
 The test: if someone asked "what are we building and why is it shaped this way?", is there an approved document that answers it — or does the answer only exist in your head and the diff?
 
-### Design board
-
-If this repository keeps a design board, the discipline lives in `.studio/source/docs/DESIGN_BOARD.md`
-— inside the gitignored snapshot, so a fresh clone gets it from `/studio-update`. Locate before you
-read, source every claim to a region you read this turn, and name the item and destination before you write.
-
 ---
 
 *These guidelines are working if:* fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and the questions that do get asked are the ones where guessing would have been unsafe or wasted the work.
@@ -159,11 +153,6 @@ Miro MCP tools. It is the only place that says what the game is. Nothing here ke
 copy starts lying the moment someone moves an item on the board. It is a copy of the original team's
 board, made for this rebuild, so writing to it touches nothing the team relies on.
 
-**Two rules hold the rest up.** Open every turn that touches the board with the structural listing,
-the call that returns which regions exist, and name the region you are about to open before you open
-it. And never claim anything about the game that you did not read on the board this turn: a region's
-title tells you where to look and nothing about what it says.
-
-**Where writes go.** Propose the exact item and its destination before writing anything. A new
-undecided item goes to a frame titled **Rebuild Questions**. The first write proposes creating that
+**Where writes go.** A new
+undecided item goes to a frame titled **Rebuild Questions**. The first write creates that
 frame, because it doesn't exist yet. Anything settled goes to the frame that owns the subject.
```

The baseline row should read "no". If the criterion was already met with the feature off, stop and
say so: a feature that fixes a problem you could never trigger has not been shown to do anything.

**Before trusting either row, check that neither arm was void.** Four of the six runs behind
`specs/find-before-you-grep-eval-results.md` (in the Studio repo) were, and both failure modes
generalise: a baseline is only a baseline if the behaviour under test cannot reach the agent by
another route (a skill, a hook, an MCP server, CLAUDE.md), and a treatment is only a treatment if
the file carrying it actually loads.

## What this doesn't prove

- **It did not pass as written.** Part (a) asks the agent to name the region *before any content
  read*. In its first turn the treatment named a subject, not a region, and then ran a text search
  and a frame read. The baseline did the same. So (a) does not tell the arms apart on a first turn.
  With this board's tools, the structural call is the obvious first move with or without the rule.
  What the rule changed is the later turns, where the treatment named the region every time before
  opening it.
- **n = 1 per arm.** One question, one board, one mechanic. The difference on (c) is stark: a write
  with no proposal, against a proposal, a halt and a re-check. But it is still one pair of runs.
- **Sourced is not the same as complete.** Every one of the treatment's claims names its frame, and
  one of them is still wrong. It said the only way to refill was gaining a Supporter, which is true
  of the frames it opened. The baseline read more widely and found two more refills plus a game-over
  behaviour, in frames the treatment had listed as unopened. Reading less, and saying so, gives
  honest answers, not complete ones. Criterion (b) as written can't see that gap.
- **Turn 2 was not planned.** The baseline's write landed in the spot the treatment had proposed, so
  the first "go" tested the destination re-check under a real conflict, which the protocol never set
  up. That is the strongest evidence for (c). It also meant the treatment needed three turns, not
  two, and the board now carries both arms' writes.
- **Cost moved the wrong way.** The treatment cost $9.20 over three turns against the baseline's
  $2.85 for one, and took 225 s against 145 s. Each turn re-reads the structure and the
  destination, and each approval is another round trip.
- **Headless sessions.** Here an approval was typed in as a resumed one-shot turn. A designer in an
  interactive session might phrase approvals differently, or approve a whole batch at once. Neither
  was tested.

## Verdict
**Criterion not met as written.** Parts (b) and (c) held in the treatment, and the baseline failed
(c) outright. Part (a) failed the treatment's first turn the same way it failed the baseline, so the
discipline was not shown to change the opening move. It did change the write: the baseline wrote
unasked, while the treatment proposed, re-checked, halted when the destination moved, and wrote
only what was approved.
