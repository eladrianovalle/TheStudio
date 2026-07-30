# superpowers vs Studio — what we learned, and what I propose we take

A study of [obra/superpowers](https://github.com/obra/superpowers) (Jesse Vincent's skills library
for Claude Code — MIT, v6.2.0, read at commit `3dcbd5c`, 2026-07-23), read against Studio to find
mechanisms worth borrowing. Same exercise we ran against gstack in July, same discipline: every
candidate went through two adversarial vetting lenses (does Studio already cover this? does it fit
the architecture, at the stated cost?) and most of them came back smaller than they went in. Six
survived. Nine were rejected after vetting. Sixteen more were rejected before vetting started.

This doc is the record and the proposal. It is reference material, not a spec — the proposal items
become specs when we build them.

## The two systems, in one breath

superpowers is a set of 14 skills (38 markdown files under `skills/`) that install into a Claude
Code session and fire automatically: a SessionStart hook injects one file's full text —
`skills/using-superpowers/SKILL.md` — wrapped in `<EXTREMELY_IMPORTANT>` tags, and that injected
file tells the model to reach for a skill if there is "even a 1% chance" one applies. Everything
else is discovered lazily from there. Its content is discipline enforcement: TDD with an Iron Law,
systematic debugging with a phase gate, a subagent-driven implementation loop, and — the part worth
studying — a methodology for *writing* that prose, in which skill text is treated as code under
test: you run a pressure scenario without the guidance, harvest the agent's rationalizations
verbatim, write only enough text to kill those specific excuses, then re-run. Studio and superpowers
are aimed at different halves of the same problem. superpowers shapes how one agent behaves while it
works. Studio structures how several agents argue about what to build, then packages the argument as
an artifact. Neither is a copy of the other, and almost nothing in superpowers' distribution layer
is relevant to us — the transferable value is concentrated in one skill (`writing-skills`) and one
set of subagent prompt templates.

| | superpowers' bet | Studio's bet |
|---|---|---|
| **Unit of value** | A skill: prose that changes how the agent behaves | A run: a staged debate packaged as a versioned artifact |
| **Where intelligence lives** | Injected markdown the model reads | Generated markdown the model executes (same instinct) |
| **Trigger** | Automatic — SessionStart hook injects the bootstrap every session (`hooks/session-start`, `hooks/hooks.json` matcher `startup\|clear\|compact`) | Explicit — the user types a slash command |
| **How prose earns its place** | Measured. RED baseline → harvested excuses → minimal counter → re-run. Wording micro-tests with a no-guidance control, 5+ reps (`skills/writing-skills/SKILL.md:575-585`) | Argued. Reviewed by a contrarian, then judged by a human 1–5 rating on live runs |
| **Adversarial signal** | A fresh subagent reviewing a diff it did not write, with a two-verdict contract | Fixed advocate/contrarian roles through a staged scoped debate |
| **Enforcement** | Almost entirely prose. No CI workflows exist in the repo; `.pre-commit-config.yaml` lints only the gitignored `evals/` Python | Python. Gates, validators, 861 tests, ruff + pytest in CI |
| **Reach** | 11 agent harnesses, one content tree, per-harness tool-name mapping files | One harness (Claude Code), on purpose |

## What they do better

- **They measure prose changes; we argue about them.** `skills/writing-skills/testing-skills-with-subagents.md`
  applies RED-GREEN-REFACTOR to instruction documents, and the rule has teeth: "If you didn't watch
  an agent fail without the skill, you don't know if the skill prevents the right failures."
  `skills/writing-skills/SKILL.md:575-585` adds the cheap inner loop — one fresh-context sample per
  call, a mandatory no-guidance control ("If the control doesn't exhibit the failure, there is
  nothing to fix — stop, don't author the guidance"), 5+ reps, every regex hit read by hand, and
  variance treated as its own metric. Studio has 861 tests and none of them can tell whether a
  prompt edit made debates better or worse.
- **They have a theory of prompt *form*; we have none.** `skills/writing-skills/SKILL.md:459-474`
  classifies the baseline failure first, then picks the form from a table: discipline slips get a
  prohibition plus a rationalization table; wrong-shaped output gets a positive recipe and
  prohibitions there measurably *backfire*; an omitted element gets a REQUIRED slot; conditional
  behavior gets a conditional keyed to an observable predicate. Two hard rules follow — no nuance
  clauses, and exemption clauses don't scope.
- **They write down excuses verbatim.** Every skill ends in an `| Excuse | Reality |` table sourced
  from real transcripts, placed where the agent is deciding rather than where it is composing.
  Studio's mandates are positive rules with a "The test:" line, which does not fire at the moment an
  agent has just talked itself out of one.
- **Their reviewer prompts distrust the author's framing.** `skills/subagent-driven-development/task-reviewer-prompt.md`
  states it flatly: a design rationale in the implementer's report "is the implementer grading their
  own work. Judge the code on its merits — a stated rationale never downgrades a finding's
  severity." Same file gates review breadth behind a named risk instead of banning it: inspect
  outside the diff "only to evaluate a concrete risk you can name — one focused check per named
  risk," and cite `file:line` for any check you would otherwise answer with a bare "yes."
- **They give a stuck agent a legal way to stop.** `skills/subagent-driven-development/implementer-prompt.md`:
  "It is always OK to stop and say 'this is too hard for me.' Bad work is worse than no work. You
  will not be penalized for escalating" — with five observable triggers, including "you've been
  reading file after file trying to understand the system without progress."
- **They pre-commit the shape of their own results.** `docs/superpowers/plans/2026-07-06-sdd-plan-scoped-workspace.md`
  contains the literal empty markdown of its future results doc — every heading, the RED baseline
  numbers already filled in, `<fill>` where data does not exist yet, and a mandatory "What RED
  showed (and did not show)" section. The filled version
  (`docs/superpowers/specs/2026-07-06-sdd-plan-scoped-workspace-eval-results.md`) reports that the
  hypothesized failure did not reproduce (25/25) and that the cost metric moved the wrong way, under
  the heading "Read this table honestly."
- **They fire without being asked.** The SessionStart bootstrap means the methodology applies to
  work the user never thought to route through it. Studio's methodology only engages when someone
  types a slash command.

## What Studio does better

- **Enforcement.** Nearly every superpowers rule is prose an agent can paraphrase away; their own
  release notes record a step that "was being skipped entirely" because it lived only in prose.
  Studio puts real gates in Python — the /forge entry and exit gates, `verdict.py`, the validators,
  doc-parity tests, ruff and pytest in CI.
- **Measurement of outcomes, not just of prose.** `rate`, `stats`, `session.json`, the outcomes
  ledger, `detect_trend_alerts` and `findings.json` are a shipped instrument set. superpowers'
  actual eval harness is not even in the repo — `evals/` is gitignored and cloned from a separate
  private repo, so the verifier prompt and scenario schema are unauditable from their tree.
- **Single-owner formats.** `decision_points.py` owns the decision format; `findings.py` owns the
  FINDING template and `scopes.py` imports it, so what we ask for and what we parse cannot drift.
  superpowers ships the same tool mapping twice (in `piToolMapping()` and in
  `skills/using-superpowers/references/pi-tools.md`) and documents the duplication as a warning
  rather than fixing it.
- **The staged debate itself.** Alignment → depth → polish → integrator duel, with clarity scores
  driving question density and a canonical pause-and-ask protocol. superpowers has one reviewer per
  diff and no notion of a settled decision that later agents may not re-litigate.
- **Doc hygiene we can prove.** `/unstale` plus doc-parity tests. Their porting guide, 828 lines
  long, instructs porters to copy `.antigravity-plugin/install.sh` — a directory that does not exist
  in the repo — and their v6.2.0 release notes point readers at `docs/specs/` and `docs/plans/`,
  which are also wrong paths.

## The proposal

Six borrowings, ranked. Every one is smaller than the candidate that entered vetting; the
"Vetting forced" line says how.

### 1. Write down how we author prompts, then use it to fix the two clauses it condemns

**Pitch.** Studio's product is prompt text and Studio has no stated theory of how to write it. The
useful part of superpowers' theory is a classifier: look at the failure you actually observed, then
pick the form from a table, because the form that fixes one failure type makes another worse.

**Mechanism.** The "Match the Form to the Failure" table plus its two hard rules, at
`skills/writing-skills/SKILL.md:459-474`. Four rows: discipline slip → prohibition + rationalization
table; wrong-shaped output → positive recipe stating what the output IS, in order; omitted element →
a REQUIRED slot in the template; conditional behavior → a conditional keyed to an observable
predicate. Then: no nuance clauses ("Don't X unless it matters" reopens the negotiation), and
exemption clauses don't scope. Plus two rules from their micro-test protocol at the same file's
lines 575-585: always include a no-guidance control, and treat variance across reps as a metric.

**How it lands.** About 25 lines as a new "Writing for Agents" section in
`studio/docs/CODING_PRINCIPLES.md` — sibling to §6 "Write for Humans", which now covers docs,
code and conversation in one section, and which
already partition writing by reader and leave agents as the obvious gap. That file already ships
cross-repo (`install.py`) and is injected into a consuming repo's CLAUDE.md between sentinels, so it
needs no new plumbing, no INDEX/README churn, and no `/spec` wiring. The section must say plainly
that this is borrowed evidence from another project's models and prompts and that Studio cannot
re-measure it — it is vocabulary for classifying guidance, not an acceptance gate.

**Size.** One commit. A few hours.

**Vetting forced.** No new `studio/docs/PROMPT_AUTHORING.md` (that directory is already at 23 files
and a standalone doc would need install plumbing a section inherits for free). No `/spec` wiring. No
repo-wide triage sweep — I ran it: 24 don't/never/avoid hits across `scopes.py`, `question_mode.py`,
`design_mandate.py` and `decision_points.py`, and essentially all are already in the endorsed form.
And the cited skill names in the original candidate (`match-the-form-to-the-failure-classifier`,
`positive-instruction-doctrine`, `no-nuance-clauses`) do not exist — they are section headings
inside one file. Also cut: the candidate's confident claim that prohibitions are "worse than no
guidance at all." The source says the prohibition arm "trended worse than even the no-guidance
control" on one domain and closes with "micro-test your own case rather than assuming." Ship the
taxonomy, not the borrowed p-value.

### 2. Make the contrarian's escape hatches earn their invocation

**Pitch.** The cut mandate is not dying of forgetfulness. It is dying by citation of its own
guardrails. Every "no edits" handoff in Studio's own forge history justifies itself by quoting
"Guard the essence" or "Cut concepts, not clarity" back at the mandate. The fix is not to rebut
those clauses — they were added on purpose — but to make invoking them cost the same evidence the
mandate already demands of a finding.

**Mechanism.** Two things, combined. superpowers' rationalization-table discipline — harvest the
excuse verbatim from a real transcript, never invent it
(`skills/writing-skills/testing-skills-with-subagents.md`) — and row 4 of the form table above:
express an exception as a conditional keyed to an observable predicate, not as a caveat.

**How it lands.** In `CONTRARIAN_MANDATE` (`studio/scopes.py:40-41`), rewrite the two escape-hatch
clauses so declining a cut on essence or clarity grounds requires quoting the specific thing and
naming what breaks if it goes — the same quote-first bar the mandate sets for findings ten lines
below. Plus at most one "Known failure mode — do not repeat" anchor in the shipped R3 voice
(`scopes.py:386`, `run_phase.py:985`), carrying the one harvested case where a skip was later shown
to be *wrong*: the finding-verifier install gap, where the editor wrote "it is not a cut, so I did
not action it in this pass" and `finding-verifier.js` shipped missing from `WORKFLOW_FILES`. It
reaches /forge for free — `implementation-loop.js:153` already tells the editor to read the mandate
off disk.

**Size.** Six lines of prompt text in one file. Half a day including the harvest.

**Vetting forced.** A lot, and one genuine disagreement worth naming. The candidate arrived as a
three-site table program (mandate + forge prompt + three CLAUDE.md principles); both lenses cut it
to one site. The forge site was dropped outright: "the writer said this was deliberate" would
contradict the shipped `load_bearing` escalation contract, and "the fix was small" is already
prevented by a mechanical gate plus a forced revert. The CLAUDE.md site was dropped because §2, §3
and §9 already end in challenge-shaped self-gates and there is no instrument to tell whether a
second layer helped. Then the two lenses split on the escape hatches themselves: one read the
harvest and concluded the clauses are how the mandate dies; the other warned that rebutting tuned
guardrails would push the editor toward compressing readable code — the exact regression they exist
to stop. Both are right, which is why the shape above rebuts nothing and only adds an evidence bar.
A third vetting pass, on candidate #1, independently flagged "Guard the essence" as a nuance clause
appended to "Default to deletion" — condemned by the very doctrine we are adopting. Three passes,
three verdicts, same two lines. Turning the caveat into an evidence-gated conditional is the one
shape that satisfies all three.

### 3. Give the /forge writer a legal way to say it is stuck

**Pitch.** The writer's only outward signal is `mvi_claimed: true/false`. A writer that is genuinely
blocked has nowhere to put *why*, and the required `writer_sha` field has no legal value when there
is no passing commit — so the schema quietly pushes a stuck writer toward faking green instead of
stopping.

**Mechanism.** The escalation licence and its five observable triggers from
`skills/subagent-driven-development/implementer-prompt.md` — especially "you've been reading file
after file trying to understand the system without progress," which is the self-detectable signature
of a lost agent that Studio's abstract "if something is unclear, stop" does not name.

**How it lands.** One optional free-text field in `WRITER_HANDOFF`
(`.claude/workflows/implementation-loop.js`) — call it `escalation` — plus making `writer_sha` and
`tests` legally omittable when it is present. Note `additionalProperties: false`, so this is a real
schema change. Then ~3 lines in `writerPrompt`: the licence, the triggers, and the mechanical
instruction (set `mvi_claimed=false`, do not commit, put the reason in the field). Surface it the
way the loop already surfaces things — `log()` it, add it to the return payload beside
`reviewerConcerns`, and give it a bullet in forge.md's report step. Reconcile
`IMPLEMENTATION_LOOP_SPEC.md` §1/§2/§3, which currently say the writer is not trusted to judge its
own work: "I am stuck" is a different kind of signal from "I think my work is good," and the spec
should say so.

**Size.** A day, plus one live /forge smoke. Any change to an `agent()` input schema in this repo
has a track record of only failing against the live API (that is why `test_workflow_shells.py`
exists).

**Vetting forced.** The four-valued status enum is gone. `BLOCKED` and `NEEDS_CONTEXT` both route to
behavior the loop already has — `implementation-loop.js:211-221` already skips the editor and
delivers flagged — and `DONE_WITH_CONCERNS` re-introduces exactly the self-attested quality boolean
the spec records cutting as redundant. Also gone: the P0 decision-point destination. The candidate
called it a free hookup; grep says decision points are not reachable from the forge loop at all, so
that would be unbudgeted net-new plumbing. What is left is one field and three lines — and it is the
only part the schema currently forbids. Worth noting honestly: all 11 real writer handoffs in
`.studio/output/impl_loop/` show `mvi_claimed=true` and green tests, so this fixes a hole we have not
yet watched anyone fall into.

### 4. A stated rationale is a claim, not evidence

**Pitch.** When an author explains why they did something, a reviewing agent reliably converts a real
finding into a non-finding. Two sentences name that move.

**Mechanism.** `skills/subagent-driven-development/task-reviewer-prompt.md`: "Design rationales in
the report are claims too: 'left it per YAGNI,' 'kept it simple deliberately,' or any other
justification is the implementer grading their own work. Judge the code on its merits — a stated
rationale never downgrades a finding's severity."

**How it lands.** Two one-sentence edits. In `CONTRARIAN_MANDATE`'s finding-gate block: a stated
reason is a claim, so when the advocate defends a choice, quote that line and critique the choice on
its merits — the advocate grading its own work settles nothing. In the Reviewer Concerns paragraph
of `editorPrompt` (`implementation-loop.js:168-175`): a `load_bearing` reason bars the *cut*, it does
not settle the *critique* — if the problem is real, record it in `unresolved_concerns` even when the
writer's reason sounds convincing.

**Size.** Two sentences. An hour, including the doc updates.

**Vetting forced.** Everything except the two sentences, and the two lenses disagreed about which
site survives. One showed the forge editor is never handed the writer's rationale (only `writer_sha`,
`files_touched`, `load_bearing`) and that `edits` is an *editor* output field, not a writer one — so
the original clause would defend a channel that does not exist. The other showed
`CONTRARIAN_MANDATE` ships into market, design and studio debates where there is no artifact
separable from the argument, and that a blanket "never lowers severity" would fight the
rejection-feedback loop through which Studio's runs actually reach APPROVED. The reframe above
answers both: quote-and-engage works in a market debate, and the forge clause is scoped to the one
channel that does exist (`load_bearing`). Dropped: the proposed `test_prompt_policy.py`, which would
assert that a phrase appears in the module defining that phrase. Also dropped, and this matters —
the candidate's headline evidence does not hold. The "0 of 10 planted defects" number is real
(`docs/superpowers/specs/2026-06-10-strict-cost-sdd-design.md:205-214`) but it measured *forced-haiku*
reviewers, only 1 of the 10 was the rationale downgrade, and superpowers' actual fix was killing the
cheap-reviewer tier ("DEAD, as pre-registered"). **This borrowing was structural reasoning, not
measured evidence** — originally labelled speculative on that basis.

**Upgraded to convergent (2026-07-28).** A second, unrelated source states the same rule
independently. Alexey Grigorev's AI-native development write-up defines a QA agent role whose closing
instruction is: "Ignore what the implementation says it does. Only the acceptance criteria and the
running code count" — and separately, "When the same agent writes and judges the code, it's grading
its own homework." That is this borrowing, arrived at by a different person solving a different
problem with a different toolchain. Two independent practitioners is weaker evidence than a
measurement and much stronger than one project's reasoning. Still no number behind it, so the
scorecard row stands unchanged; but "speculative" understated it.

### 5. Let the /forge editor look outside its read scope — against a risk it names

**Pitch.** The editor is told "Do not wander beyond that read scope," a ban with no valve. A
legitimate cross-cutting check — this diff changed a contract, are the callers fine? — is therefore
either skipped or done quietly. Replace the ban with a gate.

**Mechanism.** `skills/subagent-driven-development/task-reviewer-prompt.md`: inspect outside the diff
"only to evaluate a concrete risk you can name — one focused check per named risk, and name both the
risk and what you checked in your report," with cross-cutting changes named as legitimate risks. Plus
its evidence rule: `file:line` for every finding "and for any check you would otherwise answer with
a bare 'yes.'"

**How it lands.** Rewrite the one-line ban at `implementation-loop.js:159` into a valve: read outside
scope only against a named risk, one check per risk, and name the risk and the check in `edits`. Give
the concrete legitimate cases (a changed signature, shared mutable state, a changed file format or
config key), since generic phrasing is what agents route around. Separately, one phase-neutral clause
on `CONTRARIAN_MANDATE`'s "Quote before you claim": evidence is owed for a clean verdict too, not
only a finding — worded "cite, don't narrate." Update `IMPLEMENTATION_LOOP_SPEC.md` §3/§4 and the
read-scope descriptions in `CLAUDE_CODE_USAGE.md` and `CLAUDE.md`, which currently call it a hard
bound. Decide explicitly what `read_scope = "touched"` now means: either the valve applies to both
settings and the knob only sets the default width, or `"touched"` stays a real ban.

**Size.** Half a day including docs. No new config field, no new schema field.

**Vetting forced.** The `breadth_checks` schema field is gone — nothing in the JS or Python would
read it, and `edits` is already a free-text rationale field; the spec records cutting a field for
exactly this reason. The evidence-for-a-pass rule was nearly dropped: `CONTRARIAN_MANDATE` ships to
market and design debates where "cite `file:line`" is meaningless, so it must be phase-neutral or
live in `editorPrompt` only. Word it "cite, don't narrate" from the start — superpowers' own eval log
shows the unqualified version drove a 14.5M → 32.2M token regression before that phrasing clawed it
back. Also: the candidate's "repo-wide greps cost 4-8× the scoped ones" figure does exist in
superpowers' spec, but it measured *their* diff-only default, and Studio's default is already
`touched+importers`, so the flagship use case is already inside our scope. Ten real editor handoffs
report zero cases of being blocked by read scope. **Land this with the cadence lab, not before it** —
capture the current per-unit editor token cost first so a widened scope is measurable rather than
assumed.

**Declined 2026-07-28.** This was specced (`/spec`, PR #78) and the spec was rejected — on the
condition this section had already named. The valve trades editor input cost for cross-cutting
coverage, and there is no measurement of either side: the current per-unit editor cost was never
captured, and ten real handoffs report nobody being blocked by the read scope. So the trade cannot be
evaluated, only guessed at. The proposal is not wrong; it is unmeasured, and the honest move was to
decline rather than ship on a hunch. Phase 0 ran on 2026-07-30 without closing this: it recovered a
cut-rate baseline but no cost baseline, and cost is what this trade turns on. Revisit once per-unit
editor cost is instrumented — the scorecard row below is the test it would then have to pass.

### 6. Pre-commit the shape of a verification, including what it will not show

**Pitch.** An agent asked to write up its own results picks the sections that flatter them. Fix it by
pre-committing the form: the approved spec states the pass criterion before the work starts, and the
results file exists with its headings — including a mandatory section for what the result does not
demonstrate — before any data lands in it.

**Mechanism.** `docs/superpowers/plans/2026-07-06-sdd-plan-scoped-workspace.md` (Task 4 Step 7)
carries the verbatim empty skeleton of its results doc with `<fill>` placeholders and the RED
baseline pre-filled; the filled sibling
(`docs/superpowers/specs/2026-07-06-sdd-plan-scoped-workspace-eval-results.md`) keeps the mandatory
"What RED showed (and did not show)" and "Limitations" headings.

**How it lands.** Add `## Verification` to the spec template in `.claude/commands/spec.md`, required
only when the feature is prompt-shaped — i.e. its behavior lives in an agent prompt, so tests cannot
be the pass criterion. It states the pass criterion as an iff, names the baseline that must reproduce
first, and names the sibling results file. Adopt `specs/<slug>-eval-results.md` (`.studio/specs/` in
consuming repos) with a `Spec:` back-link, created at approval time with headings plus `<fill>`, and
a mandatory `## What this does not show`. Define the stop condition: a results file still at `FILL_ME`
blocks the claim that the feature works.

**Size.** A few hours. Template prose plus one convention.

**Vetting forced.** The summary.md skeleton is cut — `summary.md` is a per-run debate artifact with
no baseline and no arms, and editing its generator means touching the file already flagged for
decomposition. The "null baseline escalates to P0" rule is cut as new machinery; it is one sentence
inside the template pointing at the decision protocol that already pauses on P0. Pasting the results
markdown *inside* the spec is cut — the spec names the criteria, the sibling file holds the headings.
And the candidate's whole motivating claim is wrong and must not be repeated: it said
`GSTACK_SCORECARD.md` "has no pre-registered thresholds." It does — a per-mechanism trigger table,
three top-line questions, a review cadence, an exit rule, and a section stating outright that there
is no clean before/after A/B. The scorecard's defect is that it has no data, and no markdown template
fixes low run volume. Size this borrowing as a template change for *future* prompt-shaped features
and judge it on that. One pre-existing wrinkle to resolve while we are in there: `.gitignore` ignores
`.studio/`, while spec.md calls specs "tracked ... meant to be committed."

## Rejected, with reasons

This section matters as much as the proposal. Two of the most valuable outcomes of the gstack
exercise were a rejection and a reshaping; the same is true here.

### Rejected after vetting

| Candidate | Why |
|---|---|
| **A deterministic gate that rejects specs and unit briefs containing placeholder phrasing** (TBD, "add appropriate error handling") | The concern is already owned upstream by the Open-Questions Pre-Flight, the decision protocol and clarity scores — Studio's answer to an undecided thing is to surface it as a P0 before the loop starts, not to grep the prose that resulted. Worse, it would fight a mandated section: the spec template requires "Risks & Open Questions — anything still genuinely open. Be honest here." A hard failure on TBD punishes exactly that honesty. Zero observed instances: I grepped all five approved specs for the proposed patterns and got no hits. And the /forge half cannot be deterministic at all — the brief is free text an agent composes and hands to a JS workflow, never passing through Python, so the check would be the agent grepping text it just wrote. Also Goodhart-trivial: "add appropriate error handling" becomes "the handler surfaces a friendly failure message," same undecidedness, zero matches. |
| **Give `reviewer-concerns.md` a consumer obliged to triage every line** | The borrowed mechanism's precondition does not exist here. In superpowers a deferred finding lives inside a bounded episode — a plan-scoped ledger with a named *terminal* consumer that triages before merge, after which the ledger dies with the branch. `/forge` is single-unit and one-shot: no plan, no episode, no final whole-branch review. Substituting "the next forge run" gives the obligation no end condition and no disposition state, so it grows forever. Two of the three `why_unresolved` values are unfixable by construction (`load_bearing` means the writer declared it off-limits; `breaks_green` means acting on it breaks the gate), and the spec titles the mechanism "persist the disagreement, **don't loop on it**." The file is also written by a best-effort LLM side instruction, not by the orchestrator, so a consumer globbing for it would silently miss runs. **What survives:** sharpen forge.md's report step, which already lists concerns, to require a disposition per concern from *this* run. A few words. |
| **Mark tuned prompt text as protected and assert its load-bearing phrases in pytest** | Three of the six named invariants are already guarded, two of them better than the proposal would: "Default to deletion" is asserted at four sites with negative guards, the canonical FINDING block is guarded by an executable round-trip parse, and the verifier firewall is guarded *structurally* (`item.quote` reaches the prompt, `item.flaw`/`impact`/`reason`/`confidence` do not) — a reword cannot defeat that, and a prose check beside it would be a downgrade. Asserting all 11 blacklist items would freeze a count the scorecard explicitly says to prune when a human overrides an entry, turning the documented correct action into a red suite. And the policy half duplicates a contract the scorecard already owns per mechanism. The doc-parity analogy also fails in kind: that test correlates two independent artifacts where the code is the source of truth; a literal asserted against the module that defines it is a speed bump, since the cheapest repair for the agent that just reworded the prose is to reword the literal. **What survives, and it is worth doing:** the R3 scar text exists twice with divergent wording (`scopes.py:386`, `run_phase.py:985`) and is asserted nowhere. Hoist it to one owner constant, the way `FINDING_BLOCK_TEMPLATE` already owns the finding format. That is Studio hygiene, not a borrowing. |
| **Make "I watched the test fail" a required handoff field gating the editor** | The Mutation Verification Rule already proves the stronger property, with a real tool: `AI_TDD_METHODOLOGY.md` mandates breaking the production code and rejecting if tests still pass, `writerPrompt` already carries a break-and-restore fallback, `mutation_check` already exists as a structured field, and `/detest` already hunts green-checkmark traps. `red_evidence` would be three free-text strings an agent writes about its own past behavior — trading a verified check for an attested one and calling it stronger. It also cannot establish the property claimed for it (that tests preceded the code): a writer can write code, write tests, remove the code, observe red, restore, and report all three fields truthfully. Gating on it would additionally skip the editor pass entirely as the punishment for not narrating a failure. **Two real fixes it surfaced, both one-liners, both worth taking:** `implementation-loop.js:137` tells the writer to hand-mutate by breaking "2-3 critical **assertions**" while the methodology says break the production **code** they guard — breaking an assertion makes a test fail trivially and proves nothing, so the fallback as written is close to tautological. And "test output pristine — new warnings are a finding" appears nowhere in Studio; add it to the editor's checks. |
| **A fixed `## Global Constraints` section in every spec, stamped into every prompt by Python** | Rejected on the mechanism, kept as a known gap. The pitch's whole claim is that Studio is a generator so nobody has to remember anything — but no Studio run knows a spec exists. `prepare` has no `--spec`, `run.json` records no spec field, and the only existing link runs the wrong way (spec frontmatter records `studio_run`). Every way out is bad: a `--spec` flag reintroduces the remembering; auto-globbing `specs/` would assert five unrelated features' constraints as binding on every run. It also defines the section as *project-wide* but puts it in a *per-feature* document, which makes every new spec carry a copy with no owner — a stale-constraint generator in a repo that maintains `/unstale`. Project-wide values already reach every agent through the sentinel-marked CLAUDE.md block the installer maintains. **The real gap it points at is genuine and stays on the list:** `/forge` never reads the approved spec, so the architecture reaches the build only if a human pastes it. The minimal shape — a `--spec <path>` pointer plus one line each in `writerPrompt` and `editorPrompt` — is a separate, speculative future item, not part of this proposal. |
| **Scan for spec-vs-principles conflicts and escalate plan-mandated findings** | The third path already exists and is load-bearing: the writer lists `load_bearing` items with reasons, the editor must escalate rather than remove one, and a real critique it cannot act on becomes a Reviewer Concern. The batched pre-flight half duplicates `/spec` itself, where the contrarian already carries the cut mandate, the run pauses on P0s, and unresolved concerns are written into the spec's own "Risks & Open Questions" before a human approves. The candidate's slogan — "the spec's authorship does not grade its own work" — is factually wrong about Studio: the spec is adversarially graded at authorship and gated on human approval. And the claimed P0 machinery is not reachable from the loop; forge.md tells the assistant not to poll a backgrounded workflow, so a mid-loop human pause is not available. **What survives:** one line in `writerPrompt` telling the writer to list spec-mandated choices in `load_bearing` with the mandate as the reason. |
| **Verify that a claimed fix removed the defect, scoped to the fix diff** | Contradicts a decision the spec made deliberately: "there is **no re-run loop**: the writer runs once, the editor runs once, the unit is delivered," and it records cutting `max_unit_iterations` as "configurability for a loop the design forbids." The trigger also does not exist — concerns are terminal, have no ID, no open/resolved state and no base SHA, and `runDir` is keyed by `unit_id` so a repeat overwrites the handoff. The claimed reuse is false too: `findings.json` is only ever populated from `contrarian*.md` in a debate run, and the forge loop never writes it, so a `resolution` field would land on the wrong record. The debate half is already covered by `rerun.py` plus the iterate-to-APPROVED contrarian loop. **What survives:** one line in `editorPrompt` adopting the standard — "'Attempted' is not addressed: the specific defect must no longer exist" — so when a writer touches a previously flagged problem the editor judges removal rather than effort. |
| **Prove a fresh install fires, and assert what must never be in it** | The import-closure half already exists and is stronger: `test_installed_snapshot_imports` installs into a temp dir and runs `python -c "import run_phase"` as a subprocess, which exercises the real transitive closure — an AST scan would be a regression. The forbidden-path walk is vacuous against this installer: `_collect_source_files` iterates an explicit allowlist plus two narrow globs, there is no `copytree`, so `tests/`, `.private/` and `.scratch/` cannot enter. Two of the six named forbidden paths are worse than vacuous: install *deliberately* creates `.studio/output/` and `.studio/knowledge/`, asserted by an existing test. And the bug the candidate promises to catch mechanically is invisible to its mechanism — the /forge install gap was a missing `.js` in `WORKFLOW_FILES`, which no Python import scan can see. **What survives, and it is the right guard — now built (`test_install.py::TestShipListParity`, 2026-07-29):** nothing asserted that every file on disk in `.claude/commands/` and `.claude/workflows/` is a member of `SLASH_COMMANDS`/`WORKFLOW_FILES`. That is exactly the class of the shipped bug, and it took about six lines in the both-ways idiom `test_doc_parity.py` already uses. It caught a second instance on the way in: `/handoff` shipped 2026-07-29 without being added to `SLASH_COMMANDS`, so consuming repos would never have received it. |
| **A behavioral eval harness for prompt changes: RED baseline, control, N reps, pressure scenarios** | The most tempting item here, and the one I would not build yet. Three problems. **The install path breaks as specified:** `SOURCE_FILES` has no `tests/` entry, so shipping the workflow shell gives every consuming repo a runner pointing at a fixture directory that does not exist there; not shipping it still drags a dev-only `prompt-eval` subcommand into the installed CLI, and `test_doc_parity.py` asserts both ways against API.md's command table, forcing a command consumers cannot run into the installer-facing reference doc. **Construct validity:** in superpowers the skill under test *is* the whole instruction one agent receives, so the harness measures the real thing. In Studio, `CONTRARIAN_MANDATE` is injected at two points into a multi-page instructions.md and consumed inside a staged multi-agent debate alongside the persona, scope prompt, decision protocol, clarity and MVI. A one-shot subagent handed a scenario plus one fragment measures a configuration Studio never ships — it can read green while the real run degrades, or red while production is fine. **The cheap path already exists and is unused:** `implementation_loop.toml` ships the `mandate` knob (at `"contrarian"`; `"off"` is the value that disables the editor pass), so the "never captured a no-editor baseline" gap is one config line and a day of runs away (still true as of the 2026-07-30 Phase 0 run, which did not attempt this arm); a control arm on the contrarian mandate is one `if` at two injection sites plus two `prepare` calls. Several days of new machinery to enable something existing knobs already enable fails Simplicity First on its face. Worth noting: superpowers' own harness scores by grepping a JSON stream, not by an LLM judge — the "read the replies" upgrade would insert a second uncalibrated model into the scoring path, making variance in five reps indistinguishable from variance in the judge. **What we take for free:** the doctrine, folded into the principles as a new section — always run the scenario without the guidance first and keep that transcript; if the baseline does not exhibit the failure, do not author the guidance; treat five divergent readings across five reps as a wording defect to tighten rather than a signal to add words. **Re-entry condition:** if the doctrine plus the existing instruments still cannot tell us whether a prompt change helped once per-unit editor cost is instrumented, revisit — as a repo-local `studio/evals/` tool that never enters the shipped CLI surface, with a validated arm and grep-based scoring. |

### Rejected before vetting

Sixteen mechanisms were ruled out before they entered adversarial vetting. Grouped by reason:

- **Solves a problem Studio deliberately does not have.** The multi-harness bootstrap layer (one hook
  emitting three JSON shapes by env sniffing, in-process JS/TS injectors with dedup markers and
  compaction re-injection, per-harness tool-mapping files, seven hand-maintained manifests) only pays
  off at N>1 harnesses; we reversed the equal-peers goal in July and Claude Code is the supported
  path. The polyglot `run-hook.cmd` batch/bash wrapper and extensionless hook scripts solve a Windows
  shell-dispatch problem our Python hooks do not have. The zero-dependency rewrite doctrine is a
  constraint we already live under, more strictly.
- **Enormous surface for its job.** The visual brainstorming companion — a 723-line hand-rolled
  HTTP/WebSocket server, frame templates, capability URLs, PID watchdogs, a JSONL click stream — for
  showing mockups; the skill itself concedes it is token-intensive and their own notes say a static
  HTML file opened with `open` covers most of the value. The graphviz shape DSL plus `render-graphs.js`
  needs a system `dot` install and does regex surgery on dot source, where Mermaid renders natively
  and `/spec` already mandates a diagram.
- **Already covered, correctly.** The recorded-BASE diff discipline (never `HEAD~1`) is exactly what
  the forge editor already does with `writer_sha`. Plan-scoped workspaces are Studio's timestamped run
  directories on a different axis, already collision-free and already gitignored. The awk task-brief
  slicer is strictly worse for a generator — Studio can *write* per-unit briefs at prepare time rather
  than regex-slicing them later, and their slicer is documented as fragile.
- **Actively harmful here.** Deleting the workspace on success (`rm -rf`) with git history as "the
  record" — git contains none of the parked rulings or deferred findings that lived only in the
  ledger, and it contradicts the same skill's "a silent discard is forbidden." Studio's whole
  measurement layer depends on artifacts persisting, with cleanup already handled by a 30-day TTL and
  a 900MB budget. Likewise `defense-in-depth`'s "validate at EVERY layer so the bug becomes
  impossible" flatly contradicts CODING_PRINCIPLES §2 and §3, and the source argues only the benefit
  side. And the mental mutation check ("mentally mutate the production code") is a downgrade for a
  repo that runs mutmut for real — importing an imagined version risks agents treating it as
  sufficient.
- **Philosophical conflict.** "Continuous execution: do not pause to check in with your human partner
  between tasks" is the direct opposite of Studio's core bet that all decision points bubble up
  immediately, per agent, never batched for a closing section. Only the batched *pre-flight* half was
  compatible, and it was proposed separately — then rejected on its own merits above.
- **Right about the common case, wrong at our edge.** "Behavior, not text" stated absolutely — never
  assert that a doc contains a given line — would condemn `test_doc_parity.py`, which asserts a
  *consistency invariant between two artifacts* rather than restating one artifact. Adopt the ban on
  grepping prose wording for its own sake; keep the invariant carve-out and state it explicitly.
- **The measurement does not transfer.** superpowers deleted its independent document reviewer on
  "identical quality scores regardless of whether the review loop ran." Read carelessly that argues
  against Studio's core bet — but their deleted reviewer was handed only the document, with
  calibration tuned toward approval, no code and no independent oracle, so it had strictly less
  information than the author and mostly agreed. Studio's contrarian, verifier and forge editor all
  have an oracle the author lacks. What is worth importing is the method (measure whether the debate
  earns its tokens) and the sharper lesson: a review pass with no evidence source beyond the artifact
  under review is the one that does not pay.
- **Aimed at a funnel we do not have.** The contributor-deterrence layer — a published PR rejection
  rate, an agent-addressed "tool of embarrassment" preamble, a ~6KB PR template demanding
  model/harness/plugin provenance — targets unsolicited contributions, is unverifiable by
  construction (a fabricating agent fills the provenance table just as easily), and none of it is
  machine-checked. Its two useful clauses are already folded into items above.
- **Mostly inapplicable.** Model-tier selection doctrine: Studio has no AI runtime and selects no
  models, and superpowers' own two cost-reduction rungs both died at their gates. The one durable
  idea — write down which roles carry judgment and may never be cheapened — is worth a paragraph in
  ARCHITECTURE.md, not a roadmap slot.

## The phased plan

Each phase is independently shippable and ends in something usable on its own.

**Phase 0 — get a baseline before changing any prompt text. RUN 2026-07-30; see [PHASE_0_BASELINE.md](./PHASE_0_BASELINE.md). It was not executable as written**, which is why it sat undone: the metrics it names never measured the forge editor, and per-unit editor token cost is instrumented nowhere. The forge editor's liveness *was* recoverable from the handoffs on disk — **9 of 12 runs produced real cuts (75%)**, so the cut mandate is alive. What remains unmeasurable is cost.

**What it originally asked for, and why it could not be delivered:** a no-editor run with the shipped
`mandate` knob at `"off"`, recording per-unit editor token cost plus `editor_liveness` /
`shrink_ratio`. The loop emits no token data at all, and those two metrics read advocate-document word
counts from *debate* runs — they have never measured the forge editor and structurally cannot.

**Remaining follow-up:** instrument per-unit editor cost in the loop. That is a build, not a
measurement, and it is the only thing still standing between item 5 and a real trade-off.

**Phase 1 — the prose that costs nothing and fixes something. NOT STARTED as of 2026-07-29**, except the ship-list parity test, which shipped that day. Proposal items 1, 2 and 4, plus the
riders the rejections surfaced: hoist the R3 scar to one owner constant, fix the hand-mutation
instruction to break production code rather than assertions, add "test output pristine — warnings are
a finding" to the editor's checks, and add the six-line ship-list parity test for
`SLASH_COMMANDS`/`WORKFLOW_FILES` (**done**). **Usable output:** a prompt-doctrine section of CODING_PRINCIPLES — which does not exist yet; the file ends at §7 — ships to every
installed repo; the contrarian's escape hatch now costs evidence; two shipped bugs-in-waiting closed.
One commit each, one PR. Measured against the 75% forge cut rate in PHASE_0_BASELINE.md, not
`editor_liveness`, which never measured this loop.

**Phase 2 — the writer's escalation channel. DONE 2026-07-29** (PR #84; entry gate pinned in #87). Proposal item 3: the schema field, the relaxed
required-fields, the prompt prose, the spec reconciliation, and one live /forge smoke. **Usable
output:** a blocked writer can stop and say why without faking a commit. Ships alone; needs nothing
from Phase 3.

**Phase 3 — the breadth valve. Declined 2026-07-28, not scheduled.** Proposal item 5 was specced and
rejected: it was gated on the Phase 0 cost baseline, and no real handoff has yet reported being
blocked by the read scope. Phase 0 has since run (2026-07-30) and narrowed that gap rather than
closing it — the forge editor's cut rate is now known (75%), but **per-unit editor token cost is still
instrumented nowhere**, and cost is the half a read-scope trade turns on. Nothing here is blocked by dropping it —
this phase never fed the others. See item 5 above for the full reasoning, and treat it as available to
revisit once there is something to measure against.

**Phase 4 — the verification convention. DONE 2026-07-28**, extended with a fourth rule 2026-07-29.
Proposal item 6, built to
`specs/prompt-feature-verification.md`: `## Verification` in the spec template, the
`<slug>-eval-results.md` sibling with its `Spec:` back-link and mandatory "What this doesn't prove,"
and the stop condition. **Usable output:** the next prompt-shaped feature cannot ship claiming it works
without a written pass criterion and a place its evidence has to go. Also resolves the `.gitignore` /
"specs are tracked" inconsistency for consuming repos.

Two changes from the proposal as written. The stop marker is `FILL_ME`, not `<fill>` — angle brackets
parse as a raw HTML tag in CommonMark and render as zero visible characters, so the one file whose job
is to look conspicuously unfinished would have rendered as complete. And the convention is enforced by
`studio/tests/test_spec_verification.py`, four rules that leave existing specs alone and refuse only
the `shipped` claim — with unfilled evidence, with one of the evidence file's headings dropped, or with
one left holding nothing but the guidance the skeleton printed. That last rule closed the deletion gap
the first three missed; what remains is filler like "N/A", which that spec's Risks record as
undetectable in principle.

**Later, if the numbers ask for it.** The eval harness, under the re-entry condition above. That is
all that is left here: teaching `/forge` to read its approved spec **shipped 2026-07-29** as PR #85,
built to `specs/unit-acceptance-criteria.md` — the `--spec <slug> --unit <id>` pointer was indeed the
minimal shape.

## How we would know it worked

Same constraint as the gstack pass, and the same honesty about it: run volume is low, so a single bad
run swings any average, and Phases 1-4 are prose changes with no clean A/B. The difference this time
was supposed to be that Phase 0 gives two of the six items a genuine before-number rather than a
rough pre-date baseline. Phase 0 ran on 2026-07-30 and delivered half of that: rows measuring the
forge editor's *liveness* now have a real before-number (75% cut rate, 9 of 12 runs). Rows naming a
*token* before-number still have none, because the loop emits no token data — those remain
unmeasured.

| Item | Signal (instrument) | Helping looks like | Hurting looks like | Trigger to act |
|---|---|---|---|---|
| Prompt doctrine *(not yet written — Phase 1; CODING_PRINCIPLES ends at §7, so this row cannot fire yet)* | Whether it gets cited when prompt text changes; no new nuance clauses land in `scopes.py` / `question_mode.py` | New prompt edits pick a form deliberately and say which | It is never referenced in any prompt-change PR | Two prompt-change PRs in a row that cite no form → the section is decoration; cut it |
| Escape hatches earn their invocation | ~~`editor_liveness` / `shrink_ratio`~~ — **wrong instrument, corrected 2026-07-30**: those read *advocate-document* word counts from debate runs and have never measured the forge editor. Use the forge handoffs' cut rate instead, against the 75% baseline in PHASE_0_BASELINE.md | More forge units end with a real cut; "no edits" handoffs stop citing the mandate's own clauses | Liveness flat, or the editor starts compressing readable code (the regression the clauses exist to stop) | Liveness does not move after ~10 forge units → revert the text. Any review flagging over-compression → revert immediately |
| Writer escalation channel | Count of handoffs carrying a non-empty `escalation`; count of green-but-wrong units caught later | A genuinely stuck writer stops instead of guessing, and says what it needs | Field never used across ~10 units (the hole was theoretical), or used to dodge tractable work | Never populated across ~10 units → the schema hole was real but the failure was not; keep the field, drop the prompt prose |
| Rationale is a claim | Whether a contrarian finding survives an advocate's justification; whether the editor logs a concern it previously dropped | Findings get engaged with rather than withdrawn after a good explanation | Iteration burn: runs take more passes to reach APPROVED because rebuttals no longer resolve anything | Median iterations-to-verdict rises across ~10 runs → the wording is fighting the rejection-feedback loop; revert |
| Breadth valve + cite-don't-narrate | Per-unit editor token cost vs Phase 0; count of named-risk checks reported in `edits`; concerns raised that touch non-importer consumers | Real cross-cutting problems surface, at a small cost delta | Editor tokens climb with no new findings, or `edits` fills with narration | Editor cost up >25% over baseline with no new concerns across ~10 units → revert the valve |
| Verification section + eval sibling | Share of prompt-shaped specs that carry a pass criterion; share of results files still at `FILL_ME` when the feature shipped | The criterion is written before the build and filled after | Results files sit unfilled and readers learn to skim past them | Two shipped features with unfilled results files → the convention is decoration; either enforce the stop condition or delete the tier |

**Three top-line questions**, same as the gstack scorecard. Phase 0 ran on 2026-07-30, so question 2
now has a before-number (75% forge cut rate); questions 1 and 3 still have none, because human
ratings have never been recorded and the loop emits no token data:

1. **Human rating trend** (`rate`, 1–5). The bottom line, unchanged.
2. **Forge yield** (cut rate from the forge handoffs; baseline 75%). Not `editor_liveness` — that
   measures the debate contrarian's effect on advocate docs, not this. Cut-per-*token* remains
   unavailable: the loop emits no token data at all.
3. **Cost per unit of quality.** Items 3 and 5 add tokens by design. That is only worth it if the
   quality signal moves.

**Cadence and exit.** Review after ~10 rated runs or ~10 forge units, whichever comes first. The exit
rule carries over from the gstack scorecard: a borrowing that trips its trigger and does not recover
after one tuning pass gets reverted, and a mechanism that cannot be measured — or measures as
neutral-but-costly — is a removal candidate, not a permanent fixture. Three of the six items above
have a real instrument; three do not, and I would rather say so than pretend. For the three without
one, the review date is the gate: if nobody can point at a case where it helped, it goes.

**One watch-item I would flag hardest.** Item 2 sits on two lines of prompt text that three separate
vetting passes read three different ways. It is the highest-value change here and also the one most
likely to cause a regression, because the clauses it touches were added on purpose after the
human-readable-code feedback. If forge output starts getting denser rather than smaller, that is the
tell, and the revert is one commit.

## Postscript: a second source, read 2026-07-28

After this study was written we read Alexey Grigorev's *AI-Native Development: Specifications, Loop and
Graph Engineering* ([alexeyondata.substack.com](https://alexeyondata.substack.com/p/ai-native-development-specifications)),
the first article in the AI Dev Tools Zoomcamp series. It describes a workflow with no knowledge of
superpowers or of Studio: brainstorm a vague idea into a spec in a chat assistant, decompose it into a
backlog, then run three agent roles — a product manager who grooms each task, an engineer who
implements it, and a QA engineer who returns PASS or FAIL against the task's acceptance criteria.

Most of it Studio already does, and does harder. Spec-before-code is `/spec`. A reviewer separate from
the implementer is `/forge`'s editor, and an adversarial editor with a cut mandate is stronger than a
PASS/FAIL check. The tool-agnostic `AGENTS.md` bootstrap is the same multi-harness layer we rejected
from superpowers, for the same reason. And the article's own closing caveat retires its headline idea:
"this approach takes significantly more time and tokens than a direct loop with only a software
engineer. In many cases, you don't need this complexity."

Three things it changed here:

- **It upgraded item 4 from speculative to convergent.** See that section. Two unrelated sources
  independently landing on "the author's stated rationale does not settle the critique" is the closest
  thing to external validation this list has.
- **Three sources now agree that a deferred critique must not vanish silently.** gstack gave us
  Reviewer Concerns. superpowers states it as a rule with teeth — "every adjudication is a ledger
  entry — a silent discard is forbidden." This article states it at grooming time instead of review
  time: "If something does not belong in this task, do not silently drop it. File a follow-up issue and
  list it under out of scope with a link to that issue, so it is clear what was moved and where it
  went." Three unrelated projects converging on one principle is the strongest signal in either study,
  and it argues for hardening Reviewer Concerns rather than leaving it a best-effort side instruction.
  The concrete shape stays the one the rejection table already landed on: require a disposition per
  concern from *this* run in `/forge`'s reporting step. Nothing larger — the "named consumer" version
  is still rejected, for the reasons recorded there.
- **It found a real gap: no Studio unit carries checkable acceptance criteria.** The article's groomed
  task has four sections — Goal, Acceptance criteria ("someone should be able to point at the screen
  and say yes or no"), Out of scope, and Constraints — written before an engineer starts. Studio has no
  equivalent. A `/forge` unit carries a `title` and free-text `instructions`, and the editor's
  *authoritative* `mvi_verdict` is judged against the `title` alone
  (`.claude/workflows/implementation-loop.js:177`). So the one binding quality verdict in the
  implementation loop has a single line of prose to check against, while `/spec` already produces MVI
  build units that could carry criteria. Specced separately as
  [`specs/unit-acceptance-criteria.md`](../../specs/unit-acceptance-criteria.md).

Two smaller notes, neither promoted to a proposal. The article keeps context in per-topic documents
loaded *conditionally* ("Before writing tests, read `_docs/testing-guidelines.md`") rather than all at
once — our docs index is a catalog, not a conditional loader, and the difference is free context
economy if we ever feel the squeeze. And it uses a standing prompt to keep documents alive: "Based on
the corrections I made, find the relevant documents and update them." We have `/unstale` for audits but
no reflex for capturing a correction at the moment it happens. Both are cheap; neither is a feature.

Rejected outright: the PM/engineer/QA orchestrator graph (Studio's staged debate with an integrator is
richer, and the article concedes the cost), GitHub issues as the canonical backlog (a workflow swap
with no win for a repo whose backlog is specs and run artifacts), and the multi-harness bootstrap.

## Source

Repo studied: https://github.com/obra/superpowers (MIT), v6.2.0, commit `3dcbd5c`. The transferable
material is concentrated in `skills/writing-skills/` (SKILL.md and
testing-skills-with-subagents.md), `skills/subagent-driven-development/` (the four prompt templates),
and the 2026-07-06 spec/plan/eval-results triad under `docs/superpowers/`. Prior comparable exercise:
[GSTACK_COMPARISON.md](./GSTACK_COMPARISON.md) and
[GSTACK_SCORECARD.md](./GSTACK_SCORECARD.md).
