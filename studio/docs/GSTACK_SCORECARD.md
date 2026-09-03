# gstack, in the rearview — what we took, and how we'll know it worked

On 2026-07-16 we studied [garrytan/gstack](https://github.com/garrytan/gstack) against Studio,
borrowed a handful of its mechanisms, declined others, and shipped the lot to `main` the same day.
This doc is the retrospective and — the part that was missing until now — the plan for telling
whether any of it actually made Studio's output better.

The deep analysis and the per-item roadmap live in
[GSTACK_COMPARISON.md](./GSTACK_COMPARISON.md). This doc doesn't repeat that. It answers three
questions a teammate would ask a month from now:

1. What did we learn, and what did we take or leave?
2. Why those choices?
3. How will we measure if the borrowings help or hurt — and what would make us pull one back out?

---

## Part 1 — What we learned

**Two systems, same bet, opposite directions.** gstack and Studio independently landed on the same
architecture: markdown skills, the filesystem as the bus, advocate/contrarian energy, no runtime,
all the intelligence in the assistant's execution. gstack went wide (real-browser QA, a memory
layer, cross-model review) for general product shipping. Studio went deep on one thing — the
staged advocate/contrarian debate — for game development. Because neither copied the other, the
places they diverge are where the real lessons are.

The lessons worth keeping:

- **"Complete" and "simple" aren't enemies.** gstack's *Boil the Ocean* (do the whole thing, all
  paths, tests included) sounded like the opposite of our *Simplicity First*. It isn't. Simplicity
  First governs **structure** — how many moving parts. Boil the Ocean governs **coverage** — how
  many real paths you handle. A unit can have few parts *and* handle every path. We cut concepts,
  not thoroughness.
- **Independence is a mechanism you build, not a hope.** gstack manufactures disagreement four
  ways — a second model as the adversary, a cold reviewer that never saw the first one's notes, a
  rule that unresolved disagreement always goes to the human, and a meta-pass aimed at the reviewer
  ("what did the review *miss*?"). The general lesson: don't trust a critic that shares the
  advocate's context.
- **Consensus can bury the one voice that mattered.** Their lone-critical override — a single
  serious concern is flagged no matter how outnumbered — is the guardrail a two-agent debate
  structurally lacks.
- **Where we were already ahead:** the *staged* scoped debate (theirs is a parallel panel, not a
  process), and the clarity score plus a single-owner decision protocol as first-class parts
  (theirs surface decisions ad hoc).
- **The meta-lesson about borrowing itself:** the win wasn't "copy gstack." It was understand it,
  reshape what didn't fit our shape (the doc codegen), and refuse what didn't earn its place (the
  secret-sink harness). Two of the most valuable moves were a rejection and a reshaping.

---

## Part 2 — What we borrowed, and why

Each of these filled a specific gap Studio had. All merged 2026-07-16; PR numbers and the full
rationale are in the comparison doc.

| Borrowed | The gap it filled | Where it lives |
|---|---|---|
| **Quote-to-promote + confidence bands** | The contrarian could assert a flaw without pointing at anything. Now every critique must quote the exact thing it targets; if it can't, it's marked `(unverified)` and demoted, and a finding's confidence sets how loudly it's raised. | `scopes.py` (`CONTRARIAN_MANDATE`) |
| **Independent finding verifier** (R1) | Our contrarian checked its own work. Now a fresh agent re-judges each medium-confidence finding from *only* the quoted `file:line` and the demote rules — never the original reasoning — so agreement is real, not anchored. | `findings.py`, `verifier.py`, `finding-verifier.js` |
| **Reviewer Concerns** | The `/forge` editor's best insight could evaporate on a revert. Now a real critique it can't act on this pass is written to `reviewer-concerns.md` instead of lost. | `implementation-loop.js`, `forge.md` |
| **Named-scar prompt anchors** (R3) | Past regressions lived only in memory. Now they're encoded in the prompt where they'd fire (e.g. the all-decisions-pause scar in the decision protocol). | decision protocol in `scopes.py` |
| **Delta-trend alerts** (R4) — *retired* | `stats` reported absolutes; a slow slide was invisible, so this alerted on run-over-run *changes* that persist 2+ checks. Removed later: every metric it watched (rating, tokens, cost) was a number someone had to type in, and nobody ever did. | was `detect_trend_alerts` in `stats.py` |
| **Lone-critical override** (R5) | The integrator's synthesis could smooth over one serious concern. Now a single critical finding survives synthesis. | integrator duel in `scopes.py` |
| **Design AI-slop blacklist** (R6) | The design phase had no concrete rejection list. Now there's an 11-item, games-adapted blacklist plus a "would a designer be embarrassed?" self-gate. | `design_mandate.py` (design phase only) |
| **Goodwill Reservoir UX score** (R7) | "Taste" was unarguable. Now it's a number (start at 70, dock/credit) reported *with its ledger*, so it's debuggable. | `design_mandate.py` |

---

## Part 3 — What we didn't borrow, and why

| Left / reshaped | Why |
|---|---|
| **Doc-from-code generation** (R2) — *reshaped* | gstack generates its reference docs from source to kill doc-rot. Studio's reference docs are *intentionally richer than the code* — they carry hand-authored explanation the source doesn't. Generating would delete that prose. We took the intent (catch doc-rot) and shipped **doc-parity tests** instead: assert the names match, keep the prose. |
| **Secret-sink test harness** (R8) — *declined* | It detects credentials leaking into logs/artifacts/telemetry. Studio's entire secret surface is one env-var webhook URL. Building leak-detection for that is machinery chasing a problem we don't have. Revisit only if Studio starts handling real secrets. |
| **A second model as the adversary** (Claude vs Codex) — *declined* | gstack's strongest independence trick is cross-vendor review. We deliberately don't: Claude Code is Studio's single supported path (we retired the multi-tool "equal peers" goal). We get the anti-anchoring benefit a different way — the R1 verifier's context asymmetry (cold agent, quote-only) — without taking on a second vendor and a consensus-reconciliation layer. If single-model groupthink ever shows up in the measurements below, this is the first thing to reconsider. |
| **No fixed adversarial roles** — *declined by design* | gstack avoids fixed roles and gets adversarial signal from diversity instead. Studio's whole bet is the *opposite*: fixed advocate/contrarian roles run through a staged debate. That's our core mechanism, not a gap. We kept it. |

---

## Part 4 — How we'll measure improve vs. degrade

This is the part the comparison doc doesn't cover, and the honest hard part.

> **Status 2026-07-29: no review has been run, and there is nothing yet to review with.** Thirteen
> days on from the 2026-07-16 landing, `rate` has recorded zero ratings (no `rating.json` exists
> anywhere) and the verifier has never produced a `findings.json`. Every row below therefore has no
> data, and the first review is already overdue against the monthly clause at the bottom of this
> section. The instruments are built and wired; what's missing is runs that use them. Read the tables
> below as the plan they still are, not as measurements taken.

### The constraint we're measuring under

Everything landed the same day, so there's **no clean before/after A/B** — we can't hold one
mechanism out and compare. And Studio's run volume is low enough that a single bad run swings any
average. So the plan is not a controlled experiment. It's: **watch the instruments we already have,
forward, using pre-2026-07-16 runs as a rough baseline, and give each borrowing a concrete "pull it
back out" trigger** so a bad one doesn't just quietly stay.

### The instruments we already have

Studio ships most of this, though two instruments named in the original plan have since been
retired — `rate` and the outcomes ledger both depended on someone volunteering a score after every
run, and nobody did. What replaced them is the `shipped_impact` / `shipped_changed` pair on a spec's
frontmatter, which costs nothing extra because flipping a spec to `shipped` already demands it:

- **Spec frontmatter** — `shipped_impact` (none/minor/major) and `shipped_changed` (one line, in
  plain words) on every spec claiming `shipped`. Enforced by the suite, so it cannot be skipped.
- **`stats`** — the cross-run dashboard: verdicts, decision counts, session health, and the
  shipped-features roll-up read off that frontmatter.
- **`findings.json` + verifier verdicts** (R1) — structured, so the verifier's behavior is
  directly countable: confirm/unconfirm/uncertain rates, net confidence shift.
- **`reviewer-concerns.md`** — the artifact trail from the forge editor.


### The per-mechanism scorecard

For each borrowing: the signal to watch, what "it's helping" looks like, what "it's hurting" looks
like, and the trigger that makes us tune or revert it.

| Mechanism | Signal (instrument) | Helping looks like | Hurting looks like | Trigger to act |
|---|---|---|---|---|
| Quote-to-promote + bands | Share of findings demoted to `(unverified)`; human notes on whether real issues got dropped | Fewer hand-wavy critiques; high-confidence findings are the ones humans call real | A genuinely real concern gets dropped because it couldn't be quoted (over-suppression) | Any run where a human flags a dropped finding as "should have surfaced" → loosen the demote rule |
| Independent verifier (R1) | Confirm/unconfirm/uncertain split; net confidence change; added tokens (`stats`) | Verifier catches contrarian overreach *and* promotes real ones; cost is a small % of run | Rubber-stamps everything (adds cost, changes nothing) or fights everything (noise) | Confirm rate near 100% or near 0% across ~10 runs → the verifier isn't independent; re-check the quote-only firewall |
| Reviewer Concerns | Count of non-empty `reviewer-concerns.md`; how many concerns humans later act on | Concerns are real and get picked up in follow-up work | The file is mostly noise nobody acts on | Acted-on rate near zero over ~10 forge runs → tighten what qualifies as a concern |
| Named-scar anchors (R3) | Recurrence of the specific scarred regression | The scarred mistake stops recurring | The regression happens again anyway | Any recurrence of an anchored scar → the anchor isn't landing; move or sharpen it |
| Delta-trend alerts (R4, retired) | Alert fire rate vs. real regressions | Alerts fire when quality actually slips, and are quiet otherwise | Alert fatigue (fires on noise) or silence during a real slide | False-positive alerts 2 runs running → widen the persistence window or threshold |
| Lone-critical override (R5) | How often it fires; whether the surfaced concern was real | Rescues a real serious concern the synthesis would've buried | Fires on non-critical findings and clutters the verdict | Human marks a lone-critical surfaced item as "not actually critical" repeatedly → tighten the critical bar |
| Design slop-blacklist (R6) | Blacklist-hit count in design runs; human rating of design output | Design outputs read less generic; fewer blacklist phrases over time | Real, useful phrasing gets rejected as "slop" (false positives) | Human overrides a blacklist rejection as wrong → prune that entry |
| Goodwill Reservoir (R7) | Score distribution against the run's verdict and the spec's `shipped_impact` (`stats`) | Low scores land on design runs that get REJECTED or ship at `none`/`minor` impact; the ledger explains why | Score is theater — flat across the runs that ship well and the ones that don't | Score and the verdict / `shipped_impact` split diverge across ~10 design runs → the heuristic is mis-calibrated |

### The three top-line questions

Underneath the per-mechanism detail, the aggregate "did borrowing from gstack make Studio better?"
comes down to three numbers from `stats`, tracked forward against the pre-2026-07-16 baseline:

1. **Shipped-feature trend** (spec frontmatter). The bottom line, and the honest replacement for
   the human 1-5 rating this plan originally named: are runs still leading to specs that reach
   `shipped`, and does `shipped_changed` describe something worth having?
2. **Outcome quality** (shipped rate + impact). Are more runs leading to something that actually
   ships, and with major rather than minor impact?
3. **Cost per unit of quality** (run volume and convergence vs. shipped impact). The verifier and
   the extra discipline *add* work — visible as more runs, and as a higher median
   iterations-to-verdict and rejection rate in `stats`'s session-health block. That's only worth it
   if quality rises enough to justify the spend. If those climb while `shipped_impact` doesn't move
   toward `major`, a borrowing is a tax, not an upgrade.

### Cadence and the honest exit

- **Review every ~10 recorded runs, or monthly**, whichever comes first — run `stats`, read the
  verdict split and the session-health signals, skim the shipped-features block.
- **The exit rule:** a borrowing that trips its trigger and doesn't recover after one tuning pass
  gets reverted. We took two of gstack's ideas by *refusing* or *reshaping* them; keeping that
  honesty means being willing to pull a shipped one back out if the numbers say so. A mechanism
  that can't be measured, or that measures as neutral-but-costly, is a candidate for removal, not a
  permanent fixture.

---

## Watch-items (the risks we already suspect)

- **Over-suppression** from the confidence bands — the failure mode where the discipline that kills
  fake critiques also kills a real one that happened to be hard to quote. This is the one to watch
  hardest.
- **Verifier cost** — R1 adds a whole extra agent per medium-confidence finding. The parallelized
  per-finding calls keep wall-clock down, but tokens are tokens.
- **Concern and alert noise** — Reviewer Concerns and delta-alerts both fail by crying wolf. Low
  signal-to-noise erodes trust in the artifact, which is worse than not having it.
- **Score theater** — the Goodwill Reservoir is only worth its complexity if the number tracks real
  human taste. A pretty, auditable, uncorrelated number is dead weight.

## Source

Full analysis and roadmap: [GSTACK_COMPARISON.md](./GSTACK_COMPARISON.md). Repo studied:
https://github.com/garrytan/gstack (MIT), v1.60.x.
