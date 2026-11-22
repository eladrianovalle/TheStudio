import test from 'node:test'
import assert from 'node:assert/strict'
import {execFileSync} from 'node:child_process'
import {mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {forge} from '../../../studio/forge_host.mjs'
import {runLoop} from '../../../studio/forge_loop.mjs'

const native = readFileSync(new URL('../implementation-loop.js', import.meta.url), 'utf8')
const Native = Object.getPrototypeOf(async () => {}).constructor
const nativeLoop = new Native('args', 'agent', 'phase', 'log', native.replace('export const meta', 'const meta'))
const grade = {criterion: 'Works.', verdict: 'pass', evidence: 'test -f hello returned 0'}
const tests = {command: 'test -f hello', passed: true, exit_code: 0}
const writer = {unit_id: 'demo', tests, mvi_claimed: true, stage: 'writer', files_touched: ['hello'],
  mutation_check: {performed: false, reason: 'not_configured'}}
const editor = {unit_id: 'demo', tests, mvi_verdict: true, stage: 'editor', edits: 'Reviewed',
  criteria_verdicts: [grade], reverted: false, committed: true}

test('native and portable loops agree on recorded handoffs at both gates', async () => {
  for (const [w, e, enabled, flagged] of [
    [writer, editor, true, false], [writer, {...editor, criteria_verdicts: []}, true, true],
    [writer, {...editor, criteria_verdicts: [{...grade, verdict: 'fail'}]}, true, true],
    [{...writer, stuck: 'fixture', mvi_claimed: false}, null, true, true],
    [writer, null, false, true], [writer, {...editor, tests: {...tests, passed: false}}, true, true],
  ]) {
    const unit = {unit_id: 'demo', acceptance_criteria: ['Works.'], editor_enabled: enabled}
    const events = []
    const host = {phase: () => {}, log: () => {}, agent: async (_, opt) => {
      events.push(opt.label)
      return structuredClone(opt.phase === 'Writer' ? w : e)
    }}
    const legacy = await nativeLoop(unit, host.agent, host.phase, host.log)
    const labels = events.splice(0)
    const portable = await runLoop(unit, host)
    assert.deepEqual(portable, legacy)
    assert.deepEqual(events, labels)
    assert.equal(portable.flagged, flagged)
  }
})

function fixture() {
  const base = mkdtempSync(join(tmpdir(), 'forge-check-'))
  const repo = join(base, 'main')
  const cwd = join(base, 'linked')
  mkdirSync(repo)
  const git = (dir, ...args) => execFileSync('git', args, {cwd: dir, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']}).trim()
  git(repo, 'init', '-b', 'main')
  git(repo, 'config', 'user.name', 'Test')
  git(repo, 'config', 'user.email', 'test@example.test')
  writeFileSync(join(repo, '.gitignore'), '.studio/output/\n')
  git(repo, 'add', '.gitignore')
  git(repo, 'commit', '-qm', 'initial')
  git(repo, 'worktree', 'add', '-qb', 'feature', cwd)
  const runGit = (...args) => git(cwd, ...args)
  const sha = runGit('rev-parse', 'HEAD')
  const unit = {unit_id: 'demo', work_dir: cwd, starting_branch: 'feature', branch: 'feature',
    base_sha: sha, title: 'Works', instructions: 'Build', acceptance_criteria: ['Works.'],
    test_command: 'test "$(cat hello)" = pass', static_checks: [], require_mutation_check: false,
    roles: {writer: {runtime: 'codex', model: null}, editor: {runtime: 'codex', model: null}}}
  return {cwd, git: runGit, unit}
}

for (const scenario of ['pass', 'missing grade', 'red writer', 'red editor', 'bad pin', 'malformed',
  'wrong unit', 'wrong hash', 'extra file', 'unexpected commit', 'branch movement', 'concurrent']) {
  test('linked worktree: ' + scenario, async () => {
    const {cwd, git, unit} = fixture()
    let count = 0
    if (scenario === 'bad pin') unit.roles.writer.model = 'requested'
    const adapter = async ({execution}) => {
      count++
      Object.assign(execution, {actual_runtime: 'codex', completed: true, session_id: 'session-' + count})
      if (count === 1) {
        if (scenario === 'concurrent') await assert.rejects(forge(unit, {codex: adapter}), /owns this worktree/)
        writeFileSync(join(cwd, 'hello'), scenario === 'red writer' ? 'fail' : 'pass')
        return {changes: [{path: 'hello', blob: git('hash-object', 'hello')}],
          handoff: {...writer, base_sha: unit.base_sha, writer_sha: unit.base_sha}}
      }
      if (scenario === 'malformed') return {}
      if (scenario === 'unexpected commit') git('commit', '--allow-empty', '-qm', 'external')
      if (scenario === 'branch movement') git('switch', '-qc', 'other')
      if (scenario === 'extra file') writeFileSync(join(cwd, 'unrelated'), 'keep')
      const changes = []
      if (scenario === 'red editor' || scenario === 'wrong hash') {
        writeFileSync(join(cwd, 'hello'), 'failed edit')
        changes.push({path: 'hello', blob: scenario === 'wrong hash' ? 'incorrect' : git('hash-object', 'hello')})
      }
      return {changes, handoff: {...editor, files_touched: changes.map(c => c.path),
        unit_id: scenario === 'wrong unit' ? 'other' : 'demo',
        criteria_verdicts: scenario === 'missing grade' ? [] : [grade]}}
    }
    const state = await forge(unit, {codex: adapter})
    if (['red writer', 'bad pin'].includes(scenario)) {
      assert.equal(count, 1)
      assert.equal(state.roles.editor.status, 'skipped')
      assert.equal(git('rev-parse', 'HEAD'), unit.base_sha)
      if (scenario === 'bad pin') assert.equal(state.failed_stage, 'writer')
      else assert.equal(state.result.flagged, true)
      return
    }
    assert.equal(count, 2)
    if (['pass', 'concurrent', 'missing grade', 'red editor'].includes(scenario)) {
      assert.equal(state.error, undefined)
      assert.equal(state.result.flagged, ['red editor', 'missing grade'].includes(scenario))
      assert.equal(git('status', '--porcelain'), '')
      assert.equal(readFileSync(join(cwd, 'hello'), 'utf8'), 'pass')
      assert.equal(state.last_verified_sha, git('rev-parse', 'HEAD'))
    } else {
      assert.equal(state.failed_stage, 'editor')
      assert.equal(git('show', state.last_verified_sha + ':hello'), 'pass')
      if (scenario === 'extra file') assert.ok(existsSync(join(cwd, 'unrelated')))
      if (scenario === 'wrong hash') assert.equal(readFileSync(join(cwd, 'hello'), 'utf8'), 'failed edit')
      if (scenario === 'unexpected commit') assert.equal(git('log', '-1', '--format=%s'), 'external')
      if (scenario === 'branch movement') assert.equal(git('branch', '--show-current'), 'other')
    }
  })
}
