# Reviewer concerns — `mutation_skip_reason_recorded`

**Status: resolved in the same PR.** `skippedMutationCheckWithoutReason` in
`.claude/workflows/implementation-loop.js` now logs a reasonless skip right after the writer handoff
lands. It logs only; it does not flag the unit.

## 1. Nothing forces a reason when `performed` is false

**Concern.** The unit exists because "another 81 said `performed: false` without ever saying why."
The schema does not close that. `mutation_check` declares:

```js
required: ['performed'],
...
reason: { type: 'string', enum: ['not_configured', 'nothing_to_mutate', 'not_reached'], description: 'why the check did not run — ... omit it when performed is true' },
```

`reason` is optional, so `{"performed": false}` is still a valid handoff. The only thing asking for a
reason is prompt text — the same channel that produced the 81 records in the first place. The
orchestration does not compensate either: the entry gate reads

```js
return !!(writer.mvi_claimed && writer.tests && writer.tests.passed && (!staticRequired || writer.static_ok !== false))
```

and never looks at `mutation_check` at all, so a reasonless skip sails through unflagged.

**Why unresolved.** Out of unit scope. Acceptance criterion 1 fixes the object's required list as
exactly `['performed']`; making `reason` conditionally required would contradict the criterion this
unit is graded against.

**Follow-up.** Smallest fix: in the orchestration, right after the writer handoff comes back, log and
flag a handoff whose `mutation_check.performed` is false with no `reason`. That catches it where the
data already lands, without asking the tool-input schema to express an `if/then`.
