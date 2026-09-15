# Reviewer Concerns — wizard_writes_stamped_template

Raised by the editor pass on commit `9b75191`. Both survived the pass; neither could be
fixed here without breaking the unit's own acceptance criteria.

## 1. `is_wizard_template` has no caller outside its tests

**The concern.** The spec says the stamp "exists so the wizard can tell its own untouched
template from a person's file, and for nothing else." Nothing in the shipped code makes
that distinction. `apply_implementation_loop_config` decides with

```python
    if config_path.exists():
        print(f"Kept the existing {config_path} — setup never overwrites one.")
```

which keeps any existing file, stamped or not, so `is_wizard_template` is never consulted.
Its only seven call sites are in `studio/tests/test_setup.py`. As shipped it is a public
predicate that answers a question no production path asks.

**Why it is unresolved.** load_bearing. Acceptance criterion 5 names the function by name,
and seven tests pin its behaviour; deleting it would fail the unit and redden the suite.

**Smallest follow-up.** Decide which it is, in the unit that needs the answer: either give
it a real reader (the obvious one is `update`, which could refresh its own untouched
template while still refusing to touch a hand-written file), or drop the function and the
stamp's stated purpose down to what the file actually uses it for — a provenance line a
person reads.

## 2. The loader's refusal still tells you to run the wizard that just ran

**The concern.** After the wizard writes the blank template, `/forge`'s refusal ends with

```
Set the command in <path>/.studio/implementation_loop.toml:

    [gate]
    test_command = "<the command that runs this repo's tests>"

Or run /studio-setup, which writes that file for you.
```

The file it names now exists and already has that `[gate]` block in it, and re-running
`/studio-setup` will deliberately leave it alone. The advice is a loop.

**Why it is unresolved.** out_of_unit_scope. The text lives in
`studio/impl_loop.py::_no_test_command_message`, which this unit does not touch, and unit 2
(`gate_keys_resolve_to_none`) already owns rewording the refusal around whether the file
exists.

**Smallest follow-up.** In unit 2, drop the "Or run /studio-setup" sentence from the branch
where the config file is present, and point at the blank `test_command` line instead.
