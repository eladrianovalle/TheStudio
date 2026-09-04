# Spec: Map a Feature's Architecture Before You Build It

Produce the source-of-truth architecture spec for one feature. You run a discovery-forward,
single advocate/contrarian pass over the design — surfacing the unknowns, answering them, and
pressure-testing the architectural decisions — then synthesize a single spec document that
explains the feature in **both plain language and technical detail**, with a **diagram**. Once
the user approves it, that document is the spec the feature gets built against.

A **spec** here is not code and not a debate transcript. It is one durable, tracked document: what
the feature is, why it exists, how it's structured, and the decisions (and cut scope) behind it —
readable by a newcomer and precise enough for an engineer to build from.

This is the front door to a feature. When the user says "let's `/spec` a feature that does X",
"map out the architecture for X", or "write the spec for X", that is an invocation of this command.

## Arguments

- `$ARGUMENTS`: Required. Free-text description of the feature to spec.
- Optional `--ticket <id-or-url>`: the issue / ticket / feature this spec belongs to. Recorded in
  the spec's frontmatter so the spec and its tracker stay linked. If omitted, ask once whether
  there's a ticket; if there isn't, proceed and leave it blank.
- Optional `--id <slug>`: override the spec's filename slug (default: derive a short kebab-case
  slug from the feature description, e.g. `multiplayer-lobby`).
- Optional `--max-iterations N`: total debate budget (default **2**). The tech phase paces this as
  a discovery scope then a depth scope (see below), so 2 gives exactly one unknowns-surfacing pass
  and one finalize pass. Raise it only for genuinely thorny architecture.
- Optional `--plan`: echo the resolved plan (slug, ticket, path, framing) and STOP. No debate.

## The shape of this run

This is a **single advocate / single contrarian** pass (the `tech` phase — *not* the multi-role
scoped studio debate), and it's deliberately **discovery-forward**. The tech phase paces one
advocate/contrarian pair across scopes, which happens to front-load discovery exactly the way a
spec wants:

1. **Alignment scope — surface the unknowns and answer them.** The Open-Questions Pre-Flight folds
   in here: the architectural forks, the load-bearing assumptions, the things nobody has decided.
   This is where most of a spec's value is. Pause on P0 blockers before going further.
2. **Depth scope — finalize the architecture.** The advocate designs it in full; the contrarian
   hunts edge cases, pushes simpler alternatives, and cuts scope. One pass that sharpens the
   proposal, not a restart. (`instructions.md` drives the exact scope pacing; follow it.)
3. **Synthesize the spec document** and get the user's approval. Approval is what makes it the
   source of truth.

## Instructions

**Studio path:** use `.studio/source/run_phase.py` for the commands below. If that file does not
exist but `studio/run_phase.py` does, use `studio/run_phase.py` (you are in the Studio source repo).

**Finding code:** if this repo has a code index or symbol search, use it to locate code during
discovery and throughout the debate, before grepping or opening files blind. It tells you where, not
what — open the file at the returned `file:line` and quote what you read there. An index summary or
an inlined source excerpt is not evidence, however sufficient the tool says it is.

### Step 1: Resolve the spec's identity

Before running anything, settle where this spec lives and what it's tied to:

- **Slug:** from `--id`, else a short kebab-case slug of the feature.
- **Ticket:** from `--ticket`, else ask once. Leave blank if there genuinely isn't one.
- **Spec path:** specs are **tracked source-of-truth docs, meant to be committed** (unlike the
  gitignored `output/`). Resolve the path:
  - In the Studio source repo (a root `studio/` dir is present): `specs/<slug>.md`.
  - In a consuming repo (Studio is installed under `.studio/`): `.studio/specs/<slug>.md`.
- **New vs update:** if the spec file already exists, read it and treat this as a revision — carry
  its ticket and prior decisions forward rather than starting blank.

If `--plan`, print the resolved slug / ticket / path / one-line framing and STOP here.

### Step 2: Run the discovery + finalize debate (reuse the tech-phase machinery)

Frame the feature as an **architecture** question, then prepare a `tech` run. The framing
steers the debate toward structure — components, data flow, interfaces, failure modes, and simpler
alternatives — rather than product framing:

```bash
python ".studio/source/run_phase.py" prepare --phase tech \
  --text "Architecture spec for: <feature>. Map the components, data flow, interfaces/contracts, data model, failure modes, and dependencies. Surface the architectural unknowns first; prefer the simplest structure that works and cut speculative scope." \
  --max-iterations <N> --json
```

Parse the final stdout line for `run_id`, `run_dir`, and `instructions`. Then **read
`instructions.md` in the run dir and follow it as the authority on procedure** — it encodes the
scope pacing and the pieces this run needs, and you execute them in order:

- **Step 0: Open-Questions Pre-Flight (the heart of this command).** In the scoped tech run this
  folds into the start of the alignment scope. Surface what is genuinely unsettled about the
  architecture — the forks, the load-bearing assumptions, the integration points. Present P0
  blockers and **pause for the user's answers** before finalizing; record them as `instructions.md`
  directs. Do not paper over an unknown with a silent assumption.
- **The advocate/contrarian scopes** (alignment → depth), within the `--max-iterations` budget
  (default 2). The advocate designs the architecture; the contrarian pressure-tests it (edge cases,
  simpler alternatives, scope to cut) and votes `APPROVED`/`REJECTED`. Surface every decision point
  and pause on P0s exactly as `instructions.md` describes.

Skip `instructions.md`'s implementation/deliverable step — the deliverable for `/spec` is the spec
document in Step 3, not an implementation.

If the contrarian rejects and the iteration cap is exhausted, **don't bury it**: tell the user what
the contrarian found and ask whether to run another pass (`--max-iterations`) or fold the concern
into the spec as a known risk. A rejected architecture should not silently become a source of truth.

### Step 3: Synthesize the spec document

From the approved advocate proposal, the contrarian's critique, and the recorded decisions
(`{run_dir}/decisions.md` if present), write the spec to the path from Step 1. Write it for two
readers at once — a newcomer who needs to understand the feature, and an engineer who has to build
it. Use this structure (the outer fence is four backticks so the inner ` ```mermaid ` block
below doesn't close it early — the spec file you write uses a normal three-backtick fence):

````markdown
---
feature: <human title>
slug: <slug>
ticket: <id-or-url, or "none">
# status: draft → approved (a human approved it) → shipped (built AND verified)
status: draft
studio_run: <run_dir>    # the debate this spec came from
# verification_due: the date the evidence is due (YYYY-MM-DD). Required once this spec is
# `approved`, and only if it carries a `## Verification` section — no section, no deadline.
verification_due:
# Leave the two below EMPTY until this spec flips to `shipped`, and keep their notes on
# comment lines like these. An inline `# ...` after the colon is read as the VALUE, and
# `shipped_changed` has no vocabulary check to catch it — so a spec could otherwise
# satisfy the gate having edited nothing.
# shipped_impact: one of none | minor | major — how much it changed downstream
# shipped_changed: one line, in plain words, on what this actually changed
shipped_impact:
shipped_changed:
---

# <Feature> — Architecture Spec

## In Plain Language
What this feature is and why it exists, in terms a non-engineer teammate would follow. No jargon;
define any unavoidable term of art the first time. Two or three short paragraphs.

## Architecture at a Glance
A **Mermaid diagram** of the structure — components and how data/control flows between them. Use
whichever Mermaid type fits (`flowchart` for components/data flow, `sequenceDiagram` for an
interaction, `erDiagram` for a data model). Keep it readable; it renders natively on GitHub.

```mermaid
flowchart TD
    User[Player] --> UI[Lobby UI]
    UI --> API[Lobby Service]
    API --> Store[(Session Store)]
```

Follow the diagram with a short prose walk-through of what it shows.

## How It Works (Technical)
The precise detail an engineer builds from:
- **Components / modules** and each one's responsibility.
- **Data flow** — the path of a request/event through the system.
- **Interfaces & contracts** — key APIs, function signatures, message/event shapes.
- **Data model** — entities, fields, relationships, persistence.
- **Dependencies** — what this leans on (services, libraries, other features).

## Key Decisions
The architectural choices and *why*, pulled from the debate — including alternatives that were
weighed and rejected. Fold in the settled decisions from the pre-flight and the loop. This is the
record that stops the choices being re-litigated mid-build.

## Non-Goals / Cut Scope
What this feature deliberately does **not** do, and what the contrarian cut. Explicit boundaries
keep the build from sprawling.

## Risks & Open Questions
Known risks, unresolved contrarian concerns, and anything still genuinely open. Be honest here — a
spec that hides its soft spots is worse than one that names them.

## Verification
Required only for a **prompt-shaped** feature — one whose behavior lives in an agent's prompt, where
no test can tell you it broke. The test to apply: *could a failing pytest tell us this feature broke?*
If yes, delete this section — the tests are the criterion and this would be theatre. If the only
instrument is a person reading the output, keep it and fill it in.

- **Pass criterion.** This feature works if and only if <observable outcome>. Write it as an *iff*,
  now, before the build — so someone can disagree with it while disagreeing is still cheap.
- **Baseline.** The same behavior with the feature off. Say how to reproduce it on demand. If you
  can't make the old behavior fail, there's nothing here to improve on — treat it as a blocker and
  surface it.
- **Where the evidence goes.** `specs/<slug>-eval-results.md` (`.studio/specs/` in a consuming repo),
  created from the skeleton when this spec is approved.
- **Stop condition.** While that file still says `FILL_ME`, nobody may call this feature working and
  this spec stays `status: approved`. You set it to `shipped` when you fill the file in — that flip is
  the claim, and the spec-verification test is what makes the claim cost evidence.

## Build Plan
How this maps to buildable units — a short list of MVI units (each a complete, usable interaction;
"build a skateboard, not a wheel"), in dependency order. This is the bridge to `/forge`, which reads
this section directly, so give every unit the same shape:

1. **`<unit_id>` — <one-line usable outcome>.** What gets built: the files, the behavior, the tests.
   - **Acceptance criteria:**
     - [ ] <one checkable statement>
     - [ ] <another>
   - **Out of scope:** what this unit deliberately does not do.

The criteria are the part `/forge` depends on, so write them with care:

- **Make them checkable.** Someone should be able to look at the running code or the test output and
  say yes or no. "Loading is fast" is not checkable. "The list renders in under a second with 1,000
  rows" is.
- **Describe outcomes, not steps.** What is true when the unit works — not which function you wrote.
- **Three to six per unit.** If you need more, the unit is too big; split it.
- **Keep them checkable from the code and its tests.** The `/forge` editor reads the diff and runs the
  unit's tests; it has no browser and no Play mode. A criterion that only a human at the screen can
  judge belongs in `/smoke`, not here.
- **`<unit_id>` is a short snake_case handle, unique within this spec.** `/forge --spec <slug> --unit
  <unit_id>` is how the builder pulls this unit's criteria, so don't rename it once the spec is approved.
````

Keep the writing human (Coding Principles §6): plain language, say what a thing does and why it
matters, match a calm engineering voice. The diagram is required, not optional — if the feature
truly has no structure worth drawing, it probably didn't need a spec.

### Step 4: Open a PR for the spec — this is how a /spec run ends

**A `/spec` run is not finished until the spec document is pushed as a pull request.** Not written to
the working tree, not described in chat, not left for someone to ask about: committed on a branch and
opened as a PR. That PR is the review, and merging it is the approval.

Do this without being asked, every time:

```bash
git checkout -b spec/<slug>
git add specs/<slug>.md              # .studio/specs/<slug>.md in a consuming repo
git commit                            # say what the feature is and why it is shaped that way
git push <remote-url> spec/<slug>:spec/<slug>
```

Then open the PR. Commit **only** the spec file — a `git add -A` here sweeps unrelated working-tree
changes into a document review, and the reviewer cannot tell which is which.

The spec goes up at `status: draft`. Leaving it at draft is what makes merging mean something: the
frontmatter should not claim approval that has not happened yet. Say so in the PR body — "merging is
the approval" — so a reviewer knows the status flip follows the merge rather than preceding it.

**The PR body is where the debate's value survives.** The spec records what was decided; the PR
records what was *rejected and why*, which is the part that stops a settled question being reopened
in three months. Include: what the contrarian cut and the reason, any factual claim the debate
corrected (especially one of yours), and any limit the design does not fix — stated plainly rather
than left for a reader to discover. A `VERDICT: REJECTED` that was resolved by revising the design
belongs here too; a rejected architecture must never become a source of truth silently.

Summarize the same things in chat, in plain words, so the user can decide without opening the file
(the Coding Principles section "Write for Humans"). Then:

- **On approval — which in practice means the PR merged:** set `status: approved` in the frontmatter
  and confirm the path. That flip is a follow-up commit, not part of the spec PR, because a document
  cannot honestly claim approval in the same change that requests it. Ship the flip on its own or
  alongside the first `/forge` unit built from it; either way it lands after the merge, never before.
  If a `--ticket` was given, link the spec on that ticket so the tracker and the spec stay tied
  together (do it with `gh` rather than reminding the user to). This approved document is now the
  spec the feature is built against.

  **Leave `shipped_impact` and `shipped_changed` blank here.** You don't know yet what the feature
  changed, and asking this early is how you get an invented answer. They are filled in at the moment
  the spec flips to `status: shipped`, and the suite refuses that flip while either is empty — so the
  two honest exits are to fill them in or leave the spec at `approved`. `shipped_impact` is exactly
  one of `none`, `minor`, or `major`; `none` is a real answer, since a feature that shipped and
  changed nothing downstream is still worth recording. `shipped_changed` is one line, in plain words,
  saying what actually changed for someone using this. Write it from what the feature does, not from
  the fact that it landed: "it shipped" satisfies the test and tells a reader nothing.

  **If the spec carries a `## Verification` section**, set `verification_due` to 30 days from today
  and create its evidence file now — empty, before any data exists. That ordering is the whole point:
  headings written before the outcome is known can't be arranged to flatter it. The date bounds the
  wait: once it passes with the evidence still blank, the suite goes red until you either record what
  you found or move the date. Write the skeleton below to
  `specs/<slug>-eval-results.md` (`.studio/specs/<slug>-eval-results.md` in a consuming repo),
  substituting `<Feature>` and `<slug>`, and **copy the pass criterion out of the spec word for
  word** — don't summarize it, don't improve it. Leave every `FILL_ME` in place; each one marks data
  that does not exist yet. Then run `git check-ignore -q <path>` on the file you just created: if it
  exits 0, tell the user the evidence file is gitignored and would never be committed, and point
  them at the `.gitignore` recipe in the bridge doc's Maintenance section.

  ```markdown
  # <Feature> — Verification Results

  **Spec:** [`<slug>.md`](./<slug>.md). The pass criterion below was copied from that spec before
  anything was measured. Don't edit it to match what happened — if it turned out to be the wrong
  criterion, say so under "What this doesn't prove."

  Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
  Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
  suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

  ## Pass criterion (written before the build)
  > _Copy the iff from the spec's Verification section, word for word._

  ## What happened
  | Condition | What was run | Times | Criterion met | Notes |
  |---|---|---|---|---|
  | Baseline (feature off) | FILL_ME | FILL_ME | FILL_ME | FILL_ME |
  | With the feature | FILL_ME | FILL_ME | FILL_ME | FILL_ME |

  The baseline row should read "no". If the criterion was already met with the feature off, stop and
  say so: a feature that fixes a problem you could never trigger has not been shown to do anything.
  **Before trusting either row, read `find-before-you-grep-eval-results.md`.** Four of its five runs
  were void, and both failure modes generalise: a baseline is only a baseline if the behaviour under
  test cannot reach the agent by another route (a skill, a hook, an MCP server, CLAUDE.md), and a
  treatment is only a treatment if the file carrying it actually loads.

  ## What this doesn't prove
  Required — this section is the point of the file.
  - Did the criterion pass *as written*, un-rewritten after the fact? Name every number that moved the
    wrong way, cost included.
  - What could a reader wrongly conclude from that table? At minimum: the sample size, the conditions
    you did not test, and the alternative explanation you can't rule out. "Nothing" is not an answer;
    if you can't name a limit, you haven't looked yet.

  FILL_ME

  ## Verdict
  One of **criterion met** / **criterion not met** / **inconclusive, and why**.

  FILL_ME
  ```

  The file gets no frontmatter of its own — a second `status:` sitting beside the spec's would just
  be one more thing to drift.
- **On changes requested:** revise the spec (and, if the change is architectural, offer another
  advocate/contrarian pass) and re-present. Don't mark it approved until they say so.

### Step 5: Finalize the debate record

Close out the underlying run so its decisions are captured in the cross-run dashboard:

```bash
python ".studio/source/run_phase.py" finalize --phase tech --run-id {run_id} \
  --status completed --verdict {APPROVED|REJECTED}
```

## Key Rules

- **Discovery first.** The pre-flight is where a spec earns its keep — surface the architectural
  unknowns and get them answered before finalizing. Never paper over an open fork with a silent
  assumption.
- **Single-pair, not multi-role.** One advocate, one contrarian (the `tech` phase, scope-paced
  discovery → depth). This is a focused architecture pass, not the multi-role studio debate.
- **Two readers, one doc.** Every spec explains the feature in plain language *and* in build-ready
  technical detail, and carries a diagram. If an engineer couldn't build from it, it's not done.
- **Approval is the gate.** A spec is the source of truth only after the user approves it. A
  rejected or shaky architecture gets surfaced, not silently shipped.
- **A prompt-shaped feature says up front how you'd know it works.** When no failing test could tell
  you the feature broke, the spec carries a `## Verification` section — the pass criterion as an
  *iff*, agreed before the build — and approval creates the evidence file beside it. The spec stays
  `approved` until that file is filled in: `shipped` is the claim that the feature works, and the
  claim costs evidence. When a test *could* catch the breakage, leave the section out; prose beside a
  test is theatre.
- **Specs are tracked, and a run ends in a PR.** They live in `specs/` (or `.studio/specs/` in a
  consuming repo), stay linked to their ticket, and are not throwaway `output/` artifacts. Every
  `/spec` run finishes by pushing the spec as a pull request at `status: draft` — that PR is the
  review and merging it is the approval. A spec left sitting in the working tree has not been
  delivered, however good it is.
- **The Build Plan is a contract, not a summary.** Each unit carries checkable criteria, because
  `/forge --spec` judges the built unit against them one by one. Vague criteria there become a vague
  verdict downstream.
- **A spec precedes the build.** Once approved, this is what `/forge` and the feature
  work build against. (See the Coding Principles section "Spec Before Build.")
