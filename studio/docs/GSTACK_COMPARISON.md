# gstack vs Studio — what we learned and what we took

A study of [garrytan/gstack](https://github.com/garrytan/gstack) (Garry Tan's open-source
"virtual engineering team" of ~60 Claude Code skills), read against Studio to find ideas worth
borrowing. This doc is the record of that comparison and the roadmap it produced. It is reference
material, not a spec — the roadmap items below become their own specs when we build them.

## The two systems, in one breath

Both make the same bet: markdown skills + the filesystem as the bus + advocate/contrarian energy,
no runtime, all intelligence in the assistant's execution. gstack built it out to production depth
(real-browser QA, a persistent memory layer, cross-model review), pointed at general product
shipping. Studio went deep on one mechanism — the structured advocate/contrarian debate — pointed
at game development. Neither is a copy of the other; they converged on the same shape from opposite
directions, which is why the differences are the interesting part.

## The philosophical fork: "Boil the Ocean" vs "Simplicity First"

gstack's first ethos principle is **Boil the Ocean**: because AI makes the marginal cost of
completeness near-zero, do the *complete* thing every time — all edge cases, all error paths, tests
included. Studio's CODING_PRINCIPLES §2 is the opposite instinct: **Simplicity First** — minimum
code, nothing speculative.

They are not actually in conflict, and the reconciliation is worth keeping in mind:

- **Simplicity First governs *structure*** — the number of moving parts, concepts, abstractions.
  Its target is the LLM's habit of over-engineering (200 lines of machinery for a 50-line problem).
- **Boil the Ocean governs *coverage*** — how many of the real paths you actually handle. Its
  target is the opposite LLM habit: stopping at 90%, deferring the tests, skipping the error path.

A unit can be simple (few parts) *and* complete (all paths). §2 already says "remove concepts, not
characters"; Boil the Ocean is the coverage-side complement to that. Where we lean toward cutting,
it is worth being explicit that we cut *concepts*, not *thoroughness*.

## The critique architecture — the core contrast

Studio assigns two agents fixed roles (advocate piles on, contrarian-as-editor cuts), runs a
scoped debate (alignment → depth → polish → integrator duel), and synthesizes a verdict. gstack
deliberately **avoids fixed adversarial roles** and gets its "adversarial" signal four other ways:

1. **Model diversity as the adversary** — Claude vs Codex (OpenAI), reconciled in a
   CONFIRMED/DISAGREE consensus table, rather than one model arguing with itself.
2. **Context asymmetry as the independence mechanism** — one reviewer primed with all prior
   findings, the other a *cold* fresh subagent, to break groupthink.
3. **Disagreement is never auto-resolved** — every DISAGREE routes to the human. Their whole ethos
   is "models recommend, users decide"; even unanimous cross-model agreement is "strong signal, not
   permission to act."
4. **A meta-adversary aimed at the reviewer, not the plan** — a final pass whose only job is "find
   what the review MISSED."

Two mechanisms of theirs that a two-agent debate structurally lacks, and that we found most worth
taking:

- **The lone-critical override** — "a single critical finding from one voice is flagged
  regardless." Consensus-seeking must never bury one serious concern.
- **The convergence guard** — cap the writer/editor loop, and when they deadlock, *persist the
  disagreement into the artifact* instead of looping forever.

Where Studio is genuinely ahead: the structured *scoped* debate (theirs is a parallel panel, not a
staged process), and the clarity score + canonical decision-point protocol as first-class,
single-owner mechanisms (theirs surface decisions ad hoc via AskUserQuestion).

## What we took (shipped)

Two mechanisms ported directly, plus this doc:

1. **Quote-to-promote + confidence bands in the contrarian's finding discipline**
   (`scopes.py`, `CONTRARIAN_MANDATE`). Every flaw the contrarian raises must quote the exact thing
   it critiques; if it cannot, the finding is marked `(unverified)` and demoted. Findings carry a
   confidence, and the confidence sets how loudly they are raised (high → stated plainly; medium →
   "verify this"; low/unverified → a separate "Lower-confidence notes" list, or dropped unless it
   would be fatal). This is gstack's "#1539" gate — the cheapest known way to kill hallucinated
   critiques — adapted to our critic role. Flows to every deliverable contrarian prompt; suppressed
   in `--mode questions` (where cutting is wrong).

2. **Reviewer Concerns in the `/forge` writer/editor loop**
   (`implementation-loop.js`, `IMPLEMENTATION_LOOP_SPEC.md`, `forge.md`). Studio's loop is one-way
   by design — it never hands work back, which is what keeps it from thrashing (the convergence
   guard, already structural). The missing half was the *other* half of gstack's mechanism: a real
   critique the editor can't act on this pass (would break green, hits a `load_bearing` item, or is
   out of unit scope) used to evaporate on revert. The editor now records these in
   `unresolved_concerns` and writes a `reviewer-concerns.md` artifact, so the second agent's most
   valuable output survives instead of being lost.

## Roadmap — the rest of the steal-list

Ranked by leverage for Studio. Each becomes its own `/spec` when picked up.

| # | Idea | What it buys | Rough effort | Notes |
|---|------|--------------|--------------|-------|
| R1 | **Independent verifier subagent** for contrarian findings | A finding is confirmed by a fresh agent that sees only the quoted `file:line` + the demote rules, *not* the original reasoning (anti-anchoring); +1 confidence when two agree. The verification arm behind the quote-to-promote gate we just shipped. | M | Natural next step after the confidence gate; pairs with it. |
| R2 | **Compile skills/commands from templates + CI freshness gate** | Kills doc-rot structurally: `gen --dry-run \| git diff --exit-code` fails CI if a committed command doc drifts from source. This is what `/unstale` chases by hand. | L | Biggest architectural lift. gstack's own caution: don't hardcode install paths in generated output — resolve the root at runtime. |
| R3 | **Named failure-mode citations as prompt anchors** | Encode past regressions directly in prompts ("this is the precise failure of the all-decisions-pause bug"). We keep these scars in memory; gstack keeps them in the prompt where they actually fire. | S | Cheap, high-value. Start with the decision-pause and impl-loop-in-worktree scars. |
| R4 | **Delta-based alerts with N-consecutive-check persistence** | For any run-over-run comparison (ratings, session health, stats trends): alert on *changes* not absolutes, and only when a pattern persists 2+ checks. Best anti-noise rule they have. | S | Fits `stats.py` / session-health trends. |
| R5 | **Lone-critical override in the scoped debate** | Don't let the integrator's synthesis bury a single serious contrarian finding just because the room didn't reach consensus on it. | S | Small change to integrator/polish guidance. |
| R6 | **AI-slop blacklist + "would a designer be embarrassed?" self-gate** | A concrete rejection list for the design phase (and any UI work), plus an anti-convergence directive (vary the look across generations). Directly useful for game UI/marketing output. | M | Adapt their 11-item list to game dev. |
| R7 | **Goodwill Reservoir UX score** | A UX heuristic that starts at 70 and is docked for dark patterns / credited for good behavior — makes "taste" a debuggable number. | M | Design-phase deliverable. |
| R8 | **Secret-sink test harness with positive controls** | If Studio ever handles credentials: seed a fake secret, assert it never leaks to stdout/files/telemetry, *and* keep controls that deliberately leak to prove the detector works. | M | Only if/when we touch secrets (currently env-only webhooks). Lower priority. |

## Source

Full analysis (all four skill clusters) is captured in the memory note
`reference_gstack_analysis`. Repo studied: https://github.com/garrytan/gstack (MIT), v1.60.x.
