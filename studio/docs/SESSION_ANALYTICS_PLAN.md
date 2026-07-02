# Session Analytics — plan (not yet built)

A design for measuring Studio runs over time *without* rating outputs that
haven't been implemented yet. Captured from a Fable 5 design pass; not
implemented. Single-user context assumed throughout (one person, one machine,
records moving between their own repos) — so the "central ledger" is just a local
file path, and there are no multi-user or access concerns to design around.

## The problem this solves

Rating a run at finalize is noise: a Studio run is a *planning session*, and its
specs/decisions get implemented later (via `/studio-implement` or by hand in a
consuming repo). You can't judge whether the plan was good before it's built. So
`rate` after a run is close to useless, and the outcome ledger it feeds only sees
the runs you bothered to rate.

The reframe: you can't measure plan *quality* at finalize, but you can measure
session *health* — did the debate converge, surface and settle the right
questions, reduce uncertainty, and at what cost. All of that is derivable
automatically from data a run already produces. No rating, no waiting for
implementation.

## Part 1 — `session.json`, auto-written at finalize

Written into the run dir at the end of `finalize_run`, entirely from files
finalize already touches. No human input. Proposed schema:

```json
{
  "run_id": "run_studio_20260701_...",
  "repo": "Pictorly",
  "phase": "studio",
  "mode": "deliverables",
  "finalized_iso": "...",
  "verdict": "APPROVED",
  "convergence": { "iterations": 3, "max_iterations": 4, "rejections": 2 },
  "decisions": {
    "surfaced": {"P0": 2, "P1": 5, "P2": 3},
    "answered_by_user": 6, "answered_by_assumption": 3, "unanswered": 1,
    "p0_assumed": 0
  },
  "clarity": { "mean_before": 0.42, "mean_after": 0.71, "topics_touched": 3 },
  "cost": { "total_tokens": 210000, "duration_ms": 840000, "agents": 9,
            "tokens_per_settled_decision": 23300,
            "scope_pct": {"alignment": 25, "depth": 60, "polish": 15} },
  "editor": { "first_draft_words": 2400, "final_words": 1600, "shrink_ratio": 0.33 },
  "outcome": null
}
```

### Signals, ranked by signal-to-effort

Tier 1 — data already in hand at finalize, zero new plumbing:

1. **Convergence: iterations-to-verdict + rejection count.** `finalize_run`
   already computes `iterations_run`; the contrarian files are on disk, so run
   `verdict.py`'s extractor over each `contrarian_*.md` and count REJECTED
   verdicts before the final one. `iterations=1, rejections=0` on a hard topic is
   a rubber-stamp smell; `rejections=2 → APPROVED` is the debate doing work.
2. **Decision profile: surfaced / answered-by-user / answered-by-assumption, by
   priority.** `decisions.json` already carries `priority` and `answered_by`
   ("user" vs "assumption"). The killer stat is **P0s answered by assumption** —
   every one is a blocking thing the session guessed on.
3. **Clarity delta.** `finalize_run` already loads the prior snapshot right
   before computing the new one. Record `mean_before`, `mean_after`, topics
   touched. This is the de-risking signal.
4. **Cost per settled decision.** `metrics.json` gives tokens/duration; divide by
   decisions answered. Turns raw token counts into "what the spend bought."
5. **Scope spend distribution.** `_summarize_metrics` already produces per-scope
   token percentages. 60% of tokens in polish = misallocation.

Tier 2 — one small addition:

6. **Contrarian cut signal (editor liveness).** The mandate says delete, but
   nothing measures it. Cheapest honest proxy: word counts of the advocate doc
   first draft vs final (`len(text.split())` on files already on disk). Report
   `shrink_ratio`. Crude, but it detects the real failure mode — a *dead*
   mandate where docs only ever grow. Don't over-engineer into diffing.

Skip: semantic measures of cut quality, per-role "intensity," any LLM-judge at
finalize. Effort-heavy and gameable.

`session.json` is mandatory, automatic, judgment-free. `rating.json` stays as-is:
optional, later, human. The `outcome` field starts null and is the only part a
human ever touches (Part 4).

## Part 2 — trends in `stats`

A "Session health (last N vs. prior N)" block reading `session.json` files. Keep
it to five that mean something:

- **Assumed-P0 rate** — P0s answered by assumption / P0s surfaced. Should trend
  to zero; the best "are we pausing when we should" number.
- **Convergence profile** — median iterations and rejection rate. Watch for drift
  toward 1-iteration-0-rejection (rubber-stamping) as much as toward churn.
- **Clarity gain per session** — mean delta. Zero on a new project means sessions
  aren't de-risking.
- **Tokens per settled decision** — the honest efficiency number.
- **Editor liveness** — % of sessions where the final doc is smaller than the
  first draft.

Vanity metrics to refuse: total runs, total tokens, and approval-rate-as-a-target
(100% approval means the contrarian died).

## Part 3 — automating export → import (single-user simplification)

Because it's one person on one machine, the "central ledger" is just a fixed
local path (the tool repo's `knowledge/outcomes.jsonl`). Collapse the manual
`export-outcomes` → carry → `import-outcomes` two-step into an **auto-append at
finalize**:

- New `[outcomes] ledger_path = "..."` config (natural home: `.studio/integrations.toml`,
  already the "where finalize side-effects go" file; copy the `_maybe_notify`
  soft-fail pattern).
- At finalize, append the session record to that path. Same dedup key
  `(repo, run_id)`; a later outcome update re-appends and the merge refreshes.
- **Every session becomes visible to tool-repo `stats` automatically — including
  unrated runs**, which fixes the actual complaint.

Keep `export-outcomes`/`import-outcomes` as the fallback for the rare case a repo
lives on another machine. Pitfalls: soft-fail if the path is unreachable (never
break finalize); keep the raw run `input` text OUT of the record (only
run_id/repo/phase) so the gitignored ledger stays cheap to redact; append lines
from consuming repos, compact/dedup only in the tool repo.

## Part 4 — linking a session to what it produced (deferred)

The plan's real value shows up only when implemented — the honest hard part.
Lowest-ceremony approach, added once a month of session records exists:

- **Automatable:** `/studio-implement` (and rerun) carries `--from-run <run_id>`,
  writes `spawned_by` into its own record and appends the implement-run id into
  the parent session's `outcome.implementations`. Free when implementation
  happens in the same repo.
- **The irreducible human moment** (implemented-by-hand, weeks later): one
  command, three enums, no score —
  `studio outcome --run-id <id> --result implemented|partial|dropped|superseded [--note]`.
  "Dropped" is a legit win (the session correctly killed a bad idea). `stats` can
  nag: "4 approved sessions >30 days old have no outcome." That's the only human
  touch, and it happens when you actually know.

## Honest caveats

- **Low iterations** = easy topic OR a contrarian that folded. Cross-check with
  rejections and clarity-before; flag 1-iteration runs on low-clarity topics.
- **High P0 count** = thorough agents OR an under-specified prompt. Read per-topic
  over time; P0s should fall as clarity rises.
- **Shrink ratio** isn't quality; a lazy editor could cut essence. Liveness check
  only, never a target.
- **Goodhart:** none of these may ever appear in agent prompts as targets
  ("surface ≥N decisions" would poison the P0 signal instantly). They're for the
  human reading `stats`, full stop.
- Deepest check: periodically ask whether healthy-looking sessions actually get
  implemented. If not, the health metrics are theater — process is only the
  product if the product eventually exists.

## Recommended first slice (when built)

1. `session.json` at finalize (convergence, decisions, clarity delta, cost;
   editor word-count block only if trivial).
2. Ledger auto-append via `[outcomes] ledger_path`, soft-fail.
3. `stats` session-health block with the five trends and the assumed-P0 nag.

Defer: the `studio outcome` command and `--from-run` linking, any correlation
analytics, all semantic/LLM-judged measures. `rate` stays exactly as-is.
