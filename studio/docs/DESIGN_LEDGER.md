# The design ledger

**This document applies only if this repository builds a game from a design board.** It follows on
from `DESIGN_BOARD.md`: that document says how an agent reads the board; this one says what the build
keeps as its record of having read it. A repository that names no board has no ledger, and nothing
here changes how it works.

A design ledger is the build's account of every design call it made and where each one came from. The
board says what the game is. The ledger says what the build did about it, and quotes the board's own
words for each thing it did. It is not a copy of the board, a summary of it, or a cache of it. It is
provenance: the trail from a rule or a number in the game back to the region of the board it was read
from, or an honest note that the board said nothing and the build chose.

Three rules hold it up.

1. **The board is the only place that says what the game is.** The ledger never carries a design
   statement the board does not; when it quotes, it quotes verbatim, and when the board is silent it
   says so rather than filling the gap.
2. **The ledger records what the build did and where it got it.** Every rule and every tunable number
   in the game is reachable from an entry. A number with no entry is a number nobody can trace, and
   the game's own tests should refuse it.
3. **A quote is the board's words, verbatim.** Not a paraphrase, not a tidy-up, not a translation into
   the game's terms. A check that compares the ledger to the live board can only work when the words
   match exactly, so the quote is kept as it was read.

## Where it lives

`design/ledger.json`, relative to the repository root, unless the repository's own `CLAUDE.md` names
another path. A game whose build lives in a subdirectory may keep it there (`web/design/ledger.json`)
and say so. The game's own code may import it under whatever typed shape it likes; the JSON file is
the record, and a tool outside the game's toolchain reads only that.

## What an entry is

The ledger is one JSON object keyed by ledger id. An id is a short dotted name for one design call,
such as `stamina.cost_per_hit` or `clock.day_length`. Each value has these fields:

| Field | Required | Meaning |
|---|---|---|
| `kind` | yes | How the call was reached: `board`, `joined`, `mine` or `left` (below). |
| `built` | yes | What the game does because of this entry, in plain words. |
| `frames` | all but `mine` | The titles of the board regions the call was read from, as the board shows them. |
| `says` | `board` | The board's words, verbatim, as read. A span of a longer item is fine; the span is the quote. |
| `because` | `joined`, `mine`, `left` | The reasoning: what was connected, why the build chose, or why the board's design was left out. |
| `items` | no | The board's own ids for the items the quote was read from, when the board tool gives them. An entry without them is matched by text alone, which is weaker. |
| `read_on` | no | The date (`YYYY-MM-DD`) the quote was last confirmed against the board. |

The four kinds:

- **`board`**: the board says it, and `says` quotes the region.
- **`joined`**: the build connected two or more regions, or read one a particular way, to get it.
  `because` says how; `says` may quote the part that was read.
- **`mine`**: the board is silent and the build chose. `because` says what was chosen and that the
  board did not decide it. The repository's board rules say where such a choice is raised with the
  designer.
- **`left`**: the board describes it and the build deliberately leaves it out. `because` says why.

An example, in the shape a tool would read:

```json
{
  "stamina.cost_per_hit": {
    "kind": "board",
    "built": "A hit costs ten stamina.",
    "frames": ["Hazards"],
    "says": "−10 stamina per hit",
    "items": ["1234567890"],
    "read_on": "2026-10-20"
  },
  "save.storage": {
    "kind": "mine",
    "built": "Progress is kept in this browser only.",
    "frames": [],
    "because": "The board says nothing about where a save lives."
  }
}
```

## What a tool reading the ledger may assume

Exactly this shape, and nothing else about the game. A tool may rely on the object being keyed by id,
on the fields above with the meanings above, and on `says` being verbatim. It may not assume where the
game keeps its tuning, how it is tested, what its toolchain is, or that any field outside this table
exists. A game that wants to record more keeps it beside the ledger, not inside an entry, so every
reader of the ledger reads the same thing.

## What the game's own tests enforce

Every `board` entry has `says`. Every entry except `mine` names at least one region. Every tunable
number the game exposes is reachable from an entry, by whatever mechanism the game's code uses to tie
a constant to an id. These are the game's tests, run in the game's toolchain; the ledger file carries
no test of its own.
