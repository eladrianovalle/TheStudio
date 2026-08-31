---
feature: The static-check command comes from detection, not from a guess
slug: detected-static-check-command
ticket: https://github.com/eladrianovalle/TheStudio/issues/131
status: approved
studio_run: studio/output/tech/run_tech_20260827_220909
# Leave the two below EMPTY until this spec flips to `shipped`, and keep their notes on
# comment lines like these. An inline `# ...` after the colon is read as the VALUE, and
# `shipped_changed` has no vocabulary check to catch it — so a spec could otherwise
# satisfy the gate having edited nothing.
# shipped_impact: one of none | minor | major — how much it changed downstream
# shipped_changed: one line, in plain words, on what this actually changed
shipped_impact:
shipped_changed:
---

# The Static-Check Command Comes From Detection — Architecture Spec

## In Plain Language

When `/forge` builds a unit of work, it runs a linter over the result. Studio already works out
which linter your repository has — it reads your `package.json` and knows you use eslint, or sees a
`pyproject.toml` and knows it's ruff. Then it throws that away. The actual command is written by an
AI, from an instruction whose only worked example is `ruff check`. So a Node project is correctly
told "a lint check is required" and handed a Python command.

That is the same wrong-reason failure the stack-aware gates removed for the *test* command, one
level down, and the fix is the same shape: the command comes from what's in the repository.

There's a second, quieter problem this fixes. The setting that holds this — `static_checks` — has
two meanings in the wild. Studio's own documentation says it holds tool *names* (`["ruff"]`), and
the code only ever checks whether the list is empty. But Alfred's config holds a *command*
(`["make lint"]`), with a careful comment explaining what it does. Nothing has ever run it. After
this change the list holds commands and they actually run, so Alfred's lint starts working without
Alfred changing a line.

One honest limit, stated up front because it would otherwise read as more than it is: the paths the
lint command is scoped to are **predicted** when the unit's arguments are built, before the writer
has touched anything. That is exactly as accurate as today's guess. What changes is *which command*
runs, not how precisely it is aimed.

## Architecture at a Glance

```mermaid
flowchart TD
    subgraph DETECT["Detection — impl_loop.py"]
        PJ["package.json"] --> NP["_node_profile"]
        PY["pyproject.toml"] --> PR["PROFILES['python']"]
        NP --> SP["StackProfile.static_checks<br/>now COMMANDS, not names"]
        PR --> SP
    end

    OV[".studio/implementation_loop.toml<br/>(project override)"] -->|"merges over"| MERGE["load_loop_config"]
    SP --> MERGE
    MERGE --> GUARD{"a bare tool name?<br/>ruff / eslint / mypy"}
    GUARD -->|"yes"| REFUSE["LoopConfigError:<br/>names the file, the entry,<br/>and the line to write"]
    GUARD -->|"no"| KNOBS["runtime_knobs → /forge"]

    KNOBS --> SUB{"command holds<br/>{paths}?"}
    SUB -->|"yes, and paths predicted"| SCOPED["substitute → 'ruff check \"a.py\" \"b.py\"'"]
    SUB -->|"yes, but no paths"| SKIP["skip the check, say why"]
    SUB -->|"no token"| VERBATIM["run as written<br/>('make lint', 'npm run lint')"]

    SCOPED --> W["writerPrompt: run every command,<br/>static_ok is the AND"]
    VERBATIM --> W

    style REFUSE fill:#f5b7b1,stroke:#c0392b
    style SKIP fill:#fdebd0,stroke:#b7950b
    style W fill:#d5f5e3,stroke:#27ae60
```

The one field now answers both questions it used to split: a non-empty `static_checks` means a check
is required *and* says what runs. The amber branch is the safety property — when there are no paths
to scope to, the check is skipped rather than silently widened to the whole repository.

## How It Works (Technical)

### The field becomes commands

`StackProfile.static_checks` and `LoopConfig.static_checks` keep their types. Only the meaning of an
element changes: a shell command, optionally containing the literal token `{paths}`.

- `PROFILES["python"]` → `("ruff check {paths}",)`
- `LoopConfig.static_checks` default → `["ruff check {paths}"]`. Unreachable in production (the
  loader always passes gate keys in) but it is the shape a reader copies, so it must be right.

`.claude/workflows/implementation-loop.js:322-327` currently documents the duality — `static_checks`
gates *whether*, `static_check` is *what* — and ends by naming this change as its own removal
instruction: *"If the schema ever consolidates on the array, drive the command off it here and in
writerPrompt too, so the two don't drift."* So `static_check` (singular) is deleted from
`DEFAULT_UNIT:30`, `writerPrompt:212`, and `forge.md:113,241`.

**Multi-element lists need a stated rule**, because the type has always been a list and
`test_impl_loop.py:151` already exercises `["ruff", "mypy"]`. Under the old duality that was fine —
the array was a flag. Now: **every element runs, and `static_ok` is the AND across them.** Said
where the type is defined, because `WRITER_HANDOFF` carries a single `static_ok` boolean under
`additionalProperties: false` (`implementation-loop.js:104,126`), so there is no room to report per
command and the aggregate has to be the contract.

### Node tells its two signals apart

`_node_profile` (`impl_loop.py:182-205`) currently collapses both causes into one flag:

```python
has_linter = "lint" in scripts or "eslint" in dev_dependencies   # :199
```

| package.json says | `static_checks` |
|---|---|
| a `lint` script with a non-blank body | `("npm run lint",)` — **no token** |
| no usable `lint` script, `eslint` in devDependencies | `("npx eslint {paths}",)` |
| neither | `()` |

**The `.strip()` is not a detail.** Line `:198` is already careful for the test script —
`bool(str(scripts.get("test", "")).strip())` — while `:199` is membership-only. That asymmetry was
harmless while the array was a flag. Once a `lint` script *becomes the command*, a repo with
`"lint": ""` or `"lint": "echo TODO"` exits 0 and reports a clean static check having run nothing.
Mirror `:198`.

**The lint script carries no `{paths}`, deliberately.** `npm run lint -- src/foo.js` appends to a
script that usually already ends in a target (`eslint .`), which widens the run rather than narrowing
it. The reason is written beside the branch so the next reader does not "fix" it by adding `-- {paths}`.

### Scoping: an explicit `{paths}` token

`/forge` replaces every `{paths}` with the unit's predicted paths, space-separated, each
double-quoted. A command with no token runs verbatim.

**Why a token rather than provenance.** The obvious rule — append paths only to commands Studio
*detected*, never to one from an override — is knowable at `impl_loop.py:504`, where
`gate.get("static_checks", ...)` distinguishes the two. It is destroyed by Studio's own wizard:
`_format_loop_toml` writes the detected value *into* the override file (`setup.py:651`), and
`apply_implementation_loop_config` never overwrites it afterwards. One `/studio-setup` run turns a
detected command into a project-supplied one, provenance then says "don't append paths," and
`ruff check` silently widens to the whole repository. The rule self-destructs through Studio's own
tooling. The token travels inside the string, so it survives that round-trip, and an override author
can opt into scoping — which provenance could never offer.

**No paths means skip, not `.`.** Substituting `.` would lint the entire repository, so any
pre-existing lint debt anywhere fails a unit for code it never touched — the precise wrong-reason
failure this work exists to delete. The config already has a first-class way to say "don't run this"
(the empty list at `implementation-loop.js:327`); no-paths takes the same branch and logs why.

**And the honest limit.** `writerPrompt` is rendered at `implementation-loop.js:320`, *before* the
writer runs; `files_touched` does not exist until the handoff comes back. So `{paths}` carries paths
`/forge` predicted from the unit's instructions — the same guess `static_check` makes today, at the
same accuracy. This change fixes *which command*, not how well it is aimed. Anyone maintaining this
should know that before reading "the unit's touched paths" and believing it.

### The leftover-name guard

`_require_gate_commands` (`impl_loop.py:306`) refuses an entry equal to `ruff`, `eslint` or `mypy` —
the only names Studio ever shipped — with a message in the house style of `_no_test_command_message`,
naming the file, the entry, and the replacement (`"ruff"` → `"ruff check {paths}"`). Any other single
word is accepted verbatim: Studio owes migration only for values it authored, and a "looks like a
name" heuristic would refuse someone's legitimate one-word script.

**The justification is the wizard, not the fleet, and the difference decides the message.** No
project override on this machine holds a bare name — only `_Alfred` (`["make lint"]`) and
`Orkid Garden` (`[]`), both already valid. But `/studio-setup` in any Python repo writes
`static_checks = ["ruff"]` today and never overwrites it, so every wizard run between now and this
change plants one that no update will clean up. The refusal therefore points at
`.studio/implementation_loop.toml`, which is where a wizard-written value lives.

Two installed repos (`_Cerebro`, `OrcPunk-biz`) *do* carry a bare `ruff`, in the shipped-config
snapshot at `.studio/source/config/implementation_loop.toml`. That is harmless and needs no shim:
`impl_loop.py` and the shipped config are both in `SOURCE_FILES` (`install.py:67`), so they update in
lockstep and no repo can get the new semantics without the new config. Stated here so nobody builds
a migration for a split-brain that cannot happen.

### Docstrings that will be wrong the moment this ships

`_require_gate_commands`'s own docstring (`impl_loop.py:315-316`) currently says *"`static_checks` is
never a refusal … and the command that runs is authored per unit by /forge."* That is the bug,
written down, inside the function the guard is added to.

`specs/stack-aware-forge-gates.md:206` is at `status: shipped` and records the rationale for the
current design. It gets a line saying this spec supersedes that reasoning — not a silent edit.

## Key Decisions

- **One field, holding commands.** Collapses a documented duality that had already produced two
  incompatible readings in the wild. Alfred's `["make lint"]` starts running as written.
- **`{paths}` token over provenance**, because the wizard's detected→override round-trip destroys
  provenance and no amount of care at the merge point survives it.
- **No paths → skip, not `.`**, so the check never widens to code the unit didn't touch.
- **Every element runs; `static_ok` is the AND.** Forced by the closed handoff schema, and better
  stated than discovered.
- **Refuse a leftover bare name rather than auto-upgrading it.** An auto-upgrade leaves the config
  file saying one thing and the loop running another — the exact class of bug being fixed.
- **Three cut on the contrarian's advice:** a writer instruction to report a missing linter as
  `static_ok: false` (it shuts the entry gate over a *config* problem, and duplicates the escalation
  trigger already at `implementation-loop.js:224`); an editor static re-run (`EDITOR_HANDOFF` is
  `additionalProperties: false` with no static field, and `passesExitGate` reads only tests — prompt
  words with no enforcement); and a separate migration unit (the guard is meaningless without the
  semantics change and the change is unsafe without the guard).

## Non-Goals / Cut Scope

- Any change to `passesExitGate`, or a second revert trigger. The gate stays keyed on tests.
- Any editor-prompt change, and any new field on either handoff schema.
- Making the scoping accurate — `{paths}` inherits today's prediction accuracy and this spec does not
  claim to improve it.
- Auto-upgrading a leftover name, or editing any consuming repo's config.
- A migration shim for `.studio/source` snapshot skew, which cannot desynchronise.
- `mypy` gaining a profile. It appears only in the refusal list, as a name Studio once documented.

## Risks & Open Questions

- **The `lint`-script branch is the common Node case and gets no scoping.** Justified above, but it
  means most Node repos lint their whole tree per unit. If that turns out to fail units for unrelated
  debt, the answer is the empty-list escape, not a token bolted onto `npm run lint`.
- **`{paths}` is a template token in a hand-edited TOML file.** Small, but it is syntax a user can get
  wrong, and a typo (`{path}`) silently runs the command unscoped rather than erroring.
- **Multi-element lists are now genuinely executable** and nothing bounds how many. A config with five
  commands makes a slow gate with one boolean of feedback.
- **The byte-exact prompt fixture must be regenerated** as part of the build, not after — deleting
  `static_check` changes both `fixtures/prompts-no-work-dir.json`'s `unit` object and its frozen
  `writer_prompt` text, and the in-repo `UNIT` at `workflow-shells.test.mjs:81`. Missed, the workflow
  suite goes red for a reason the writer will misread as its own bug.

## Build Plan

Two units. The migration guard is folded into the first because the guard is meaningless without the
semantics change and the change is unsafe without the guard — shipping them apart leaves a window
where one is in and the other is not.

### 1. `static_checks_are_commands` — the lint command comes from the repo, and a leftover name refuses

**Acceptance criteria:**
- [ ] `resolve_profile` on a Python repo returns `static_checks == ("ruff check {paths}",)`, and `_node_profile` returns `("npm run lint",)` for a non-blank `lint` script, `("npx eslint {paths}",)` for an `eslint` devDependency with no usable script, and `()` for neither — with a test proving a `"lint": ""` or whitespace-only script takes the third case, not the first.
- [ ] `load_loop_config` raises `LoopConfigError` on a `static_checks` entry equal to `ruff`, `eslint` or `mypy`, naming the config file, the entry, and the replacement; a one-word entry Studio never shipped (e.g. `pylint`) is accepted verbatim and raises nothing.
- [ ] `_Alfred`'s exact override (`static_checks = ["make lint"]`, `test_command = "make test"`) and `Orkid Garden`'s (`static_checks = []`) both load unchanged and raise nothing.
- [ ] No `static_check` (singular) identifier remains in `.claude/workflows/implementation-loop.js` or `.claude/commands/forge.md`; `writerPrompt` renders every element of `static_checks`, and behaviour on `[]` is unchanged.
- [ ] `.claude/workflows/tests/fixtures/prompts-no-work-dir.json` and the in-file `UNIT` are regenerated for the removed key, and the workflow suite passes via `node --test .claude/workflows/tests/workflow-shells.test.mjs`.
- [ ] `cd studio && python -m pytest tests/ -q` passes, `ruff check .` is clean, and `_require_gate_commands`'s docstring no longer says the command is authored per unit by `/forge`.

**Out of scope:** `setup.py`, `passesExitGate`, the editor prompt, and any handoff schema field.

### 2. `wizard_writes_static_commands` — the file `/studio-setup` writes says what actually runs

**Acceptance criteria:**
- [ ] `_format_loop_toml` on a Python profile emits `static_checks = ["ruff check {paths}"]`, and on a Node profile with a `lint` script emits `static_checks = ["npm run lint"]`.
- [ ] The comment block in the written file explains in one line that `{paths}` is substituted and that a command without it runs as written.
- [ ] A file written by `apply_implementation_loop_config` parses back through `load_loop_config` to the same `static_checks` list, and raises nothing — the round-trip that defeats a provenance rule, pinned so it cannot regress.
- [ ] `studio/docs/IMPLEMENTATION_LOOP_SPEC.md` (the §4 table row, the config example, and the lint/static-only note), `studio/docs/CLAUDE_CODE_USAGE.md`, and `.claude/commands/forge.md`'s knob paragraph all describe commands rather than names.
- [ ] `specs/stack-aware-forge-gates.md` carries a line recording that this spec supersedes its static-check rationale.
- [ ] Suite green, `ruff check .` clean.

**Out of scope:** any change to detection or the refusal, and any edit to a consuming repo's config file.
