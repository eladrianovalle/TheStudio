# Superpowers Phase 0 — the baseline, and why it could never be run as written

Captured 2026-07-30 from the run data on disk.

## The headline

**Phase 0 as specified is not executable, and that — not procrastination — is why it has sat undone
since 2026-07-16 while three separate decisions deferred to it.**

The phase says: *"record the current per-unit editor token cost and `editor_liveness` /
`shrink_ratio` over the existing forge runs."* Neither half works:

1. **Per-unit editor token cost is recorded nowhere.** `.claude/workflows/implementation-loop.js`
   contains zero references to `record-metrics` or a session record, and there are **0
   `metrics.json` files** under any `impl_loop/` run directory. The instrument does not exist.
2. **`editor_liveness` / `shrink_ratio` do not measure the forge editor.** `session._summarize_editor`
   takes *advocate document word counts* from a debate run — first draft vs final. It is a metric
   about the **debate contrarian's** effect on advocate docs. The forge loop writes no session record
   at all, so it contributes nothing to it, ever.

## The metric is also broken on its own terms

All 6 session records in the repo:

| Run | first | final | shrink_ratio |
|---|---|---|---|
| run_tech_20260708_164348 | 249 | 249 | 0.0 |
| run_tech_20260708_223215 | 160 | 160 | 0.0 |
| run_tech_20260716_163522 | 568 | 568 | 0.0 |
| run_tech_20260716_181851 | 773 | 773 | 0.0 |
| run_tech_20260730_134434 | 859 | 859 | 0.0 |
| run_tech_20260730_152947 | 618 | 4676 | **−6.5663** |

`editor_liveness` = **0/6 = 0%**, which the scorecard defines as the failure mode ("a dead cut
mandate"). It is not. Two construction faults:

- **Five of six are single-iteration runs.** With one advocate document, the first draft *is* the
  final draft, so `shrink_ratio` is 0.0 by arithmetic. It reports "nothing was cut" for a run where
  there was never a second draft to cut *to*.
- **The sixth reads −6.57 because scoped runs are designed to grow.** `advocate_1` is the alignment
  doc under a ~500-word budget; `advocate_2` is the full depth doc. Growth alignment→depth is the
  intended shape of a scoped run, and the metric scores it as the worst result in the set.

So the number that three decisions were waiting on would have read 0% regardless of how well the
editor was working.

## The baseline that IS available, and it's the one that matters

The forge editor's liveness can be derived from the handoffs on disk — 12 unique runs across both
output locations:

| unit_id | real cuts? | reverted | mvi | rationale words |
|---|---|---|---|---|
| check_updates_signal | no | false | true | 127 |
| finding_verifier | no | false | true | 125 |
| findings_json | yes | false | true | 111 |
| ledger_auto_append | yes | false | true | 86 |
| loop_config_args | yes | false | true | 90 |
| principles_write_for_humans | yes | false | true | 270 |
| pull_source_ff_primitives | yes | false | true | 101 |
| pull_source_wiring_cli | yes | false | true | 79 |
| session_json_finalize | no | false | true | 158 |
| sessionstart_hook_install | yes | false | true | 161 |
| stats_session_health | yes | false | true | 109 |
| unit_impl_loop_config | yes | false | true | 175 |

- **Forge editor liveness: 9/12 = 75%.** The cut mandate is alive. The three "no" runs are ones where
  the editor examined the diff and reported nothing worth cutting, which is a legitimate outcome, not
  a dead mandate.
- **Reverted: 0/12.** No editor edit has ever broken green. The revert path is untested in the field.
- **MVI verdict: 12/12 true.** The editor has never overturned a writer's claim. Worth watching — a
  gate that never fires is either well-fed or asleep.
- **Median rationale: 125 words** against a 400-word budget, so `output_budget` is not binding.

## What this unblocks

The declined breadth valve, the cadence lab, and every scorecard row naming a "before-number" have
been gated on this. The honest answers:

- **Is the editor mandate dead?** No — 75% of runs produce real cuts.
- **What does a widened read scope cost?** Still unanswerable. Token cost per unit is not instrumented,
  and no amount of reading existing runs will produce it.

So the breadth valve's original rejection stands, but the reason should be restated: not "we lack a
baseline because nobody ran Phase 0," but **"per-unit editor cost is not instrumented, so the valve
cannot be measured until it is."** That is a smaller, fixable gap.

## Recommended follow-ups

1. **Fix or retire `editor_liveness`.** As implemented it reads 0% on every single-iteration run and
   negative on every scoped run. Either compare like-for-like documents within a scope, or drop the
   metric and stop citing it in the scorecard.
2. **Instrument the forge loop** if per-unit cost is genuinely wanted — the loop currently emits no
   token data at all. This is the real Phase 0, and it is a build, not a measurement.
3. **Correct the scorecard rows** that name `editor_liveness` as the instrument for forge-editor
   questions; it has never measured that and cannot.
