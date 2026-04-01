"""Tests for cross-repo Studio installation.

Tests cover:
  - install_studio: copies source, slash commands, config, manifest, VERSION
  - check_studio: detects up-to-date, changed, missing
  - update_studio: refreshes source, preserves user customizations
  - slash commands copied verbatim (no rewriting needed)
"""
import json
import pytest
from pathlib import Path

from install import (
    install_studio,
    check_studio,
    update_studio,
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

    def test_copies_role_packs(self, target_dir, studio_dir):
        """Install copies role pack JSON files."""
        install_studio(target_dir, studio_dir)
        packs = list((target_dir / ".studio" / "source" / "role_packs").glob("*.json"))
        assert len(packs) > 0

    def test_copies_prompt_docs(self, target_dir, studio_dir):
        """Install copies role prompt docs."""
        install_studio(target_dir, studio_dir)
        prompts = target_dir / ".studio" / "source" / "docs" / "role_prompts"
        assert prompts.is_dir()
        assert len(list(prompts.glob("*.md"))) > 0

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
