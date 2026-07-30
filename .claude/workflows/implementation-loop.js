export const meta = {
  name: 'implementation-loop',
  description: 'Writer/editor implementation loop — one agent builds an MVI unit, a fresh editor cuts/refines it, gated on tests-green. See studio/docs/IMPLEMENTATION_LOOP_SPEC.md',
  whenToUse: 'Build a single MVI unit with a structurally-guaranteed contrarian-editor pass. Always pass the unit via args — /forge does this for you. The built-in fallback unit is a historical example that has already shipped, so a no-args run would rebuild existing code.',
  phases: [
    { title: 'Writer', detail: 'build one complete MVI unit; commit passing state; declare done' },
    { title: 'Edit', detail: 'fresh editor cuts/refines against writer_sha; revert if it breaks green' },
  ],
}

// ---------------------------------------------------------------------------
// Fallback unit, kept as the worked example of the args shape. It describes Phase 2 of the
// spec — the config loader — which SHIPPED on 2026-06-28, so running the loop without `args`
// would set a writer to rebuild studio/impl_loop.py. Always pass `args` (same shape); /forge
// always does.
// ---------------------------------------------------------------------------
const DEFAULT_UNIT = {
  unit_id: 'unit_impl_loop_config',
  // Optional model override for the writer + editor agents (e.g. 'fable', 'sonnet',
  // 'opus'). Passed straight to agent()'s `model` opt; undefined inherits the
  // session model (the prior behavior), so this is a no-op unless callers set it.
  model: undefined,
  title: 'Studio can load implementation_loop.toml into a LoopConfig (with project-local override)',
  // Run from repo root; tests live under studio/.
  test_command: 'cd studio && python -m pytest tests/test_impl_loop.py -q',
  static_check: 'cd studio && ruff check impl_loop.py',
  mutation_command: 'cd studio && mutmut run',
  instructions: [
    'Build studio/impl_loop.py mirroring the ScopeConfig / load_scopes_config() pattern in studio/scopes.py:',
    '  - a `LoopConfig` dataclass for the [loop]/[gate]/[editor] tables documented in',
    '    studio/docs/IMPLEMENTATION_LOOP_SPEC.md §4 (deliver_on_gate_fail, test_command, static_checks,',
    '    require_mutation_check, mutation_command, mandate, read_scope, output_budget).',
    '  - `load_loop_config(path)` using the tomllib/tomli fallback already used in scopes.py / cleanup.py.',
    '  - resolution chain: explicit path -> .studio/implementation_loop.toml -> config/implementation_loop.toml -> defaults.',
    'Ship config/implementation_loop.toml as the shipped default (copy the §4 example from the spec).',
    'Write tests in studio/tests/test_impl_loop.py: valid file parses; missing file -> defaults;',
    '  malformed TOML -> clear error; .studio override beats shipped default. Mirror the scopes loader tests.',
    'This is one complete MVI unit: when done, Studio can actually load the loop config end-to-end.',
  ].join('\n'),
  // Checkable acceptance criteria for this unit, copied verbatim from the approved spec's Build
  // Plan by /forge --spec. Empty on a spec-less run: the editor then judges against the title, as
  // it always did.
  acceptance_criteria: [],
}

const runDir = (u) => `.studio/output/impl_loop/${u.unit_id}`

// The one place acceptance criteria are read, so both prompts see the same list and a malformed
// `args` payload degrades to "no criteria" instead of injecting junk into a prompt.
function unitCriteria(u) {
  if (!u || !Array.isArray(u.acceptance_criteria)) return []
  return u.acceptance_criteria.filter((c) => typeof c === 'string' && c.trim())
}

// ---------------------------------------------------------------------------
// Handoff schemas — the portable baton (spec §1). Plain, serializable fields.
// ---------------------------------------------------------------------------
const WRITER_HANDOFF = {
  type: 'object',
  required: ['unit_id', 'writer_sha', 'files_touched', 'tests', 'mvi_claimed', 'stage'],
  additionalProperties: false,
  properties: {
    unit_id: { type: 'string' },
    title: { type: 'string' },
    writer_sha: { type: 'string', description: 'commit of the writer\'s passing state — diff base + revert point' },
    files_touched: { type: 'array', items: { type: 'string' } },
    tests: {
      type: 'object',
      required: ['command', 'passed', 'exit_code'],
      additionalProperties: false,
      properties: {
        command: { type: 'string' },
        passed: { type: 'boolean' },
        exit_code: { type: 'integer' },
      },
    },
    static_ok: { type: 'boolean', description: 'ruff (or configured static check) clean' },
    mvi_claimed: { type: 'boolean', description: 'writer\'s DECLARATION it finished a complete thought — a trigger, not a verdict' },
    mutation_check: {
      type: 'object',
      additionalProperties: false,
      properties: {
        performed: { type: 'boolean' },
        assertions_broken: { type: 'integer' },
        caught: { type: 'boolean' },
      },
    },
    load_bearing: { type: 'array', items: { type: 'string' }, description: 'looks cuttable but is not — off-limits to the editor without escalation' },
    stuck: { type: 'string', description: 'set ONLY when the writer stopped deliberately: the specific blocker, quoting the file/test/interface it is about. Absent on a normal run.' },
    stage: { type: 'string', enum: ['writer'] },
  },
}

const EDITOR_HANDOFF = {
  type: 'object',
  required: ['unit_id', 'tests', 'mvi_verdict', 'edits', 'reverted', 'committed', 'stage'],
  additionalProperties: false,
  properties: {
    unit_id: { type: 'string' },
    files_touched: { type: 'array', items: { type: 'string' } },
    committed: { type: 'boolean', description: 'true if the editor committed its kept edits; false if it reverted (writer_sha already holds the state)' },
    tests: {
      type: 'object',
      required: ['command', 'passed', 'exit_code'],
      additionalProperties: false,
      properties: {
        command: { type: 'string' },
        passed: { type: 'boolean' },
        exit_code: { type: 'integer' },
      },
    },
    mvi_verdict: { type: 'boolean', description: 'AUTHORITATIVE: could someone use this unit? Overturns writer.mvi_claimed.' },
    edits: { type: 'string', description: 'what was cut / merged / renamed, and what (if anything) was lost' },
    reverted: { type: 'boolean', description: 'true if the editor reset to writer_sha because an edit broke green or hit a load_bearing item' },
    // Reviewer Concerns — the third path between "edit it" and "silently drop it". A real problem the
    // editor spotted but could NOT resolve within the tests-green + load_bearing + read-scope bounds.
    // The loop is one-way (no re-run debate), so without this the critique evaporates on revert. Persisted
    // so it surfaces to the human / the next unit instead of being lost.
    unresolved_concerns: {
      type: 'array',
      description: 'problems the editor could not safely act on this pass; empty if none',
      items: {
        type: 'object',
        required: ['concern', 'why_unresolved'],
        additionalProperties: false,
        properties: {
          concern: { type: 'string', description: 'the specific problem, quoting the thing it is about' },
          why_unresolved: { type: 'string', enum: ['breaks_green', 'load_bearing', 'out_of_unit_scope'], description: 'why it could not be fixed in this pass' },
          suggested_followup: { type: 'string', description: 'the smallest next step that would resolve it' },
        },
      },
    },
    // One grade per acceptance criterion the unit carried. Optional like unresolved_concerns: a
    // spec-less run has no criteria to grade, so an absent field is normal, not a failure.
    criteria_verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['criterion', 'verdict', 'evidence'],
        additionalProperties: false,
        properties: {
          criterion: { type: 'string', description: 'the criterion, verbatim from the spec' },
          verdict: { type: 'string', enum: ['pass', 'fail', 'unverifiable'] },
          evidence: { type: 'string', description: 'what was actually checked — a test and its result, a file:line, a command run; or why it could not be checked' },
        },
      },
    },
    stage: { type: 'string', enum: ['editor'] },
  },
}

// ---------------------------------------------------------------------------
// Prompts. The script is orchestration only — all behavior lives in these
// strings + the gate logic below, so a port rewrites only this shell.
// ---------------------------------------------------------------------------
function writerPrompt(u) {
  const criteria = unitCriteria(u)
  return [
    `You are the WRITER in an implementation writer/editor loop. Build ONE complete MVI unit, then declare done.`,
    ``,
    `UNIT: ${u.title}`,
    ``,
    u.instructions,
    ...(criteria.length ? [
      ``,
      `ACCEPTANCE CRITERIA — the definition of done for this unit, from the approved spec:`,
      ...criteria.map((c, i) => `  ${i + 1}. ${c}`),
      `The editor will judge each of these against the running code, one by one. Build so each is true,`,
      `and cover them in the tests you write.`,
    ] : []),
    ``,
    `Discipline:`,
    `- Build a usable interaction, not a partial component (MVI). No speculative scope beyond the unit.`,
    `- Hold AI-TDD: write the tests and run them.${u.require_mutation_check === false ? ' (Mutation check disabled by config: require_mutation_check=false.)' : ` Then run the configured mutation check on the code you touched: \`${u.mutation_command}\` (scope + runner live in studio/setup.cfg), and report the outcome in mutation_check. If mutmut isn't installed, fall back to hand-mutating — break 2-3 critical assertions, confirm the tests FAIL, then restore.`}`,
    `- Run the unit tests: \`${u.test_command}\`${(Array.isArray(u.static_checks) && u.static_checks.length === 0) ? ' (static check skipped — config static_checks=[]).' : `  and the static check: \`${u.static_check}\`.`}`,
    `- When (and only when) tests pass, COMMIT the passing state on the current branch (one exception: escalation, below).`,
    `  (\`git add -A && git commit -m "writer: ${u.unit_id}"\`) and capture the short SHA — that is writer_sha.`,
    `- Persist your handoff: \`mkdir -p ${runDir(u)}\` then write it to ${runDir(u)}/impl--${u.unit_id}--writer.json.`,
    `- Set mvi_claimed=true ONLY if you believe the unit is a complete, usable thought. This is a trigger you`,
    `  pull, not a verdict — the editor renders the authoritative MVI verdict next.`,
    `- List anything load_bearing (looks cuttable but is not, with the reason).`,
    `- It is always OK to stop and say this is too hard for me. Bad work is worse than no work, and you will`,
    `  NOT be penalized for escalating. What IS penalized is faking done: weakening a test to get green,`,
    `  stubbing a function you could not write, or claiming a complete thought you know is a fragment.`,
    `- Escalate on the trigger, not the feeling. STOP when you notice any of: you have read file after file`,
    `  without getting closer to a change you can actually make; you cannot make the tests pass without`,
    `  changing what the unit is supposed to mean; a dependency, interface, or file this unit needs does not`,
    `  exist or contradicts the instructions; you are about to weaken, skip, or delete a test to get to green.`,
    `- To escalate: commit what you have with \`git add -A && git commit --allow-empty -m "writer(stuck): ${u.unit_id}"\``,
    `  and report that short SHA as writer_sha. If you never got as far as running the tests, run \`${u.test_command}\``,
    `  once so \`tests\` holds a real result. Report \`tests\` as what actually happened — the real exit code, and`,
    `  \`passed\` matching it, even when a suite you never got to influence comes back green. Do NOT report a red`,
    `  suite to signal that you are stuck; \`stuck\` is what says that. Set mvi_claimed=false, and put the blocker`,
    `  in \`stuck\` — the specific thing you got stuck on, quoting the file, test, or interface it is about.`,
    `  Persist the handoff JSON either way.`,
    `Return the writer handoff object.`,
  ].join('\n')
}

function editorPrompt(u, writer) {
  const criteria = unitCriteria(u)
  return [
    `You are the EDITOR in an implementation writer/editor loop — a fresh agent reviewing the writer's unit.`,
    ``,
    `Your mandate IS the CONTRARIAN_MANDATE defined in scopes.py — read it at \`.studio/source/scopes.py\``,
    `(installed repos) or \`studio/scopes.py\` (the Studio source repo), and adopt it: applied to code,`,
    `default to deletion, name the specific cut, collapse don't accumulate, guard the essence.`,
    ``,
    `Scope of review: \`git diff ${writer.writer_sha}..\` — these are the writer's changes. Read the touched`,
    `files (${(writer.files_touched || []).join(', ') || 'see the diff'})${u.read_scope === 'touched' ? '' : ' and their direct importers'}.`,
    `Do not wander beyond that read scope.`,
    ``,
    `Hard bounds:`,
    `- BEHAVIOR PRESERVATION: you may restructure and delete freely ONLY as long as the unit's tests stay green.`,
    `  After editing, re-run: \`${u.test_command}\`.`,
    `- Do NOT remove a load_bearing item (${JSON.stringify(writer.load_bearing || [])}) without escalating.`,
    `- If an edit breaks tests, or you must touch a load_bearing item, REVERT: \`git reset --hard ${writer.writer_sha}\``,
    `  and set reverted=true. Never deliver red code from an edit.`,
    ``,
    `Reviewer Concerns — the third path. When you spot a REAL problem you cannot safely fix in this pass —`,
    `an edit that would break green, a load_bearing item you'd need to touch, or something genuinely wrong that`,
    `sits outside this unit's scope — do NOT force a breaking edit and do NOT let the concern evaporate on a`,
    `revert. Record it in unresolved_concerns: the concern (quote the thing it's about), why_unresolved`,
    `(breaks_green | load_bearing | out_of_unit_scope), and the smallest suggested_followup that would resolve`,
    `it. This loop does not hand work back and forth, so this list is the ONLY place a valid-but-unactionable`,
    `critique survives. Leave it empty if there is genuinely nothing. If it is non-empty, also write it as a`,
    `readable checklist to ${runDir(u)}/reviewer-concerns.md (one item per section: concern, why, follow-up).`,
    ``,
    ...(criteria.length ? [
      `Then render the verdict against the ACCEPTANCE CRITERIA from the approved spec — the definition of`,
      `done for this unit:`,
      ...criteria.map((c, i) => `  ${i + 1}. ${c}`),
      ``,
      `For EACH criterion, decide pass, fail, or unverifiable, and record it in criteria_verdicts: the`,
      `criterion verbatim, the verdict, and the evidence you actually checked (a test name and its result,`,
      `a file:line you read, or a command you ran). Use unverifiable when the criterion cannot be checked`,
      `from the diff and the unit's tests — you have no browser and no Play mode — and say in evidence why.`,
      `Ignore what the writer's handoff, the commit message, or the comments SAY the unit does — only the`,
      `criteria and the running code count. A test that merely restates a criterion's wording is not`,
      `evidence the criterion holds: check it against what the code does, not what a test is named.`,
      `Set mvi_verdict=true only if the unit is usable as a complete interaction AND every criterion passes.`,
      `This can overturn the writer's claim.`,
    ] : [
      `Then render mvi_verdict: AUTHORITATIVELY judge "if we stopped here, could someone use this unit?" against`,
      `the title "${u.title}" (no acceptance criteria were supplied — this run had no --spec pointer). Leave`,
      `criteria_verdicts empty. This can overturn the writer's claim.`,
    ]),
    ``,
    `Keep your edits rationale under ${u.output_budget || 400} words.`,
    `Deliver: if you KEPT your edits (tests green, not reverted), commit them — \`git commit -am "editor: ${u.unit_id}"\``,
    `— and set committed=true. If you reverted, do NOT commit (writer_sha already holds the delivered state); set committed=false.`,
    `Persist your handoff to ${runDir(u)}/impl--${u.unit_id}--editor.json, and return the editor handoff object.`,
  ].join('\n')
}

// ---------------------------------------------------------------------------
// Orchestration: writer -> entry gate -> editor -> exit gate (revert) -> deliver
// ---------------------------------------------------------------------------
// Merge any provided args over the default unit field-by-field: provided keys win,
// unspecified keys fall back to DEFAULT_UNIT (so partial args are safe). The log
// makes the resolved unit visible — if args didn't arrive, this shows the default.
// NOTE: args arrives as a JSON-encoded STRING (the runtime serializes it when forwarding),
// not a parsed object — normalize before merging, else everything falls back to DEFAULT_UNIT.
let parsedArgs = args
if (typeof parsedArgs === 'string') {
  try { parsedArgs = JSON.parse(parsedArgs) } catch { parsedArgs = {} }
}
const overrides = (parsedArgs && typeof parsedArgs === 'object' && !Array.isArray(parsedArgs)) ? parsedArgs : {}
const unit = { ...DEFAULT_UNIT, ...overrides }
log(`Unit: ${unit.unit_id} — ${unit.title}`)

phase('Writer')
const writer = await agent(writerPrompt(unit), { schema: WRITER_HANDOFF, label: `writer:${unit.unit_id}`, phase: 'Writer', model: unit.model })

// Entry gate — purely mechanical: writer declared done AND machine checks pass.
// NOTE the static-check duality: `static_checks` (config array) gates WHETHER static checking is
// required; `static_check` (per-unit command string, used in writerPrompt) is WHAT runs. They
// travel together today. If the schema ever consolidates on the array, drive the command off it
// here and in writerPrompt too, so the two don't drift.
const staticRequired = !(Array.isArray(unit.static_checks) && unit.static_checks.length === 0)

// NOTE: named function, not an inline expression, so the JS shell tests can load and exercise it.
// The gate is the only load-bearing branch here and its two subtleties — `static_ok !== false`
// (absent is fine, explicit false is not) and the `!staticRequired ||` short-circuit — had no
// coverage at all before this.
//
// It takes no null check on `writer` because it is only ever called below the abort that handles a
// missing one. `writer.tests` is still guarded: the schema requires that field, but a guard costs
// nothing and a missing one would read as a passing gate rather than a crash.
function passesEntryGate(writer, staticRequired) {
  return !!(writer.mvi_claimed && writer.tests && writer.tests.passed && (!staticRequired || writer.static_ok !== false))
}

if (!writer) {
  log('Writer agent failed to return a handoff — aborting.')
  return { delivered: false, reason: 'writer_failed' }
}
// Computed below the abort, so `writer` is known to exist by here. Moving this line back above the
// abort reintroduces the null case, and the entry-gate ordering test is what says so.
const entryGate = passesEntryGate(writer, staticRequired)
// A stuck writer stopped on purpose; that reads differently from a crash or a red test, so say it
// out loud in the transcript — and say it whichever way the gate falls.
if (writer.stuck) {
  log(`Writer escalated (stopped deliberately): ${writer.stuck}`)
}
if (!entryGate) {
  // deliver_on_gate_fail: do not spin. Leave the writer's state, flag it.
  log(`Entry gate failed (mvi_claimed=${writer.mvi_claimed}, tests.passed=${writer.tests?.passed}). Delivering flagged, no editor pass.`)
  return { delivered: true, flagged: true, editorRan: false, writer }
}

// Config knob (editor.mandate="off" → editor_enabled=false, merged into args by /forge):
// skip the editor pass entirely and deliver the writer's version.
//
// A unit that carried criteria is the exception, and it ships FLAGGED. With no editor there is
// nobody to grade them, so `flagged: false` would report a clean unit for a run that was explicitly
// asked to check something and checked nothing. That is the silent downgrade to an ungraded run the
// spec refuses elsewhere — a mistyped `--spec` stops rather than quietly proceeding, and this is the
// same failure arriving through config instead of a typo. A run with no criteria keeps shipping
// unflagged: nothing was ever promised there, so nothing is being withheld.
if (unit.editor_enabled === false) {
  const promisedGrades = unitCriteria(unit).length > 0
  log(promisedGrades
    ? `editor_enabled=false (mandate off) but the unit carried ${unitCriteria(unit).length} acceptance criterion(a) — nobody graded them, so this ships FLAGGED. Turn the editor mandate on, or run without criteria.`
    : `editor_enabled=false (mandate off) — delivering the writer's version, no editor pass.`)
  return { delivered: true, flagged: promisedGrades, editorRan: false, finalVersion: 'writer', writer }
}

phase('Edit')
const editor = await agent(editorPrompt(unit, writer), { schema: EDITOR_HANDOFF, label: `editor:${unit.unit_id}`, phase: 'Edit', model: unit.model })

// Exit gate — tests green, authoritative MVI verdict, AND every acceptance criterion the unit
// carried confirmed by a matching pass. A revert does not fail the gate: writer_sha still holds a
// green, usable unit, so the reverted case ships the writer's version rather than flagging it.
// `editHeld` below only decides which version gets reported as final; it is not a gate input.
const editHeld = !!(editor && editor.tests && editor.tests.passed && !editor.reverted)

// One grade per acceptance criterion the unit carried — empty on a spec-less run, and empty rather
// than a crash if the editor returns something that isn't a list.
const criteriaVerdicts = (editor && Array.isArray(editor.criteria_verdicts)) ? editor.criteria_verdicts : []

// The criteria the gate could not confirm. Matching each criterion by its own text is what makes
// this a check rather than a count: three verdicts that all name the same easy criterion would pass
// a unit whose other two were never looked at. A pass also has to carry evidence, or the field the
// schema requires costs nothing to fill. Extra verdicts nobody asked for are ignored, not punished.
function unconfirmedCriteria(criteria, verdicts) {
  return criteria.filter((criterion) => {
    const graded = verdicts.filter((entry) =>
      entry && typeof entry.criterion === 'string' && entry.criterion.trim() === criterion.trim())
    if (!graded.length) return true
    return !graded.every((entry) =>
      entry.verdict === 'pass' && typeof entry.evidence === 'string' && entry.evidence.trim())
  })
}

// NOTE: a named function, not an inline expression, so the JS shell tests can exercise the gate
// itself and not merely the rule it calls. That distinction is load-bearing — with the gate inline,
// neutralizing the criteria check left every test in both suites green.
function passesExitGate(editor, unconfirmed) {
  return !!(editor && editor.tests && editor.tests.passed && editor.mvi_verdict && !unconfirmed.length)
}

const criteria = unitCriteria(unit)
const unconfirmed = unconfirmedCriteria(criteria, criteriaVerdicts)
const exitGate = passesExitGate(editor, unconfirmed)

// Safety net: if the editor broke green but did not revert itself, force the revert.
if (editor && editor.tests && editor.tests.passed === false && !editor.reverted) {
  log(`Editor left red code without reverting — forcing reset to ${writer.writer_sha}.`)
  await agent(
    `Run \`git reset --hard ${writer.writer_sha}\` to restore the writer's passing state for ${unit.unit_id}, then confirm \`${unit.test_command}\` passes. Return a one-line confirmation.`,
    { label: `revert:${unit.unit_id}`, phase: 'Edit' },
  )
  // The tree is now back at writer_sha; reflect that in the payload so the log/return don't misreport.
  editor.reverted = true
}

// Safety net: if the editor kept its edits but didn't commit them, commit now so delivery is complete.
// NOTE: `git commit -am` stages only tracked, modified files — intentional. The editor's contract is to
// refine/cut EXISTING files; a new file is out-of-contract, so it's left uncommitted to surface (not
// silently swept in via `git add -A`). Widen this only if editors are ever allowed to create files.
if (editHeld && editor && !editor.committed) {
  log(`Editor kept edits but did not commit — committing now.`)
  await agent(
    `Run \`git commit -am "editor: ${unit.unit_id}"\` to commit the editor's kept changes for ${unit.unit_id}. If git reports nothing to commit, say so. Return a one-line confirmation.`,
    { label: `commit:${unit.unit_id}`, phase: 'Edit' },
  )
  // Reflect the safety-net commit in the payload.
  editor.committed = true
}

// Pure aggregation, extracted into a named function so the reviewerConcerns contract is
// unit-testable without running the workflow. The Workflow sandbox can't be imported (no fs/module
// access), so .claude/workflows/tests/workflow-shells.test.mjs loads THIS function from source and
// exercises it — the test drives the real code, not a copy.
function collectReviewerConcerns(editor) {
  return (editor && Array.isArray(editor.unresolved_concerns)) ? editor.unresolved_concerns : []
}
const reviewerConcerns = collectReviewerConcerns(editor)
if (reviewerConcerns.length) {
  log(`Editor logged ${reviewerConcerns.length} unresolved concern(s) → ${runDir(unit)}/reviewer-concerns.md`)
}
if (unconfirmed.length) {
  // Name them: this is the reason the unit ships flagged. Each verdict and its evidence ride out in
  // the payload, so the report can say whether a criterion failed, was ungradeable, or went ungraded.
  log(`Criteria not confirmed (${unconfirmed.length}/${criteria.length}): ${unconfirmed.join(' | ')}`)
}
log(`Done. editorRan=${!!editor} editHeld=${editHeld} mvi_verdict=${editor?.mvi_verdict} reverted=${editor?.reverted} committed=${editor?.committed} concerns=${reviewerConcerns.length} criteria=${criteriaVerdicts.length}`)
return {
  delivered: true,
  flagged: !exitGate,                // delivered, but editor couldn't confirm a usable green unit
  editorRan: true,
  finalVersion: editHeld ? 'editor' : 'writer',
  reviewerConcerns,                  // valid-but-unactionable critiques the one-way loop would otherwise lose
  criteriaVerdicts,                  // per-criterion grade + the evidence the editor checked
  writer,
  editor,
}
