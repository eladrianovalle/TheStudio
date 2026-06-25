# TICKET: Expand stats — trends, drill-down, persisted report

**Type:** Feature · **Component:** `studio/run_phase.py` (`stats`) · **Priority:** P2
**Status:** Open · **Author:** Adriano Valle · **Date:** 2026-06-25
**Follows:** Stats + ratings feature (shipped) · **Gated by:** `TICKET-stats-progress-check` (go/no-go)

## Summary

`stats` v1 is a point-in-time snapshot: it tells you *where you are*, not *which way you're
trending*. This ticket adds the next layer of insight once we've confirmed (via the progress
check) that the data is real and worth investing in. Keep the MVI discipline — each item below
is independently shippable; do the high-leverage ones first, don't build all of it speculatively.

## Candidate work (pick by value, not completeness)

### A. Trends over time (highest value)
- Bucket runs by week/month (runs already carry `created_iso`) and show direction: approval
  rate, avg rating, avg tokens per period. "Are we getting better or just busier?"
- Sparkline-ish text trend or a simple `--since <date>` / `--last N` window filter.

### B. Per-run drill-down
- `stats --run <run_id>` or surface the *worst* runs with enough context to act (verdict +
  rating + note + top unanswered P0/P1). The progress-check ticket flagged that tracing "why a
  run scored low" is currently manual.

### C. Persisted report
- `stats --write` → `output/stats.md` (mirrors `index.md`) so the dashboard can be committed,
  shared, or diffed over time. Cheap, and gives a poor-man's history without a DB.

### D. Richer rating breakdowns
- Avg rating **by role** and **by scope** (join ratings to `run.json` `metrics.by_role` /
  `scope_stats`). This is the bridge to calibration — "depth scope with persona X rates well."
- Rating distribution (how many 1s/2s/3s/4s/5s), not just the mean.

### E. Correlation hints (lightweight)
- Flag simple signals: "REJECTED runs average N more P0 decisions," "runs rated ≤2 average X%
  higher token spend." Pure descriptive stats, no ML — just surface the obvious correlations
  for a human to judge. (Anything heavier belongs in `TICKET-stats-calibration`.)

## Constraints

- Stdlib only; keep `aggregate_stats()` pure and testable (extend it, don't fork it).
- Tolerate missing fields (old runs predate `rating.json`).
- Every new view needs tests + a docs update (CLAUDE_CODE_USAGE.md, API.md) per the doc contract.

## Acceptance criteria

- [ ] At least the trend view (A) and persisted report (C) shipped, or a documented decision to
      defer specific items.
- [ ] `aggregate_stats()` extended (not duplicated); new pure helpers unit-tested.
- [ ] Docs updated for any new flags.
- [ ] Full suite green.

## References

- `aggregate_stats()` / `format_stats()` / `_parse_usage_log()` in `studio/run_phase.py`.
- `write_index()` as the model for a persisted-report writer.
- Related: `TICKET-stats-progress-check`, `TICKET-stats-calibration`, `project_agent_metrics`.
