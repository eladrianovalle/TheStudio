# Reviewer concerns — finish_check_install_entry

## 1. Acceptance criterion 3 asks for something `init` cannot give, and should not

**The concern.** Criterion 3 reads:

> A `settings.local.json` that is a JSON array, one whose `hooks` is a string, and one whose
> `hooks.Stop` is a dict each produce one warning and a byte-identical file from both `init` and
> `update`, raising nothing.

Two of the three shapes hold. The third does not, and cannot. When `hooks.Stop` is a dict, `hooks`
itself is a perfectly good JSON object, so the *SessionStart* installer — which has no interest in
`Stop` — goes ahead and writes its own update-check entry. The file is therefore not byte-identical
after `init` or `update`, even though the finish-check installer behaved exactly as intended.

Measured directly against this build:

```
C3 array:        identical after init=True  after update=True
C3 hooks-string: identical after init=True  after update=True
C3 stop-dict:    identical after init=False after update=False
```

What *does* hold for the dict case, and is what the criterion was reaching for: exactly one warning
("has a non-list 'hooks.Stop'; ... skipped the finish-check hook"), `hooks.Stop` returned untouched
as `{"oops": "a dict"}`, no entry of ours added, and nothing raised.

**Why it is unresolved: out_of_unit_scope.** The only code change that would satisfy the criterion
literally is making `_install_sessionstart_hook` bail out over a malformed `Stop` key that is none of
its business — silently costing a user their session brief because of an unrelated typo elsewhere in
the file. That is a worse product than the one that exists. The criterion is over-stated, not the
code under-built, and amending an approved spec's acceptance criteria is a human's call rather than
the editor's.

**Smallest follow-up.** Reword criterion 3 in `specs/shipped-finish-check.md` so the byte-identity
claim is scoped to the finish-check installer instead of the whole install: for example, "…each
produce one warning from the finish-check installer, leave `hooks.Stop` exactly as it was, add no
entry of ours, and raise nothing." The existing tests already assert precisely that
(`TestFinishCheckMalformedSettings::test_one_warning_and_no_write` over all three shapes, plus
`test_install_and_update_leave_a_dict_stop_alone`), so no test has to change.
