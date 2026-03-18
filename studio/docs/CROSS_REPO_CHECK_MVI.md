# Cross-Repo Version Check — MVI Scope

`studio check` compares the installed `.studio/VERSION` file against the Studio source repo on the local filesystem. It reports whether the installed copy matches the source version. If the source path is unreachable, it prints: `"Cannot verify: source repo not found at <path>. Re-run 'studio init --target .' to update."` No files are modified; the command is read-only.

`studio check` does NOT make network calls. It cannot detect upstream changes that have not been pulled into the local source repo. This is an intentional constraint for the $0/mo budget and zero-dependency architecture. HTTP-based version checking is deferred to a future milestone. To make this limitation visible, the CLI output must always surface the line: `"Comparing against local Studio source at <path>"` so users understand the scope of the comparison. When implementing M3, use this doc as the contract for honest UX messaging.
