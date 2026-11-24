import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtempSync, writeFileSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join, delimiter} from 'node:path'
import {runCodex} from '../../../studio/forge_codex.mjs'

test('Codex correlates selection, reroutes and completed model output to this thread and turn', async () => {
  const bin = mkdtempSync(join(tmpdir(), 'studio-codex-test-'))
  const executable = join(bin, 'codex')
  writeFileSync(executable, '#!' + process.execPath + '\n' + String.raw`
const rl = require('node:readline').createInterface({input: process.stdin})
const send = m => console.log(JSON.stringify(m))
let model
rl.on('line', line => {
  const m = JSON.parse(line)
  if (m.id === 1) send({id: 1, result: {}})
  if (m.id === 2) {
    model = m.params.model
    send({id: 2, result: {model, thread: {id: 'own'}}})
    if (model === 'thread-only') process.exit(0)
  }
  if (m.id === 3) {
    send({id: 3, result: {turn: {id: 'turn1'}}})
    for (const [threadId, turnId] of [['other', 'turn1'], ['own', 'other']]) {
      send({method: 'model/rerouted', params: {threadId, turnId, fromModel: 'a', toModel: 'helper'}})
    }
    if (model === 'rerouted') send({method: 'model/rerouted', params: {threadId: 'own', turnId: 'turn1', fromModel: model, toModel: 'served'}})
    send({method: 'item/completed', params: {threadId:'own',turnId:'turn1',item: {type:'agentMessage',text:'{"result":true}'}}})
    send({method:'turn/completed',params:{threadId:'own',turn:{id:'turn1',status:'completed'}}})
  }
})
`, {mode: 0o755})
  const prev = process.env.PATH
  process.env.PATH = bin + delimiter + prev
  try {
    for (const model of ['thread-only', 'writer-pin', 'editor-pin', 'rerouted', null]) {
      const record = {observed_models: [], reroutes: [], completed: false}
      const promise = runCodex({cwd: bin, prompt: 'fixture', schema: {}, model, execution: record})
      if (model === 'thread-only') {
        await assert.rejects(promise, /before completing/)
        assert.equal(record.completed, false)
        assert.deepEqual(record.observed_models, [])
      } else {
        assert.deepEqual(await promise, {result: true})
        assert.deepEqual(record.observed_models, model ? [model === 'rerouted' ? 'served' : model] : [])
        assert.deepEqual(record.reroutes, model === 'rerouted' ? [{from:model, to:'served'}] : [])
        assert.equal(record.completed, true)
      }
    }
  } finally {
    process.env.PATH = prev
  }
})
