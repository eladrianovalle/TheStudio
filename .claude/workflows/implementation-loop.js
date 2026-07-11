export const meta = {
  name: 'implementation-loop',
  description: 'Writer/editor implementation loop — one agent builds an MVI unit, a fresh editor cuts/refines it, gated on tests-green. See studio/docs/IMPLEMENTATION_LOOP_SPEC.md',
  whenToUse: 'Build a single MVI unit with a structurally-guaranteed contrarian-editor pass. Pass the unit via args; defaults to building studio/impl_loop.py (the spec\'s own Phase 2).',
  phases: [
    { title: 'Writer', detail: 'build one complete MVI unit; commit passing state; declare done' },
    { title: 'Edit', detail: 'fresh editor cuts/refines against writer_sha; revert if it breaks green' },
  ],
}

// ---------------------------------------------------------------------------
// Default target unit = Phase 2 of the spec: the config loader, dogfooded.
// Override by passing `args` (same shape) to the Workflow tool.
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
    '    require_mutation_check, mandate, read_scope, output_budget).',
    '  - `load_loop_config(path)` using the tomllib/tomli fallback already used in scopes.py / cleanup.py.',
    '  - resolution chain: explicit path -> .studio/implementation_loop.toml -> config/implementation_loop.toml -> defaults.',
    'Ship config/implementation_loop.toml as the shipped default (copy the §4 example from the spec).',
    'Write tests in studio/tests/test_impl_loop.py: valid file parses; missing file -> defaults;',
    '  malformed TOML -> clear error; .studio override beats shipped default. Mirror the scopes loader tests.',
    'This is one complete MVI unit: when done, Studio can actually load the loop config end-to-end.',
  ].join('\n'),
}

const runDir = (u) => `.studio/output/impl_loop/${u.unit_id}`

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
    stage: { type: 'string', enum: ['editor'] },
  },
}

// ---------------------------------------------------------------------------
// Prompts. The script is orchestration only — all behavior lives in these
// strings + the gate logic below, so a port rewrites only this shell.
// ---------------------------------------------------------------------------
function writerPrompt(u) {
  return [
    `You are the WRITER in an implementation writer/editor loop. Build ONE complete MVI unit, then declare done.`,
    ``,
    `UNIT: ${u.title}`,
    ``,
    u.instructions,
    ``,
    `Discipline:`,
    `- Build a usable interaction, not a partial component (MVI). No speculative scope beyond the unit.`,
    `- Hold AI-TDD: write the tests and run them.${u.require_mutation_check === false ? ' (Mutation check disabled by config: require_mutation_check=false.)' : ` Then run the configured mutation check on the code you touched: \`${u.mutation_command}\` (scope + runner live in studio/setup.cfg), and report the outcome in mutation_check. If mutmut isn't installed, fall back to hand-mutating — break 2-3 critical assertions, confirm the tests FAIL, then restore.`}`,
    `- Run the unit tests: \`${u.test_command}\`${(Array.isArray(u.static_checks) && u.static_checks.length === 0) ? ' (static check skipped — config static_checks=[]).' : `  and the static check: \`${u.static_check}\`.`}`,
    `- When (and only when) tests pass, COMMIT the passing state on the current branch`,
    `  (\`git add -A && git commit -m "writer: ${u.unit_id}"\`) and capture the short SHA — that is writer_sha.`,
    `- Persist your handoff: \`mkdir -p ${runDir(u)}\` then write it to ${runDir(u)}/impl--${u.unit_id}--writer.json.`,
    `- Set mvi_claimed=true ONLY if you believe the unit is a complete, usable thought. This is a trigger you`,
    `  pull, not a verdict — the editor renders the authoritative MVI verdict next.`,
    `- List anything load_bearing (looks cuttable but is not, with the reason).`,
    `Return the writer handoff object.`,
  ].join('\n')
}

function editorPrompt(u, writer) {
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
    `Then render mvi_verdict: AUTHORITATIVELY judge "if we stopped here, could someone use this unit?" against`,
    `the title "${u.title}". This can overturn the writer's claim.`,
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
const entryGate = !!(writer && writer.mvi_claimed && writer.tests && writer.tests.passed && (!staticRequired || writer.static_ok !== false))
if (!writer) {
  log('Writer agent failed to return a handoff — aborting.')
  return { delivered: false, reason: 'writer_failed' }
}
if (!entryGate) {
  // deliver_on_gate_fail: do not spin. Leave the writer's state, flag it.
  log(`Entry gate failed (mvi_claimed=${writer.mvi_claimed}, tests.passed=${writer.tests?.passed}). Delivering flagged, no editor pass.`)
  return { delivered: true, flagged: true, editorRan: false, writer }
}

// Config knob (editor.mandate="off" → editor_enabled=false, merged into args by /forge):
// skip the editor pass entirely and deliver the writer's version.
if (unit.editor_enabled === false) {
  log(`editor_enabled=false (mandate off) — delivering the writer's version, no editor pass.`)
  return { delivered: true, flagged: false, editorRan: false, finalVersion: 'writer', writer }
}

phase('Edit')
const editor = await agent(editorPrompt(unit, writer), { schema: EDITOR_HANDOFF, label: `editor:${unit.unit_id}`, phase: 'Edit', model: unit.model })

// Exit gate — edit must hold (tests green) AND authoritative MVI verdict.
const editHeld = !!(editor && editor.tests && editor.tests.passed && !editor.reverted)
const exitGate = !!(editor && editor.tests && editor.tests.passed && editor.mvi_verdict)

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

log(`Done. editorRan=${!!editor} editHeld=${editHeld} mvi_verdict=${editor?.mvi_verdict} reverted=${editor?.reverted} committed=${editor?.committed}`)
return {
  delivered: true,
  flagged: !exitGate,                // delivered, but editor couldn't confirm a usable green unit
  editorRan: true,
  finalVersion: editHeld ? 'editor' : 'writer',
  writer,
  editor,
}
