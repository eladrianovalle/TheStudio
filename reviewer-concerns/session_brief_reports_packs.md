# Reviewer concerns: session_brief_reports_packs

- [ ] **A broken config with no `[packs]` table is reported as a pack problem.**
  - Concern: `session_note` turns any `PackConfigError` from `load_declaration` into "1 pack problem; first: ...", and `load_declaration` raises one for any TOML syntax error in `.studio/implementation_loop.toml`. A repository that declares no pack but has a typo in `[gate]` (checked: `[gate\n`) gets "1 pack problem; first: .../implementation_loop.toml: not valid TOML: ..." in every session brief. That bends criterion 1 ("With no `[packs]`, `check-updates` prints nothing new") and names the wrong subsystem.
  - Why unresolved: out of unit scope. Which reading is right is a spec decision: the file can't be parsed, so nobody can tell whether it has a `[packs]` table.
  - Follow-up: decide in `specs/pack-mechanism.md` whether an unparseable config is reported. If it is, word it as a config problem ("implementation_loop.toml is not valid TOML") rather than a pack problem.
