import { execFileSync, spawnSync } from 'node:child_process'
import { accessSync, constants, closeSync, existsSync, lstatSync, mkdirSync, openSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { delimiter, join, isAbsolute, normalize } from 'node:path'
import { randomUUID } from 'node:crypto'
import { pathToFileURL } from 'node:url'
import { runLoop } from './forge_loop.mjs'
import { runCodex } from './forge_codex.mjs'

const adapters = {codex: runCodex}

function executable(name) {
  return (process.env.PATH || '').split(delimiter).some(dir => {
    try {
      const path = join(dir, process.platform === 'win32' ? name + '.exe' : name)
      accessSync(path, constants.X_OK)
      return statSync(path).isFile()
    } catch { return false }
  })
}

function saveJson(path, value) {
  const tmp = path + '.' + randomUUID() + '.tmp'
  writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n', {mode: 0o600, flag: 'wx'})
  renameSync(tmp, path)
}


function execution({runtime, model}) {
  return {requested_runtime: runtime, requested_model: model, actual_runtime: null, session_id: null,
    observed_models: [], confirmed_aliases: [], reroutes: [], completed: false, status: 'skipped'}
}

// Structured-output transports require every property to be required. Null represents
// an absent optional handoff field on the wire; native callers keep their original schema.
function transportSchema(schema) {
  if (schema.type === 'array') return {...schema, items: transportSchema(schema.items)}
  if (schema.type !== 'object') return schema
  const properties = {}
  for (const [key, field] of Object.entries(schema.properties)) {
    const inner = transportSchema(field)
    properties[key] = schema.required.includes(key) ? inner : {anyOf: [inner, {type: 'null'}]}
  }
  return {...schema, required: Object.keys(properties), properties}
}

function handoffValue(value, schema) {
  const fail = () => { throw Error('Malformed ' + (schema.description || schema.type) + ' handoff field') }
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) fail()
    for (const key of schema.required) if (value[key] == null) fail()
    const result = {}
    for (const [key, v] of Object.entries(value)) {
      if (!Object.hasOwn(schema.properties, key)) fail()
      if (v !== null) result[key] = handoffValue(v, schema.properties[key])
    }
    return result
  }
  if (schema.type === 'array') {
    if (!Array.isArray(value)) fail()
    return value.map(v => handoffValue(v, schema.items))
  }
  if (schema.type === 'integer' ? !Number.isInteger(value) : typeof value !== schema.type) fail()
  if (schema.enum && !schema.enum.includes(value)) fail()
  return value
}

const changesSchema = {type: 'array', items: {type: 'object', additionalProperties: false,
  required: ['path', 'blob'], properties: {path: {type: 'string'}, blob: {type: ['string', 'null']}}}}

function rolePrompt(prompt, stage, checkpoint, writer) {
  // Keep the common mandate, unit, criteria, read scope and gate instructions. The native
  // agent owns commits and recovery; the portable host performs those operations itself.
  if (stage === 'writer') {
    prompt = prompt.slice(0, prompt.indexOf('- When (and only when) tests pass, COMMIT'))
    prompt += '\nDeclare mvi_claimed truthfully; set stuck and mvi_claimed=false if blocked. Report load_bearing choices.'
    prompt += '\nUse the full current base SHA for BOTH base_sha and writer_sha: ' + checkpoint
  } else {
    prompt = prompt.slice(0, prompt.indexOf('Deliver: if you KEPT'))
      .replace(/- If an edit breaks tests[\s\S]*?Never deliver red code from an edit\./,
        '- If an edit breaks tests or needs a load_bearing change, request recovery by setting reverted=true.')
      .replace(/If it is non-empty, also write it as a[\s\S]*?survives a worktree being removed\./,
        'The host persists concerns from your structured response.')
    prompt += '\nWriter handoff: ' + JSON.stringify(writer) + '\nReturn committed=false; the host commits after testing.'
  }
  return prompt + '\nWork directly in the supplied directory. Leave Git refs and the index alone. ' +
    'The host owns staging, commits, recovery and all run records. Return the structured envelope. ' +
    'For changes list ONLY files you personally changed with their final repository-relative path and ' +
    'exact blob from git hash-object -- <path> (null for a deletion). Recheck your changes before hashing. ' +
    'Include all of these paths in handoff.files_touched. Use [] for no changes. ' +
    'Do not write handoff files or reviewer concern records yourself.'
}

function checkIdentity(record) {
  if (!record.completed || record.actual_runtime !== record.requested_runtime) throw Error('Role did not complete')
  const pin = record.requested_model
  if (!pin) return
  const matches = observed => observed === pin || record.confirmed_aliases.some(a => a.alias === pin && a.model === observed)
  if (!record.observed_models.length || !record.observed_models.every(matches) ||
      record.reroutes.some(route => !matches(route.to))) throw Error('Unverified model pin ' + pin)
}

export async function forge(unit, runtimes = adapters) {
  const cwd = unit.work_dir
  const git = (...args) => execFileSync('git', ['--literal-pathspecs', ...args],
    {cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 32 * 1024 * 1024})
  const head = () => git('rev-parse', 'HEAD').trim()
  const branch = () => git('branch', '--show-current').trim()
  const state = {attempt: randomUUID(), branch: unit.branch, base_sha: null, last_verified_sha: null,
    roles: {writer: execution(unit.roles.writer), editor: execution(unit.roles.editor)}}
  const gitDir = git('rev-parse', '--absolute-git-dir').trim()
  const lock = join(gitDir, 'studio-forge.lock')
  let fd
  try { fd = openSync(lock, 'wx') }
  catch (err) {
    if (err.code === 'EEXIST') throw Error('A Forge run owns this worktree (' + lock + ')')
    throw err
  }
  let stage = 'preflight', recordPath, writer
  const output = '.studio/output/impl_loop/' + unit.unit_id + '/'
  const dir = join(cwd, output)
  const handoffPath = role => join(dir, 'impl--' + unit.unit_id + '--' + role + '.json')
  let checkpoint = unit.base_sha
  function ensureLocation(expected = unit.branch) {
    if (branch() !== expected || head() !== checkpoint) throw Error('Branch or HEAD moved; preserving checkout')
  }
  function status() {
    // Installed projects can choose to track their Studio directory. Ignore only
    // untracked records in this unit's reserved journal namespace.
    return git('status', '--porcelain=v1', '-z', '--no-renames', '--untracked-files=all')
      .split('\0').filter(line => line && !(line.startsWith('?? ' + output) &&
        /^(attempt-[0-9a-f-]{36}|impl--[a-z0-9_]+--(writer|editor))\.json$/.test(line.slice(3 + output.length))))
  }
  function validateChanges(changes) {
    ensureLocation()
    if (!Array.isArray(changes)) throw Error('Missing change manifest; preserving checkout')
    const entries = status()
    if (entries.length !== changes.length) throw Error('Ambiguous edits; preserving checkout')
    const manifest = new Map(changes.map(c => [c.path, c.blob]))
    for (const line of entries) {
      const code = line.slice(0, 2), path = line.slice(3)
      if (![' M', ' D', '??'].includes(code) || !manifest.has(path) || isAbsolute(path) ||
          normalize(path) !== path || path.startsWith('../')) throw Error('Ambiguous or staged edits; preserving checkout')
      const info = code === ' D' ? null : lstatSync(join(cwd, path))
      if (info && !info.isFile()) throw Error('Unsupported file type; preserving checkout')
      const blob = info ? git('hash-object', '--', path).trim() : null
      if (blob !== manifest.get(path)) throw Error('Change content differs from role handoff; preserving checkout')
      // A blob identifies content, not a chmod. Refuse ambiguous changes of mode.
      if (code === ' M' && git('diff', '--summary', '--', path).includes('mode change')) {
        throw Error('Unverified file mode change; preserving checkout')
      }
    }
    return entries
  }
  function test(command) {
    const r = spawnSync(command, {cwd, shell: true, stdio: ['ignore', 2, 2]})
    return {command, passed: r.status === 0, exit_code: r.status ?? 1}
  }
  function recover(changes) {
    const entries = validateChanges(changes)
    for (const entry of entries) {
      const path = entry.slice(3)
      if (entry.startsWith('??')) unlinkSync(join(cwd, path))
      else git('restore', '--source', checkpoint, '--worktree', '--', path)
    }
    validateChanges([])
    if (!test(unit.test_command).passed) throw Error('Restored writer checkpoint failed its test')
    validateChanges([])
  }
  function commit(changes, label) {
    validateChanges(changes)
    const paths = changes.map(c => c.path)
    if (paths.length) git('add', '--', ...paths)
    ensureLocation()
    // Verify the immutable tree that commit-tree will use, even if another process
    // changes the index between staging and taking this snapshot.
    const tree = git('write-tree').trim()
    const staged = git('diff', '--name-only', '--no-renames', '-z', checkpoint, tree).split('\0').filter(Boolean)
    if (staged.length !== paths.length || staged.some(p => !paths.includes(p))) throw Error('Unexpected staged paths')
    for (const {path, blob} of changes) {
      const entry = git('ls-tree', '-z', tree, '--', path)
      const stagedBlob = entry ? entry.split('\t', 1)[0].split(' ')[2] : null
      if (stagedBlob !== blob) throw Error('Staged content changed; preserving index')
    }
    const message = label + ': ' + unit.unit_id
    const next = git('commit-tree', tree, '-p', checkpoint, '-m', message).trim()
    ensureLocation()
    // Compare-and-swap the named branch. A branch switch cannot redirect this commit,
    // and Git refuses an intervening commit without overwriting it.
    git('update-ref', '-m', message, 'refs/heads/' + unit.branch, next, checkpoint)
    if (branch() !== unit.branch || git('rev-parse', next + '^').trim() !== checkpoint) throw Error('Unexpected commit')
    checkpoint = next
    validateChanges([])
  }
  try {
    ensureLocation(unit.starting_branch)
    if (status().length) throw Error('dirty-tree: commit or stash existing changes before running Forge')
    if (unit.starting_branch !== unit.branch) {
      const exists = git('branch', '--list', unit.branch).trim()
      if (exists && git('rev-parse', 'refs/heads/' + unit.branch).trim() !== checkpoint) {
        throw Error('Target branch has a different HEAD. Check it out first and repeat the plan so its spec and gate config are used.')
      }
      git('switch', ...(exists ? [] : ['-c']), unit.branch)
    }
    ensureLocation()
    state.base_sha = checkpoint
    state.last_verified_sha = checkpoint
    if (git('ls-files', '--', output)) throw Error('Run records are tracked; refusing to overwrite them')
    mkdirSync(dir, {recursive: true})
    recordPath = join(dir, 'attempt-' + state.attempt + '.json')
    state.record = recordPath
    const save = () => saveJson(recordPath, state)
    save()
    for (const role of ['writer', 'editor']) {
      // Every portable result lives in its attempt record. Retain older native handoffs
      // as well before removing their "current" name for this attempt.
      const path = handoffPath(role)
      if (existsSync(path)) {
        const archive = join(dir, 'attempt-' + randomUUID() + '.json')
        renameSync(path, archive)
      }
    }
    if (runtimes === adapters) {
      for (const role of ['writer', 'editor']) {
        if (role === 'editor' && unit.editor_enabled === false) continue
        stage = role
        const runtime = unit.roles[role].runtime
        if (!executable(runtime)) throw Error(runtime + ' executable missing')
        if (!runtimes[runtime]) throw Error('Unsupported runtime ' + runtime)
      }
    }
    async function agent(prompt, options) {
      stage = options.label.split(':')[0]
      const req = unit.roles[stage]
      const record = state.roles[stage]
      record.status = 'running'
      save()
      validateChanges([])
      const adapter = runtimes[req.runtime]
      if (!adapter) throw Error('Unsupported runtime ' + req.runtime)
      const schema = {type: 'object', additionalProperties: false, required: ['handoff', 'changes'],
        properties: {handoff: transportSchema(options.schema), changes: changesSchema}}
      const reply = await adapter({cwd, model: req.model, schema, execution: record,
        prompt: rolePrompt(prompt, stage, checkpoint, writer)})
      const handoff = handoffValue(reply?.handoff, options.schema)
      if (handoff.unit_id !== unit.unit_id || handoff.stage !== stage ||
          (stage === 'writer' && (handoff.base_sha !== checkpoint || handoff.writer_sha !== checkpoint))) {
        throw Error('Wrong handoff identity')
      }
      validateChanges(reply.changes)
      const paths = reply.changes.map(c => c.path)
      if (paths.some(p => !handoff.files_touched?.includes(p))) throw Error('Changes absent from handoff.files_touched')
      try { checkIdentity(record) } catch (err) {
        if (stage === 'editor') recover(reply.changes)
        throw err
      }
      const verified = test(unit.test_command)
      validateChanges(reply.changes)
      const reportedPass = handoff.tests.passed && handoff.tests.exit_code === 0
      handoff.tests = {...verified, passed: verified.passed && reportedPass}
      record.host_test = verified
      if (stage === 'writer') {
        if (handoff.stuck) handoff.mvi_claimed = false
        const quoted = paths.map(p => "'" + p.replaceAll("'", "'\\''") + "'").join(' ')
        const checks = unit.static_checks.filter(cmd => quoted || !cmd.includes('{paths}'))
        for (const cmd of checks) {
          if (!test(cmd.replaceAll('{paths}', quoted)).passed) handoff.static_ok = false
        }
        if (handoff.stuck || (handoff.tests.passed && handoff.mvi_claimed && (!checks.length || handoff.static_ok !== false))) {
          commit(reply.changes, handoff.stuck ? 'writer(stuck)' : 'writer')
          if (!handoff.stuck) state.last_verified_sha = checkpoint
        }
        handoff.writer_sha = checkpoint
        writer = handoff
      } else if (!handoff.tests.passed || handoff.reverted) {
        recover(reply.changes)
        handoff.reverted = true
        handoff.committed = false
      } else {
        if (paths.length) commit(reply.changes, 'editor')
        handoff.committed = true
        state.last_verified_sha = checkpoint
      }
      saveJson(handoffPath(stage), handoff)
      record.status = 'completed'
      save()
      return handoff
    }
    state.result = await runLoop(unit, {agent, log: () => {}, phase: () => {}})
    const concerns = state.result.reviewerConcerns || []
    if (concerns.length) {
      const dir = join(cwd, 'reviewer-concerns')
      mkdirSync(dir, {recursive: true})
      writeFileSync(join(dir, unit.unit_id + '.md'), concerns.map(c =>
        '## ' + c.concern + '\n\n' + c.why_unresolved + '\n\n' + (c.suggested_followup || '')).join('\n\n'),
      {flag: 'wx'})
    }
  } catch (err) {
    state.failed_stage = stage
    if (state.roles[stage]) state.roles[stage].status = 'failed'
    state.error = err.message
  } finally {
    try {
      if (recordPath) saveJson(recordPath, state)
    } finally {
      closeSync(fd)
      unlinkSync(lock)
    }
  }
  return state
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const state = await forge(JSON.parse(readFileSync(0, 'utf8')))
    console.log(JSON.stringify(state, null, 2))
    if (state.error || !state.result?.delivered || state.result.flagged) process.exitCode = 1
  } catch (err) {
    console.error(err.message)
    process.exitCode = 1
  }
}
