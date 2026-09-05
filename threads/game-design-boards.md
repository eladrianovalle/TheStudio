---
type: thread
status: active
slug: game-design-boards
created: 2026-09-04
updated: 2026-09-04
---

# Game Design Boards: make the GDB Studio's live working surface

## Goal
A designer keeps a Game Design Board — a visual, living game design document, Miro as the reference
implementation — and works with Claude against it conversationally: what's still open, scope this
updated feature into the game, write this feature onto the board, go research a mechanic or an art
direction and file it under art. Eventually an instance watches each board and keeps building.

## Where this stands

**Settled by Adriano, do not re-litigate**
- **The GDB is the only source of truth for what the game is** — mechanics, feel, art direction,
  what's designed and what's open.
- **`specs/` stays the only source of truth for how a feature's code is shaped.** A spec cites the
  board rather than copying it. Adriano agreed to this after initially saying "one source of truth
  only: the GDB"; the argument that moved it was that PR review and the test-enforced verification
  gates only exist for files in git, and they matter most when an agent builds unattended.
- **Studio must not hardcode a vendor.** Shipped prompt text says "a design board" as a category;
  the consuming repo names the tool. This is the `find-before-you-grep` precedent — see that spec's
  "Naming the tool is the repo's job" and "What Studio does *not* do".
- **Reading and writing the board are one capability used differently.** An earlier four-way split
  (read / comment / write / watch) was wrong — it decomposed by mechanism, and with the board
  connected all four are the same thing.

**Verified about the tooling (2026-09-04)**
- Official Miro MCP server: OAuth 2.1, remote-hosted, ~32 tools. Reads `context_explore`,
  `context_get` (costs AI credits), `board_list_items`. Writes docs, tables (`sync_rows` is a
  key-based upsert), mermaid diagrams, images, sticky notes, frames, shapes, cards. Comments:
  `comment_list_comments` / `comment_reply` / `comment_resolve` — a working ask-and-answer loop that
  already exists and does not need building.
- **Miro retired webhooks 2025-12-05 with no replacement.** Nothing can watch a board. Any watcher
  must poll and diff, and an autonomous writer cannot know a human just edited something. This is why
  the watcher is scoped out of the first spec and should be built last.

**Done**
- Tech run `run_tech_20260904_151044` complete; both contrarian passes returned REJECTED and both were
  acted on rather than argued with. `specs/game-design-board.md` merged in #148 and is **`approved`**
  (#153), `verification_due: 2026-10-04`, evidence skeleton created empty beside it.
- **Unit 1 `board_conversation` is built — [PR #154](https://github.com/eladrianovalle/TheStudio/pull/154), 6/6 criteria pass, not flagged.** Ships
  `studio/docs/DESIGN_BOARD.md` + a 3-line conditional pointer in `CODING_PRINCIPLES.md` + one
  `SOURCE_FILES` entry. 1007 tests. Built in the worktree at
  `_TheGameStudio-wt/board-conversation` — **archive `reviewer-concerns/` and any `.studio/output/`
  before removing it**, per [[feedback_worktree_removal_eats_run_artifacts]].
- The editor raised two concerns and **both were fixed in the same PR**, not deferred. The first is
  worth remembering: the vendor-name guard scanned line by line and skipped each line's first word as
  a sentence opener, but the docs are hard-wrapped, so a product name at the start of a wrapped line
  passed the only guard Studio has — and criterion 2 had already been graded `pass` against it. Now
  scans blocks. The second: the pointer shipped to every consuming repo's CLAUDE.md while this repo's
  own never gained it, invisible to the doc-parity mirror because that test only reads *numbered*
  principles.

**Next**
- Merge #154, then unit 2 `board_cited_spec` (the `/spec` citation clause — small, depends on unit 1).
- **Adriano: connect a board.** `claude mcp add --transport http miro https://mcp.miro.com/ --scope user`.
  Everything shipped is inert until a repo declares one. The 2026-10-04 evidence deadline needs a real
  board with real content, most likely in whichever repo holds the game — not this one, which has no
  game design board.

## Settled by the alignment pass (2026-09-04)
- **No cached structural map.** Cut. Its contents are exactly what Miro's `context_explore` returns,
  and that call is free — only `context_get` costs AI credits (verified against Miro's tools table).
  The cache saved free calls while its own failure mode, a lookup at a stale id, was the paid one.
  Deleting it also dissolved two P1s that existed only to prop it up, and is what lets the design
  stay honestly prompt-text-only.
- **The repo designates where agent writes land.** Studio's shipped text says "one place the repo
  designates"; the repo's CLAUDE.md (or an optional `.studio/integrations.toml` entry, following
  `slack_digest.py`'s disabled-unless-enabled pattern) names it. An earlier proposal of "one
  agent-owned landing frame" was cut: "frame" is a Miro noun and shipping it breaches vendor
  neutrality. This also dissolved the P0 I had put to Adriano about conventions on his board — he
  picks a destination as a config value, not as an architecture decision.
- **Kept:** read-before-write in the same turn on the region being written (nothing can tell the
  agent a human just edited it); writes constrained to structured types, never prose on a canvas;
  every claim about board content sourced from a real read, never from structure.

## The delivery vector (depth pass, verified 2026-09-04)
`studio/docs/CODING_PRINCIPLES.md` is in `SOURCE_FILES` (`install.py:69`) and `install.py` injects it,
sentinel-wrapped and heading-downgraded, into every consuming repo's CLAUDE.md. **A new section there
lands the whole capability, always-on, in all ten repos with zero Python** — no `SLASH_COMMANDS`
registry edit, no retirement debt, no version bump. Cleaner than find-before-you-grep's own three-file
delivery. A `/board` slash command was rejected for the opposite reason: it needs a Python registry
edit, and plain chat is the right ergonomic anyway. Also verified: `load_integrations_config` returns
the whole parsed dict, so an unknown `[design_board]` table is ignored rather than rejected.

## Open questions
- **How does the agent tell "still open" from "decided" on a free-form board?** The real hole. Nothing
  on a canvas signals it. Lean: the repo states its marker in one line (sticky colour, "TBD" prefix,
  a dedicated area — whatever Adriano actually uses), and with no marker the agent gives a reading it
  explicitly labels as a guess. **Waiting on Adriano to say how he marks undecided today.** The option
  where the agent maintains its own open-questions list is cut — that is the duplication the settled
  source-of-truth decision forbids.
- **Is the coding-principles doc the right home?** It is behavioural guidance for writing code, and
  this rents ~30 dormant lines in ten repos that mostly have no board. Recorded as a provisional P1;
  the depth contrarian was asked to rule on the topical fit and its ruling wins.

## Landmines
- **Do not split this by mechanism again.** Read/write/comment/watch is not a unit boundary.
- **Nothing may assume push notification of board changes.** See the webhook retirement above.
- **A committed copy of board content is a second source of truth that goes stale silently** — the
  exact failure mode a living GDB exists to avoid. Specs cite, never duplicate.
