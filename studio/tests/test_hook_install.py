"""Tests for the SessionStart update-check hook install/merge.

Covers ``_install_sessionstart_hook`` and its wiring through ``install_studio``:
  - install_studio drops exactly one check-updates SessionStart hook
  - merging into an existing settings.local.json never clobbers other keys/hooks
  - re-install is idempotent (no duplicate entry)
  - opt-out (install_hook=False or the sentinel) removes / never adds our entry
  - an unparseable settings.local.json is left untouched, no exception
"""
import json
import sys
from pathlib import Path

import pytest

from install import (
    install_studio,
    _install_sessionstart_hook,
    _hook_command,
    _HOOK_MARKER,
    UPDATE_CHECK_SENTINEL,
)


@pytest.fixture
def studio_dir():
    """Return the real studio source directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def target_dir(tmp_path):
    """Create a fake target project directory."""
    project = tmp_path / "my_game"
    project.mkdir()
    return project


def _settings_path(target: Path) -> Path:
    return target / ".claude" / "settings.local.json"


def _our_entries(data: dict) -> list:
    """All SessionStart entries whose command contains our marker."""
    found = []
    for entry in data.get("hooks", {}).get("SessionStart", []):
        for inner in entry.get("hooks", []):
            if _HOOK_MARKER in inner.get("command", ""):
                found.append(inner)
    return found


class TestInstallStudioHook:
    """End-to-end: the hook lands via install_studio."""

    def test_install_drops_single_check_updates_hook(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir)

        settings = _settings_path(target_dir)
        assert settings.is_file()
        data = json.loads(settings.read_text(encoding="utf-8"))

        ours = _our_entries(data)
        assert len(ours) == 1
        command = ours[0]["command"]
        assert _HOOK_MARKER in command
        assert sys.executable in command
        assert ours[0]["type"] == "command"


class TestHookMerge:
    """_install_sessionstart_hook merges without clobbering."""

    def test_merge_preserves_other_keys_and_hooks(self, target_dir):
        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        seed = {
            "permissions": {"allow": ["Bash(ls:*)"]},
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash",
                     "hooks": [{"type": "command", "command": "echo pre"}]}
                ]
            },
        }
        settings.write_text(json.dumps(seed, indent=2), encoding="utf-8")

        _install_sessionstart_hook(target_dir, enabled=True)

        data = json.loads(settings.read_text(encoding="utf-8"))
        # Unrelated content survives unchanged.
        assert data["permissions"] == seed["permissions"]
        assert data["hooks"]["PreToolUse"] == seed["hooks"]["PreToolUse"]
        # Our entry was added.
        assert len(_our_entries(data)) == 1

    def test_idempotent_no_duplicate(self, target_dir):
        _install_sessionstart_hook(target_dir, enabled=True)
        _install_sessionstart_hook(target_dir, enabled=True)

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        ours = _our_entries(data)
        assert len(ours) == 1
        assert ours[0]["command"] == _hook_command()

    def test_install_studio_twice_is_idempotent(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir)
        install_studio(target_dir, studio_dir)

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert len(_our_entries(data)) == 1


class TestHookOptOut:
    """Disabling removes our entry / never adds one."""

    def test_disable_removes_existing_entry(self, target_dir):
        # Seed an unrelated hook plus ours, then disable.
        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "echo keep-me"}]},
                ]
            }
        }, indent=2), encoding="utf-8")
        _install_sessionstart_hook(target_dir, enabled=True)
        assert len(_our_entries(json.loads(settings.read_text()))) == 1

        _install_sessionstart_hook(target_dir, enabled=False)

        data = json.loads(settings.read_text(encoding="utf-8"))
        assert _our_entries(data) == []
        # The unrelated SessionStart hook survives.
        commands = [
            inner["command"]
            for entry in data["hooks"]["SessionStart"]
            for inner in entry["hooks"]
        ]
        assert "echo keep-me" in commands

    def test_sentinel_present_installs_no_hook(self, target_dir, studio_dir):
        # A durable opt-out sentinel disables the hook even on a normal install.
        (target_dir / ".studio").mkdir(parents=True, exist_ok=True)
        (target_dir / ".studio" / UPDATE_CHECK_SENTINEL).write_text("", encoding="utf-8")

        install_studio(target_dir, studio_dir)

        settings = _settings_path(target_dir)
        if settings.is_file():
            data = json.loads(settings.read_text(encoding="utf-8"))
            assert _our_entries(data) == []


class TestHookUnparseable:
    """A malformed settings file is left untouched, no exception."""

    def test_unparseable_left_untouched(self, target_dir):
        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        malformed = "{ this is not: valid json ,,, "
        settings.write_text(malformed, encoding="utf-8")

        # Must not raise.
        _install_sessionstart_hook(target_dir, enabled=True)

        assert settings.read_text(encoding="utf-8") == malformed


class TestHookCommand:
    """The hook command string must survive Claude Code's execution context."""

    def test_command_paths_are_absolute_and_quoted(self):
        cmd = _hook_command()
        # Interpreter is absolute AND quoted (a space in the path must not split it).
        assert cmd.startswith(f'"{sys.executable}"')
        # Script path is anchored to the project dir, not cwd-relative: Claude Code
        # runs hooks from the session's working dir, which may be a subdirectory.
        assert '"$CLAUDE_PROJECT_DIR/.studio/source/run_phase.py"' in cmd
        # It does NOT reference the script by a bare relative path.
        assert '".studio/source/run_phase.py"' not in cmd
        assert "check-updates" in cmd
        assert '--target "$CLAUDE_PROJECT_DIR"' in cmd


class TestHookMalformedFields:
    """Non-object hooks / non-list SessionStart are left untouched, no exception."""

    def test_non_object_hooks_left_untouched(self, target_dir):
        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        original = json.dumps({"hooks": ["oops-a-list"]}, indent=2)
        settings.write_text(original, encoding="utf-8")

        _install_sessionstart_hook(target_dir, enabled=True)  # must not raise

        assert settings.read_text(encoding="utf-8") == original

    def test_non_list_sessionstart_left_untouched(self, target_dir):
        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        original = json.dumps({"hooks": {"SessionStart": {"oops": "a dict"}}}, indent=2)
        settings.write_text(original, encoding="utf-8")

        _install_sessionstart_hook(target_dir, enabled=True)  # must not raise

        assert settings.read_text(encoding="utf-8") == original


class TestUpdateHookOnEarlyReturn:
    """update --no-hook must (un)install the hook even when it short-circuits."""

    def test_update_no_hook_removes_hook_when_up_to_date(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        assert len(_our_entries(json.loads(_settings_path(target_dir).read_text()))) == 1

        # Explicit studio_dir => update sees the repo as up to date and takes the
        # short-circuit that returns before the re-install. The hook must still go.
        update_studio(target_dir, studio_dir, install_hook=False)

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert _our_entries(data) == []

    def test_update_refreshes_hook_when_up_to_date(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        # Tamper the installed hook command; a normal update should refresh it back
        # even on the up-to-date path.
        settings = _settings_path(target_dir)
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["hooks"]["SessionStart"][0]["hooks"][0]["command"] = "python old check-updates"
        settings.write_text(json.dumps(data, indent=2), encoding="utf-8")

        update_studio(target_dir, studio_dir, install_hook=True)

        data = json.loads(settings.read_text(encoding="utf-8"))
        ours = _our_entries(data)
        assert len(ours) == 1
        assert ours[0]["command"] == _hook_command()


def _make_out_of_date(target: Path, studio_dir: Path) -> None:
    """Make an installed target genuinely out of date, so `update` re-installs.

    Overwrite one snapshot file and record ITS hash in the manifest, so the file
    is not "locally modified" (which would block the update) but does differ from
    live source (which is what makes the update do real work). Same trick as
    ``TestSnapshotStaleDetection._stale_install`` in test_install.py.
    """
    import hashlib

    stale = b"# stale snapshot"
    (target / ".studio" / "source" / "verdict.py").write_bytes(stale)
    manifest_path = target / ".studio" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["verdict.py"] = hashlib.sha256(stale).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


class TestUpdateHookOnReinstall:
    """Regression for #120: the update that actually re-installs must KEEP the hook.

    Every one of these drives an update past the up-to-date short-circuit and into
    the re-install — the path where the hook used to be written and then deleted
    milliseconds later, which is why the bug shipped with a green suite.
    """

    def test_reinstalling_update_keeps_the_hook(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        _make_out_of_date(target_dir, studio_dir)

        result = update_studio(target_dir, studio_dir, install_hook=True)
        # Guard the guard: if this update short-circuited, the assertion below
        # would pass on the broken code too.
        assert result["updated"] >= 1

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        ours = _our_entries(data)
        assert len(ours) == 1
        assert ours[0]["command"] == _hook_command()

    def test_reinstalling_update_no_hook_removes_the_hook(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        assert len(_our_entries(json.loads(_settings_path(target_dir).read_text()))) == 1
        _make_out_of_date(target_dir, studio_dir)

        result = update_studio(target_dir, studio_dir, install_hook=False)
        assert result["updated"] >= 1

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert _our_entries(data) == []

    def test_reinstalling_update_respects_sentinel(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        (target_dir / ".studio" / UPDATE_CHECK_SENTINEL).write_text("", encoding="utf-8")
        _make_out_of_date(target_dir, studio_dir)

        result = update_studio(target_dir, studio_dir, install_hook=True)
        assert result["updated"] >= 1

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert _our_entries(data) == []


class TestInitHookIntent:
    """`init` honours the same flag: on by default, off with --no-hook."""

    def test_init_installs_hook(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir)

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert len(_our_entries(data)) == 1

    def test_init_no_hook_leaves_target_without_one(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir, install_hook=False)

        settings = _settings_path(target_dir)
        if settings.is_file():
            data = json.loads(settings.read_text(encoding="utf-8"))
            assert _our_entries(data) == []
