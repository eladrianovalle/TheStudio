# Reviewer concerns — `obligation_queue_core`

Two things the editor pass found, verified, and could not fix without breaking a test the
writer had just written. Neither is a defect a user would see today; both are shapes worth
settling before the next change lands on this code.

## 1. `stats` derives the whole answer twice

**The concern.** `show_stats` reads the specs directory and runs `git log` to build its
ledger:

```python
built_ids = _built_unit_ids(root)
unit_ledger = reconcile_units(_approved_spec_units(), built, escalated, _mentioned_unit_ids())
obligations = _collect_obligations(root, today=date.today(), specs_dir=get_specs_dir())
```

`_collect_obligations` then reads the same specs directory, parses the same Build Plans, runs
`git log` a second time and reconciles a second ledger, whose `unbuilt`, `escalated` and
`dropped` are identical to the one above. The spec's data flow says "One `git log` call yields
the built and escalated unit ids. This is today's call, unchanged" — the dashboard now makes
two. Nothing is wrong in the output, and on this repo the whole command still runs in about a
fifth of a second, so this is duplication rather than a bug. It matters mainly because the two
reads could drift: they already disagree about one thing, the `spec_file` on a `PlannedUnit`
(`_approved_spec_units` records an absolute path, `_collect_obligations` a repo-relative one).

**Why it was not fixed in this pass.** The fix changes `_collect_obligations`'s signature or
its return shape, and `tests/test_update_check.py::test_one_unparseable_spec_takes_only_its_own_obligations_down`
calls it directly and compares the list it returns. Rewriting a test the writer added in the
same unit, to accommodate a refactor with no user-visible payoff, is more than this pass should
spend.

**Smallest follow-up.** Let `show_stats` hand the units and the `(built, escalated)` sets it has
already read to `_collect_obligations`, so the dashboard reads the specs and calls git once;
keep the session brief on the current no-arguments path.

## 2. "Approved" is filtered in two places, and only half of it reaches the units

**The concern.** `obligations.derive` filters the spec-level kinds itself:

```python
for spec in specs:
    if spec.status != "approved":
        continue
```

but the unit-level obligations are built straight off `ledger.unbuilt`, which nothing in the
module filters by status. The only caller, `_collect_obligations`, already iterates
`_approved_specs(...)`, so in production every `SpecView` is approved and every unit in the
ledger came from an approved spec — the guard never fires, and `SpecView.status` never holds
anything but `"approved"`. A reader meeting the guard reasonably concludes the module screens
its own inputs, which is only true of two of the three kinds.

**Why it was not fixed in this pass.** Deleting the field and the guard reds
`tests/test_obligations.py::test_a_spec_that_is_not_approved_is_skipped_and_the_next_one_is_still_read`,
and `status: str` is part of the `SpecView` interface written into the approved spec, so
removing it is a spec change rather than an editor's cut.

**Smallest follow-up.** Pick one owner for the approved filter. Either the caller owns it —
drop `SpecView.status` and the guard, and say in the docstring that every view handed in is
approved — or the module owns it, and `derive` also drops unbuilt units whose `spec_file` is not
one of the approved views it was given.
