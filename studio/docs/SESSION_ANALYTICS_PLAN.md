# Session Analytics: design + status

A design for measuring Studio runs over time *without* rating outputs that
haven't been implemented yet. Captured from a Fable 5 design pass. Single-user
context assumed throughout (one person, one machine, records moving between their
own repos). The "central ledger" is just a local file path, and there are no
multi-user or access concerns to design around.

**Status: first slice shipped.** The recommended first slice (see the bottom
section) is built, via the `/forge` writer/editor loop:

- `session.json`, auto-written at finalize. `session.py` holds the pure
  record builder (`build_session_record` + the `_summarize_*` helpers); the
  finalize wiring lives in `run_phase._write_session_record`, which reads the run
  dir and passes the pieces in. Additive and soft-fail: it never gates finalize.
- `stats` session-health block. `stats.summarize_session_health` (pure) computes
  the signals; `run_phase.show_stats` loads each run's `session.json` and adds
  a `session_health` key to `--json`.

**Since retired (see `specs/retire-volunteer-metrics.md`):** the cost and editor
blocks, and with them tokens-per-settled-decision, scope spend distribution and
editor liveness. All three were fed by the per-agent token ledger, which an agent
had to write by hand after every agent in every run — and across roughly 150 runs
in ten repos, not one ever did. The `outcome` field went with them: it was the
one field a human was meant to edit later. The rest of that volunteer path is
gone too: `rate` and `rating.json`, the `export-outcomes`/`import-outcomes`
ledger, and the `[outcomes] ledger_path` auto-append this section used to
describe as shipped. Outcome capture now lives in a shipped spec's frontmatter,
which `stats` reads. What survives here is what finalize can count off disk on
its own: convergence, decisions, clarity.

**Still deferred:** session→implementation linking (Part 4, `--from-run`) and any
correlation/LLM-judged analytics. The honest caveats below still apply to what
shipped.

## The problem this solves

Rating a run at finalize is noise: a Studio run is a *planning session*, and its
specs/decisions get implemented later (via `/forge` or by hand in a
consuming repo). You can't judge whether the plan was good before it's built. So
the rating prompt Studio used to close a run with was close to useless, and the
outcome ledger it fed only ever saw the runs somebody bothered to rate — which,
in five months, was none of them.

The reframe: you can't measure plan *quality* at finalize, but you can measure
session *health*: did the debate converge, surface and settle the right
questions, reduce uncertainty. All of that is derivable automatically from data
a run already produces. None of it needs a rating or a wait for implementation.

## Part 1: `session.json`, auto-written at finalize

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
  "clarity": { "mean_before": 0.42, "mean_after": 0.71, "topics_touched": 3 }
}
```

### Signals, ranked by signal-to-effort

Tier 1, data already in hand at finalize, zero new plumbing:

1. **Convergence: iterations-to-verdict + rejection count.** `finalize_run`
   already computes `iterations_run`; the contrarian files are on disk, so run
   `verdict.py`'s extractor over each `contrarian_*.md` and count REJECTED
   verdicts before the final one. `iterations=1, rejections=0` on a hard topic is
   a rubber-stamp smell; `rejections=2 → APPROVED` is the debate doing work.
2. **Decision profile: surfaced / answered-by-user / answered-by-assumption, by
   priority.** `decisions.json` already carries `priority` and `answered_by`
   ("user" vs "assumption"). The killer stat is **P0s answered by assumption**:
   every one is a blocking thing the session guessed on.
3. **Clarity delta.** `finalize_run` already loads the prior snapshot right
   before computing the new one. Record `mean_before`, `mean_after`, topics
   touched. This is the de-risking signal.

Skip: semantic measures of cut quality, per-role "intensity," any LLM-judge at
finalize. Effort-heavy and gameable.

`session.json` is mandatory, automatic, judgment-free.

## Part 2: trends in `stats`

A "Session health (last N vs. prior N)" block reading `session.json` files. Keep
it to the few that mean something:

- **Assumed-P0 rate**: P0s answered by assumption / P0s surfaced. Should trend
  to zero; the best "are we pausing when we should" number.
- **Convergence profile**: median iterations and rejection rate. Watch for drift
  toward 1-iteration-0-rejection (rubber-stamping) as much as toward churn.
- **Clarity gain per session**: mean delta. Zero on a new project means sessions
  aren't de-risking.

Vanity metrics to refuse: total runs, total tokens, and approval-rate-as-a-target
(100% approval means the contrarian died).

## Part 3: automating export → import (single-user simplification)

Because it's one person on one machine, the "central ledger" is just a fixed
local path (the tool repo's `knowledge/outcomes.jsonl`). Collapse the manual
`export-outcomes` → carry → `import-outcomes` two-step into an **auto-append at
finalize**:

- New `[outcomes] ledger_path = "..."` config (natural home: `.studio/integrations.toml`,
  already the "where finalize side-effects go" file; copy the `_maybe_notify`
  soft-fail pattern).
- At finalize, append the session record to that path. Same dedup key
  `(repo, run_id)`; a later outcome update re-appends and the merge refreshes.
- **Every session becomes visible to tool-repo `stats` automatically, including
  unrated runs**, which fixes the actual complaint.

Keep `export-outcomes`/`import-outcomes` as the fallback for the rare case a repo
lives on another machine. Pitfalls: soft-fail if the path is unreachable (never
break finalize); keep the raw run `input` text OUT of the record (only
run_id/repo/phase) so the gitignored ledger stays cheap to redact; append lines
from consuming repos, compact/dedup only in the tool repo.

## Part 4: linking a session to what it produced (deferred)

The plan's real value shows up only when implemented, the honest hard part.
Lowest-ceremony approach, added once a month of session records exists:

- **Automatable:** `/forge` (and rerun) carries `--from-run <run_id>`,
  writes `spawned_by` into its own record and appends the implement-run id into
  the parent session's `outcome.implementations`. Free when implementation
  happens in the same repo.
- **The irreducible human moment** (implemented-by-hand, weeks later): one
  command, three enums, no score:
  `studio outcome --run-id <id> --result implemented|partial|dropped|superseded [--note]`.
  "Dropped" is a legit win (the session correctly killed a bad idea). `stats` can
  nag: "4 approved sessions >30 days old have no outcome." That's the only human
  touch, and it happens when you actually know.

## Honest caveats

- **Low iterations** = easy topic OR a contrarian that folded. Cross-check with
  rejections and clarity-before; flag 1-iteration runs on low-clarity topics.
- **High P0 count** = thorough agents OR an under-specified prompt. Read per-topic
  over time; P0s should fall as clarity rises.
- **Goodhart:** none of these may ever appear in agent prompts as targets
  ("surface ≥N decisions" would poison the P0 signal instantly). They're for the
  human reading `stats`, full stop.
- Deepest check: periodically ask whether healthy-looking sessions actually get
  implemented. If not, the health metrics are theater: process is only the
  product if the product eventually exists.

## Recommended first slice (when built)

1. `session.json` at finalize (convergence, decisions, clarity delta).
2. Ledger auto-append via `[outcomes] ledger_path`, soft-fail. *(Retired — see the header.)*
3. `stats` session-health block with the trends and the assumed-P0 nag.

Defer: the `studio outcome` command and `--from-run` linking, any correlation
analytics, all semantic/LLM-judged measures. `rate` stays exactly as-is. *(`rate` has since been retired — see the header.)*
