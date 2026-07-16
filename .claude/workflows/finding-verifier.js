export const meta = {
  name: 'finding-verifier',
  description: 'Independent second opinion on contrarian findings — a fresh agent re-checks each Medium-confidence finding from ONLY its quote (never the contrarian\'s reasoning) and writes adjusted confidence back to findings.json. See specs/contrarian-finding-verifier.md.',
  whenToUse: 'After a run produced findings.json, get its Medium-confidence findings an independent second opinion. Pass the run directory via args.',
  phases: [
    { title: 'Select', detail: 'load findings.json; pick the Medium-confidence findings' },
    { title: 'Verify', detail: 'one fresh agent per finding — sees ONLY the quote + demotion rules' },
    { title: 'Write-back', detail: 'aggregate verdicts; write adjusted confidence back to findings.json' },
  ],
}

// ---------------------------------------------------------------------------
// args = the run directory containing findings.json. A bare string path is
// accepted; a { run_dir } object also works. The runtime forwards args as a
// JSON-encoded STRING, so normalize before use (same as implementation-loop.js).
// ---------------------------------------------------------------------------
let parsedArgs = args
if (typeof parsedArgs === 'string') {
  try { parsedArgs = JSON.parse(parsedArgs) } catch { /* leave as a raw path string */ }
}
const runDir = (parsedArgs && typeof parsedArgs === 'object' && !Array.isArray(parsedArgs))
  ? parsedArgs.run_dir
  : parsedArgs
if (!runDir) {
  log('No run_dir given — pass the run directory containing findings.json.')
  return { verified: 0, reason: 'no_run_dir' }
}
log(`Run dir: ${runDir}`)

// ---------------------------------------------------------------------------
// Handoff schema — the typed baton from each fresh verifier agent. finding_id is
// the finding's position (index) in the ordered findings.json list, which is how
// the write-back matches a verdict back to its Finding.
// ---------------------------------------------------------------------------
const VERIFIER_HANDOFF = {
  type: 'object',
  required: ['finding_id', 'verdict', 'one_line_reason'],
  additionalProperties: false,
  properties: {
    finding_id: { type: 'integer', description: 'index of the finding in the ordered findings.json list' },
    verdict: { type: 'string', enum: ['confirmed', 'unconfirmed', 'uncertain'] },
    // No resulting_confidence override: confidence tracks veracity (two voices agree -> promote),
    // never severity. The write-back always derives it from the verdict — confirmed promotes,
    // unconfirmed demotes, uncertain leaves it. Whether a real flaw is *minor* is a separate axis.
    one_line_reason: { type: 'string', description: 'one line, from the verifier\'s own read of the code — not the contrarian\'s argument (it never saw it)' },
  },
}

// ---------------------------------------------------------------------------
// Select — an agent runs the Python core to list the Medium findings as JSON.
// Each row carries the index (position in findings.json) + the quote, which is
// the ONLY thing the per-finding verifier is allowed to see.
// ---------------------------------------------------------------------------
phase('Select')
const SELECT_SNIPPET = [
  'import json, sys',
  'from findings import load_findings_json',
  'from verifier import select_findings_to_verify',
  'run_dir = sys.argv[1]',
  'findings = load_findings_json(run_dir)',
  'rows = [',
  '    {"index": i, "quote": f.quote}',
  '    for i, f in enumerate(findings)',
  '    if f in select_findings_to_verify(findings)',
  ']',
  'print(json.dumps(rows))',
].join('; ')
const selected = await agent(
  [
    `List the Medium-confidence findings eligible for verification in the run directory \`${runDir}\`.`,
    `From the repo root, run (findings.py / verifier.py live under studio/, so run from there):`,
    ``,
    `  cd studio && python -c '${SELECT_SNIPPET}' "${runDir}"`,
    ``,
    `(If this Workflow runs in an installed repo, the modules live under .studio/source/ — cd there instead.)`,
    `Return a JSON object { "findings": [...] } wrapping the array it prints (a list of { index, quote } objects). If it prints [], return { "findings": [] }.`,
  ].join('\n'),
  {
    // NOTE: a custom tool's top-level input schema MUST be an object — the Anthropic API rejects a
    // bare top-level array (400 input_schema.type). So the array of findings is wrapped in `findings`.
    schema: { type: 'object', additionalProperties: false, required: ['findings'], properties: { findings: { type: 'array', items: { type: 'object', required: ['index', 'quote'], additionalProperties: false, properties: { index: { type: 'integer' }, quote: { type: 'string' } } } } } },
    label: 'select-medium-findings',
    phase: 'Select',
  },
)

const eligible = (selected && Array.isArray(selected.findings)) ? selected.findings : []
log(`Eligible Medium findings: ${eligible.length}`)
if (eligible.length === 0) {
  return { verified: 0, confirmed: 0, demoted: 0, uncertain: 0 }
}

// ---------------------------------------------------------------------------
// Verify — one FRESH agent per finding. THE FIREWALL: the prompt carries ONLY
// the finding's quote (the `file:line` + the quoted text) and the demotion
// rules. The contrarian's flaw description and reasoning are deliberately absent
// — that anchoring is exactly what this feature exists to avoid. The verifier
// MAY open the real code at file:line and judge it independently; it must never
// be handed the argument for why the code is wrong.
// ---------------------------------------------------------------------------
phase('Verify')
const verdicts = []
for (const item of eligible) {
  const verdict = await agent(
    [
      `You are an INDEPENDENT verifier. Below is a single quoted claim pulled from a code review.`,
      `You are NOT told what anyone thinks is wrong with it, and you must not guess at their reasoning.`,
      `Judge only this: reading the real code at the cited location, does this quoted code actually have a problem?`,
      ``,
      `QUOTE (finding #${item.finding_id ?? item.index}):`,
      `${item.quote}`,
      ``,
      `The quote is \`file:line\` — "exact code/text". You MAY open that file at that line and read the`,
      `surrounding code to judge it. Do NOT go looking for any review notes, comments, or argument about it.`,
      ``,
      `Return a verdict on whether the flaw is real (this is a veracity judgment, not a severity one —`,
      `do not weigh how minor or major it is, only whether it is real):`,
      `- "confirmed": you independently see a real problem in this code.`,
      `- "unconfirmed": you read the code and cannot find the alleged problem.`,
      `- "uncertain": the quote (even with the code) doesn't give you enough to judge.`,
      ``,
      `Set finding_id to ${item.index}. Give a one-line reason from YOUR OWN read of the code.`,
    ].join('\n'),
    { schema: VERIFIER_HANDOFF, label: `verify-finding-${item.index}`, phase: 'Verify' },
  )
  if (verdict) {
    verdicts.push({
      index: item.index,
      verdict: verdict.verdict,
    })
    log(`Finding #${item.index}: ${verdict.verdict}`)
  }
}

// ---------------------------------------------------------------------------
// Write-back — apply every verdict to findings.json via the Python core. The
// finding record IS the overlay (no separate verifier artifact); apply_verdicts_
// to_run loads, applies, and saves in place.
// ---------------------------------------------------------------------------
phase('Write-back')
const verdictsJson = JSON.stringify(verdicts)
const WRITEBACK_SNIPPET = [
  'import json, sys',
  'from verifier import apply_verdicts_to_run',
  'run_dir, verdicts = sys.argv[1], json.loads(sys.argv[2])',
  'updated = apply_verdicts_to_run(run_dir, verdicts)',
  'print(f"wrote {len(updated)} findings back to findings.json")',
].join('; ')
await agent(
  [
    `Write the verifier verdicts back into findings.json in \`${runDir}\`.`,
    `From the repo root, run (single-quote the code, pass the JSON as a separate arg):`,
    ``,
    `  cd studio && python -c '${WRITEBACK_SNIPPET}' "${runDir}" '${verdictsJson}'`,
    ``,
    `(Installed repos: cd into .studio/source/ instead, where verifier.py lives.)`,
    `Return a one-line confirmation of what it printed.`,
  ].join('\n'),
  { label: 'write-back-verdicts', phase: 'Write-back' },
)

const summary = {
  verified: verdicts.length,
  confirmed: verdicts.filter((v) => v.verdict === 'confirmed').length,
  demoted: verdicts.filter((v) => v.verdict === 'unconfirmed').length,
  uncertain: verdicts.filter((v) => v.verdict === 'uncertain').length,
}
log(`Done. verified=${summary.verified} confirmed=${summary.confirmed} demoted=${summary.demoted} uncertain=${summary.uncertain}`)
return summary
