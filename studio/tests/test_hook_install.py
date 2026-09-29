"""Tests for the two hooks the installer writes into settings.local.json.

The SessionStart update-check hook (``_install_sessionstart_hook``) and the Stop
finish-check hook (``_install_stop_hook``), each wired through ``install_studio``
and ``update_studio``. They share a settings file and a shape, so they share a
test file:
  - install_studio drops exactly one entry of each
  - merging into an existing settings.local.json never clobbers other keys/hooks
  - re-install is idempotent (no duplicate entry)
  - each opt-out (its flag or its sentinel) removes / never adds only its own entry
  - a malformed settings.local.json is left untouched, no exception
  - the finish-check script ships outside the manifest: never blocking an update,
    and rewritten by every update (specs/shipped-finish-check.md)
"""
import json
import sys
from pathlib import Path

import pytest

from install import (
    install_studio,
    _install_sessionstart_hook,
    _install_stop_hook,
    _hook_command,
    _finish_check_command,
    _HOOK_MARKER,
    _FINISH_CHECK_MARKER,
    UPDATE_CHECK_SENTINEL,
    FINISH_CHECK_SENTINEL,
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


def _our_stop_entries(data: dict) -> list:
    """All Stop entries whose command contains the finish-check marker."""
    found = []
    for entry in data.get("hooks", {}).get("Stop", []):
        for inner in entry.get("hooks", []):
            if _FINISH_CHECK_MARKER in inner.get("command", ""):
                found.append(inner)
    return found


def _stop_hooks_of(target: Path) -> list:
    return _our_stop_entries(json.loads(_settings_path(target).read_text(encoding="utf-8")))


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

    def test_install_hook_false_installs_no_hook(self, target_dir, studio_dir):
        # `init --no-hook`: the target comes out with no hook at all.
        install_studio(target_dir, studio_dir, install_hook=False)

        settings = _settings_path(target_dir)
        if settings.is_file():
            data = json.loads(settings.read_text(encoding="utf-8"))
            assert _our_entries(data) == []

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


def _make_out_of_date(target: Path) -> None:
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
        _make_out_of_date(target_dir)

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
        _make_out_of_date(target_dir)

        result = update_studio(target_dir, studio_dir, install_hook=False)
        assert result["updated"] >= 1

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert _our_entries(data) == []

    def test_reinstalling_update_respects_sentinel(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        (target_dir / ".studio" / UPDATE_CHECK_SENTINEL).write_text("", encoding="utf-8")
        _make_out_of_date(target_dir)

        result = update_studio(target_dir, studio_dir, install_hook=True)
        assert result["updated"] >= 1

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert _our_entries(data) == []


# ---------------------------------------------------------------------------
# The Stop finish-check hook (specs/shipped-finish-check.md, unit 2).
# ---------------------------------------------------------------------------


def _manifest(target: Path) -> dict:
    return json.loads((target / ".studio" / "MANIFEST.json").read_text(encoding="utf-8"))


def _installed_script(target: Path) -> Path:
    return target / ".studio" / "source" / "finish_check.py"


class TestFinishCheckEntry:
    """`init` lands exactly one Stop entry, with paths that survive a hook's context."""

    def test_install_drops_single_finish_check_hook(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir)

        ours = _stop_hooks_of(target_dir)
        assert len(ours) == 1
        entry = ours[0]
        assert entry["type"] == "command"
        assert entry["timeout"] == 10
        assert entry["statusMessage"] == "Finish-check: anything left undone?"

    def test_command_paths_are_absolute_and_quoted(self):
        cmd = _finish_check_command()
        # Interpreter absolute AND quoted: on a stock macOS a bare `python` is
        # command not found, and a space in the path must not split the command.
        assert f' "{sys.executable}" ' in cmd
        # Script anchored to the project dir, not cwd-relative: Claude Code runs
        # hooks from the session's working dir, which may be a subdirectory.
        assert '"$CLAUDE_PROJECT_DIR/.studio/source/finish_check.py"' in cmd
        assert '".studio/source/finish_check.py"' not in cmd

    def test_three_installs_leave_one_entry_and_spare_sessionstart(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir)
        session_start_after_first = json.loads(
            _settings_path(target_dir).read_text(encoding="utf-8")
        )["hooks"]["SessionStart"]

        install_studio(target_dir, studio_dir)
        install_studio(target_dir, studio_dir)

        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert len(_our_stop_entries(data)) == 1
        # The two installers share one file; neither may disturb the other's entry.
        assert data["hooks"]["SessionStart"] == session_start_after_first
        assert len(_our_entries(data)) == 1

    def test_merge_preserves_other_stop_hooks(self, target_dir):
        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        seed = {"hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "echo someone-elses-stop"}]}
        ]}}
        settings.write_text(json.dumps(seed, indent=2), encoding="utf-8")
        # The entry is only registered when the script it runs is in place.
        _installed_script(target_dir).parent.mkdir(parents=True)
        _installed_script(target_dir).write_text("", encoding="utf-8")

        _install_stop_hook(target_dir, enabled=True)

        data = json.loads(settings.read_text(encoding="utf-8"))
        assert len(_our_stop_entries(data)) == 1
        commands = [
            inner["command"]
            for entry in data["hooks"]["Stop"]
            for inner in entry["hooks"]
        ]
        assert "echo someone-elses-stop" in commands


class TestFinishCheckMissingScript:
    """An entry must never point at a script that isn't there.

    Python exits 2 on a missing file, and a Stop hook exiting 2 blocks the stop —
    so a dangling entry would refuse every stop in the session, indefinitely.
    """

    def _pre_unit_2_install(self, target: Path, studio_dir: Path) -> None:
        """An install from before the finish-check shipped: no script, no entry."""
        install_studio(target, studio_dir)
        _installed_script(target).unlink()
        _install_stop_hook(target, enabled=False)
        assert _stop_hooks_of(target) == []

    def test_no_source_update_registers_nothing(self, target_dir, studio_dir, monkeypatch):
        """The reviewer's repro: a pre-unit-2 install whose source checkout is gone."""
        import install
        from install import update_studio

        self._pre_unit_2_install(target_dir, studio_dir)
        version_path = target_dir / ".studio" / "VERSION"
        version = json.loads(version_path.read_text(encoding="utf-8"))
        version["source_path"] = str(target_dir / "gone")
        version_path.write_text(json.dumps(version), encoding="utf-8")
        snapshot = target_dir / ".studio" / "source"
        monkeypatch.setattr(install, "_get_studio_root", lambda: snapshot)

        result = update_studio(target_dir)

        assert result.get("skipped_no_source") is True  # really took that return
        assert not _installed_script(target_dir).exists()
        assert _stop_hooks_of(target_dir) == []

    def test_up_to_date_update_registers_once_the_script_lands(self, target_dir, studio_dir):
        """Same install, source available: the copy lands the script, then the entry."""
        from install import update_studio

        self._pre_unit_2_install(target_dir, studio_dir)

        result = update_studio(target_dir, studio_dir)

        assert result["updated"] == 0  # the short-circuit path
        assert _installed_script(target_dir).is_file()
        assert len(_stop_hooks_of(target_dir)) == 1

    def test_install_from_a_source_without_the_script_registers_nothing(
        self, target_dir, studio_dir, monkeypatch
    ):
        import install

        monkeypatch.setattr(install, "_copy_finish_check", lambda *_: None)

        install_studio(target_dir, studio_dir)

        assert not _installed_script(target_dir).exists()
        assert _stop_hooks_of(target_dir) == []

    def test_install_stop_hook_removes_an_entry_whose_script_is_gone(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir)
        _installed_script(target_dir).unlink()

        _install_stop_hook(target_dir, enabled=True)

        assert _stop_hooks_of(target_dir) == []

    @pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX sh")
    def test_command_exits_0_when_the_script_is_deleted_later(self, target_dir):
        """The command itself fails open, for a script removed after install."""
        import os
        import subprocess

        result = subprocess.run(
            ["sh", "-c", _finish_check_command()],
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(target_dir)},
            input="{}", capture_output=True, text=True,
        )

        assert result.returncode == 0, result.stderr


class TestFinishCheckOptOut:
    """The flag and the sentinel each switch it off, on both subcommands."""

    def test_init_no_finish_check_writes_no_entry(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir, install_finish_check=False)

        assert _stop_hooks_of(target_dir) == []

    def test_init_sentinel_writes_no_entry(self, target_dir, studio_dir):
        (target_dir / ".studio").mkdir(parents=True, exist_ok=True)
        (target_dir / ".studio" / FINISH_CHECK_SENTINEL).write_text("", encoding="utf-8")

        install_studio(target_dir, studio_dir)

        assert _stop_hooks_of(target_dir) == []

    def test_update_no_finish_check_removes_entry_when_up_to_date(self, target_dir, studio_dir):
        """The case the flag is usually reached for, and the one that silently no-ops.

        An explicit studio_dir makes the install look current, so update takes the
        short-circuit that returns before the re-install. The entry must still go.
        """
        from install import update_studio

        install_studio(target_dir, studio_dir)
        assert len(_stop_hooks_of(target_dir)) == 1

        result = update_studio(target_dir, studio_dir, install_finish_check=False)

        assert result["updated"] == 0  # guard the guard: this really did short-circuit
        assert _stop_hooks_of(target_dir) == []

    def test_update_sentinel_removes_entry_when_up_to_date(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        (target_dir / ".studio" / FINISH_CHECK_SENTINEL).write_text("", encoding="utf-8")

        update_studio(target_dir, studio_dir, install_finish_check=True)

        assert _stop_hooks_of(target_dir) == []

    def test_reinstalling_update_no_finish_check_removes_entry(self, target_dir, studio_dir):
        """#120's shape, for this hook: the re-install must not put back what the flag removed."""
        from install import update_studio

        install_studio(target_dir, studio_dir)
        _make_out_of_date(target_dir)

        result = update_studio(target_dir, studio_dir, install_finish_check=False)

        assert result["updated"] >= 1  # this update really did re-install
        assert _stop_hooks_of(target_dir) == []

    def test_reinstalling_update_keeps_the_entry(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        _make_out_of_date(target_dir)

        result = update_studio(target_dir, studio_dir)

        assert result["updated"] >= 1
        ours = _stop_hooks_of(target_dir)
        assert len(ours) == 1
        assert ours[0]["command"] == _finish_check_command()

    def test_update_refreshes_a_tampered_command(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        settings = _settings_path(target_dir)
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["hooks"]["Stop"][0]["hooks"][0]["command"] = "python old/finish_check.py"
        settings.write_text(json.dumps(data, indent=2), encoding="utf-8")

        update_studio(target_dir, studio_dir)

        ours = _stop_hooks_of(target_dir)
        assert len(ours) == 1
        assert ours[0]["command"] == _finish_check_command()

    def test_the_two_opt_outs_are_independent(self, target_dir, studio_dir):
        """Wanting the session brief without a blocking finish-check is an ordinary position.

        So neither flag may reach the other's entry — the reason this is a second
        flag and a second sentinel rather than a shared one.
        """
        install_studio(target_dir, studio_dir, install_hook=False)
        assert _our_entries(json.loads(_settings_path(target_dir).read_text())) == []
        assert len(_stop_hooks_of(target_dir)) == 1

        install_studio(target_dir, studio_dir, install_finish_check=False)
        data = json.loads(_settings_path(target_dir).read_text(encoding="utf-8"))
        assert len(_our_entries(data)) == 1
        assert _our_stop_entries(data) == []


MALFORMED_SETTINGS = {
    "top level is a JSON array": json.dumps(["not", "an", "object"], indent=2),
    "hooks is a string": json.dumps({"hooks": "oops"}, indent=2),
    "hooks.Stop is a dict": json.dumps({"hooks": {"Stop": {"oops": "a dict"}}}, indent=2),
}


class TestFinishCheckMalformedSettings:
    """A shape we didn't write gets one warning and is left byte-identical."""

    @pytest.mark.parametrize("original", MALFORMED_SETTINGS.values(), ids=list(MALFORMED_SETTINGS))
    def test_one_warning_and_no_write(self, target_dir, original, capsys):
        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(original, encoding="utf-8")

        _install_stop_hook(target_dir, enabled=True)  # must not raise

        assert settings.read_text(encoding="utf-8") == original
        warnings = [
            line for line in capsys.readouterr().out.splitlines()
            if "finish-check hook" in line
        ]
        assert len(warnings) == 1

    @pytest.mark.parametrize("original", [
        MALFORMED_SETTINGS["top level is a JSON array"],
        MALFORMED_SETTINGS["hooks is a string"],
    ], ids=["top level is a JSON array", "hooks is a string"])
    def test_install_and_update_leave_the_file_alone(
        self, target_dir, studio_dir, original, capsys
    ):
        """Both shapes stop both installers, so the whole file survives byte-for-byte."""
        from install import update_studio

        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(original, encoding="utf-8")

        install_studio(target_dir, studio_dir)  # must not raise
        assert settings.read_text(encoding="utf-8") == original

        update_studio(target_dir, studio_dir)  # must not raise
        assert settings.read_text(encoding="utf-8") == original
        assert "finish-check hook" in capsys.readouterr().out

    def test_install_and_update_leave_a_dict_stop_alone(self, target_dir, studio_dir, capsys):
        """A dict `Stop` stops only us.

        `hooks` is a perfectly good object here, so the SessionStart installer goes
        ahead and writes its own entry — which is its job and not ours to prevent.
        What has to hold is that the shape WE would have written into is returned
        untouched and gains no entry of ours.
        """
        from install import update_studio

        settings = _settings_path(target_dir)
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(MALFORMED_SETTINGS["hooks.Stop is a dict"], encoding="utf-8")

        install_studio(target_dir, studio_dir)  # must not raise
        update_studio(target_dir, studio_dir)  # must not raise

        data = json.loads(settings.read_text(encoding="utf-8"))
        assert data["hooks"]["Stop"] == {"oops": "a dict"}
        assert "finish-check hook" in capsys.readouterr().out


class TestFinishCheckScriptShipsUnguarded:
    """Copied into every install, recorded in no manifest — deliberately."""

    def test_init_writes_the_script_and_records_nothing(self, target_dir, studio_dir):
        install_studio(target_dir, studio_dir)

        assert _installed_script(target_dir).is_file()
        assert _installed_script(target_dir).read_bytes() == (
            studio_dir / "finish_check.py"
        ).read_bytes()
        # Manifest membership is what the clobber guard reads. An entry here would
        # let one local edit to the hook freeze the whole repo's update stream.
        assert [key for key in _manifest(target_dir) if "finish_check" in key] == []

    def test_update_overwrites_a_local_edit_without_blocking(self, target_dir, studio_dir):
        """The hardest case: nothing else has changed, so the install looks current."""
        from install import update_studio

        install_studio(target_dir, studio_dir)
        _installed_script(target_dir).write_text("# someone edited this\n", encoding="utf-8")

        result = update_studio(target_dir, studio_dir)

        assert not result.get("blocked")
        assert result["locally_modified"] == []
        assert _installed_script(target_dir).read_bytes() == (
            studio_dir / "finish_check.py"
        ).read_bytes()

    def test_reinstalling_update_also_overwrites_a_local_edit(self, target_dir, studio_dir):
        from install import update_studio

        install_studio(target_dir, studio_dir)
        _installed_script(target_dir).write_text("# someone edited this\n", encoding="utf-8")
        _make_out_of_date(target_dir)

        result = update_studio(target_dir, studio_dir)

        assert result["updated"] >= 1
        assert not result.get("blocked")
        assert "finish_check.py" not in result["locally_modified"]
        assert _installed_script(target_dir).read_bytes() == (
            studio_dir / "finish_check.py"
        ).read_bytes()

    def test_override_and_sentinel_are_never_written(self, target_dir, studio_dir):
        """The two files a repo owns. Studio writes neither, on either subcommand."""
        from install import update_studio

        install_studio(target_dir, studio_dir)
        update_studio(target_dir, studio_dir)

        dot_studio = target_dir / ".studio"
        assert not (dot_studio / "finish-check.txt").exists()
        assert not (dot_studio / FINISH_CHECK_SENTINEL).exists()
        assert [key for key in _manifest(target_dir) if "finish-check" in key] == []
