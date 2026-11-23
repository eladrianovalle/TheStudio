import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

// A rebuilt function gets no scope from the file it came from, so a helper that calls other
// top-level helpers (writerPrompt uses unitCriteria and runDir) needs those named as `deps`. Their
// real source is prepended to the body, so the test still drives the file's code, not a copy.
export function loadFunction(relSource, name, deps = []) {
  const src = readFileSync(new URL(relSource, import.meta.url), 'utf8')
  const re = new RegExp(`function ${name}\\(([^)]*)\\)\\s*\\{([\\s\\S]*?)\\n\\}`)
  const m = src.match(re)
  assert.ok(m, `${name} must be defined in ${relSource}`)
  const preamble = deps.map((dep) => declarationSource(src, dep, relSource)).join('\n')
  return new Function(m[1], `${preamble}\n${m[2]}`)
}

// A top-level one-line `const name = ...` (e.g. gitIn), rebuilt and returned as a value. The
// single-line extraction is the reason those consts have to stay one-liners.
export function loadConst(relSource, name) {
  const src = readFileSync(new URL(relSource, import.meta.url), 'utf8')
  return new Function(`${declarationSource(src, name, relSource)}\nreturn ${name}`)()
}

// The source text of a top-level `function name(...) {...}` or a one-line `const name = ...`.
export function declarationSource(src, name, relSource) {
  const asFunction = src.match(new RegExp(`function ${name}\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n\\}`))
  if (asFunction) return asFunction[0]
  const asObject = src.match(new RegExp(`^const ${name} = \\{[\\s\\S]*?\\n\\}`, 'm'))
  if (asObject) return asObject[0]
  const asConst = src.match(new RegExp(`const ${name} = .*`))
  assert.ok(asConst, `${name} must be defined in ${relSource}`)
  return asConst[0]
}
