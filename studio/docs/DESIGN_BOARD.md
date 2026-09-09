# Working against a design board

**This document applies only if this repository names a design board in its own `CLAUDE.md`.** If it
names none, everything here is inert — there is no board, so the agent says it has no board rather
than answering from memory, and nothing below changes how the repository already works.

A design board is the living version of a game design document: mechanics, feel, art direction, what
is decided and what is still up in the air, kept on a shared visual surface instead of in a file
nobody opens. With one connected, the designer works against it in plain conversation. No command to
type first.

Two rules hold the rest up. **The board is the only place that says what the game is** — nothing here
keeps a copy, a cache, a mirror or an index, because a copy starts lying the moment someone moves an
item. And **the agent never claims anything about the game that it did not just read.**

The repository names the actual tool, the board itself, and the destinations for writes in that same
`CLAUDE.md`. Nothing parses that declaration; it is prose the agent reads.

## The order of operations

### 1. Locate before you read

Every turn that touches the board opens with the board's structural listing — the call that returns
which regions exist. Make it first, make it every turn, and never substitute a listing remembered
from an earlier turn. It is the cheap call; the content read is the expensive one. Having listed the
regions, name the one you are about to open and why, then open it.

### 2. Structure gives addresses, never content

The structural listing returns region names, ids and types. Those are addresses. A region titled
"combat" tells you where to look for the combat rules and tells you nothing whatsoever about what
they say. Never answer a question about the game out of a title, an id, or the shape of the listing.

### 3. Every claim about the game is sourced to a region read this turn

If the agent says the game does something, it can point at the region it opened in this turn to say
where that came from. Not a title. Not an earlier turn. Not the model's memory of the conversation.
A claim with no region behind it does not get made.

When the listing offers more regions than you can sensibly choose from, ask the designer which area
to look in. Opening twenty regions to find one is not thoroughness; it is spending the expensive call
in place of a question.

### 4. Re-read the destination region in the same turn, before any write

Nothing tells the agent when a board changed, so the only way to know a destination still looks the
way it did is to look again, in the same turn as the write. If it moved — an item edited, removed, or
added since the read — stop, say what changed, and write nothing. Never overwrite work someone typed
a minute ago.

### 5. Propose the exact item and the exact destination before writing

Say what will be written, in the words it will be written in, and where it will land. Then wait. The
designer must have seen the proposal before anything is written, and nothing gets written that they
did not see proposed. Once the write lands, report what landed and where, with ids.

### 6. Say so plainly when something cannot be sourced

"The board does not say" is a real answer and the required one. When a region does not cover the
question, when the read failed, or when the board has no such area, say that. Never fill the gap with
something plausible: an invented answer about the designer's own game is worse than no answer,
because it is indistinguishable from a read.

## Where writes land

Agent writes go to the destination the repository designates. A repository may also name further
destinations by purpose — research output to one place, art references to another. When it names
only one destination, everything falls to that one.

## Answering "what is still open"

Nothing on a free-form board separates an open question from a settled one on its own. So: if the
repository states how it marks something undecided, use that marker and answer from it. If it states
none, give a reading and label it as a reading of what you found, not a status you looked up.

Never keep your own list of open questions. That is the copy the first rule forbids, and it goes
stale the moment the designer settles something on the board.
