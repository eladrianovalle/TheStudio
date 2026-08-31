# Implementation Writer/Editor Loop Spec

> **Status: shipped (executor + config); cadence tuning ongoing.** The Workflow shell
> (`.claude/workflows/implementation-loop.js`), the `/forge` trigger, and the config
> loader (`studio/impl_loop.py` + `config/implementation_loop.toml`) are built and merged. What
> remains is the cadence lab: tuning gate granularity against the success/kill metric. This doc
> is the design of record; the "Build phases" section tracks what's done.
>
> Refined once via a Product + Engineering role pass (see "Refinement log").

## Why

Studio already runs an advocate/contrarian debate at the **planning** level: the advocate piles
on, and the contrarian-as-editor carves the proposal down to its essence (`CONTRARIAN_MANDATE`,
`studio/scopes.py:27`). That writer→editor dynamic is the thing that produces tight output.

Implementation has no equivalent. Code is written in one pass by one agent, and whatever sprawl,
duplication, or dead scaffolding accumulates ships as-is. This spec brings the same cadence to
implementation: **one agent builds a complete unit of work; a second agent reviews it and
*applies* edits (cut, collapse, rename, restructure), then the unit is delivered.**

The goal is not more review for its own sake. It is a structurally-guaranteed second pass by a
fresh agent whose entire mandate is to remove what doesn't earn its keep, run at a cadence coarse
enough that the pass is worth its cost, and held to a measurable bar that decides whether the
pass stays on at all (see "Success / kill metric").

## Design principles

These were settled deliberately; each rejects a plausible alternative.

- **Pipeline, not debate.** In planning, advocate and contrarian genuinely disagree and an
  integrator resolves the tension; disagreement *is* the value. In code, two agents arguing
  about an implementation thrashes. So the editor **applies its edits directly** and does not
  hand the work back to the writer. There is no ping-pong, and there is **no re-run loop**: the
  writer runs once, the editor runs once, the unit is delivered. The only branch is a one-shot
  **revert** when an edit can't hold (see escalation).

- **Coarse cadence: fire at a checkpoint, not per edit.** The editor must re-read the unit plus
  a *bounded* slice of surrounding code (see read-scope) to edit safely. That re-read is the
  dominant cost of the loop, so it must buy enough to be worth it. The checkpoint is **one
  complete MVI unit AND tests green**, not "every N edits," not "every file."

- **Native executor, portable core.** The first executor is a Claude Code **Workflow**: it
  enforces the gates with real control flow and doubles as the cadence lab. The
  expensive-to-design parts (prompts, gate criteria, cadence params, the handoff shape) live as
  **data**, not baked into the workflow script, so a port rewrites only the thin shell.

- **In-memory handoff, anchored to a commit.** The writer→editor baton is an in-memory metadata
  object the orchestrator passes between stages (the natural shape in every agent runtime). It
  carries a `writer_sha` (the commit of the writer's passing state), which is what makes the
  diff base, the unit boundary, and the revert restore-point all deterministic.

- **Editor diffs against `writer_sha`, then reads from disk.** The handoff carries metadata only.
  The editor computes `git diff <writer_sha>..` for an unambiguous picture of what the writer
  changed (no conflation with pre-existing uncommitted work, no bleed between sequential units in
  one tree), then reads the touched files directly.

## The portable core (provider-neutral data)

Everything in this section is runtime-agnostic. It is the asset; the executor is throwaway.

### 1. The handoff object

The object the writer stage returns and the editor stage consumes. Serializable by construction
(plain fields, no closures or methods), so the same object doubles as the per-unit record
persisted to the run directory.

```jsonc
{
  "unit_id": "unit_01",
  "title": "Users can create and view a profile (hardcoded storage)",
  "writer_sha": "a1b2c3d",          // commit of the writer's passing state — diff base + revert point
  "files_touched": ["src/profile.py", "tests/test_profile.py"],
  "tests": {
    "command": "pytest tests/test_profile.py -q",   // unit-scoped, fast — run at the gate
    "passed": true,
    "exit_code": 0
  },
  "mvi_claimed": true,              // writer's DECLARATION that the unit is a complete thought — the handoff trigger
  "mutation_check": { "performed": true, "mutations_introduced": 2, "caught": true },  // attested; counts PRODUCTION-code changes, never broken assertions
  "load_bearing": ["the retry in save_profile guards a real race; do not cut"],
  "stuck": "…",       // present ONLY when the writer stopped deliberately: the blocker, quoted. Absent normally
  "stage": "writer"   // "writer" | "editor"
}
```

The **editor** returns the same shape with `stage: "editor"`, its own `writer_sha` no-op (it
diffs against the writer's), updated `tests` (re-run after its edits), an `edits` summary of what
was cut / merged / renamed (and what, if anything, was lost), and `mvi_verdict`: its
**authoritative** judgment of whether the unit is a usable interaction, which can overturn the
writer's `mvi_claimed`. It also carries `unresolved_concerns`: valid critiques it could not act on
this pass (see "Reviewer Concerns" below), empty when there are none. It does **not** carry a
separate `behavior_preserved` flag: "tests stay green" plus the `load_bearing` escalation already
encode that invariant, so a third self-attested boolean was cut as redundant.

When the unit carries **acceptance criteria** — checkable statements of what "done" means, copied
verbatim from the approved spec into the unit's `acceptance_criteria` — the editor grades each one
and returns `criteria_verdicts`, one entry per criterion:

```jsonc
"criteria_verdicts": [
  {
    "criterion": "A deleted profile returns 404",           // verbatim from the spec's Build Plan
    "verdict": "pass",                                       // "pass" | "fail" | "unverifiable"
    "evidence": "test_deleted_profile_404s passes (profile.py:88)"  // what was actually checked
  }
]
```

`unverifiable` exists so the editor never has to invent a grade: it reads a diff and runs the
unit's tests, with no browser and no Play mode, and some criteria simply can't be checked from
there. Anything short of `pass` means the unit ships **flagged** — nothing reverts, and there is no
retry. A run with no criteria (no spec pointer) returns the field empty and the editor judges
against the unit's `title`, exactly as it always did.

`load_bearing` is the writer's signal: these choices look cuttable but aren't. The editor must
not remove a `load_bearing` item without escalating (below).

`stuck` is the writer's escalation channel, and it is present only when the writer stopped on
purpose: the specific blocker, quoting the file, test, or interface it is about. Without it a
genuinely blocked writer had two ways out and both were bad — invent a `writer_sha` and pretend it
finished, or return no valid handoff at all, which aborts the run with `writer_failed` and explains
nothing. An escalating writer instead commits whatever partial work it has as
`writer(stuck): <unit_id>` (with `--allow-empty`, because "read and read, changed nothing" is the
likeliest blocker and leaves a clean tree), reports that SHA, reports `tests` honestly, and sets
`mvi_claimed: false`. So no field leaves `required`, the dead end is a commit someone can read, and
`git log --grep='^writer(stuck):'` is the escalation tally.

### 2. The gate: "MVI unit complete AND tests green"

The gate is the checkpoint, and it has **two distinct moments**, not one rule applied twice:

- **Entry gate (after the writer): purely mechanical.** Admits the unit to the editor when the
  writer has *declared done* (`mvi_claimed`) **and** the machine checks pass (tests green + the
  repo's static check).
  The writer's declaration is only a trigger: the writer is the one agent that knows when it has
  finished a complete thought, so it must be the one to say "hand it off." It is *not* a trusted
  MVI verdict.
- **Exit gate (after the editor): adds the authoritative judgment.** The edit must hold (tests
  still green) **and** the editor renders its `mvi_verdict`. The editor (the fresh, skeptical
  second agent) can overturn the writer's claim. If it judges the unit *not* a usable interaction,
  that is a surfaced finding (deliver flagged / escalate), never a silent pass. When the unit
  carries acceptance criteria, the gate also checks the grades **itself** rather than trusting
  `mvi_verdict` to reflect them: every criterion has to be matched, by its own text, to a passing
  grade that carries evidence.

So the writer never has to "define MVI" to hand off; it only has to declare it believes it's done.
The editor owns the verdict the gate actually trusts. Be honest about what is *machine-enforced*
versus *agent-attested*: conflating the two would manufacture exactly the false confidence the
"Tests green" criterion warns against.

The two things the writer says about itself are not the same kind of claim, and the entry gate treats
them differently on purpose. `mvi_claimed` is a claim about the work's **quality**, which only the
fresh editor can judge — so it can *request* the editor pass but never grant it. `stuck` is a claim
about the writer's **own state**, where no other agent has better access, so there is no second
opinion to defer to. It still extends no trust: an escalation opens no gate. It fails the entry gate
through the existing mechanics (`mvi_claimed: false`, red tests) and takes the existing
deliver-flagged path, adding no branch. A writer's declaration can never open a gate, only explain
why the gate stayed shut. The corollary is that `stuck` is deliberately *not* in the gate expression:
a green, claimed unit that also files an advisory `stuck` note still gets its editor pass, matching
the existing rule that a self-reported problem is not a delivery blocker.

**Machine-enforced (deterministic; the orchestrator branches on these):**

| Component | Criterion | Source |
| --- | --- | --- |
| Tests green | `tests.command` (unit-scoped) exits 0, run by the agent and recorded in the handoff. | `TEST_DRIVEN_GUIDE.md` |
| Static checks | Every command in the repo's configured `static_checks` runs clean, and `static_ok` is the AND across them — `ruff check {paths}` in a Python repo, `npm run lint` in a Node one that declares a lint script, `[]` skips the check entirely. `/forge` replaces `{paths}` with the paths the unit is scoped to; a command without the token runs as written. (mypy is **out** of the gate: `mypy . --strict` blocks virtually any real repo; opt-in only.) | `impl_loop.py`, `forge.md` |
| Full suite at delivery | The complete test suite runs once before the unit is delivered, not on every gate check (keeps the inner loop fast). | n/a |

**Agent-attested (recorded signals, not enforcement; judged by the *editor*, the fresh agent,
not the writer about its own work):**

| Component | Criterion | Source |
| --- | --- | --- |
| MVI complete | Editor's exit-gate `mvi_verdict`: *"If we stopped here, could someone use what we've built?"* — judged against the unit's `title`, or, when the unit carries acceptance criteria, `true` only if the unit is usable as a complete interaction **and** every criterion passes. Overturns the writer's `mvi_claimed`. | `MVI_METHODOLOGY.md` |
| Mutation verified | Run the configured `mutation_command` (mutmut in this repo; scope in `setup.cfg`) on the touched code; survivors → strengthen tests and redo. Falls back to hand-mutating 2-3 places in the production code if mutmut is absent — never the assertions, which fail by construction and prove nothing. | `AI_TDD_METHODOLOGY.md` |
| No anti-patterns | No self-mocking tests, hallucinated assertions, green-checkmark traps. | `AI_TDD_METHODOLOGY.md` |
| Test output pristine | Green is not enough: a suite passing while it emits new warnings, deprecation notices or stray output is a finding. The editor fixes it in the pass or records it as a Reviewer Concern. | `AI_TDD_METHODOLOGY.md` |

What's genuinely reused from `CodeValidator`: its subprocess runner and `ruff`/`pytest`
invocation. The gate still needs **net-new glue** to aggregate `List[CheckResult]` → bool, run the
unit-scoped `tests.command`, and capture the attested signals. The mutation check now runs a
real tool (`mutation_command`) and reports its result, but it still sits in the attested half:
the writer runs it and reports, and no deterministic exit-gate blocks on survivors yet, so
calling it "non-negotiable" would still overstate it.

### 3. The mandates (prompts as data)

Authored the same way personas and roles already are: shipped defaults that a project-local file
shallow-merges over (mirrors `persona_overrides.py` and `role_overrides.py`).

- **Editor mandate** = the existing `CONTRARIAN_MANDATE` (`studio/scopes.py:27`), pointed at code:
  default to deletion, name the specific cut (not "this is complex"), collapse rather than
  accumulate, guard the essence. With one code-specific bound, **behavior preservation**: the
  editor may restructure and delete freely *as long as tests stay green*, and may not touch a
  `load_bearing` item without escalating. The editor also renders the authoritative `mvi_verdict`
  at the exit gate, which can overturn the writer's claim. When the unit carries acceptance
  criteria, it grades each one first — `pass`, `fail`, or `unverifiable`, with the evidence it
  actually checked — and is told to ignore what the handoff, the commit message, and the comments
  *say* the unit does: only the criteria and the running code count.

- **Writer mandate** = build exactly one complete MVI unit: a usable interaction, not a partial
  component (`MVI_METHODOLOGY.md`). No speculative scope. When it believes the unit is a complete
  thought, **declare done** (`mvi_claimed`). That declaration is the handoff trigger, not a
  verdict. Commit the passing state (this is `writer_sha`). Declare `load_bearing` choices so the
  editor knows what looks cuttable but isn't.

- **Escalation + revert (the only branch):** if the editor wants to cut a `load_bearing` item, or
  an edit can't keep tests green, it does **not** silently override. Revert is mechanical: the
  writer committed its passing state (`writer_sha`), so the orchestrator restores it with
  `git reset --hard <writer_sha>` (or `git checkout <writer_sha> -- <files_touched>`) and records
  the disagreement in `edits`. Without that commit there is nothing to revert to: the snapshot
  is what makes "keep the writer's version" executable at all.

- **Reviewer Concerns (persist the disagreement, don't loop on it):** the pipeline is one-way by
  design — it never hands work back for another round, which is what keeps it from thrashing. The
  cost of that is a real critique the editor *can't* act on this pass (it would break green, hit a
  `load_bearing` item, or falls outside the unit) would simply vanish on revert. So the editor
  records each such critique in `unresolved_concerns` — the concern (quoting what it's about), why
  it couldn't be resolved (`breaks_green` | `load_bearing` | `out_of_unit_scope`), and the smallest
  follow-up that would — and writes them to `reviewer-concerns.md` in the run directory. This is the
  same move gstack's plan-review loop makes when a writer/editor pair deadlocks: stop looping,
  persist the unresolved issue into the artifact so a human (or the next unit) sees it. It keeps the
  loop one-way without throwing away the second agent's most valuable output.

### 4. Config: `implementation_loop.toml`

Follows the `scopes.toml` + `ScopeConfig` pattern: same `[table]` shape, same
tomllib/tomli loader, same resolution chain (CLI flag → `.studio/` override → shipped default).
`LoopConfig` + `load_loop_config()` live in `studio/impl_loop.py`, co-located like
`ScopeConfig`/`load_scopes_config()` in `scopes.py`.

Below is **everything a repo may set**, not what ships. Studio ships `[loop]` and `[editor]`
only; the `[gate]` commands are detected from the repo's own stack (`impl_loop.STACK_MARKERS` →
`resolve_profile`), so a Python repo gets `pytest -q` + `ruff` + `mutmut run`, a Node repo with a
`test` script gets `npm test`, and a repo Studio can't identify — or one matching two stacks at
once — is refused at load with the file and the lines to write.

Two things about the file itself. A `[gate]` table in a project file merges **over** the detected
profile, so setting only `test_command` leaves the rest as the stack's rather than another
language's. `/studio-setup` writes that project file with the detected commands (and leaves an
existing one untouched), so what the gate runs is visible and editable rather than implied. And a
project file is read **instead of** the shipped one, never merged with it — so copy over any
`[loop]`/`[editor]` value you want to keep. Those two tables match the dataclass
defaults exactly, which is the only reason that shadowing is harmless; `test_impl_loop.py` holds
them to it.

```toml
[loop]
deliver_on_gate_fail = true   # if the writer can't reach green, deliver flagged (uncommitted) rather than spin

[gate]                             # detected per repo; set these only to override the detection
test_command = "pytest -q"       # what runs the unit-scoped tests here (a Node repo: "npm test")
static_checks = ["ruff check {paths}"]  # the lint commands to run; {paths} = the unit's paths, [] skips
require_mutation_check = true    # writer runs the mutation check on the touched code and reports it
mutation_command = "mutmut run"  # the tool that check runs (scope/runner in setup.cfg)

[editor]
mandate = "contrarian"        # reuse CONTRARIAN_MANDATE; "off" disables the editor pass
read_scope = "touched+importers"  # bound the editor's reads: diff + files_touched + direct importers
output_budget = 400           # word cap on the editor's rationale (matches scope output budgets)
```

Notes on what was cut vs the first draft:

- **`max_unit_iterations` removed.** The pipeline is one-way with a single revert branch; there is
  at most one editor pass, so the knob could only ever be 1: configurability for a loop the
  design forbids.
- **`test_command` is now the single source of truth for running tests.** The first draft also had
  `validator_checks = ["pytest", ...]`, duplicating the test run and implying `CodeValidator`
  consumes `test_command` (it does not: `run_pytest` hardcodes `pytest -v` + a path). Tests run
  via `test_command`; `static_checks` holds the lint/static commands only — commands, not tool
  names, so a leftover `"ruff"` is refused at load with the line to write instead.
- **`read_scope` added** because the real cost driver is the editor's *input* context, and the
  only prior knob (`output_budget`) caps *output*. Bounding reads is also what makes the
  cadence-lab token numbers meaningful.
- **`deliver_on_gate_fail`** must leave red code **uncommitted** and tag the failure in the unit's
  `impl--unit_NN--*.json` record, so a delivered-but-failing unit is never mistaken for a passing
  one. One exception: a deliberate escalation commits its partial work as `writer(stuck): <unit_id>`,
  because `writer_sha` is required and there is nothing honest to put in it otherwise. The rule's
  intent survives — that label, plus `mvi_claimed: false` and the blocker in `stuck`, means nobody
  mistakes it for a passing unit — and committing keeps the tree clean between units. Note `tests` is
  *not* part of that signal: an escalating writer reports whatever the suite actually did, including a
  green result it never got to influence, because `stuck` is what says it was blocked.

## The executor shell (Claude-specific, disposable)

A thin Claude Code Workflow script: **orchestration only**. Every prompt, gate criterion, and
parameter is read from the config above; nothing about the loop's logic is hardcoded. Per MVI
unit:

```js
writer = agent(writer_prompt(unit, config), { schema: HANDOFF })   // build unit; commit passing state -> writer_sha
if (gate(writer)) {                                                 // tests green + static check + attested MVI/mutation
  editor = agent(editor_prompt(writer, CONTRARIAN_MANDATE),         // diff writer_sha.., apply edits, re-run tests
                 { schema: HANDOFF })
  if (!gate(editor)) revertTo(writer.writer_sha)                    // edit broke green / hit load_bearing -> reset
}
runFullSuite()                                                      // delivery-time check
deliver(unit)                                                       // if gate failed: leave uncommitted + flag
```

- The handoff is passed **in-memory** between stages. Running tests, `git commit`, `git diff
  <writer_sha>..`, and the revert are delegated to the agents' / orchestrator's Bash tool (the
  workflow script is pure JS).
- Each unit's final handoff object is written to the run directory as
  `impl--unit_NN--writer.json` / `impl--unit_NN--editor.json`, matching the existing artifact
  naming convention (`advocate--<role>--NN.md`).

A native workflow's edge over an honor-system executor is **enforcement** (the gate provably
fires), not token savings. The cost is that enforcement only holds while the workflow is the
executor; that trade is acceptable because the workflow is also where the cadence gets tuned.

**Portability:** the config, handoff, mandates, and tuned cadence are plain data, so a port to
another runtime (LangGraph, Google ADK, OpenAI Agents SDK) rewrites only the ~40-line
orchestration shell; those frameworks all express the same "sequential stages + conditional
branch + shared state" shape.

### Building in a git worktree (`--work-dir`)

Every git command the loop runs is a line of text inside an agent's prompt, so it executes wherever
that agent's shell is standing — by default, the checkout you invoked `/forge` from, on whatever
branch that checkout has open. `/forge --work-dir <path>` puts a `work_dir` on the unit, and the
workflow does two things with it: both agent prompts open with an instruction to `cd` into that
directory and keep everything there, and every git command inside them renders as `git -C "<path>"`.

**The `cd` is the mechanism; the pinned git is only a backstop.** The test command, the static check
and the mutation run are not git commands, so `git -C` never reaches them. Pinning git alone would
have been worse than doing nothing: the agent would commit to the correct branch and then report
green tests describing a different tree. One `cd` at the top covers all of them, including whatever
gets added later.

**The path is validated before the loop starts.** `/forge` resolves and checks it in Step 3, before
a single agent spawns, and stops the run naming which of four reasons it hit: `missing` (nothing at
that path), `not-a-worktree` (a directory that exists but isn't inside a git worktree),
`different-repo` (a worktree of some other repository), or `unquotable` (a path holding a character
outside the set the prompts can safely render into `git -C "<path>"`). The accepted set is the rule:
letters, digits, and `/ . _ - ~` or a space, so a character nobody anticipated is refused rather than
waved through — at the price of refusing legitimate paths with a `+`, a `(` or an accent in them.
Checking first is what
makes the flag worth reaching for — a typo'd path costs nothing, instead of failing an hour in with
both agents already run.

**What it does not do.** It reduces the blast radius of a run pointed at the wrong directory; it
cannot make that impossible. Every one of these instructions is prompt text an agent may ignore, and
the validation is one shot at the start while the agents work for an hour. A test can prove the
prompt *says* `cd`; only watching a live run tells you the agent did it.

With no `--work-dir` the key is absent, the `cd` lines aren't rendered, and git stays bare — every
run that doesn't ask for this is unchanged.

## Success / kill metric

The cadence lab needs a terminating verdict, or it runs forever and the feature has no measurable
outcome. Before tuning anything, capture a **no-editor baseline** (writer-only) so cut-per-token
has something to compare against. Then the editor pass earns its place only if, across a sample of
units, it delivers:

- **≥ one substantive simplification per unit** (a real cut/merge/restructure, not cosmetic), or a
  measurable reduction in delivered LOC / duplication over baseline, **and**
- at an editor-pass token cost **≤ ~50% of the writer pass** (tunable, but a stated ceiling).

Below that bar, the editor defaults to `mandate = "off"`: the loop ships dormant rather than
doubling per-unit cost for marginal gain. This is the kill switch.

## Cadence lab

The one parameter that needs empirical tuning rather than design is **gate granularity**: editor
pass per *MVI unit* (the default), per *file*, or per *feature*. Run real work through the
executor and watch:

1. **Cut-per-token** at each granularity (the success-metric numerator over editor token cost).
   Too little cut → the cadence is too fine and the re-read isn't earning its keep.
2. Whether `read_scope` is capturing enough context to edit safely without ballooning input.

Lock the granularity that maximizes cut-per-token into `implementation_loop.toml`. Because that
value lives in config, the tuning result survives any later port.

## Build phases

Each phase must end in something usable (the feature's own MVI rule applies to its build). Each is
gated on reviewing the one before it.

1. ✅ **Runnable loop on one unit**: the Claude Workflow shell + gate glue (run `test_command`,
   `ruff`, writer commit + revert), driving a real MVI unit end-to-end. *Done*. The loop built its
   own config loader as the first real run.
2. ✅ **Extract config + harden**: `studio/config/implementation_loop.toml` + `studio/impl_loop.py`
   (`LoopConfig` + `load_loop_config()`), patterned on `scopes.py`, with loader tests. Plus
   `runtime_knobs()`, read by running the module as a script, so the workflow consumes the config, and the
   `/forge` command. *Done.*
3. ⏳ **Cadence lab**: capture the no-editor baseline, run real units, tune granularity against the
   success/kill metric, write the result back into config. *Pending*. Only ~2 data points so far.

The documentation contract is satisfied: `CLAUDE.md` (Architecture + Implementation Loop section)
and `CLAUDE_CODE_USAGE.md` (`/forge` section) document the shipped loop.

> **Implementation gotchas** (cost three no-op runs to find; documented in
> `.claude/commands/forge.md`): `Workflow({name})` resolves a *frozen registry snapshot*
> and ignores on-disk edits, so invoke by `scriptPath`; and the Workflow `args` arrive as a *JSON
> string*, not an object, so the workflow `JSON.parse`s them.

## Refinement log

One Product + Engineering role iteration applied to the first draft:

- **Eng (P0):** defined the revert mechanism (writer commit → `writer_sha` → `git reset`), which
  was previously non-executable; added `writer_sha` to the handoff as the diff base + unit
  boundary + revert point.
- **Product (P0):** reordered build phases so the first milestone is a runnable loop, not a
  config-only artifact that violates MVI.
- **Product (P0):** added the Success / kill metric + no-editor baseline so the cadence lab can
  terminate.
- **Both:** relabeled the gate into machine-enforced vs agent-attested (mutation/MVI are attested,
  not enforced). Split the gate into an **entry** moment (writer *declares done* + machine checks →
  triggers the editor) and an **exit** moment (editor's authoritative `mvi_verdict` can overturn
  the writer's claim), so the writer hands off without having to "define MVI" itself.
- **Both / Simplicity:** cut mypy from the gate, cut `max_unit_iterations`, removed the
  `test_command`/`validator_checks` redundancy, dropped `behavior_preserved`, trimmed the
  three-framework portability table to one sentence.
- **Eng (P1):** added `read_scope` to bound the editor's input context (the real cost driver);
  `deliver_on_gate_fail` must leave red code uncommitted + flagged.

## References

- `studio/scopes.py:27`: `CONTRARIAN_MANDATE` (the editor mandate, reused verbatim).
- `studio/validators/code_validator.py`: `CodeValidator.validate_implementation()` returns
  `List[CheckResult]`; `run_pytest` is `pytest -v` + path, `run_ruff` is `ruff check .`,
  `run_mypy` is `mypy . --strict`. Gate reuses the runner + ruff/pytest; aggregation is net-new.
- `studio/scopes.py`: `ScopeConfig` / `load_scopes_config()` (the config pattern to mirror).
- `studio/persona_overrides.py`, `studio/role_overrides.py`: the shallow-merge override pattern
  for prompts-as-data.
- `MVI_METHODOLOGY.md`, `AI_TDD_METHODOLOGY.md`, `TEST_DRIVEN_GUIDE.md`: the gate criteria.
