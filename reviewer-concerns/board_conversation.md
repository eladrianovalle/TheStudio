# Reviewer concerns — board_conversation

> **Both concerns below were fixed in commit `5e214af`, in this same PR.** They are kept as written
> because they are the editor pass doing its job — and because the first one is the more interesting
> half: the vendor-name guard had a hole in the exact position a vendor name lands, and criterion 2
> had already been graded `pass` against it. Read them as a record of what the loop caught, not as
> open work.

Two real problems the editor pass could not safely fix. Both were checked against the
files, not inferred.

## 1. The vendor scan misses the start of every wrapped line

**Concern.** `_mid_sentence_capitalized_words()` in `studio/tests/test_design_board.py`
walks the document one line at a time and skips each line's first word:

```python
for sentence in _SENTENCE_SPLIT.split(line):
    words = sentence.split()
    for word in words[1:]:
```

Skipping the first word is right for a sentence, which always opens with a capital. But
`DESIGN_BOARD.md` is hard-wrapped, so most lines *start mid-sentence* — and that first
word gets the same exemption. A board vendor's name that happens to land at the start of
a wrapped line is not seen. That is roughly one word position in twelve going unchecked
in the only guard Studio has against naming a tool in shipped text.

**Why the editor pass left it.** `_mid_sentence_capitalized_words()` is a load_bearing item for
this unit, and the obvious fix — join the paragraph's lines before scanning — changes how
headings and bullets are fed to the same function, which is where the deliberate
"title-case heading trips the scan" signal lives.

**How it was fixed.** The text is split into blocks first — a heading is its own block, a
bullet or numbered item opens a block its own wrapped lines join, and a paragraph is its
lines joined by a space — and the existing per-sentence scan runs over each block. That
closes the wrapped-line hole and leaves the heading behavior exactly as it is today.

## 2. Studio ships the pointer to other repos but never carries it itself

**Concern.** `_build_principles_block()` in `studio/install.py` injects the *whole* of
`docs/CODING_PRINCIPLES.md` into a consuming repo's `CLAUDE.md`, so the new `## Design
board` pointer reaches all ten installed repos. This repo's own `CLAUDE.md` does not have
it — `grep -i "design board" CLAUDE.md` returns nothing. The parity test does not notice,
because `_principle_lines()` in `studio/tests/test_doc_parity.py` only collects headings
matching `^#{2,3} (\d+\. .+)$`, and the pointer is deliberately not numbered. That is the
exact drift the mirror test's own docstring warns about: "Studio starts telling other
repos something it doesn't tell itself."

**Why the editor pass left it.** Out of this unit's scope — the fix is a change to the repo's
`CLAUDE.md`, which is not a file this unit touches, and the pointer's placement outside
the numbered principles is a load_bearing decision that keeps the parity test green.

**How it was fixed.** The same three-line pointer was added to this repo's `CLAUDE.md`
after principle 7, so the invariant stays true rather than gaining a documented exception.
