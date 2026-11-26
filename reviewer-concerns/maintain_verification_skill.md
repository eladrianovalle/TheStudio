# Reviewer concerns: maintain_verification_skill

## The scheduled job may not find `claude`

- **Concern:** The plist runs `<string>claude</string>` by bare name, and the doc says "`claude`, `node` and `gh` live in Homebrew's prefix". Claude Code's native installer puts `claude` in `~/.local/bin`, which the recipe's `PATH` leaves out. It is also unproven that launchd looks up `ProgramArguments[0]` on the job's own `EnvironmentVariables` `PATH` rather than its default one. Either way the daily job could fail before Claude starts. Confidence: medium, verify this.
- **Why unresolved:** out of unit scope. Proving it means loading a real LaunchAgent on the user's machine, which this pass can't do, and the plist's paths are a load-bearing part of the recipe.
- **Follow-up:** Have the plist's first `ProgramArguments` entry be the absolute path that `which claude` prints, and say so in the line about `PATH`. Then load the agent once with `launchctl kickstart` and check that `out.log` ends with an `OUTCOME:` line.
- **Resolution:** The recipe's first `ProgramArguments` entry is now the absolute path `which claude` prints, and the `PATH` sentence says why. It also tells the reader to run the job once with `launchctl kickstart` and check `out.log` for an `OUTCOME:` line before relying on it. No real LaunchAgent has been loaded yet, so the schedule itself is still unproven.
