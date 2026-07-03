# Smoke: Stand Up a Live Version to Hand-Test

Build and launch a live, running version of whatever this repo produces so the user can smoke test it by hand, then hand them the entry point and a short golden path to click through.

A **smoke test** here is not automated: it's you standing the product up in a running state — a web app on a local URL, a game in Play mode, a service listening on a port, a CLI you can invoke — and handing it to the user to poke at. Tests-green means the code compiles and unit tests pass; a smoke means *the thing actually runs and a human can use it*.

This command is **stack-agnostic**. It detects what kind of product the repo builds (website, game, software, service) and stands up *that*. A repo can pin exactly what "live" means for it with an optional `.studio/smoke.toml` (schema at the bottom).

## Arguments

- `$ARGUMENTS`: Optional. A hint about what to smoke, e.g. `--focus "the new lobby screen"` to seed the golden path, or `--teardown` to stop a smoke you started earlier and skip standing up a new one. Default: stand up the whole product.

## Instructions

Your goal: get a running instance in front of the user with the least ceremony, confirm it's actually up before handing off, and tell them exactly how to reach it and what to try. You are not writing tests here — you are standing up the real thing.

### Phase 0: Resolve the Smoke Profile

Figure out what "live" means for this repo before you launch anything.

**1. Config override (preferred when present).** If `.studio/smoke.toml` exists, load it and use its values verbatim. Skip stack detection. Recognized keys, all under `[smoke]` and all optional:

- `kind` — one of `web`, `game`, `service`, `cli`, `desktop`, `library`, `custom`. Shapes how you launch and hand off.
- `setup` — list of one-time prep commands run before launch (install deps, run migrations, import assets).
- `build` — list of build commands run after setup, before launch.
- `launch` — the long-running command that stands the thing up. You run this in the **background** so it stays alive after you hand off.
- `url` — for `web`/`service`: the address you open and point the user to.
- `ready_probe` — a shell command you poll until it exits 0, meaning the instance is up (e.g. a `curl` against the health endpoint).
- `ready_log` — alternatively, a substring in the launch output that signals readiness (e.g. `"ready in"`, `"listening on"`).
- `golden_path` — an ordered list of things the user should try. You present these as a checklist.
- `teardown` — list of commands that stop the instance and clean up.

Use whatever keys are present; fall back to detection (below) for anything the file omits.

**2. Stack self-detection (when no config, or to fill gaps).** Inspect marker files in the repo root and resolve a profile:

| Marker file(s) | `kind` | How to stand it up |
|---|---|---|
| `package.json` | `web` (or `service`/`cli`) | Read `scripts`. Prefer `dev`, then `start`, then `serve`. Run `install` first if `node_modules/` is missing. Launch backgrounded; the ready line is usually the printed local URL. |
| `Cargo.toml` | `cli` (or `service`) | `cargo run` (or `cargo run --release`). For a bin+server, treat the listening log line as ready. |
| `*.csproj` or `ProjectSettings/` | `game` | Unity. Stand up via the Unity MCP: enter Play mode in the editor (see Unity note below). No shell launch. |
| `go.mod` | `service` (or `cli`) | `go run .`; treat the listening log line as ready. |
| `pyproject.toml` / `setup.py` | `cli` (or `web`) | Install editable if needed, then run the package's entrypoint (`python -m <pkg>` or the console script). For a web framework, run its dev server. |
| *(a compose/container file: `docker-compose.yml`, `compose.yaml`)* | `service` | `docker compose up` backgrounded; ready when the health probe passes. |
| *(none of the above)* | `custom` | Ask the user how they normally run this project, then do that. Offer to save the answer to `.studio/smoke.toml`. |

If detection is ambiguous (e.g. `package.json` could be a web app, a service, or a library), **say what you inferred and why**, and let the user correct you before you launch.

**State the resolved profile** — kind, the launch command, how you'll know it's ready, whether config was used — in one short block before continuing, so the user sees what's about to run.

### Phase 1: Stand It Up

1. **Prep.** Run the `setup` commands (or the detected equivalent: install deps, run migrations, import assets). Skip anything already done — don't reinstall if `node_modules/` is present and fresh.
2. **Build.** Run the `build` commands if any. If the build fails, stop and show the user the error; a smoke of a broken build is worthless.
3. **Launch.** Run the `launch` command **in the background** so it keeps running after you finish. Capture its output so you can watch for the ready signal and surface errors.

For a **Unity game** (`kind = game`): don't shell-launch. Use the Unity MCP tools — check the editor state, make sure a scene with a Camera and Light is loaded, then enter Play mode (`manage_editor` play control). Watch `read_console` for errors. "Live" here means Play mode is running and the game is interactive in the editor.

### Phase 2: Confirm It's Actually Up

Never hand off a thing you haven't seen come up.

- If the profile has a `ready_probe`, poll it (a few attempts, short backoff) until it passes. If it never passes within a reasonable window, treat the launch as failed.
- Otherwise watch the launch output for `ready_log` (or the printed URL / "listening" line).
- For a Unity game, confirm Play mode entered and the console shows no errors.
- If it fails to come up: show the captured error output, stop, and don't pretend it's live. Offer to fix and retry.

### Phase 3: Hand Off

Once it's confirmed up, hand the user everything they need to drive it themselves:

- **The entry point**, made obvious: the clickable URL for web/service; "Play mode is running in the Unity editor" for a game; the exact command to run for a CLI; the window/app for desktop.
- **The golden path**: present the profile's `golden_path` as a short checklist of concrete things to try. If none is configured, propose 3–5 based on what the repo builds and on `$ARGUMENTS` if given (e.g. focus the path on the feature just built). Keep each step to one clear action.
- **How it's running**: note that the instance is live in the background and will keep running, and how to stop it (see teardown).

Then let the user test. Don't tear down until they say they're done.

### Teardown

When the user is finished (or if they passed `--teardown`), stop the instance cleanly: run the profile's `teardown` commands, or stop the backgrounded launch process / exit Unity Play mode. Confirm it's down. Leave no orphaned server or port held.

### Key Rules

- **Stand up the real thing, don't fake it.** A smoke is a running instance a human can use, not a test run or a description of what would happen.
- **Confirm up before handoff.** Poll readiness; never say "it's live" on hope.
- **Background the launch** so it outlives this turn and the user can actually poke at it.
- **Fail loud.** A broken build or a launch that won't come up: show the error and stop. Don't hand off a corpse.
- **Don't guess silently.** If the stack is ambiguous or you had to infer the launch command, say so and let the user correct you.
- **Clean up after.** Tear down on request; don't leave ports held or Play mode running.

### Config reference: `.studio/smoke.toml`

Optional. Pin exactly what "live" means for this repo when self-detection isn't precise enough. Every key is optional; omitted keys fall back to stack detection.

```toml
[smoke]
kind        = "web"                          # web | game | service | cli | desktop | library | custom
setup       = ["npm install"]                # one-time prep before launch (deps, migrations, assets)
build       = ["npm run build"]              # build step(s), if any
launch      = "npm run dev"                  # long-running command; run backgrounded
url         = "http://localhost:5173"        # web/service: the address to open and hand off
ready_probe = "curl -sf http://localhost:5173 >/dev/null"  # polled until it exits 0 = up
ready_log   = "ready in"                     # OR: a substring in launch output that means ready
golden_path = [
  "Open the URL and confirm the landing page renders",
  "Create a new farm and plant a crop",
  "Start a deduction round with a second player",
]
teardown    = ["docker compose down"]        # stop + clean up
```
