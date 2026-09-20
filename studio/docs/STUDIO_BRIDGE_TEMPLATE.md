# Studio ↔ Project Bridge Template

Copy this into a repo that uses Studio, as `docs/studio-bridge.md`. Studio writes it for you on the first run in a new repo, substituting the Studio path; the rest is yours to fill in.

Its job is to hold the two things Studio cannot work out for itself: what this project *is*, and which documents count as canon here. Everything about how to drive Studio lives in the slash commands and in the coding-principles block injected into your `CLAUDE.md` — this file deliberately does not repeat it.

## 1. What this project is
- **Project:** `<PROJECT_NAME>` — one line an outsider would understand.
- **Why it uses Studio:** one line. For example, "we stress-test design decisions before building them."
- **Where the current plan lives:** link the roadmap, milestone or issue an agent should read for recency.

## 2. Studio location
- Studio root: set via the `STUDIO_ROOT` environment variable (e.g., `export STUDIO_ROOT="/path/to/studio"`).
- You drive Studio through its slash commands — `/run-phase`, `/run-studio-phase`, `/spec`, `/forge`, `/studio-setup`. There is no runtime and no API; the debate happens inside your assistant.
- Artifacts land in this repo under `.studio/output/`. Override with `STUDIO_ARTIFACT_ROOT` if you need them elsewhere.

## 3. Canon
The documents that count as authoritative here, so an agent has the full picture and does not invent one. Keep this current — a stale canon list is worse than none, because it is trusted.

| Canon doc | Why it matters | Last updated |
| --- | --- | --- |
| `<path>` | `<what it settles>` | `<YYYY-MM-DD>` |

## 4. Maintenance
- Update the Studio path here if the repo moves or `STUDIO_ROOT` changes.
- Staying current is automatic: a SessionStart hook opens each session with a brief — an update nudge when your installed Studio falls behind, and unfinished planned work when an approved spec has a unit nobody built. Turn it off with `studio update --no-hook` or an empty `.studio/update-check.off`.
- Studio's specs and their evidence files under `.studio/specs/` are **tracked docs meant to be committed** — unlike `.studio/output/` and `.studio/knowledge/`, which must not be. If your `.gitignore` ignores `.studio/`, git silently refuses to track them, and the obvious one-line fix does not work: git cannot re-include a file whose parent directory is excluded, so `!.studio/specs/` under a `.studio/` rule does nothing. Use this form:

  ```gitignore
  .studio/*
  !.studio/specs/
  ```

  Confirm with `git ls-files .studio/specs/`, which prints the tracked paths. Do **not** use `git check-ignore -v` here: on a negated pattern its output reads as a match either way, and it will tell you the file is ignored when it is not.
