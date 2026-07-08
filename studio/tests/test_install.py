"""Tests for cross-repo Studio installation.

Tests cover:
  - install_studio: copies source, slash commands, config, manifest, VERSION
  - check_studio: detects up-to-date, changed, missing
  - update_studio: refreshes source, preserves user customizations
  - slash commands copied verbatim (no rewriting needed)
"""
import json
import shutil
import subprocess
import pytest
from pathlib import Path

import install
from install import (
    install_studio,
    check_studio,
    update_studio,
    _SENTINEL_BEGIN,
    _SENTINEL_END,
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


class TestInstallStudio:
    """Tests for install_studio()."""

    def test_creates_studio_source_dir(self, target_dir, studio_dir):
        """Install creates .studio/source/ with Python files."""
        install_studio(target_dir, studio_dir)
        source = target_dir / ".studio" / "source"
        assert source.is_dir()
        assert (source / "run_phase.py").is_file()
        assert (source / "decision_points.py").is_file()
        assert (source / "install.py").is_file()

    def test_installed_snapshot_imports(self, target_dir, studio_dir):
        """The installed snapshot must import cleanly in a fresh interpreter.

        This is the guard against SOURCE_FILES drifting behind run_phase's import
        graph: if a module that run_phase imports (directly or transitively) isn't
        shipped, the installed CLI dies with ModuleNotFoundError. Importing the
        snapshot exercises the whole closure, so a missing file fails here.
        """
        import subprocess
        import sys

        install_studio(target_dir, studio_dir)
        source = target_dir / ".studio" / "source"
        result = subprocess.run(
            [sys.executable, "-c", "import run_phase"],
            cwd=str(source), capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_creates_slash_commands(self, target_dir, studio_dir):
        """Install creates .claude/commands/ with rewritten slash commands."""
        install_studio(target_dir, studio_dir)
        commands = target_dir / ".claude" / "commands"
        assert (commands / "run-phase.md").is_file()
        assert (commands / "run-studio-phase.md").is_file()

    def test_slash_commands_copied_verbatim(self, target_dir, studio_dir):
        """Slash commands are copied verbatim (no rewriting needed)."""
        install_studio(target_dir, studio_dir)
        src = studio_dir.parent / ".claude" / "commands" / "run-phase.md"
        dst = target_dir / ".claude" / "commands" / "run-phase.md"
        assert src.read_text() == dst.read_text()

    def test_creates_version_file(self, target_dir, studio_dir):
        """Install creates .studio/VERSION with metadata."""
        install_studio(target_dir, studio_dir)
        version_path = target_dir / ".studio" / "VERSION"
        assert version_path.is_file()
        version = json.loads(version_path.read_text())
        assert "installed_at" in version
        assert "file_count" in version
        assert version["file_count"] > 0

    def test_creates_manifest(self, target_dir, studio_dir):
        """Install creates .studio/MANIFEST.json with checksums."""
        install_studio(target_dir, studio_dir)
        manifest_path = target_dir / ".studio" / "MANIFEST.json"
        assert manifest_path.is_file()
        manifest = json.loads(manifest_path.read_text())
        assert "run_phase.py" in manifest
        assert len(manifest["run_phase.py"]) == 64  # SHA-256 hex

    def test_manifest_covers_claude_commands_and_workflows(self, target_dir, studio_dir):
        """Manifest checksums the verbatim .claude/ commands + workflows too, so the
        clobber guard can see local edits to them — not just .studio/source/ files."""
        install_studio(target_dir, studio_dir)
        manifest = json.loads((target_dir / ".studio" / "MANIFEST.json").read_text())
        assert ".claude/commands/run-phase.md" in manifest
        assert ".claude/workflows/implementation-loop.js" in manifest
        # Recorded checksum matches the installed file on disk.
        wf = target_dir / ".claude" / "workflows" / "implementation-loop.js"
        import hashlib
        assert manifest[".claude/workflows/implementation-loop.js"] == \
            hashlib.sha256(wf.read_bytes()).hexdigest()

    def test_creates_output_and_knowledge_dirs(self, target_dir, studio_dir):
        """Install creates .studio/output/ and .studio/knowledge/."""
        install_studio(target_dir, studio_dir)
        assert (target_dir / ".studio" / "output").is_dir()
        assert (target_dir / ".studio" / "knowledge").is_dir()

    def test_copies_config_files(self, target_dir, studio_dir):
        """Install copies config files."""
        install_studio(target_dir, studio_dir)
        source = target_dir / ".studio" / "source"
        assert (source / "config" / "scopes.toml").is_file()
        assert (source / "studio.manifest.json").is_file()

    def test_ships_scopes_guide(self, target_dir, studio_dir):
        """SCOPES_GUIDE.md is shipped so the CLI's 'see SCOPES_GUIDE' pointers resolve."""
        install_studio(target_dir, studio_dir)
        assert (target_dir / ".studio" / "source" / "docs" / "SCOPES_GUIDE.md").is_file()

    def test_ships_implementation_loop(self, target_dir, studio_dir):
        """Install ships the writer/editor loop: source, config, command, workflow."""
        install_studio(target_dir, studio_dir)
        source = target_dir / ".studio" / "source"
        # Python source + shipped config default
        assert (source / "impl_loop.py").is_file()
        assert (source / "config" / "implementation_loop.toml").is_file()
        # Slash command
        assert (target_dir / ".claude" / "commands" / "forge.md").is_file()
        # Claude Code workflow (copied verbatim, like commands)
        wf = target_dir / ".claude" / "workflows" / "implementation-loop.js"
        assert wf.is_file()
        src_wf = studio_dir.parent / ".claude" / "workflows" / "implementation-loop.js"
        assert wf.read_text() == src_wf.read_text()

    def test_copies_role_packs(self, target_dir, studio_dir):
        """Install copies role pack JSON files."""
        install_studio(target_dir, studio_dir)
        packs = list((target_dir / ".studio" / "source" / "role_packs").glob("*.json"))
        assert len(packs) > 0

    def test_no_prompt_docs_shipped(self, target_dir, studio_dir):
        """Studio ships no role-prompt docs (they're project-supplied), but the
        prompt-doc glob mechanism stays wired for projects that add their own."""
        install_studio(target_dir, studio_dir)
        prompts = target_dir / ".studio" / "source" / "docs" / "role_prompts"
        # Decoupled from product-specific prompts — none shipped.
        assert not prompts.exists() or not list(prompts.glob("*.md"))
        # Mechanism preserved.
        from install import PROMPT_DOC_GLOB
        assert PROMPT_DOC_GLOB == "docs/role_prompts/*.md"

    def test_idempotent(self, target_dir, studio_dir):
        """Running install twice doesn't break anything."""
        install_studio(target_dir, studio_dir)
        install_studio(target_dir, studio_dir)
        assert (target_dir / ".studio" / "source" / "run_phase.py").is_file()

    def test_preserves_existing_user_files(self, target_dir, studio_dir):
        """Install doesn't clobber user customizations in .studio/."""
        dot_studio = target_dir / ".studio"
        dot_studio.mkdir(parents=True, exist_ok=True)
        custom = dot_studio / "scopes.toml"
        custom.write_text("# my custom scopes", encoding="utf-8")

        install_studio(target_dir, studio_dir)

        assert custom.read_text() == "# my custom scopes"


class TestCheckStudio:
    """Tests for check_studio()."""

    def test_not_installed(self, target_dir, studio_dir):
        """Check reports not installed when no VERSION file."""
        status = check_studio(target_dir, studio_dir)
        assert status["installed"] is False

    def test_up_to_date(self, target_dir, studio_dir):
        """Check reports up to date right after install."""
        install_studio(target_dir, studio_dir)
        status = check_studio(target_dir, studio_dir)
        assert status["installed"] is True
        assert status["up_to_date"] is True
        assert status["changed"] == []
        assert status["missing"] == []

    def test_detects_changed_file(self, target_dir, studio_dir):
        """Check detects when an installed file differs from source."""
        install_studio(target_dir, studio_dir)

        # Tamper with installed file
        installed = target_dir / ".studio" / "source" / "run_phase.py"
        installed.write_text("# tampered", encoding="utf-8")

        # Recalculate manifest to reflect tampered checksum
        manifest_path = target_dir / ".studio" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        import hashlib
        manifest["run_phase.py"] = hashlib.sha256(b"# tampered").hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        status = check_studio(target_dir, studio_dir)
        assert status["up_to_date"] is False
        assert "run_phase.py" in status["changed"]

    def test_check_reports_locally_modified(self, target_dir, studio_dir):
        """check_studio flags installed source files edited after install (the clobber set)."""
        install_studio(target_dir, studio_dir)
        f = target_dir / ".studio" / "source" / "config" / "scopes.toml"
        f.write_text(f.read_text() + "\n# local edit\n", encoding="utf-8")
        status = check_studio(target_dir, studio_dir)
        assert "config/scopes.toml" in status["locally_modified"]
        assert "run_phase.py" not in status["locally_modified"]  # untouched → not flagged

    def test_check_reports_locally_modified_command(self, target_dir, studio_dir):
        """A locally-edited .claude/ command/workflow is in the clobber set too."""
        install_studio(target_dir, studio_dir)
        cmd = target_dir / ".claude" / "commands" / "run-phase.md"
        cmd.write_text(cmd.read_text() + "\n<!-- local edit -->\n", encoding="utf-8")
        status = check_studio(target_dir, studio_dir)
        assert ".claude/commands/run-phase.md" in status["locally_modified"]


class TestUpdateStudio:
    """Tests for update_studio()."""

    def test_update_when_up_to_date(self, target_dir, studio_dir):
        """Update is a no-op when already up to date."""
        install_studio(target_dir, studio_dir)
        result = update_studio(target_dir, studio_dir)
        assert result["updated"] == 0
        assert result["added"] == 0

    def test_update_not_installed_raises(self, target_dir, studio_dir):
        """Update raises when Studio not installed."""
        with pytest.raises(FileNotFoundError):
            update_studio(target_dir, studio_dir)

    def test_update_refreshes_files(self, target_dir, studio_dir):
        """Update refreshes changed files."""
        install_studio(target_dir, studio_dir)

        # Tamper with installed file AND its manifest checksum
        installed = target_dir / ".studio" / "source" / "run_phase.py"
        installed.write_text("# tampered", encoding="utf-8")
        manifest_path = target_dir / ".studio" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        import hashlib
        manifest["run_phase.py"] = hashlib.sha256(b"# tampered").hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = update_studio(target_dir, studio_dir)
        assert result["updated"] >= 1

        # Verify file was restored
        content = installed.read_text()
        assert content != "# tampered"


    def test_update_from_installed_copy(self, target_dir, studio_dir):
        """Update works when studio_dir points to the installed .studio/source/ (self-update)."""
        install_studio(target_dir, studio_dir)

        # Simulate running update from the installed copy itself
        installed_source = target_dir / ".studio" / "source"
        result = update_studio(target_dir, installed_source)
        # Should succeed (no SameFileError) and report no changes
        assert result["updated"] == 0
        assert result["added"] == 0

    def test_update_blocked_on_local_modification(self, target_dir, studio_dir):
        """A locally-edited snapshot file blocks update (no clobber); --force overrides."""
        install_studio(target_dir, studio_dir)
        # Local edit to an installed source file, WITHOUT syncing the manifest (drift).
        cfg = target_dir / ".studio" / "source" / "config" / "scopes.toml"
        cfg.write_text(cfg.read_text() + "\n# my local tweak\n", encoding="utf-8")
        # Make an update appear pending by dropping a different file from the manifest.
        manifest_path = target_dir / ".studio" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["verdict.py"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # update refuses to clobber the local edit
        result = update_studio(target_dir, studio_dir)
        assert result.get("blocked") is True
        assert "config/scopes.toml" in result["locally_modified"]
        assert "# my local tweak" in cfg.read_text()  # edit survived

        # --force overrides — the edit is intentionally overwritten
        forced = update_studio(target_dir, studio_dir, force=True)
        assert not forced.get("blocked")
        assert "# my local tweak" not in cfg.read_text()

    def test_update_blocked_on_locally_modified_command(self, target_dir, studio_dir):
        """An edited .claude/ command blocks update (clobber guard); --force overwrites it."""
        install_studio(target_dir, studio_dir)
        cmd = target_dir / ".claude" / "commands" / "run-phase.md"
        cmd.write_text(cmd.read_text() + "\n<!-- my command tweak -->\n", encoding="utf-8")
        # Make an update appear pending by dropping an unrelated file from the manifest.
        manifest_path = target_dir / ".studio" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["verdict.py"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = update_studio(target_dir, studio_dir)
        assert result.get("blocked") is True
        assert ".claude/commands/run-phase.md" in result["locally_modified"]
        assert "<!-- my command tweak -->" in cmd.read_text()  # edit survived

        forced = update_studio(target_dir, studio_dir, force=True)
        assert not forced.get("blocked")
        assert "<!-- my command tweak -->" not in cmd.read_text()


class TestSnapshotStaleDetection:
    """Regression tests for #20: check/update run via the installed snapshot
    must compare against live upstream source, not the snapshot itself."""

    def _stale_install(self, target_dir, studio_dir):
        """Install, then make the snapshot+manifest agree on a value that
        DIFFERS from live source — i.e. a stale install that snapshot-vs-self
        would wrongly call up to date."""
        import hashlib

        install_studio(target_dir, studio_dir)
        snap_file = target_dir / ".studio" / "source" / "verdict.py"
        snap_file.write_text("# stale snapshot", encoding="utf-8")
        manifest_path = target_dir / ".studio" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["verdict.py"] = hashlib.sha256(b"# stale snapshot").hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_check_detects_stale_via_version_source_path(
        self, target_dir, studio_dir, monkeypatch
    ):
        """check_studio (studio_dir=None) run from the snapshot resolves live
        source from VERSION and detects the drift instead of trusting itself."""
        import install

        self._stale_install(target_dir, studio_dir)
        snapshot = target_dir / ".studio" / "source"
        # Simulate invocation through the installed snapshot.
        monkeypatch.setattr(install, "_get_studio_root", lambda: snapshot)

        status = check_studio(target_dir)  # default source resolution
        assert status["up_to_date"] is False
        assert "verdict.py" in status["changed"]
        assert status["warning"] is None  # live source resolved cleanly

    def test_update_refreshes_via_resolved_live_source(
        self, target_dir, studio_dir, monkeypatch
    ):
        """update_studio run from the snapshot copies from live source and
        restores the stale file."""
        import install

        self._stale_install(target_dir, studio_dir)
        snapshot = target_dir / ".studio" / "source"
        monkeypatch.setattr(install, "_get_studio_root", lambda: snapshot)

        result = update_studio(target_dir)
        assert result["updated"] >= 1
        restored = (snapshot / "verdict.py").read_text()
        assert restored != "# stale snapshot"

    def test_warns_when_source_path_unresolvable(
        self, target_dir, studio_dir, monkeypatch
    ):
        """If VERSION.source_path is gone, surface a warning rather than a
        silent (and unreliable) 'up to date'."""
        import install

        install_studio(target_dir, studio_dir)
        version_path = target_dir / ".studio" / "VERSION"
        version = json.loads(version_path.read_text())
        version["source_path"] = str(target_dir / "does_not_exist")
        version_path.write_text(json.dumps(version), encoding="utf-8")

        snapshot = target_dir / ".studio" / "source"
        monkeypatch.setattr(install, "_get_studio_root", lambda: snapshot)

        status = check_studio(target_dir)
        assert status["warning"] is not None
        assert "snapshot" in status["warning"]

    def test_self_install_preserves_upstream_source_path(
        self, target_dir, studio_dir
    ):
        """Re-installing FROM the snapshot must not record a self-pointing
        source_path — it would make future snapshot checks compare the snapshot
        against itself (silent 'up to date'). A prior upstream pointer survives."""
        install_studio(target_dir, studio_dir)  # source_path -> real upstream
        snapshot = target_dir / ".studio" / "source"

        # Simulate `init`/install run through the installed snapshot itself.
        install_studio(target_dir, snapshot)

        version = json.loads((target_dir / ".studio" / "VERSION").read_text())
        assert Path(version["source_path"]).resolve() == studio_dir.resolve()
        assert Path(version["source_path"]).resolve() != snapshot.resolve()


class TestSlashCommandsUseDirectPaths:
    """Verify slash commands use .studio/source/ paths directly (no rewriting needed)."""

    def test_no_studio_root_refs_in_source_commands(self, studio_dir):
        """Source slash commands should not contain $STUDIO_ROOT references."""
        commands_dir = studio_dir.parent / ".claude" / "commands"
        for cmd_file in commands_dir.glob("*.md"):
            content = cmd_file.read_text(encoding="utf-8")
            assert '"$STUDIO_ROOT/' not in content, (
                f"{cmd_file.name} still contains $STUDIO_ROOT references"
            )

    def test_commands_reference_studio_source(self, studio_dir):
        """Slash commands that invoke run_phase.py use .studio/source/ paths."""
        commands_dir = studio_dir.parent / ".claude" / "commands"
        run_phase_cmd = commands_dir / "run-phase.md"
        content = run_phase_cmd.read_text(encoding="utf-8")
        assert ".studio/source/run_phase.py" in content


class TestClaudeMdInjection:
    """Tests for coding principles injection into target CLAUDE.md."""

    def test_creates_claude_md_when_missing(self, target_dir, studio_dir):
        """Install creates CLAUDE.md with principles when none exists."""
        install_studio(target_dir, studio_dir)
        claude_md = target_dir / "CLAUDE.md"
        assert claude_md.is_file()
        content = claude_md.read_text()
        assert _SENTINEL_BEGIN in content
        assert _SENTINEL_END in content
        assert "Think Before Coding" in content

    def test_injects_into_existing_claude_md(self, target_dir, studio_dir):
        """Install injects principles into existing CLAUDE.md without clobbering."""
        claude_md = target_dir / "CLAUDE.md"
        claude_md.write_text("# My Game\n\nThis is my game project.\n", encoding="utf-8")

        install_studio(target_dir, studio_dir)

        content = claude_md.read_text()
        assert "# My Game" in content
        assert "This is my game project." in content
        assert _SENTINEL_BEGIN in content
        assert "Think Before Coding" in content

    def test_principles_inserted_after_heading(self, target_dir, studio_dir):
        """Principles block appears after the first heading, not before it."""
        claude_md = target_dir / "CLAUDE.md"
        claude_md.write_text("# My Game\n\nProject description.\n", encoding="utf-8")

        install_studio(target_dir, studio_dir)

        content = claude_md.read_text()
        heading_pos = content.index("# My Game")
        sentinel_pos = content.index(_SENTINEL_BEGIN)
        assert sentinel_pos > heading_pos

    def test_update_replaces_sentinel_block(self, target_dir, studio_dir):
        """Re-install replaces the sentinel block in place, not duplicating."""
        claude_md = target_dir / "CLAUDE.md"
        claude_md.write_text("# My Game\n\nProject description.\n", encoding="utf-8")

        install_studio(target_dir, studio_dir)
        install_studio(target_dir, studio_dir)

        content = claude_md.read_text()
        assert content.count(_SENTINEL_BEGIN) == 1
        assert content.count(_SENTINEL_END) == 1

    def test_preserves_content_around_sentinels(self, target_dir, studio_dir):
        """Content before and after the sentinel block is preserved on update."""
        claude_md = target_dir / "CLAUDE.md"
        claude_md.write_text(
            "# My Game\n\nProject description.\n\n## Architecture\n\nSome details.\n",
            encoding="utf-8",
        )

        install_studio(target_dir, studio_dir)

        content = claude_md.read_text()
        assert "Project description." in content
        assert "## Architecture" in content
        assert "Some details." in content

    def test_copies_principles_source_file(self, target_dir, studio_dir):
        """CODING_PRINCIPLES.md is also copied into .studio/source/docs/."""
        install_studio(target_dir, studio_dir)
        assert (target_dir / ".studio" / "source" / "docs" / "CODING_PRINCIPLES.md").is_file()


class TestClaudeMdSync:
    """The coding-principles block in a target's CLAUDE.md is injected at install
    time and is NOT a manifest file, so check/update must detect and refresh it
    directly rather than by checksum (see _principles_block_stale)."""

    @staticmethod
    def _drift_block(claude_md: Path) -> None:
        """Make the installed principles block differ from the current template."""
        content = claude_md.read_text(encoding="utf-8")
        start = content.index(_SENTINEL_BEGIN)
        end = content.index(_SENTINEL_END) + len(_SENTINEL_END)
        drifted = content[start:end].replace("Talk to Humans", "OLD PRINCIPLE")
        claude_md.write_text(content[:start] + drifted + content[end:], encoding="utf-8")

    def test_fresh_install_block_not_stale(self, target_dir, studio_dir):
        """Right after install the block matches the template — not flagged."""
        install_studio(target_dir, studio_dir)
        status = check_studio(target_dir, studio_dir)
        assert status["claude_md_stale"] is False
        assert status["up_to_date"] is True

    def test_check_detects_stale_block(self, target_dir, studio_dir):
        """A principles block that drifted from the template is flagged."""
        install_studio(target_dir, studio_dir)
        self._drift_block(target_dir / "CLAUDE.md")
        status = check_studio(target_dir, studio_dir)
        assert status["claude_md_stale"] is True
        assert status["up_to_date"] is False

    def test_check_detects_missing_block(self, target_dir, studio_dir):
        """A CLAUDE.md that lost its sentinels is flagged so update re-injects."""
        install_studio(target_dir, studio_dir)
        (target_dir / "CLAUDE.md").write_text(
            "# My Game\n\nNo principles block here.\n", encoding="utf-8"
        )
        status = check_studio(target_dir, studio_dir)
        assert status["claude_md_stale"] is True

    def test_missing_claude_md_not_flagged(self, target_dir, studio_dir):
        """A deliberately-removed CLAUDE.md isn't resurrected by a routine check."""
        install_studio(target_dir, studio_dir)
        (target_dir / "CLAUDE.md").unlink()
        status = check_studio(target_dir, studio_dir)
        assert status["claude_md_stale"] is False

    def test_update_refreshes_block_preserving_notes(self, target_dir, studio_dir):
        """Update refreshes a drifted block in place and leaves the user's notes."""
        claude_md = target_dir / "CLAUDE.md"
        claude_md.write_text("# My Game\n\nMy project notes.\n", encoding="utf-8")
        install_studio(target_dir, studio_dir)

        self._drift_block(claude_md)
        # Add user content AFTER the block too, to prove it survives.
        claude_md.write_text(
            claude_md.read_text(encoding="utf-8") + "\n## My Section\n\nKeep me.\n",
            encoding="utf-8",
        )

        result = update_studio(target_dir, studio_dir)
        assert result.get("claude_md_refreshed") is True

        refreshed = claude_md.read_text(encoding="utf-8")
        assert "Talk to Humans" in refreshed        # template restored
        assert "OLD PRINCIPLE" not in refreshed      # drift gone
        assert "My project notes." in refreshed      # notes above kept
        assert "Keep me." in refreshed               # notes below kept

    def test_update_runs_when_only_block_stale(self, target_dir, studio_dir):
        """Source files all match; only the block drifted — update still runs."""
        install_studio(target_dir, studio_dir)
        self._drift_block(target_dir / "CLAUDE.md")

        result = update_studio(target_dir, studio_dir)
        assert result.get("claude_md_refreshed") is True
        # No source-file churn, so counts are zero, but it was not a no-op.
        assert result["updated"] == 0
        assert result["added"] == 0


class TestSourceAtDefaultBranch:
    """The backstop that makes check/update read the finished `main` version of
    Studio source, never whatever branch the source checkout is parked on."""

    @staticmethod
    def _make_source_repo(root: Path) -> Path:
        """A minimal git repo shaped like Studio (studio/ under root) with `main`
        committed. Returns the studio/ dir."""
        studio = root / "studio"
        studio.mkdir(parents=True)
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
        (studio / "marker.txt").write_text("main version\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
        return studio

    def test_disabled_yields_original(self, tmp_path):
        studio = self._make_source_repo(tmp_path / "src")
        with install._source_at_default_branch(studio, enabled=False) as (src, note):
            assert src == studio
            assert note is None

    def test_non_git_yields_original(self, tmp_path):
        plain = tmp_path / "plain" / "studio"
        plain.mkdir(parents=True)
        with install._source_at_default_branch(plain, enabled=True) as (src, note):
            assert src == plain
            assert note is None

    def test_on_main_clean_uses_fast_path(self, tmp_path):
        studio = self._make_source_repo(tmp_path / "src")
        # Already on main + clean → source used directly, no worktree spun up.
        with install._source_at_default_branch(studio, enabled=True) as (src, note):
            assert src == studio
            assert note is None

    def test_reads_main_when_parked_on_feature_branch(self, tmp_path):
        root = tmp_path / "src"
        studio = self._make_source_repo(root)
        # Park on a feature branch that changes the marker, plus an uncommitted edit.
        subprocess.run(["git", "-C", str(root), "checkout", "-q", "-b", "feature"], check=True)
        (studio / "marker.txt").write_text("feature version\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "commit", "-qam", "feat"], check=True)
        (studio / "marker.txt").write_text("uncommitted edit\n", encoding="utf-8")

        with install._source_at_default_branch(studio, enabled=True) as (src, note):
            assert src != studio
            assert (src / "marker.txt").read_text(encoding="utf-8") == "main version\n"
            assert note is not None and "feature" in note

        # The throwaway worktree is cleaned up: only the primary remains.
        listed = subprocess.run(
            ["git", "-C", str(root), "worktree", "list"],
            capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()
        assert len(listed) == 1

    def test_reads_committed_main_when_dirty_on_main(self, tmp_path):
        root = tmp_path / "src"
        studio = self._make_source_repo(root)
        # Still on main, but with an uncommitted edit → read committed main, not it.
        (studio / "marker.txt").write_text("uncommitted edit\n", encoding="utf-8")
        with install._source_at_default_branch(studio, enabled=True) as (src, note):
            assert (src / "marker.txt").read_text(encoding="utf-8") == "main version\n"
            assert note is None  # on main (just dirty), so no branch was bypassed


class TestCheckStudioStaleness:
    """check-install refuses a false 'up to date' when the resolved Studio source
    is itself behind its own git remote (the #20 follow-up). Hermetic: a temp git
    source repo wired to a LOCAL BARE remote, no network."""

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args],
                       check=True, capture_output=True, text=True)

    def _source_repo_with_remote(self, tmp_path, studio_dir):
        """Build a hermetic Studio source repo (a copy of the real studio/ tree)
        on `main`, wired to a bare origin remote sharing one commit. Returns the
        studio/ dir inside it."""
        root = tmp_path / "src"
        studio = root / "studio"
        shutil.copytree(
            studio_dir, studio,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
        remote = tmp_path / "origin.git"
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "--bare", "-q", str(remote)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "-q", str(root)],
            check=True, capture_output=True,
        )
        self._git(root, "config", "user.email", "t@t")
        self._git(root, "config", "user.name", "t")
        self._git(root, "remote", "add", "origin", str(remote))
        self._git(root, "add", "-A")
        self._git(root, "commit", "-qm", "init")
        self._git(root, "push", "-q", "-u", "origin", "main")
        return studio

    def _advance_origin(self, tmp_path, remote_name="origin.git"):
        """Push one new commit onto the bare remote's main through a throwaway
        clone, so the source repo's local main falls behind origin/main. The new
        commit adds a non-source file, so it moves the ref WITHOUT changing any
        installed file — isolating staleness from the file diff."""
        remote = tmp_path / remote_name
        clone = tmp_path / "advancer"
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)],
                       check=True, capture_output=True)
        self._git(clone, "config", "user.email", "t@t")
        self._git(clone, "config", "user.name", "t")
        (clone / "NOTES.txt").write_text("moved origin ahead\n", encoding="utf-8")
        self._git(clone, "add", "-A")
        self._git(clone, "commit", "-qm", "advance origin")
        self._git(clone, "push", "-q", "origin", "main")

    def test_stale_source_refuses_up_to_date(self, target_dir, tmp_path, monkeypatch):
        """A source whose local main is behind origin returns up_to_date=False and
        a stale `staleness`, even though every installed file still matches."""
        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin(tmp_path)
        # check_studio(studio_dir=None) auto-resolves the source through _get_studio_root.
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        status = check_studio(target_dir)  # fetch=True catches the unfetched origin

        assert status["up_to_date"] is False
        assert status["staleness"] is not None
        assert status["staleness"]["is_stale"] is True
        assert status["staleness"]["behind"] == 1
        assert status["staleness"]["remote_ref"] == "origin/main"
        # Isolated staleness signal: the honest diff, not phantom file changes.
        assert status["changed"] == []
        assert status["missing"] == []

    def test_even_source_still_reports_up_to_date(self, target_dir, tmp_path, monkeypatch):
        """Regression guard: an even/clean source (not behind origin) must still
        report up_to_date=True and must not be falsely flagged stale."""
        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        status = check_studio(target_dir)  # fetch against origin, which is even

        assert status["up_to_date"] is True
        assert status["staleness"] is not None
        assert status["staleness"]["is_stale"] is False

    def test_no_fetch_uses_cached_refs(self, target_dir, tmp_path, monkeypatch):
        """--no-fetch (fetch=False) compares against cached refs only. Origin moved
        ahead but was never fetched, so the cached refs still look even → not stale."""
        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin(tmp_path)  # origin ahead, but source never fetches it
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        status = check_studio(target_dir, fetch=False)

        assert status["staleness"] is not None
        assert status["staleness"]["is_stale"] is False
        assert status["up_to_date"] is True

    def test_handler_exits_nonzero_on_stale_source(self, target_dir, tmp_path, monkeypatch):
        """The check-install handler prints a block and exits non-zero over a stale
        source, so a false 'up to date' can never reach stdout."""
        import argparse
        import run_phase

        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin(tmp_path)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        args = argparse.Namespace(target=target_dir, no_fetch=False)
        with pytest.raises(SystemExit) as exc:
            run_phase._do_check_install(args)
        assert exc.value.code == 1

    def test_status_is_json_serializable_over_stale_source(
        self, target_dir, tmp_path, monkeypatch
    ):
        """The check_studio return stays plain-data — `staleness` is a dict, not a
        dataclass — so a caller can json.dumps the whole status without choking."""
        import json

        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin(tmp_path)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        status = check_studio(target_dir)

        assert isinstance(status["staleness"], dict)
        assert status["staleness"]["is_stale"] is True
        json.dumps(status)  # must not raise

    def test_handler_shows_local_edits_over_stale_source(
        self, target_dir, tmp_path, monkeypatch, capsys
    ):
        """A user with local edits over a stale source sees the LOCAL EDITS clobber
        preview from check-install itself, not only when a later update refuses."""
        import argparse
        import run_phase

        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin(tmp_path)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)
        # Drift an installed snapshot file so it registers as a local edit.
        edited = target_dir / ".studio" / "source" / "run_phase.py"
        edited.write_text(
            edited.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8"
        )

        args = argparse.Namespace(target=target_dir, no_fetch=False)
        with pytest.raises(SystemExit) as exc:
            run_phase._do_check_install(args)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "behind" in out          # the stale-source block printed
        assert "LOCAL EDITS" in out     # and the clobber preview alongside it


# A source file that install_studio copies into .studio/source/ — editing it on
# origin/main is how we prove the update re-installs the fresher tree.
_STALE_MARKER_KEY = "docs/SCOPES_GUIDE.md"
_STALE_MARKER_LINE = "\nUPDATED-ON-ORIGIN-MAIN marker line\n"


class TestUpdateStudioStaleness:
    """/studio-update (update_studio) refuses to no-op over a stale source and
    re-installs from origin/main, computing staleness in its OWN scope rather than
    inheriting it from the delegated check_studio. Hermetic: a temp git source repo
    wired to a LOCAL BARE remote, no network."""

    @staticmethod
    def _git(repo, *args):
        subprocess.run(["git", "-C", str(repo), *args],
                       check=True, capture_output=True, text=True)

    def _source_repo_with_remote(self, tmp_path, studio_dir):
        """Build a hermetic Studio source repo (a copy of the real studio/ tree)
        on `main`, wired to a bare origin remote sharing one commit. Returns the
        studio/ dir inside it."""
        root = tmp_path / "src"
        studio = root / "studio"
        shutil.copytree(
            studio_dir, studio,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
        remote = tmp_path / "origin.git"
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "--bare", "-q", str(remote)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "-q", str(root)],
            check=True, capture_output=True,
        )
        self._git(root, "config", "user.email", "t@t")
        self._git(root, "config", "user.name", "t")
        self._git(root, "remote", "add", "origin", str(remote))
        self._git(root, "add", "-A")
        self._git(root, "commit", "-qm", "init")
        self._git(root, "push", "-q", "-u", "origin", "main")
        return studio

    def _advance_origin_with_source_edit(self, tmp_path):
        """Push one commit onto the bare remote that EDITS an installed source file,
        so the source's local main falls behind an origin/main that carries newer
        Studio content. Returns the new content of that file, so a test can assert
        the consumer ends up matching it after update. No network (local bare)."""
        remote = tmp_path / "origin.git"
        clone = tmp_path / "advancer"
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)],
                       check=True, capture_output=True)
        self._git(clone, "config", "user.email", "t@t")
        self._git(clone, "config", "user.name", "t")
        marker = clone / "studio" / _STALE_MARKER_KEY
        new_content = marker.read_text(encoding="utf-8") + _STALE_MARKER_LINE
        marker.write_text(new_content, encoding="utf-8")
        self._git(clone, "add", "-A")
        self._git(clone, "commit", "-qm", "advance origin with source edit")
        self._git(clone, "push", "-q", "origin", "main")
        return new_content

    def test_update_stale_source_reinstalls_from_origin(
        self, target_dir, tmp_path, monkeypatch
    ):
        """THE DELEGATION-TRAP GUARD. The source's local main is behind an
        origin/main that carries newer Studio content. update_studio must NOT
        no-op: it installs origin/main's content, so the consumer's installed file
        ends up matching origin's NEWER version. Fails if staleness is wrongly
        routed through the delegated check_studio (which reads the stale local main
        with an explicit dir → staleness off → false 'already up to date')."""
        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)  # consumer gets the OLD local-main content
        newer = self._advance_origin_with_source_edit(tmp_path)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        result = update_studio(target_dir)  # fetch=True catches the unfetched origin

        # It proceeded (did not take the 'already up to date' no-op).
        assert not result.get("blocked")
        assert result["updated"] > 0
        assert result["staleness"] is not None
        assert result["staleness"]["is_stale"] is True
        assert result["staleness"]["behind"] == 1
        assert result["staleness"]["remote_ref"] == "origin/main"
        # The consumer's installed file now matches origin/main's NEWER version.
        installed = target_dir / ".studio" / "source" / _STALE_MARKER_KEY
        assert installed.read_text(encoding="utf-8") == newer

    def test_no_fetch_over_stale_source_no_ops_as_today(
        self, target_dir, tmp_path, monkeypatch
    ):
        """--no-fetch (fetch=False) can't see the unfetched origin, so the cached
        refs still look even → update behaves exactly as today (a clean no-op)."""
        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin_with_source_edit(tmp_path)  # origin ahead, never fetched
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        result = update_studio(target_dir, fetch=False)

        assert result["staleness"] is not None
        assert result["staleness"]["is_stale"] is False
        assert result["updated"] == 0 and result["added"] == 0

    def test_even_source_update_behaves_as_today(
        self, target_dir, tmp_path, monkeypatch
    ):
        """Regression guard: an even/clean source (not behind origin) still no-ops
        when the consumer already matches, and is not falsely flagged stale."""
        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        result = update_studio(target_dir)  # fetch against origin, which is even

        assert result["staleness"] is not None
        assert result["staleness"]["is_stale"] is False
        assert result["updated"] == 0 and result["added"] == 0

    def test_stale_source_blocked_on_local_modification(
        self, target_dir, tmp_path, monkeypatch
    ):
        """The clobber precondition still holds over a stale source: a locally
        edited installed file blocks the update (unless --force), even though the
        source is behind origin and would otherwise re-install from it."""
        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin_with_source_edit(tmp_path)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)
        # Drift an installed file so update has something it would clobber.
        edited = target_dir / ".studio" / "source" / "scopes.py"
        edited.write_text(edited.read_text(encoding="utf-8") + "\n# local edit\n",
                          encoding="utf-8")

        blocked = update_studio(target_dir)
        assert blocked.get("blocked") is True
        assert "scopes.py" in blocked["locally_modified"]
        assert blocked["staleness"]["is_stale"] is True

        # --force overrides the block and still re-installs from origin/main.
        forced = update_studio(target_dir, force=True)
        assert not forced.get("blocked")
        assert forced["updated"] > 0
        assert forced["staleness"]["is_stale"] is True

    def test_update_handler_prints_pull_hint_over_stale_source(
        self, target_dir, tmp_path, monkeypatch, capsys
    ):
        """The update handler surfaces the staleness note and the one command that
        catches the user's own source checkout up (never pulling it for them)."""
        import argparse
        import run_phase

        source = self._source_repo_with_remote(tmp_path, install._get_studio_root())
        install_studio(target_dir, source)
        self._advance_origin_with_source_edit(tmp_path)
        monkeypatch.setattr(install, "_get_studio_root", lambda: source)

        args = argparse.Namespace(target=target_dir, force=False, no_fetch=False)
        run_phase._do_update(args)

        out = capsys.readouterr().out
        assert "origin/main" in out
        assert "git -C" in out and "pull" in out
