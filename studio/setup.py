"""
Studio setup wizard: project configuration after install.

Tracks setup state in ``.studio/SETUP.json`` and generates configuration
files (``.studio/roles/*.json``, ``.studio/personas.toml``, etc.) based on
user choices.  Supports incremental setup: when new configurable features
are added (bumping ``CURRENT_SETUP_VERSION``), the wizard detects pending
steps and prompts re-configuration.

Usage via run_phase.py:
    python run_phase.py setup --target /path/to/project --status
    python run_phase.py setup --target /path/to/project --defaults
    python run_phase.py setup --target /path/to/project --answers answers.json
    python run_phase.py setup --target /path/to/project --role-pack studio_core
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Version & step registry
# ---------------------------------------------------------------------------

# Bump when adding new configurable features so the wizard detects them.
CURRENT_SETUP_VERSION = 5

SETUP_STEPS: List[Dict[str, Any]] = [
    {"name": "role_pack", "introduced_at": 1, "label": "Role Pack Selection"},
    {"name": "role_customization", "introduced_at": 1, "label": "Role Customization"},
    {"name": "cleanup", "introduced_at": 1, "label": "Cleanup Settings"},
    {"name": "persona_customization", "introduced_at": 2, "label": "Phase Persona Customization"},
    {"name": "unstale_config", "introduced_at": 3, "label": "Unstale Audit Configuration"},
    {"name": "smoke_config", "introduced_at": 4, "label": "Smoke Test Configuration"},
    {"name": "implementation_loop_config", "introduced_at": 5, "label": "Forge Gate Commands"},
]

# O(1) lookup by step name
_STEPS_BY_NAME: Dict[str, Dict[str, Any]] = {s["name"]: s for s in SETUP_STEPS}

SETUP_FILE = "SETUP.json"
# Schema version for the SETUP.json format (bump on structural changes).
SCHEMA_VERSION = 1

DEFAULT_CLEANUP = {"ttl_days": 30, "size_limit_mb": 900}

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def _empty_state() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "setup_version": 0,
        "completed_steps": {},
        "choices": {},
        "timestamps": {},
    }


def load_setup_state(target: Path) -> Dict[str, Any]:
    """Read ``.studio/SETUP.json`` or return empty state."""
    setup_path = Path(target).resolve() / ".studio" / SETUP_FILE
    if not setup_path.exists():
        return _empty_state()
    try:
        data = json.loads(setup_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_state()
        return data
    except (json.JSONDecodeError, ValueError):
        return _empty_state()


def save_setup_state(target: Path, state: Dict[str, Any]) -> None:
    """Write ``.studio/SETUP.json``."""
    target = Path(target).resolve()
    setup_path = target / ".studio" / SETUP_FILE
    setup_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.setdefault("timestamps", {})
    if "first_setup" not in state["timestamps"]:
        state["timestamps"]["first_setup"] = now
    state["timestamps"]["last_setup"] = now
    state["setup_version"] = CURRENT_SETUP_VERSION
    setup_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def pending_steps(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return setup steps that need (re-)configuration."""
    completed = state.get("completed_steps", {})
    result: List[Dict[str, Any]] = []
    for step in SETUP_STEPS:
        completed_at = completed.get(step["name"], 0)
        if completed_at < step["introduced_at"]:
            result.append(step)
    return result


def _mark_step(state: Dict[str, Any], step_name: str) -> None:
    """Record that *step_name* was configured at its ``introduced_at`` version."""
    state.setdefault("completed_steps", {})
    step = _STEPS_BY_NAME.get(step_name)
    if step is not None:
        state["completed_steps"][step_name] = step["introduced_at"]


# ---------------------------------------------------------------------------
# Manifest & pack helpers. Delegates to run_phase_roles where possible
# ---------------------------------------------------------------------------


def _find_studio_dir(target: Path) -> Path:
    """Locate the studio source directory for a target project.

    Checks ``.studio/source/`` (cross-repo install) first, then falls
    back to the directory containing this file (running from source).
    """
    installed = Path(target).resolve() / ".studio" / "source"
    if (installed / "studio.manifest.json").exists():
        return installed
    return Path(__file__).resolve().parent


def get_manifest_roles(studio_dir: Optional[Path] = None) -> Dict[str, Dict]:
    """Return all roles from the manifest with their full definitions."""
    if studio_dir is None:
        studio_dir = Path(__file__).resolve().parent
    from run_phase_roles import load_manifest
    manifest = load_manifest(studio_dir)
    return manifest.get("roles", {})


def get_available_packs(studio_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return all role packs with name, description, and roles list."""
    if studio_dir is None:
        studio_dir = Path(__file__).resolve().parent
    packs_dir = studio_dir / "role_packs"
    if not packs_dir.is_dir():
        return []
    result: List[Dict[str, Any]] = []
    for path in sorted(packs_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result.append({
                "name": data.get("name", path.stem),
                "description": data.get("description", ""),
                "roles": data.get("roles", []),
            })
        except (json.JSONDecodeError, ValueError):
            continue
    return result


def get_default_pack_name(studio_dir: Optional[Path] = None) -> str:
    """Return the default role pack name from the manifest."""
    if studio_dir is None:
        studio_dir = Path(__file__).resolve().parent
    from run_phase_roles import load_manifest, default_role_pack_name
    manifest = load_manifest(studio_dir)
    try:
        return default_role_pack_name(manifest)
    except Exception:
        return "studio_core"


# ---------------------------------------------------------------------------
# Apply functions. Each generates config files and updates state
# ---------------------------------------------------------------------------


def apply_role_pack(
    target: Path,
    pack_name: str,
    overrides: Optional[List[str]] = None,
    state: Optional[Dict[str, Any]] = None,
    _save: bool = True,
) -> Dict[str, Any]:
    """Select a role pack and optional +/- overrides.

    Stores the choice in state but does NOT generate role override files
    (that's the role_customization step).

    Returns the resolved role list.
    """
    from run_phase_roles import load_manifest, load_role_pack, resolve_role_list

    target = Path(target).resolve()
    studio_dir = _find_studio_dir(target)
    manifest = load_manifest(studio_dir)

    # load_role_pack raises RoleConfigError for invalid pack names
    pack_data = load_role_pack(studio_dir, pack_name)
    roles = resolve_role_list(manifest, pack_data, overrides)

    if state is None:
        state = load_setup_state(target)

    state.setdefault("choices", {})
    state["choices"]["role_pack"] = pack_name
    state["choices"]["role_overrides"] = overrides or []
    state["choices"]["resolved_roles"] = roles
    _mark_step(state, "role_pack")
    if _save:
        save_setup_state(target, state)

    return {"pack": pack_name, "roles": roles}


def apply_role_customization(
    target: Path,
    customizations: Dict[str, Dict],
    state: Optional[Dict[str, Any]] = None,
    _save: bool = True,
) -> None:
    """Write per-role override files to ``.studio/roles/``.

    ``customizations`` maps role name -> override fields dict.
    Empty dict means "no customizations, accept defaults".
    """
    from role_overrides import validate_role_override

    target = Path(target).resolve()
    roles_dir = target / ".studio" / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    for role_name, fields in customizations.items():
        validate_role_override(role_name, fields)
        override_path = roles_dir / f"{role_name}.json"
        override_path.write_text(
            json.dumps(fields, indent=2), encoding="utf-8"
        )

    if state is None:
        state = load_setup_state(target)
    state.setdefault("choices", {})
    state["choices"]["role_customizations"] = {
        k: list(v.keys()) for k, v in customizations.items()
    }
    _mark_step(state, "role_customization")
    if _save:
        save_setup_state(target, state)


def _toml_quote(value: str) -> str:
    """Quote and escape *value* as a TOML basic string.

    Escapes backslash and quote first, then the control chars TOML forbids as
    literals (newline/tab/CR/backspace/form-feed). Otherwise a multi-line
    value writes a file that tomllib refuses to parse on the next run.
    """
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    for raw, esc in (
        ("\n", "\\n"), ("\t", "\\t"), ("\r", "\\r"),
        ("\b", "\\b"), ("\f", "\\f"),
    ):
        out = out.replace(raw, esc)
    return '"' + out + '"'


def _format_personas_toml(customizations: Dict[str, Dict]) -> str:
    """Format a phase-persona customizations dict as TOML content.

    ``customizations`` maps phase name -> override fields dict (same shape as a
    ``[phase]`` table in ``.studio/personas.toml``). Emits a ``[phase]`` table
    plus a nested ``[phase.implementer]`` table when present.
    """
    lines = ["# Phase persona overrides (generated by setup wizard)\n"]
    for phase, fields in customizations.items():
        implementer = fields.get("implementer")
        lines.append(f"[{phase}]")
        for key, value in fields.items():
            if key == "implementer":
                continue
            lines.append(f"{key} = {_toml_quote(value)}")
        lines.append("")
        if isinstance(implementer, dict):
            lines.append(f"[{phase}.implementer]")
            if "title" in implementer:
                lines.append(f"title = {_toml_quote(implementer['title'])}")
            if "deliverables" in implementer:
                items = ", ".join(_toml_quote(d) for d in implementer["deliverables"])
                lines.append(f"deliverables = [{items}]")
            lines.append("")
    return "\n".join(lines)


def apply_persona_customization(
    target: Path,
    customizations: Dict[str, Dict],
    state: Optional[Dict[str, Any]] = None,
    _save: bool = True,
) -> None:
    """Write per-phase persona overrides to ``.studio/personas.toml``.

    ``customizations`` maps phase name -> override fields dict (same shape as a
    ``[phase]`` table in ``.studio/personas.toml``). Empty dict means "no
    customizations, keep neutral defaults"; no file is written.
    """
    from persona_overrides import validate_persona_overrides

    target = Path(target).resolve()

    for phase, fields in customizations.items():
        validate_persona_overrides({phase: fields})

    if customizations:
        content = _format_personas_toml(customizations)
        personas_path = target / ".studio" / "personas.toml"
        personas_path.parent.mkdir(parents=True, exist_ok=True)
        personas_path.write_text(content, encoding="utf-8")

    if state is None:
        state = load_setup_state(target)
    state.setdefault("choices", {})
    state["choices"]["persona_customizations"] = {
        phase: list(fields.keys()) for phase, fields in customizations.items()
    }
    _mark_step(state, "persona_customization")
    if _save:
        save_setup_state(target, state)


# The three suggest_*_from_stack helpers below sniff the same marker files as
# impl_loop.STACK_MARKERS, and deliberately do not share it: a wizard suggestion has to
# make a best guess out of whatever it finds, while the loop's gate has to refuse rather
# than guess wrong. Same markers, opposite policy on being unsure.
def suggest_personas_from_stack(target: Path) -> Dict[str, Dict]:
    """Suggest phase persona overrides by sniffing the project's tech stack.

    Pure suggestion helper. Inspects well-known marker files and returns a
    ``{phase: fields}`` dict the user can confirm and feed through
    ``apply_persona_customization``. Returns ``{}`` when no stack is detected.
    """
    target = Path(target).resolve()

    def _exists(*names: str) -> bool:
        return any((target / name).exists() for name in names)

    if _exists("Cargo.toml"):
        return {
            "tech": {
                "advocate": "Rust Systems Architect — define a performant, "
                "memory-safe architecture for the Rust stack.",
                "implementer": {
                    "title": "Rust Systems Architect & Code Generator",
                },
            }
        }
    if _exists("package.json"):
        return {
            "tech": {
                "advocate": "JS/TS Application Architect — define a maintainable "
                "TypeScript architecture for the Node/web stack.",
                "implementer": {
                    "title": "JS/TS Application Architect & Code Generator",
                },
            }
        }
    if _exists("ProjectSettings") or any(target.glob("*.csproj")):
        return {
            "tech": {
                "advocate": "Unity/C# Gameplay Architect — define a performant, "
                "component-driven architecture for the Unity stack.",
                "implementer": {
                    "title": "Unity/C# Gameplay Architect & Code Generator",
                },
            }
        }
    return {}


# Doc globs the unstale audit checks regardless of stack.
_UNSTALE_DEFAULT_DOCS = [
    "README.md", "CHANGELOG.md", "CLAUDE.md", "AGENTS.md", "docs/**/*.md",
]


def suggest_unstale_from_stack(target: Path) -> Dict[str, Any]:
    """Suggest an unstale audit config by sniffing the project's tech stack.

    Pure suggestion helper. Inspects the same marker files as
    ``suggest_personas_from_stack`` and returns a config dict matching the
    ``.studio/unstale.toml`` schema (``snapshot`` commands + ``audit`` globs).
    Returns ``{}`` when no stack is detected, in which case ``/unstale``
    self-detects at run time and no override file is needed.
    """
    target = Path(target).resolve()

    def _exists(*names: str) -> bool:
        return any((target / name).exists() for name in names)

    def _cfg(snapshot: Dict[str, str], source_globs: List[str]) -> Dict[str, Any]:
        return {
            "snapshot": snapshot,
            "audit": {"doc_globs": list(_UNSTALE_DEFAULT_DOCS), "source_globs": source_globs},
        }

    if _exists("Cargo.toml"):
        return _cfg(
            {"test_count": "cargo test 2>&1 | tail -3",
             "module_inventory": "find src -name '*.rs' | wc -l"},
            ["src/**/*.rs"],
        )
    if _exists("package.json"):
        return _cfg(
            {"test_count": "npm test --silent 2>&1 | tail -5",
             "module_inventory": "find src -type f \\( -name '*.ts' -o -name '*.tsx' -o -name '*.js' \\) | wc -l"},
            ["src/**/*.ts", "src/**/*.tsx", "src/**/*.js"],
        )
    if _exists("ProjectSettings") or any(target.glob("*.csproj")):
        # Unity tests run through the editor test runner, not a shell command.
        # Leave test_count out so /unstale skips the count check.
        return _cfg(
            {"module_inventory": "find Assets/Scripts -name '*.cs' | wc -l"},
            ["Assets/Scripts/**/*.cs"],
        )
    if _exists("go.mod"):
        return _cfg(
            {"test_count": "go test ./... 2>&1 | tail -3",
             "module_inventory": "find . -name '*.go' -not -path './vendor/*' | wc -l"},
            ["**/*.go"],
        )
    if _exists("pyproject.toml", "setup.py"):
        return _cfg(
            {"test_count": "python -m pytest -q --no-header 2>&1 | tail -1",
             "module_inventory": "find . -name '*.py' | wc -l"},
            ["**/*.py"],
        )
    return {}


def _format_unstale_toml(config: Dict[str, Any]) -> str:
    """Format an unstale config dict as ``.studio/unstale.toml`` content.

    ``config`` may contain ``snapshot`` (dict of command strings) and ``audit``
    (dict with ``doc_globs``/``source_globs``/``cross_refs`` lists). Empty
    sub-tables are omitted.
    """
    def _arr(values: List[str]) -> str:
        return "[" + ", ".join(_toml_quote(v) for v in values) + "]"

    lines = ["# Unstale audit configuration (generated by setup wizard)\n"]
    snapshot = config.get("snapshot") or {}
    if snapshot:
        lines.append("[snapshot]")
        for key in ("test_count", "module_inventory", "cli_help"):
            if key in snapshot:
                lines.append(f"{key} = {_toml_quote(snapshot[key])}")
        lines.append("")
    audit = config.get("audit") or {}
    if audit:
        lines.append("[audit]")
        for key in ("doc_globs", "source_globs", "cross_refs"):
            if key in audit:
                lines.append(f"{key} = {_arr(audit[key])}")
        lines.append("")
    return "\n".join(lines)


def apply_unstale_config(
    target: Path,
    config: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    _save: bool = True,
) -> None:
    """Write ``.studio/unstale.toml`` from a config dict.

    ``config`` mirrors the ``.studio/unstale.toml`` schema. Empty/None means
    "no override, let ``/unstale`` self-detect the stack" and no file is
    written (matching the persona-customization step's opt-in behavior).
    """
    target = Path(target).resolve()
    config = config or {}

    if config:
        content = _format_unstale_toml(config)
        unstale_path = target / ".studio" / "unstale.toml"
        unstale_path.parent.mkdir(parents=True, exist_ok=True)
        unstale_path.write_text(content, encoding="utf-8")

    if state is None:
        state = load_setup_state(target)
    state.setdefault("choices", {})
    state["choices"]["unstale_config"] = {
        "snapshot": list((config.get("snapshot") or {}).keys()),
        "audit": list((config.get("audit") or {}).keys()),
    }
    _mark_step(state, "unstale_config")
    if _save:
        save_setup_state(target, state)


# Keys the smoke profile can carry, split by TOML type so the formatter and
# validator agree. All live under a single ``[smoke]`` table.
_SMOKE_STRING_KEYS = ("kind", "launch", "url", "ready_probe", "ready_log")
_SMOKE_LIST_KEYS = ("setup", "build", "golden_path", "teardown")


def suggest_smoke_from_stack(target: Path) -> Dict[str, Any]:
    """Suggest a ``/smoke`` profile by sniffing the project's tech stack.

    Pure suggestion helper. Inspects the same marker files as the other
    ``suggest_*_from_stack`` helpers and returns a starting point matching the
    ``[smoke]`` table of ``.studio/smoke.toml`` (see ``apply_smoke_config``).
    Returns ``{}`` when no stack is detected, in which case ``/smoke``
    self-detects at run time and no override file is needed.

    The suggestion is deliberately partial: it fills in what the stack makes
    obvious (kind, prep/build commands, a launch command where there's a clear
    convention) and leaves the rest for the user to complete. It is a draft,
    not a finished config.
    """
    target = Path(target).resolve()

    def _exists(*names: str) -> bool:
        return any((target / name).exists() for name in names)

    if _exists("package.json"):
        return {
            "kind": "web",
            "setup": ["npm install"],
            "launch": "npm run dev",
            "url": "http://localhost:3000",
            "ready_log": "ready",
            "golden_path": [
                "Open the URL and confirm the app loads",
                "Walk the primary user flow end to end",
            ],
        }
    if _exists("Cargo.toml"):
        return {
            "kind": "cli",
            "build": ["cargo build --release"],
            "launch": "cargo run",
            "golden_path": [
                "Run the binary with a representative command",
                "Confirm the output and behavior are correct",
            ],
        }
    if _exists("ProjectSettings") or any(target.glob("*.csproj")):
        # Unity has no shell launch — /smoke enters Play mode via the Unity MCP.
        return {
            "kind": "game",
            "golden_path": [
                "Enter Play mode in the Unity editor",
                "Play the core loop for about a minute",
                "Confirm the console shows no errors",
            ],
        }
    if _exists("go.mod"):
        return {
            "kind": "service",
            "build": ["go build ./..."],
            "launch": "go run .",
            "url": "http://localhost:8080",
            "ready_log": "listening",
            "golden_path": [
                "Hit the health endpoint",
                "Exercise the primary API path",
            ],
        }
    if _exists("pyproject.toml", "setup.py"):
        # Launch left blank: we can't infer the entrypoint module from markers.
        return {
            "kind": "cli",
            "setup": ["pip install -e ."],
            "golden_path": [
                "Run the CLI's primary command",
                "Confirm it produces the expected result",
            ],
        }
    return {}


def _format_smoke_toml(config: Dict[str, Any]) -> str:
    """Format a smoke profile dict as ``.studio/smoke.toml`` content.

    ``config`` is a flat dict of ``[smoke]`` fields (the shape returned by
    ``suggest_smoke_from_stack``). String keys are emitted first, then list
    keys; unknown keys are ignored so a stray field can't corrupt the file.
    """
    def _arr(values: List[str]) -> str:
        return "[" + ", ".join(_toml_quote(v) for v in values) + "]"

    lines = ["# Smoke test configuration (generated by setup wizard)\n", "[smoke]"]
    for key in _SMOKE_STRING_KEYS:
        if key in config:
            lines.append(f"{key} = {_toml_quote(config[key])}")
    for key in _SMOKE_LIST_KEYS:
        if key in config:
            lines.append(f"{key} = {_arr(config[key])}")
    lines.append("")
    return "\n".join(lines)


def apply_smoke_config(
    target: Path,
    config: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    _save: bool = True,
) -> None:
    """Write ``.studio/smoke.toml`` from a smoke profile dict.

    ``config`` is a flat dict of ``[smoke]`` fields. Empty/None means "no
    override, let ``/smoke`` self-detect the stack" and no file is written
    (matching the unstale-config step's opt-in behavior).
    """
    target = Path(target).resolve()
    config = config or {}

    if config:
        content = _format_smoke_toml(config)
        smoke_path = target / ".studio" / "smoke.toml"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        smoke_path.write_text(content, encoding="utf-8")

    if state is None:
        state = load_setup_state(target)
    state.setdefault("choices", {})
    state["choices"]["smoke_config"] = {
        "kind": config.get("kind", ""),
        "keys": [k for k in config if k != "kind"],
    }
    _mark_step(state, "smoke_config")
    if _save:
        save_setup_state(target, state)


def _format_loop_toml(profile: Any) -> str:
    """Format an ``impl_loop.StackProfile`` as ``.studio/implementation_loop.toml`` content.

    Writes all four ``[gate]`` keys, including the empty ones, so the file shows the whole
    shape of what can be set here rather than only the parts this repo's stack answered.
    """
    checks = ", ".join(_toml_quote(check) for check in profile.static_checks)
    stacks = ", ".join(profile.stacks)
    return "\n".join([
        f"# /forge gate commands, detected from this repo's stack ({stacks}) by the setup wizard.",
        "#",
        "# Edit anything here. /forge reads this file *instead of* Studio's shipped",
        "# config/implementation_loop.toml: a [gate] key you delete falls back to what detection",
        "# finds, and [loop]/[editor] keys fall back to Studio's built-in defaults.",
        "",
        "[gate]",
        f"test_command = {_toml_quote(profile.test_command)}",
        f"static_checks = [{checks}]",
        f"require_mutation_check = {str(profile.require_mutation_check).lower()}",
        f"mutation_command = {_toml_quote(profile.mutation_command or '')}",
        "",
    ])


def apply_implementation_loop_config(
    target: Path,
    state: Optional[Dict[str, Any]] = None,
    _save: bool = True,
) -> None:
    """Write ``.studio/implementation_loop.toml`` with this repo's detected gate commands.

    The step asks nothing, and it works nothing out for itself: the commands come from
    ``impl_loop.resolve_profile``, the same call ``/forge`` resolves its own gate with. One
    function, two callers, so the file you can edit and the commands the loop actually runs
    cannot drift apart.

    Three outcomes, and only one of them writes a file:

    - **A file is already there:** left exactly as it is. A hand-written override is the only
      thing making ``/forge`` work in a repo Studio cannot identify, and this step must never
      eat one.
    - **Detection has no test command** (nothing recognised, two stacks at once, or a stack
      Studio ships no command for): nothing is written, and the refusal ``/forge`` would print
      is printed here instead — it already names the file and the lines to write by hand.
    - **Otherwise:** the detected commands are written out for the user to edit.

    Everything here — the detection and the file — is about ``target``. Where this Studio's
    ``/forge`` looks is a separate question, answered by the loader's own
    ``project_artifact_root``: ``STUDIO_ARTIFACT_ROOT`` when it is set, else the repo an
    installed snapshot sits in. Either can be some other repository — a redirected env var,
    or a ``--target`` pointed away from the install's own root — and both are called out
    rather than left to be discovered later, because the file this step writes would then
    describe a repo ``/forge`` is not gating. The one case that stays quiet is a Studio
    source checkout that is not installed anywhere: there the loader falls back to the source
    directory itself, which says nothing about where any consumer's ``/forge`` will look.
    """
    import impl_loop

    target = Path(target).resolve()
    config_path = target / ".studio" / "implementation_loop.toml"

    redirect = os.environ.get("STUDIO_ARTIFACT_ROOT")
    gated = impl_loop.project_artifact_root(impl_loop.STUDIO_ROOT)
    # A source checkout that is not installed anywhere lands on the loader's last branch,
    # which returns the source directory itself — no consuming repo to compare against.
    knows_what_forge_gates = bool(redirect) or gated != impl_loop.STUDIO_ROOT
    if knows_what_forge_gates and gated != target:
        pointed_by = "STUDIO_ARTIFACT_ROOT points /forge at" if redirect else "/forge gates"
        print(
            f"Note: {pointed_by} {gated}, not {target}. "
            f"This step detects and writes for {target}, so /forge will gate a different repo."
        )

    if config_path.exists():
        print(f"Kept the existing {config_path} — setup never overwrites one.")
        outcome = {"status": "kept"}
    else:
        profile = impl_loop.resolve_profile(target)
        if profile.test_command:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(_format_loop_toml(profile), encoding="utf-8")
            print(f"Wrote {config_path}: test_command = {profile.test_command}")
            outcome = {"status": "written", "test_command": profile.test_command}
        else:
            # The loader's own refusal, word for word rather than paraphrased: the two
            # messages have to name the same file and the same lines, and a copy here
            # would be the one that goes stale.
            print(impl_loop._no_test_command_message(profile, target))
            outcome = {"status": "undetected"}

    if state is None:
        state = load_setup_state(target)
    state.setdefault("choices", {})
    state["choices"]["implementation_loop_config"] = outcome
    _mark_step(state, "implementation_loop_config")
    if _save:
        save_setup_state(target, state)


def _format_settings_toml(ttl_days: int, size_limit_mb: int) -> str:
    """Format cleanup settings as TOML content."""
    return (
        "# Studio settings (generated by setup wizard)\n"
        "\n"
        "[cleanup]\n"
        f"ttl_days = {ttl_days}\n"
        f"size_limit_mb = {size_limit_mb}\n"
    )


def apply_cleanup(
    target: Path,
    ttl_days: int = 30,
    size_limit_mb: int = 900,
    state: Optional[Dict[str, Any]] = None,
    _save: bool = True,
) -> None:
    """Write ``.studio/config/studio_settings.toml``."""
    target = Path(target).resolve()
    content = _format_settings_toml(ttl_days, size_limit_mb)
    settings_path = target / ".studio" / "config" / "studio_settings.toml"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(content, encoding="utf-8")

    if state is None:
        state = load_setup_state(target)
    state.setdefault("choices", {})
    state["choices"]["cleanup"] = {
        "ttl_days": ttl_days,
        "size_limit_mb": size_limit_mb,
    }
    _mark_step(state, "cleanup")
    if _save:
        save_setup_state(target, state)


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------


def apply_defaults(target: Path) -> Dict[str, Any]:
    """Apply all setup steps with default values.

    Returns the resulting state.
    """
    target = Path(target).resolve()
    state = load_setup_state(target)
    studio_dir = _find_studio_dir(target)

    default_pack = get_default_pack_name(studio_dir)
    apply_role_pack(target, default_pack, state=state, _save=False)
    apply_role_customization(target, {}, state=state, _save=False)
    apply_persona_customization(target, {}, state=state, _save=False)
    apply_cleanup(target, state=state, _save=False)
    apply_unstale_config(target, {}, state=state, _save=False)
    apply_smoke_config(target, {}, state=state, _save=False)
    apply_implementation_loop_config(target, state=state, _save=False)

    save_setup_state(target, state)
    return state


def apply_from_answers(target: Path, answers: Dict[str, Any]) -> Dict[str, Any]:
    """Apply setup from an answers dict.

    Expected keys (all optional):
        role_pack: str: pack name
        role_overrides: list[str]: e.g. ["+ml", "-art"]
        role_customizations: dict[str, dict]: per-role override fields
        persona_customizations: dict[phase, dict]: per-phase persona override fields
        unstale_config: dict: .studio/unstale.toml override (snapshot + audit)
        smoke_config: dict: .studio/smoke.toml override (flat [smoke] fields)
        implementation_loop_config: any value: the step takes no options, so the key's
            presence is the whole instruction ("run it"); detection decides the rest
        cleanup: dict with ttl_days and size_limit_mb
    """
    target = Path(target).resolve()
    state = load_setup_state(target)

    if "role_pack" in answers:
        apply_role_pack(
            target,
            answers["role_pack"],
            answers.get("role_overrides", []),
            state=state,
            _save=False,
        )

    if "role_customizations" in answers:
        apply_role_customization(
            target, answers["role_customizations"], state=state, _save=False,
        )

    if "persona_customizations" in answers:
        apply_persona_customization(
            target, answers["persona_customizations"], state=state, _save=False,
        )

    if "unstale_config" in answers:
        apply_unstale_config(
            target, answers["unstale_config"], state=state, _save=False,
        )

    if "smoke_config" in answers:
        apply_smoke_config(
            target, answers["smoke_config"], state=state, _save=False,
        )

    if "implementation_loop_config" in answers:
        apply_implementation_loop_config(target, state=state, _save=False)

    cleanup = answers.get("cleanup")
    if cleanup is not None:
        apply_cleanup(
            target,
            ttl_days=cleanup.get("ttl_days", DEFAULT_CLEANUP["ttl_days"]),
            size_limit_mb=cleanup.get("size_limit_mb", DEFAULT_CLEANUP["size_limit_mb"]),
            state=state,
            _save=False,
        )

    save_setup_state(target, state)
    return state


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------


def show_status(target: Path) -> str:
    """Return a human-readable summary of setup state."""
    target = Path(target).resolve()
    state = load_setup_state(target)
    pend = pending_steps(state)
    choices = state.get("choices", {})

    lines: List[str] = []

    if not state.get("completed_steps"):
        lines.append("Studio setup: NOT CONFIGURED")
        lines.append(f"  {len(pend)} step(s) pending: {', '.join(s['label'] for s in pend)}")
        lines.append("")
        lines.append("Run /studio-setup or: python run_phase.py setup --target . --defaults")
        return "\n".join(lines)

    lines.append("Studio setup status:")
    lines.append("")

    # Role pack
    if "role_pack" in choices:
        pack = choices["role_pack"]
        roles = choices.get("resolved_roles", [])
        overrides = choices.get("role_overrides", [])
        lines.append(f"  Role pack: {pack}")
        lines.append(f"  Roles: {', '.join(roles)}")
        if overrides:
            lines.append(f"  Overrides: {' '.join(overrides)}")
    else:
        lines.append("  Role pack: not configured")

    # Role customizations
    custs = choices.get("role_customizations", {})
    if custs:
        lines.append(f"  Role customizations: {', '.join(custs.keys())}")
    else:
        lines.append("  Role customizations: none (using defaults)")

    # Phase personas
    personas = choices.get("persona_customizations", {})
    if personas:
        lines.append(f"  Phase personas: {', '.join(personas.keys())}")
    else:
        lines.append("  Phase personas: none (using neutral defaults)")

    # Unstale audit config
    unstale = choices.get("unstale_config", {})
    if unstale.get("snapshot") or unstale.get("audit"):
        keys = unstale.get("snapshot", []) + unstale.get("audit", [])
        lines.append(f"  Unstale audit: custom override ({', '.join(keys)})")
    else:
        lines.append("  Unstale audit: self-detect (no override)")

    # Smoke test config
    smoke = choices.get("smoke_config", {})
    if smoke.get("kind") or smoke.get("keys"):
        kind = smoke.get("kind") or "custom"
        lines.append(f"  Smoke test: custom profile ({kind})")
    else:
        lines.append("  Smoke test: self-detect (no override)")

    # /forge gate commands
    gates = choices.get("implementation_loop_config", {})
    gate_status = gates.get("status")
    if gate_status == "written":
        lines.append(
            f"  Forge gates: {gates.get('test_command')} "
            "(written to .studio/implementation_loop.toml)"
        )
    elif gate_status == "kept":
        lines.append("  Forge gates: your own .studio/implementation_loop.toml (left alone)")
    elif gate_status == "undetected":
        lines.append(
            "  Forge gates: none detected — /forge refuses until you write "
            ".studio/implementation_loop.toml"
        )
    else:
        lines.append("  Forge gates: not configured")

    # Cleanup
    cleanup = choices.get("cleanup")
    if cleanup:
        lines.append(
            f"  Cleanup: {cleanup.get('ttl_days', 30)}d TTL, "
            f"{cleanup.get('size_limit_mb', 900)}MB limit"
        )
    else:
        lines.append("  Cleanup: not configured")

    # Pending
    if pend:
        lines.append("")
        lines.append(f"  Pending: {', '.join(s['label'] for s in pend)}")
        lines.append("  Run /studio-setup to configure new features.")
    else:
        lines.append("")
        lines.append("  All steps configured.")

    ts = state.get("timestamps", {})
    if ts.get("last_setup"):
        lines.append(f"  Last configured: {ts['last_setup']}")

    return "\n".join(lines)
