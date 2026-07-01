# Cross-Repo Version Check

*Shipped as the `check-install` command (originally scoped here as `studio check`).*

`python studio/run_phase.py check-install --target <path>` tells you whether the Studio installed in another repo is up to date with the source. It checksums every installed file against the live Studio source — resolved from the pointer recorded in the target's `.studio/VERSION` at install time — and reports the result. If everything matches it prints `Studio at <path> is up to date.` Otherwise it prints `needs updating:` followed by the `Changed:` and `Missing:` file lists and a `Run: ... update --target <path>` hint. It also warns about any installed files that have local edits an update would overwrite. No files are modified; the command is read-only.

`check-install` makes no network calls — it compares against the Studio source repo on the local filesystem, so it can't see upstream commits that haven't been pulled into that source. This is an intentional constraint for the $0/mo, zero-dependency architecture; HTTP-based upstream checking is deferred. When the source can't be reached (the recorded path is missing, moved, or points back at the installed snapshot), the command prints a `WARNING:` that says it cannot compare against live source and points you at the re-run command — so the scope of the comparison is never silently misrepresented.
