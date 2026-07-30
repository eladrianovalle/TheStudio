// Unit tests for the Workflow shells' pure helpers.
//
// The Workflow sandbox has no filesystem/module access, so these shells cannot be imported and run
// directly. Instead we read the shell source, extract the pure helper by name, and rebuild it with
// `new Function` — so the assertions exercise the REAL code from the file, not a maintained copy.
//
// Run via `node --test .claude/workflows/tests` (the pytest suite does this in test_workflow_shells.py).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// A rebuilt function gets no scope from the file it came from, so a helper that calls other
// top-level helpers (writerPrompt uses unitCriteria and runDir) needs those named as `deps`. Their
// real source is prepended to the body, so the test still drives the file's code, not a copy.
function loadFunction(relSource, name, deps = []) {
  const src = readFileSync(new URL(relSource, import.meta.url), 'utf8')
  const re = new RegExp(`function ${name}\\(([^)]*)\\)\\s*\\{([\\s\\S]*?)\\n\\}`)
  const m = src.match(re)
  assert.ok(m, `${name} must be defined in ${relSource}`)
  const preamble = deps.map((dep) => declarationSource(src, dep, relSource)).join('\n')
  return new Function(m[1], `${preamble}\n${m[2]}`)
}

// A top-level one-line `const name = ...` (e.g. gitIn), rebuilt and returned as a value. The
// single-line extraction is the reason those consts have to stay one-liners.
function loadConst(relSource, name) {
  const src = readFileSync(new URL(relSource, import.meta.url), 'utf8')
  return new Function(`${declarationSource(src, name, relSource)}\nreturn ${name}`)()
}

// The source text of a top-level `function name(...) {...}` or a one-line `const name = ...`.
function declarationSource(src, name, relSource) {
  const asFunction = src.match(new RegExp(`function ${name}\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n\\}`))
  if (asFunction) return asFunction[0]
  const asConst = src.match(new RegExp(`const ${name} = .*`))
  assert.ok(asConst, `${name} must be defined in ${relSource}`)
  return asConst[0]
}

// implementation-loop.js — reviewerConcerns aggregation (the #65 review follow-up: pin that a
// returned unresolved_concerns payload is actually surfaced).
const collectReviewerConcerns = loadFunction('../implementation-loop.js', 'collectReviewerConcerns')

test('collectReviewerConcerns surfaces the editor\'s unresolved_concerns', () => {
  const concerns = [
    { concern: 'ships engine without shell', why_unresolved: 'out_of_unit_scope', suggested_followup: 'add to WORKFLOW_FILES' },
    { concern: 'x', why_unresolved: 'load_bearing' },
  ]
  assert.deepEqual(collectReviewerConcerns({ unresolved_concerns: concerns }), concerns)
})

test('collectReviewerConcerns is empty when there are none', () => {
  assert.deepEqual(collectReviewerConcerns({ unresolved_concerns: [] }), [])
})

test('collectReviewerConcerns defaults safely on a missing/absent field', () => {
  assert.deepEqual(collectReviewerConcerns({}), [])
  assert.deepEqual(collectReviewerConcerns(null), [])
  assert.deepEqual(collectReviewerConcerns(undefined), [])
})

test('collectReviewerConcerns defaults safely on a non-array field (never crashes)', () => {
  assert.deepEqual(collectReviewerConcerns({ unresolved_concerns: 'nope' }), [])
  assert.deepEqual(collectReviewerConcerns({ unresolved_concerns: null }), [])
  assert.deepEqual(collectReviewerConcerns({ unresolved_concerns: 42 }), [])
})

// ---------------------------------------------------------------------------
// implementation-loop.js — acceptance criteria: the unit carries a list of checkable statements
// and the editor grades each one. A spec-less run carries none and must behave exactly as before.
// ---------------------------------------------------------------------------
const unitCriteria = loadFunction('../implementation-loop.js', 'unitCriteria')
const writerPrompt = loadFunction('../implementation-loop.js', 'writerPrompt', ['unitCriteria', 'runDir', 'gitIn', 'workDirPreamble'])
const editorPrompt = loadFunction('../implementation-loop.js', 'editorPrompt', ['unitCriteria', 'runDir', 'gitIn', 'workDirPreamble'])

// A unit with no acceptance_criteria key at all — the shape every run had before this feature.
const UNIT = {
  unit_id: 'unit_demo',
  title: 'Users can create and view a profile',
  test_command: 'pytest -q',
  static_check: 'ruff check .',
  mutation_command: 'mutmut run',
  instructions: 'Build the profile page.',
}
const WRITER = { writer_sha: 'a1b2c3d', files_touched: ['src/profile.py'], load_bearing: [] }

// The numbered criterion lines a prompt renders ("  1. ...").
const numberedLines = (prompt) => prompt.split('\n').filter((line) => /^\s+\d+\. /.test(line))

// The lines `after` adds to `before`, asserting they are a single contiguous insertion: nothing in
// the original prompt may be changed or removed by carrying criteria.
function insertedLines(before, after) {
  const original = before.split('\n')
  const updated = after.split('\n')
  let prefix = 0
  while (prefix < original.length && original[prefix] === updated[prefix]) prefix++
  let suffix = 0
  while (
    suffix < original.length - prefix &&
    original[original.length - 1 - suffix] === updated[updated.length - 1 - suffix]
  ) suffix++
  assert.equal(prefix + suffix, original.length,
    'carrying criteria must only ADD lines — the rest of the prompt has to stay untouched')
  return updated.slice(prefix, updated.length - suffix)
}

test('unitCriteria keeps the criteria the unit was handed, in order', () => {
  const criteria = ['The editor returns one verdict per criterion', 'A failure flags but never reverts']
  assert.deepEqual(unitCriteria({ acceptance_criteria: criteria }), criteria)
})

test('unitCriteria degrades to no criteria on a malformed payload', () => {
  assert.deepEqual(unitCriteria({ acceptance_criteria: 'not an array' }), [])
  assert.deepEqual(unitCriteria({ acceptance_criteria: 42 }), [])
  assert.deepEqual(unitCriteria({ acceptance_criteria: null }), [])
  assert.deepEqual(unitCriteria({}), [])
  assert.deepEqual(unitCriteria(null), [])
  assert.deepEqual(unitCriteria(undefined), [])
  // Junk entries are dropped; the real ones survive, so one bad element can't blank the list.
  assert.deepEqual(
    unitCriteria({ acceptance_criteria: ['keep me', '', '   ', null, 42, { criterion: 'x' }, 'keep me too'] }),
    ['keep me', 'keep me too'],
  )
})

test('writerPrompt shows the writer every criterion and changes nothing else', () => {
  const criteria = ['Rendering 1,000 rows takes under a second', 'A deleted profile 404s']
  const added = insertedLines(writerPrompt(UNIT), writerPrompt({ ...UNIT, acceptance_criteria: criteria }))
  assert.deepEqual(numberedLines(added.join('\n')), [
    '  1. Rendering 1,000 rows takes under a second',
    '  2. A deleted profile 404s',
  ])
  assert.match(added.join('\n'), /ACCEPTANCE CRITERIA/)
})

test('with zero criteria the writer prompt is what it always was', () => {
  const baseline = writerPrompt(UNIT)  // the pre-feature shape: no acceptance_criteria key
  assert.equal(writerPrompt({ ...UNIT, acceptance_criteria: [] }), baseline)
  assert.equal(numberedLines(baseline).length, 0)
  assert.ok(!baseline.includes('ACCEPTANCE CRITERIA'))
})

test('editorPrompt asks for a graded verdict on each criterion it was handed', () => {
  const criteria = ['One verdict per criterion', 'Empty verdicts without a spec', 'A failure flags']
  const prompt = editorPrompt({ ...UNIT, acceptance_criteria: criteria }, WRITER)
  // Every criterion reaches the editor, numbered and in order — that is what makes one verdict
  // per criterion possible.
  assert.deepEqual(numberedLines(prompt), ['  1. One verdict per criterion', '  2. Empty verdicts without a spec', '  3. A failure flags'])
  assert.match(prompt, /For EACH criterion, decide pass, fail, or unverifiable/)
  assert.match(prompt, /record it in criteria_verdicts/)
  assert.match(prompt, /the verdict, and the evidence you actually checked/)
  // The MVI question survives alongside the criteria; it is not replaced by them.
  assert.match(prompt, /only if the unit is usable as a complete interaction AND every criterion passes/)
  // The title-only branch must not also be present.
  assert.ok(!prompt.includes('no acceptance criteria were supplied'))
})

test('with zero criteria the editor still judges against the title', () => {
  const prompt = editorPrompt(UNIT, WRITER)
  assert.match(prompt, /AUTHORITATIVELY judge "if we stopped here, could someone use this unit\?"/)
  assert.ok(prompt.includes(`the title "${UNIT.title}"`))
  assert.ok(!prompt.includes('For EACH criterion'))
  assert.equal(numberedLines(prompt).length, 0)
  assert.match(prompt, /Leave\ncriteria_verdicts empty/)
  assert.equal(editorPrompt({ ...UNIT, acceptance_criteria: [] }, WRITER), prompt)
})

// The gate's criteria rule (unconfirmedCriteria) and the gate itself (passesExitGate).
const unconfirmedCriteria = loadFunction('../implementation-loop.js', 'unconfirmedCriteria')
const passesExitGate = loadFunction('../implementation-loop.js', 'passesExitGate')
const passing = (criterion) => ({ criterion, verdict: 'pass', evidence: 'a test that fails without it' })

test('every criterion confirmed by a matching pass leaves nothing unconfirmed', () => {
  assert.deepEqual(unconfirmedCriteria(['a', 'b'], [passing('a'), passing('b')]), [])
  // Matched on the criterion text, so verdict order does not matter.
  assert.deepEqual(unconfirmedCriteria(['a', 'b'], [passing('b'), passing('a')]), [])
  // Surrounding whitespace is not a mismatch; the criterion travels through markdown and JSON.
  assert.deepEqual(unconfirmedCriteria(['a'], [passing('  a  ')]), [])
})

test('a criterion that did not pass is unconfirmed, whatever mvi_verdict said', () => {
  const failed = { criterion: 'b', verdict: 'fail', evidence: 'the flag does not exist yet' }
  assert.deepEqual(unconfirmedCriteria(['a', 'b'], [passing('a'), failed]), ['b'])
  // unverifiable is not a pass either: "nobody confirmed this" is the honest, flagged answer.
  const unverifiable = { criterion: 'b', verdict: 'unverifiable', evidence: 'needs a browser' }
  assert.deepEqual(unconfirmedCriteria(['a', 'b'], [passing('a'), unverifiable]), ['b'])
})

test('grading one criterion three times does not confirm the other two', () => {
  // The hole a count check leaves open: three passes, three criteria, two never looked at.
  assert.deepEqual(
    unconfirmedCriteria(['a', 'b', 'c'], [passing('a'), passing('a'), passing('a')]),
    ['b', 'c'],
  )
  // Nor do verdicts naming criteria the unit never carried.
  assert.deepEqual(unconfirmedCriteria(['a'], [passing('x'), passing('y')]), ['a'])
  // A softened restatement is not the criterion it was handed.
  assert.deepEqual(unconfirmedCriteria(['renders in under a second'], [passing('renders fast')]),
    ['renders in under a second'])
  assert.deepEqual(unconfirmedCriteria(['a'], []), ['a'])
})

test('a pass with no evidence does not confirm anything', () => {
  // evidence is required by the schema but an empty string satisfies it, which would make the field
  // free to fill in. The gate is where that costs something.
  assert.deepEqual(unconfirmedCriteria(['a'], [{ criterion: 'a', verdict: 'pass', evidence: '' }]), ['a'])
  assert.deepEqual(unconfirmedCriteria(['a'], [{ criterion: 'a', verdict: 'pass', evidence: '   ' }]), ['a'])
})

test('one criterion graded both pass and fail stays unconfirmed', () => {
  const failed = { criterion: 'a', verdict: 'fail', evidence: 'it does not' }
  assert.deepEqual(unconfirmedCriteria(['a'], [passing('a'), failed]), ['a'])
})

test('a junk verdict entry confirms nothing', () => {
  assert.deepEqual(unconfirmedCriteria(['a'], [null]), ['a'])
  assert.deepEqual(unconfirmedCriteria(['a'], [{ criterion: 'a' }]), ['a'])
})

test('a unit that carried no criteria has nothing to confirm', () => {
  // A spec-less run has nothing to enforce: stray verdicts are ignored, not punished.
  assert.deepEqual(unconfirmedCriteria([], []), [])
  assert.deepEqual(unconfirmedCriteria([], [passing('never asked for')]), [])
})

// The gate, not just the rule. Without these, neutralizing the criteria check leaves both suites green.
const GREEN = { tests: { command: 'pytest -q', passed: true, exit_code: 0 }, mvi_verdict: true }

test('the exit gate holds on a green unit with nothing unconfirmed', () => {
  assert.equal(passesExitGate(GREEN, []), true)
})

test('the exit gate fails on an unconfirmed criterion even when the editor claims the unit is usable', () => {
  assert.equal(passesExitGate(GREEN, ['b']), false)
})

test('the exit gate still fails on red tests, a withheld MVI verdict, or a missing editor', () => {
  assert.equal(passesExitGate({ ...GREEN, tests: { command: 'pytest -q', passed: false, exit_code: 1 } }, []), false)
  assert.equal(passesExitGate({ ...GREEN, mvi_verdict: false }, []), false)
  assert.equal(passesExitGate(null, []), false)
  assert.equal(passesExitGate({ mvi_verdict: true }, []), false)
})

// ---------------------------------------------------------------------------
// implementation-loop.js — the entry gate. It decides whether the editor pass happens at all, and
// nothing exercised it until now.
// ---------------------------------------------------------------------------
const passesEntryGate = loadFunction('../implementation-loop.js', 'passesEntryGate')

// A writer that finished its unit: claimed done, tests green, static check clean.
const GREEN_WRITER = {
  mvi_claimed: true,
  tests: { command: 'pytest -q', passed: true, exit_code: 0 },
  static_ok: true,
}

test('the entry gate opens for a green, claimed unit', () => {
  assert.equal(passesEntryGate(GREEN_WRITER, true), true)
})

test('an escalated writer fails the entry gate through the existing mechanics', () => {
  // The gate has no `stuck` clause. An escalation fails it on mvi_claimed=false and red tests,
  // exactly as any writer that never claimed done always has.
  const escalated = {
    mvi_claimed: false,
    tests: { command: 'pytest -q', passed: false, exit_code: 1 },
    stuck: 'studio/nonexistent_ledger.py does not exist and the unit forbids creating it',
  }
  assert.equal(passesEntryGate(escalated, true), false)
  // Either mechanic shuts the gate on its own, so it does not depend on both arriving together.
  assert.equal(passesEntryGate({ ...escalated, mvi_claimed: true }, true), false)
  assert.equal(passesEntryGate({ ...escalated, tests: GREEN_WRITER.tests }, true), false)
  // A handoff with no tests block reads as a shut gate, not a crash. The missing-writer case is
  // gone from here on purpose: the gate is now computed below the loop's `if (!writer)` abort, so
  // that state cannot reach it. The ordering that makes this safe is pinned from Python.
  assert.equal(passesEntryGate({ mvi_claimed: true }, true), false)
})

test('an advisory stuck note on a green unit still gets its editor pass', () => {
  // The spec rejected `&& !writer.stuck` in the gate: a self-reported problem is not a delivery
  // blocker. Add that clause back and this test goes red — which is the reason it exists.
  const greenButWorried = { ...GREEN_WRITER, stuck: 'the fixture naming still bothers me' }
  assert.equal(passesEntryGate(greenButWorried, true), true)
  assert.equal(passesEntryGate(greenButWorried, false), true)
})

test('static_ok shuts the entry gate only when it is explicitly false', () => {
  // Absent is fine: a writer that ran no static check simply never sets the field.
  const noStaticField = { mvi_claimed: true, tests: GREEN_WRITER.tests }
  assert.equal(passesEntryGate(noStaticField, true), true)
  // An explicit false is a failed check, and it shuts the gate when static checking is required.
  assert.equal(passesEntryGate({ ...GREEN_WRITER, static_ok: false }, true), false)
  // The short-circuit: the same failed check is waived when the unit configured no static checks.
  assert.equal(passesEntryGate({ ...GREEN_WRITER, static_ok: false }, false), true)
})

// ---------------------------------------------------------------------------
// implementation-loop.js — work_dir. The loop can be told which directory to build in (a git
// worktree), instead of trusting wherever the agent's shell happens to be sitting.
//
// Honest limit, worth remembering while reading these: every one of these is prompt TEXT. A test
// can prove the prompt says `cd` and pins git; only a live run shows the agent obeyed.
// ---------------------------------------------------------------------------
const gitIn = loadConst('../implementation-loop.js', 'gitIn')
const WORK_DIR = '/Users/x/Repos/my repo-wt/wd'  // a space, on purpose: paths like this exist
const PINNED = `git -C "${WORK_DIR}"`
const occurrences = (haystack, needle) => haystack.split(needle).length - 1

test('gitIn pins git to the work dir, and quotes the path', () => {
  assert.equal(gitIn({ work_dir: WORK_DIR }), PINNED)
  // Unquoted, a path with a space would split into two arguments and git would take the wrong one.
  assert.equal(gitIn({ work_dir: '/tmp/wt' }), 'git -C "/tmp/wt"')
})

test('gitIn falls back to bare git when no work dir was named', () => {
  // The compatibility path: every run before --work-dir existed carries no work_dir at all.
  assert.equal(gitIn(UNIT), 'git')
  assert.equal(gitIn({ work_dir: '' }), 'git')
  assert.equal(gitIn({}), 'git')
  assert.equal(gitIn(null), 'git')
  assert.equal(gitIn(undefined), 'git')
})

test('the writer prompt pins every git command, including the escalation commit', () => {
  const prompt = writerPrompt({ ...UNIT, work_dir: WORK_DIR })
  assert.ok(prompt.includes(`${PINNED} add -A && ${PINNED} commit -m "writer: unit_demo"`))
  // The --allow-empty stuck commit is the easiest of the three commit shapes to miss.
  assert.ok(prompt.includes(`${PINNED} add -A && ${PINNED} commit --allow-empty -m "writer(stuck): unit_demo"`))
  // Two commands, two git tokens each: a count, so a fourth command added later can't slip past
  // unpinned without failing here.
  assert.equal(occurrences(prompt, PINNED), 4)
})

test('the editor prompt pins its diff, its revert, and its commit', () => {
  const prompt = editorPrompt({ ...UNIT, work_dir: WORK_DIR }, WRITER)
  assert.ok(prompt.includes(`${PINNED} diff ${WRITER.writer_sha}..`))
  assert.ok(prompt.includes(`${PINNED} reset --hard ${WRITER.writer_sha}`))
  assert.ok(prompt.includes(`${PINNED} commit -am "editor: unit_demo"`))
  assert.equal(occurrences(prompt, PINNED), 3)
})

test('both prompts open by telling the agent to cd into the work dir', () => {
  // First line, before the role: the `cd` is what covers the test command, the static check and
  // the mutation run — none of which git could ever be pinned for.
  for (const prompt of [writerPrompt({ ...UNIT, work_dir: WORK_DIR }), editorPrompt({ ...UNIT, work_dir: WORK_DIR }, WRITER)]) {
    assert.equal(prompt.split('\n')[0], `ALL WORK HAPPENS IN ${WORK_DIR} — cd there before you do anything else, and stay there.`)
    assert.match(prompt, /Every command below \(tests, static checks, git\) must run in that directory/)
  }
})

test('both prompts say to stop rather than fall back to bare git', () => {
  // Validation happens once, at the start, while the agents run for an hour. A silent fallback to
  // bare `git` after a failed pinned command is how the main checkout gets moved anyway.
  for (const prompt of [writerPrompt({ ...UNIT, work_dir: WORK_DIR }), editorPrompt({ ...UNIT, work_dir: WORK_DIR }, WRITER)]) {
    assert.match(prompt, /if a pinned command fails,\nSTOP and report the failure\. Never retry it as a bare `git`/)
  }
})

// The compatibility bar, and it is exact: every existing run has no work_dir. The fixture holds the
// prompts as they rendered before --work-dir landed, captured from the shipped code. Regenerate it
// only when a change to the unpinned prompts is intended — a diff here otherwise means every run
// that never asked for a work dir just changed.
const BASELINE = JSON.parse(readFileSync(new URL('./fixtures/prompts-no-work-dir.json', import.meta.url), 'utf8'))

test('with no work dir both prompts are byte-identical to the pre-feature output', () => {
  assert.equal(writerPrompt(BASELINE.unit), BASELINE.writer_prompt)
  assert.equal(editorPrompt(BASELINE.unit, BASELINE.writer), BASELINE.editor_prompt)
  // And the fixture is the same unit these tests use elsewhere, so it can't drift into a special case.
  assert.deepEqual(BASELINE.unit, UNIT)
  assert.deepEqual(BASELINE.writer, WRITER)
})

test('with no work dir nothing is pinned and no cd line appears', () => {
  for (const prompt of [writerPrompt(UNIT), editorPrompt(UNIT, WRITER)]) {
    assert.ok(!prompt.includes('git -C'))
    assert.ok(!prompt.includes('ALL WORK HAPPENS IN'))
  }
  assert.ok(writerPrompt(UNIT).includes('`git add -A && git commit -m "writer: unit_demo"`'))
  assert.ok(editorPrompt(UNIT, WRITER).includes('`git reset --hard a1b2c3d`'))
})

test('a malformed criteria payload leaves both prompts on the no-criteria path', () => {
  const junk = { ...UNIT, acceptance_criteria: 'not an array' }
  assert.equal(writerPrompt(junk), writerPrompt(UNIT))
  assert.equal(editorPrompt(junk, WRITER), editorPrompt(UNIT, WRITER))
  // Whitespace-only entries are junk too: they must not produce an empty numbered line.
  const blank = { ...UNIT, acceptance_criteria: ['  ', ''] }
  assert.equal(writerPrompt(blank), writerPrompt(UNIT))
  assert.equal(editorPrompt(blank, WRITER), editorPrompt(UNIT, WRITER))
})
