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
- Tech run `run_tech_20260904_151044` complete. Both scopes ran; both contrarian passes returned
  REJECTED and both were acted on rather than argued with — the spec is written to their cuts.
- **`specs/game-design-board.md` is up as draft PR #148.** Merging it is the approval; the flip to
  `approved` lands after the merge, not in that PR. Two units: `board_conversation` ships first
  (the whole discipline in a new `studio/docs/DESIGN_BOARD.md` plus a pointer and one `SOURCE_FILES`
  entry), then `board_cited_spec`.
- The `/spec` template's own `status:` line carried an inline comment the spec-convention test reads
  as the value, so every spec written from it failed the suite on arrival. Fixed in #148.
- An earlier run (`run_tech_20260904_144331`) was prepared with the wrong framing (read-only,
  writing out of scope) and deleted before any agent ran.

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
