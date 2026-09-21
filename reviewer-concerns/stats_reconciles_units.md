# Reviewer concerns — stats_reconciles_units

## The audit-count test freezes git but not the specs, and sits on its own ceiling

**Concern.** `test_the_audit_count_against_this_repo_stays_near_the_truth` reads the frozen
commit-log fixture but walks the *live* specs directory:

```python
SPECS_DIR = REPO_ROOT / "specs"
...
for spec_path in sorted(SPECS_DIR.glob("*.md")):
```

and then asserts `len(ledger.unplanned) <= 20`. The measured value today is exactly 20. Adding
specs only shrinks the count, so the usual direction is safe — but deleting a spec, renaming one
to `*-eval-results.md`, or rewriting prose that happens to quote a built id raises it, and the
suite reds over a change that has nothing to do with this code.

**Why it is unresolved.** Both available fixes are worse than the wart. Capturing the specs into
a second fixture defeats what the test is for (it exists to measure the reader against this
repository's real specs) and adds more of the bloat the fixture already carries. Loosening the
bound contradicts criterion 5's own wording, "the reported built-but-never-planned count is at
most 20", which the approved spec fixed deliberately.

**Smallest follow-up.** When the count next moves, re-measure and re-pin it in the same commit
that moves it, and say in the assertion message that the number is a measurement of this
repository rather than a property of the code — so the next person who reds it knows whether to
fix the reader or re-pin the number.
