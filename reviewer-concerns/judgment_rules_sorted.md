# Reviewer concerns: judgment_rules_sorted

## 1. The judge for "An index summary is not evidence; quote the file." carries only half the rule

- **Concern:** The row cites `studio/scopes.py::CONTRARIAN_MANDATE` as the judge. That list carries
  "Quote before you claim" but nothing about index summaries. The index-summary sentence reaches the
  `/forge` writer and editor (`.claude/workflows/implementation-loop.js`) and the session running
  `/spec` (`.claude/commands/spec.md`, "Finding code"), but no debate-contrarian prompt in
  `studio/scopes.py` or `studio/run_phase.py` says it. The citation test passes because the name
  exists, not because the judge judges the whole rule.
- **Why unresolved:** load_bearing. The writer marked this row's citation as deliberate, and the fix
  is a prompt change, which is outside this unit.
- **Follow-up:** Either add the index-summary line to the contrarian's prompt in `scopes.py`, or
  shorten the row's rule to the half the mandate carries ("A finding quotes the thing it critiques.").
