---
description: "Use at the end of a sprint to review every finished spec that still says status: approved with the human, one row each, and flip the ones they say yes to in a single ready-for-review pull request. Triggers include 'run the sprint review', 'which specs are finished', 'flip the finished specs to shipped', and a session brief pointing at /sprint-review. A hold records what would make it a yes instead of flipping anything."
---

# Sprint Review: Flip Finished Specs in One Reviewed Batch

A spec whose units are all built still says `status: approved` until someone flips it. Flipping
each one on its own costs a full review round for a one-line frontmatter change. This command is
the end-of-sprint meeting instead: it lists every finished spec, the human answers each row, and
every answer lands in one commit on one pull request.

Do not edit any spec's frontmatter outside step 5. Finished specs are reviewed with the human and
flipped together.

Run the steps in order. Every stop below happens before the meeting, except the two in step 5:
nothing to commit, and every answer dropped by the version check. When a step says stop, print the
quoted message exactly as written, change nothing, and end the command.

### Step 0: Studio path

Use `.studio/source/run_phase.py`. If that file does not exist but `studio/run_phase.py` does, use
`studio/run_phase.py` instead (you are in the Studio source repo). `<studio>` below means that path.

### Step 1: Preflight

1. Run `gh auth status`. If it fails, stop: "Opening the batch needs the GitHub CLI signed in. Run `gh auth login` and try again."
2. Run `gh api --paginate "repos/{owner}/{repo}/pulls?state=open&per_page=100" --jq '.[] | {number, url: .html_url, headRefName: .head.ref}'`.
   It reads every page; `gh pr list` stops at 30. If any PR's `headRefName` starts with
   `sprint-review/`, stop, with its number and URL in place of `#N` and `<url>`: "Batch #N (<url>) is still open. Merge or close it, then run /sprint-review again — a second batch now would flip the same specs twice."
3. Run `git fetch origin`. If it fails, stop: "I can't reach `origin`, so I can't see what has merged or branch from an up-to-date default branch."

### Step 2: Read the feed

Run `python <studio> stats --json` and read two keys from it. Never decide for yourself what
"finished" means; the feed's `stale_status` entries are the whole list.

- `obligations` is `null` → stop: "I can't tell what's finished: git history couldn't be read here (a shallow clone, or not a git work tree). Nothing was changed."
- `default_branch` is `null` → stop: "I can't tell which branch is the default here, so I can't tell what has merged or where to open the pull request. If this repo has a GitHub remote called `origin`, run `git remote set-head origin --auto` and try again."
- No entry in `obligations` has `kind` `stale_status` → stop: "Nothing finished is waiting for review."

`<default>` below is the value of `default_branch`.

### Step 3: One row per `stale_status` entry

The spec path is the entry's `spec_file`. Its results path is the same name with `.md` replaced by
`-eval-results.md` (`obligations.evidence_file_for(spec_file)`).

| Field | Source |
|---|---|
| Spec | `subject`, `spec_file`, and the spec's `# ` title |
| On the default branch | `units_off_default_branch`: `[]` → yes; a list → "no — not merged: `<ids>`"; `null` → "can't tell" |
| PRs | Display only. Per unit: `git log origin/<default> -F --grep "writer: <unit_id>" --format=%H`, then `gh pr list --state merged --search <sha>`. Nothing found → "—". Never blocks an answer. |
| Verification | No `## Verification` section → "none promised". Otherwise the `## Verdict` of the results file. |
| Still open | Units not on the default branch, plus every `- **Dropped:** <date> — <reason>` line in the Build Plan. Empty → "nothing". |
| Draft `shipped_impact` | `none`, `minor` or `major`, drafted from the spec's purpose and the merged commit subjects. |
| Draft `shipped_changed` | One plain line on what changed for someone using it, written from what the feature does, not from the fact that it landed. |
| Same as `<default>` | For the spec file and its results file: `git hash-object -- <path>` here against `git rev-parse --verify --quiet origin/<default>:<path>`, a file present on only one side counting as different. Both the same → yes, and keep the two `origin/<default>` ids (or "absent") for step 5. Otherwise → "differs from `<default>`". |

The PR lookup's `-F --grep` is a fixed-string match, so `writer: foo` also matches `writer: foo_bar`.
That only affects this display column. Leave the pattern as it is: a word-boundary pattern matches
nothing on some git builds.

The feed, the Verification column and the drafts are read from this checkout's copies, which can
carry uncommitted or unmerged edits. The batch edits the default branch's copies. The last column
is what lets an answer about one stand for the other.

### Step 4: The meeting

Show all rows at once, numbered.

**Only a row whose `units_off_default_branch` is exactly `[]` and whose spec and results file are
the same as `<default>` takes an answer.** Show every other row with its reason ("not on
`<default>` yet", "differs from `<default>`", or "can't tell") and "it will come back next time". A
row with an absolute `spec_file` (a spec reached through a symlink outside the repo) takes no answer
either.

A row that takes an answer offers exactly these three. A row the human does not answer is left
alone; there is no "skip".

- **yes** — use the drafts.
- **edit** — yes, with the human's `shipped_impact` and/or `shipped_changed`, verbatim. Re-ask if
  `shipped_impact` is not exactly `none`, `minor` or `major`, or `shipped_changed` is empty or more
  than one line.
- **hold** — ask "What would make this a yes?" The answer, verbatim, is the pass criterion. An empty
  or "don't know" answer leaves the row alone; tell the human a hold needs a criterion.

### Step 5: The batch

Only if there is at least one yes, edit or hold. Otherwise stop: "No yes and no hold — nothing to commit, no pull request."

1. Run `git fetch origin` again; a meeting can be long.
2. Make the worktree: `git worktree add -b sprint-review/<YYYY-MM-DD-HHMM> <mktemp -d>/sprint-review origin/<default>`,
   with the current local date and time in the branch name. Every edit happens in that worktree,
   so the session's own checkout, uncommitted work and current branch are never touched.
3. In the worktree, compare each answered row's spec and results file
   (`git rev-parse --verify --quiet HEAD:<path>`) with the ids kept in step 3. If either changed,
   appeared or disappeared on `<default>` during the meeting, drop the row and tell the human: "`<slug>` changed on `<default>` during the meeting, so your answer was about an older version; left out. Run /sprint-review again to review it as it is now."
   Do this for every row before writing anything. If no row survives, `git worktree remove` the
   worktree, `git branch -D` its branch, and stop: "Every answered spec changed on `<default>` during the meeting — nothing to commit, no pull request. Run /sprint-review again to review them as they are now."
4. Apply the writes in "What each answer writes" below, then `git add -- <each path written>`.
   Explicit paths only, never `-A` or `.`.
5. Make one commit holding every answer. Push the branch, then open the pull request with
   `gh pr create --base <default>` **without `--draft`**: the batch is finished when it opens. The body
   lists the specs flipped, the specs held with their criterion and due date, and the rows left
   alone with why.
6. Remove the worktree and print the PR URL. If the push or the PR creation fails, keep the
   worktree and print the branch name and the exact commands to retry; nothing on the default
   branch has changed.

## What each answer writes

The spec path is the feed's `spec_file`; the results path is `obligations.evidence_file_for(spec_file)`.
Both are edited in the worktree.

- **yes / edit** — the frontmatter only. `status: approved` → `status: shipped`; `shipped_impact:` and
  `shipped_changed:` set in place (keeping the template's comment lines), or added under `status:` if
  absent. Nothing else changes.
- **hold** — three writes; `status` stays `approved`.
  1. **`## Verification`, replaced, never duplicated.** If a line starts `## Verification`, replace
     from it up to the next line starting `## `, so the spec still has one Verification section;
     otherwise insert the section above `## Build Plan`. It carries the human's criterion word for
     word, the date of the review, where the evidence goes (the results path), and the stop
     condition: "while that file says `FILL_ME`, this spec stays `approved`; once it is filled in,
     the next `/sprint-review` brings it back". Write no baseline line: the human gave none, and an
     invented one is exactly the invented answer the evidence template warns against.
  2. **`verification_due`** set to the review date plus 30 days (`YYYY-MM-DD`), replacing any
     existing value.
  3. **The results file**, written from the evidence skeleton in `.claude/commands/spec.md`, with
     `<Feature>` and `<slug>` substituted and the criterion word for word, **overwriting** any
     existing file. Read the skeleton there each time instead of writing one from memory, so the
     two cannot drift. A verdict that already passed stays in git history.
