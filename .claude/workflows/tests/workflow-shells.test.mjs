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

function loadFunction(relSource, name) {
  const src = readFileSync(new URL(relSource, import.meta.url), 'utf8')
  const re = new RegExp(`function ${name}\\(([^)]*)\\)\\s*\\{([\\s\\S]*?)\\n\\}`)
  const m = src.match(re)
  assert.ok(m, `${name} must be defined in ${relSource}`)
  return new Function(m[1], m[2])
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
