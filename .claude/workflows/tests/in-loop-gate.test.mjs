import test from 'node:test'
import assert from 'node:assert/strict'
import {execFileSync, spawnSync} from 'node:child_process'
import {mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {claudeCommands} from '../../../studio/forge_host.mjs'
import {runLoop} from '../../../studio/forge_loop.mjs'

const python = process.env.PYTHON || 'python3'
const studio = fileURLToPath(new URL('../../../studio/', import.meta.url))
const native = readFileSync(new URL('../implementation-loop.js', import.meta.url), 'utf8')
const Native = Object.getPrototypeOf(async () => {}).constructor
const nativeLoop = new Native('args', 'agent', 'phase', 'log', native.replace('export const meta', 'const meta'))

function project() {
  const repo = realpathSync(mkdtempSync(join(tmpdir(), 'forge-in-loop-gate-')))
  const git = (...args) => execFileSync('git', args, {cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']}).trim()
  git('init', '-q', '-b', 'main')
  git('config', 'user.name', 'Test')
  git('config', 'user.email', 'test@example.test')
  mkdirSync(join(repo, '.studio'))
  mkdirSync(join(repo, 'web'))
  writeFileSync(join(repo, 'web/app.js'), 'app\n')
  writeFileSync(join(repo, '.gitignore'), '.studio/output/\n')
  writeFileSync(join(repo, '.studio/implementation_loop.toml'),
    '[gate]\ntest_command = "echo default-ran"\nrequire_mutation_check = false\n' +
    '[gate.suites.web]\ncommand = "echo web-ran"\npaths = ["web/"]\n')
  git('add', '-A')
  git('commit', '-qm', 'fixture')
  git('checkout', '-qb', 'impl/demo')
  return {repo, config: join(repo, '.studio/implementation_loop.toml'), head: git('rev-parse', 'HEAD')}
}

async function firstPrompt(loop, unit) {
  const prompts = []
  const agent = async (prompt) => {
    prompts.push(prompt)
    return {unit_id: unit.unit_id, stage: 'writer', stuck: 'fixture', mvi_claimed: false, files_touched: [],
      tests: {command: unit.test_command, passed: true, exit_code: 0},
      mutation_check: {performed: false, reason: 'not_reached'}}
  }
  await loop(unit, agent)
  return prompts[0]
}

function runnerFor(config, base) {
  const interpreter = execFileSync(python, ['-c', 'import sys; print(sys.executable)'], {encoding: 'utf8'}).trim()
  return `"${interpreter}" "${join(studio, 'gate_routes.py')}" --config "${config}" --base ${base}`
}

test('the native launch prints the routed gate runner and the writer runs it when there is no --test', async () => {
  const {repo, config, head} = project()
  const knobs = JSON.parse(execFileSync(python, [join(studio, 'impl_loop.py'), config, '--branch', 'impl/demo', '--unit', 'demo'],
    {cwd: repo, encoding: 'utf8'}))

  assert.equal(knobs.gate_command, runnerFor(config, head))
  const unit = {unit_id: 'demo', title: 'Works', instructions: 'Build', launched_at: knobs.launched_at,
    test_command: knobs.gate_command, static_checks: [], require_mutation_check: false}
  const prompt = await firstPrompt((args, agent) => nativeLoop(args, agent, () => {}, () => {}), unit)
  assert.ok(prompt.includes('Run the unit tests: `' + knobs.gate_command + '`'))

  writeFileSync(join(repo, 'web/app.js'), 'changed\n')
  const ran = spawnSync(knobs.gate_command, {cwd: repo, shell: true, encoding: 'utf8'})
  assert.equal(ran.status, 0, ran.stderr)
  assert.deepEqual(JSON.parse(ran.stdout).runs, [{suite: 'web', command: 'echo web-ran', exit_code: 0}])
})

test('the portable plan gives the writer the same routed gate runner when there is no --test', async () => {
  const {repo, config, head} = project()
  const plan = JSON.parse(execFileSync(python, [join(studio, 'run_phase.py'), 'forge', 'Build a demo', '--plan'],
    {cwd: repo, encoding: 'utf8'}))

  assert.equal(plan.test_command, runnerFor(config, head))
  assert.ok(claudeCommands(plan, 'writer').includes(plan.test_command))
  assert.ok(claudeCommands(plan, 'editor', {base_sha: head, writer_sha: head}).includes(plan.test_command))
  const prompt = await firstPrompt((unit, agent) => runLoop(unit, {agent, phase: () => {}, log: () => {}}), plan)
  assert.ok(prompt.includes('Run the unit tests: `' + plan.test_command + '`'))
})
