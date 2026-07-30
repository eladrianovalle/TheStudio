# TICKET: Calibration — correlate ratings × config, recommend knob changes

**Type:** Feature (Tier 3) · **Component:** `studio/stats.py` (new `calibrate` view) · **Priority:** P2
**Status:** Open · **Author:** Adriano Valle · **Date:** 2026-06-25
**Follows:** `TICKET-stats-expansion` (needs per-role/per-scope rating breakdowns)
**Gated by:** sufficient rated-run history (see Open question below)

## Summary

This is the actual "fine-tuning" payoff. There's **no model to train** — all intelligence is in
the assistant's execution — so calibration is *judgment-driven config tuning*: correlate the
human ratings against the knobs that shape a run (phase/role **personas**, **scope** budgets,
**clarity** thresholds, role pack), surface which configurations produce your best- and
worst-rated runs, and recommend specific adjustments. The human still decides; the tool makes
the evidence legible.

## Why it's gated

Correlation on a handful of runs is noise. This ticket should not start until the progress check
confirms a meaningful rated-run history exists (rough floor: ~20-30 rated runs spread across a
few configs). Until then, the per-role/per-scope breakdowns from `TICKET-stats-expansion` are
enough.

## Proposed shape

### A. `calibrate` read-out
- For each knob dimension (scope, role, persona-override-present vs not, role pack), show avg
  human rating + run count + approval rate. Rank best → worst.
- Highlight the **deltas that clear a confidence floor** (min N per bucket, e.g. ≥5 runs) so we
  don't over-read thin slices. Explicitly `log`/print what was excluded for low N — no silent
  truncation.

### B. Recommendations (conservative)
- Translate strong, well-supported deltas into concrete, reversible suggestions:
  "depth-scope runs for `engineering` average 4.3 vs 2.6 elsewhere — consider raising its budget"
  or "runs without a `.studio/personas.toml` override for `tech` rate 1.5 below those with one."
- Recommendations are **suggestions only** — never auto-edit `.studio/*` config. Print the knob,
  the file, and the evidence; let the human apply and re-rate.

### C. Close the loop
- After a config change, `calibrate` should make the before/after visible (ties into the trend
  work in `TICKET-stats-expansion` — a config change is a natural trend boundary).

## Risks / cautions

- **Confounding**: input difficulty varies run to run; a low rating may be the topic, not the
  config. Keep recommendations humble and require a human in the loop.
- **Small-N over-reading**: enforce the confidence floor; show N alongside every number.
- Resist building a stats engine — descriptive grouping + thresholds, stdlib only. If it wants
  regression/significance testing, stop and reconsider scope.

## Open question (decide at start)

- Confidence floor: min runs per bucket before a delta is shown/recommended? (proposal: 5)
- Do we need to snapshot the *config in effect* at run time into `run.json` for clean attribution?
  Today config is inferred from `studio_roles` / `scopes` already in `run.json` plus presence of
  `.studio/personas.toml` — verify that's enough, or add a `config_fingerprint` at `prepare`.

## Acceptance criteria

- [ ] `calibrate` groups rated runs by config dimension with N shown and a confidence floor.
- [ ] Recommendations are advisory, reversible, and cite evidence; nothing auto-edits config.
- [ ] Low-N buckets excluded *and reported*, not silently dropped.
- [ ] Pure aggregation unit-tested; docs updated.
- [ ] Loop demonstrated once end-to-end: low-rated config → change → later runs rate higher.

## References

- `aggregate_stats()` (extend), `run.json` `studio_roles` / `scopes` / `metrics` for attribution.
- `.studio/personas.toml`, `.studio/roles/*.json`, `.studio/scopes.toml`, clarity thresholds — the
  knobs being calibrated.
- Related: `TICKET-stats-progress-check`, `TICKET-stats-expansion`, `project_stats_and_ratings`,
  `project_phase_personas_global`.
