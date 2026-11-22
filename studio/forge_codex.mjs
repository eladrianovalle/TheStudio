// One stdio app-server process per role. Only notifications for its thread AND turn
// contribute routing evidence. Raw model messages and tool output never enter that record.
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'

export async function runCodex({cwd, prompt, schema, model, execution}) {
  const child = spawn('codex', ['app-server'], {cwd, stdio: ['pipe', 'pipe', 'ignore']})
  child.stdin.on('error', () => {}) // An early exit is reported by the process listener.
  return new Promise((resolve, reject) => {
    const lines = createInterface({input: child.stdout})
    let thread, turn, selected, finalText
    let settled = false
    const pending = []
    const finish = (error, result) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      lines.close()
      child.stdin.end()
      child.kill()
      if (error) reject(new Error(error))
      else resolve(result)
    }
    const timeout = setTimeout(() => finish('Codex role timed out'), 60 * 60 * 1000)
    const send = (message) => child.stdin.write(JSON.stringify(message) + '\n')
    child.on('error', err => finish(err.code === 'ENOENT' ? 'Codex executable missing' : 'Codex process failed'))
    child.on('exit', () => finish('Codex exited before completing the role'))
    child.on('spawn', () => {
      execution.actual_runtime = 'codex'
      send({id: 1, method: 'initialize', params: {clientInfo: {name: 'studio_forge', version: '1.0'}}})
    })

    function notification({method, params: p}) {
      if (p?.threadId !== thread || (p.turnId ?? p.turn?.id) !== turn) return
      if (method === 'model/rerouted') {
        execution.reroutes.push({from: p.fromModel, to: p.toModel})
      } else if (method === 'item/completed' && p.item?.type === 'agentMessage') {
        finalText = p.item.text
      } else if (method === 'turn/completed') {
        if (p.turn.status !== 'completed') {
          const code = p.turn.error?.codexErrorInfo
          return finish('Codex turn ' + p.turn.status + (typeof code === 'string' ? ' (' + code + ')' : ''))
        }
        finalText ??= p.turn.items?.filter(i => i.type === 'agentMessage').at(-1)?.text
        if (!finalText) return finish('Codex completed without a model response')
        execution.completed = true
        const served = execution.reroutes.at(-1)?.to ?? selected
        if (served) execution.observed_models.push(served)
        try { finish(null, JSON.parse(finalText)) }
        catch { finish('Malformed Codex handoff') }
      }
    }

    lines.on('line', line => {
      if (settled) return
      try {
        const msg = JSON.parse(line)
        if (msg.method && msg.id != null) {
          send({id: msg.id, error: {code: -32601, message: 'Unsupported interactive request'}})
          return finish('Codex requested interactive permission or input')
        }
        if (msg.error) return finish('Codex rejected request ' + msg.id + ' (RPC ' + msg.error.code + ')')
        if (msg.id === 1) {
          send({method: 'initialized'})
          send({id: 2, method: 'thread/start', params: {cwd, model, approvalPolicy: 'never',
            sandbox: 'workspace-write', ephemeral: true}})
        } else if (msg.id === 2) {
          thread = msg.result.thread.id
          execution.session_id = thread
          selected = msg.result.model
          send({id: 3, method: 'turn/start', params: {threadId: thread,
            input: [{type: 'text', text: prompt}], outputSchema: schema}})
        } else if (msg.id === 3) {
          turn = msg.result.turn.id
          for (const queued of pending) notification(queued)
          pending.length = 0
        } else if (turn) {
          notification(msg)
        } else if (thread && msg.params?.threadId === thread &&
                   ['turn/completed', 'item/completed', 'model/rerouted'].includes(msg.method)) {
          pending.push(msg)
        }
      } catch {
        finish('Invalid Codex app-server response')
      }
    })
  })
}
