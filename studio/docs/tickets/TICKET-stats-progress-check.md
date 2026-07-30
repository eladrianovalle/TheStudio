# TICKET: Check in on stats/ratings — is the feedback loop working?

**Type:** Task (ops + verification) · **Component:** `studio/stats.py` (`stats` aggregation) + `studio/run_phase.py` (`rate`) · **Priority:** P3
**Status:** Open · **Author:** Adriano Valle · **Date:** 2026-06-25
**Follows:** Stats + ratings feature (shipped — `rate`/`stats` CLI, `rating.json`)

## Summary

The diagnostics + fine-tuning loop shipped, but a dashboard is only useful if it's fed and
read. This is a recurring **check-in** ticket: after some real runs have accumulated, confirm
the loop is actually being used and that the numbers are trustworthy — *before* we invest in
expansion (`TICKET-stats-expansion`) or calibration (`TICKET-stats-calibration`).

Do this once there are ~10+ finalized runs and a handful of ratings.

## What to check

### A. Is data accumulating?
1. `python studio/run_phase.py stats` — sanity-check the totals against reality.
2. Are runs getting **rated**? If `Rated 0/N`, the loop is open — the human signal is the whole
   point. The auto rate-prompt already shipped (finalize prompts interactively at a TTY / nudges
   otherwise; `/run-phase` + `/run-studio-phase` ask conversationally). So if adoption is still
   low *despite* the prompt, the friction is elsewhere — is the prompt being skipped reflexively?
   Should ratings be required before `validate` passes? Note what's actually blocking adoption.
3. Is `.studio/usage.log` populating (it only logs `prepare`)? Confirm the usage block isn't
   silently empty.

### B. Are the numbers trustworthy?
4. Spot-check approval rate vs. your gut — does the agent verdict track your ratings, or is the
   contrarian rubber-stamping (high APPROVED, low human scores)? A gap there is a *finding*, not
   a bug — it tells you the verdict isn't a reliable quality proxy and ratings matter more.
5. Check token/cost averages for outliers — any run dominating the average?
6. Decision answer-rate: a low rate means runs are assuming rather than pausing — cross-check
   against the collaboration-protocol intent (Studio should pause and ask).

### C. Is the loop closing?
7. Pick the lowest-rated run. Can you trace *why* from its artifacts? If not, that's a signal
   the dashboard needs more per-run drill-down (feed into `TICKET-stats-expansion`).
8. After adjusting any knob (persona/scope/clarity) in response to a low score, did a later
   run on similar input rate higher? That's the loop working — note it.

## Output

A short written read-out (could live in this ticket's comments or a scratch note): current
baseline numbers, whether ratings are happening, any verdict-vs-rating gap, and a go/no-go on
expansion + calibration.

## Acceptance criteria

- [ ] `stats` reviewed against ≥10 real runs.
- [ ] Rating adoption assessed; finalize-nudge decision made (do it / skip / new ticket).
- [ ] Verdict-vs-human-rating gap characterized.
- [ ] Baseline numbers recorded so future check-ins can spot drift.
- [ ] Go/no-go recorded for `TICKET-stats-expansion` and `TICKET-stats-calibration`.

## References

- `studio/docs/CLAUDE_CODE_USAGE.md` → "Quality Ratings & Cross-Run Stats".
- `aggregate_stats()` / `format_stats()` in `studio/stats.py`.
- Related: `feedback_collaboration_protocol` (pause-and-ask intent), `TICKET-stats-expansion`,
  `TICKET-stats-calibration`.
