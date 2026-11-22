import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { loadConst, loadFunction, declarationSource } from './load-from-source.mjs'

const source = process.argv[3] ? pathToFileURL(process.argv[3]) : new URL('../implementation-loop.js', import.meta.url)
const input = JSON.parse(readFileSync(0, 'utf8'))
const gateNames = ['unconfirmedCriteria', 'passesExitGate']
const dependencies = ['editorMandate', 'unitCriteria', 'runDir', 'concernsDir', 'concernsPath', 'gitIn', 'workDirPreamble', 'observeCommand', 'editorObserveLines', 'unitBase']
let output
if (process.argv[2] === 'render') {
  const render = loadFunction(source, 'editorPrompt', dependencies)
  const script = readFileSync(source, 'utf8')
  output = {
    prompts: input.map(({ unit, writer }) => render(unit, writer)),
    schema: loadConst(source, 'EDITOR_HANDOFF'),
    model: loadConst(source, 'EDITOR_MODEL'),
    gate_source: gateNames.map(name => declarationSource(script, name, source)),
  }
} else if (process.argv[2] === 'gate') {
  const [unconfirmedCriteria, passesExitGate] = gateNames.map(name => loadFunction(source, name))
  output = input.map(({ criteria, editor }) => {
    const unconfirmed = unconfirmedCriteria(criteria, editor.criteria_verdicts || [])
    return { unconfirmed, passed: passesExitGate(editor, unconfirmed) }
  })
} else {
  throw new Error('Expected render or gate')
}
console.log(JSON.stringify(output))
