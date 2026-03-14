"""End-to-end tests exercising run_phase.py as a CLI subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _seed_studio_root

RUN_PHASE = str(Path(__file__).resolve().parents[1] / "run_phase.py")


@pytest.fixture
def cli_studio_root(tmp_path):
    """Seeded studio root for CLI tests (no monkeypatch — uses env in subprocess)."""
    root = tmp_path / "studio"
    root.mkdir()
    _seed_studio_root(root)
    return root


def _run_cli(*args, studio_root: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    env["STUDIO_ROOT"] = str(studio_root)
    env["STUDIO_ARTIFACT_ROOT"] = str(studio_root)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, RUN_PHASE, *args],
        capture_output=True, text=True, env=env, cwd=str(studio_root),
    )


class TestCLIPrepare:
    def test_prepare_market_phase(self, cli_studio_root):
        result = _run_cli(
            "prepare", "--phase", "market",
            "--text", "A cozy farming sim",
            "--max-iterations", "2",
            "--no-scopes",
            studio_root=cli_studio_root,
        )
        assert result.returncode == 0, result.stderr
        assert "run_market_" in result.stdout

        # Verify files were created
        output_dir = cli_studio_root / "output" / "market"
        run_dirs = list(output_dir.glob("run_market_*"))
        assert len(run_dirs) == 1

        run_dir = run_dirs[0]
        assert (run_dir / "instructions.md").exists()
        assert (run_dir / "run.json").exists()

        meta = json.loads((run_dir / "run.json").read_text())
        assert meta["phase"] == "market"
        assert meta["max_iterations"] == 2

    def test_prepare_studio_phase_with_roles(self, cli_studio_root):
        result = _run_cli(
            "prepare", "--phase", "studio",
            "--text", "Self-critique",
            "--role-pack", "studio_core",
            "--roles", "+design",
            "--no-scopes",
            studio_root=cli_studio_root,
        )
        assert result.returncode == 0, result.stderr

        output_dir = cli_studio_root / "output" / "studio"
        run_dirs = list(output_dir.glob("run_studio_*"))
        assert len(run_dirs) == 1

        meta = json.loads((run_dirs[0] / "run.json").read_text())
        assert "marketing" in meta["studio_roles"]["invited"]
        assert "design" in meta["studio_roles"]["invited"]


class TestCLIFinalize:
    def test_finalize_completes_run(self, cli_studio_root):
        # Prepare
        prep = _run_cli(
            "prepare", "--phase", "tech",
            "--text", "Build API",
            "--no-scopes",
            studio_root=cli_studio_root,
        )
        assert prep.returncode == 0
        # Extract run_id from stdout
        run_id = None
        for line in prep.stdout.splitlines():
            if "run_tech_" in line:
                for word in line.split():
                    if word.startswith("run_tech_"):
                        run_id = word.strip(".")
                        break
        assert run_id is not None, f"Could not find run_id in stdout: {prep.stdout}"

        run_dir = cli_studio_root / "output" / "tech" / run_id
        assert run_dir.exists()

        # Create artifacts
        (run_dir / "advocate_1.md").write_text("# Advocate\nProposal")
        (run_dir / "contrarian_1.md").write_text("# Contrarian\nVERDICT: APPROVED")
        (run_dir / "summary.md").write_text("# Summary\nDone")

        # Finalize
        fin = _run_cli(
            "finalize", "--phase", "tech",
            "--run-id", run_id,
            "--status", "completed",
            "--verdict", "APPROVED",
            "--hours", "1.0",
            "--cost", "0",
            studio_root=cli_studio_root,
        )
        assert fin.returncode == 0, fin.stderr

        meta = json.loads((run_dir / "run.json").read_text())
        assert meta["status"] == "COMPLETED"
        assert meta["verdict"] == "APPROVED"

    def test_finalize_fails_on_missing_artifacts(self, cli_studio_root):
        # Prepare
        prep = _run_cli(
            "prepare", "--phase", "market",
            "--text", "Test",
            "--no-scopes",
            studio_root=cli_studio_root,
        )
        assert prep.returncode == 0
        run_id = None
        for line in prep.stdout.splitlines():
            if "run_market_" in line:
                for word in line.split():
                    if word.startswith("run_market_"):
                        run_id = word.strip(".")
                        break
        assert run_id is not None

        # Finalize without creating artifacts
        fin = _run_cli(
            "finalize", "--phase", "market",
            "--run-id", run_id,
            "--status", "completed",
            "--verdict", "APPROVED",
            studio_root=cli_studio_root,
        )
        assert fin.returncode != 0


class TestCLICleanup:
    def test_cleanup_dry_run(self, cli_studio_root):
        result = _run_cli(
            "cleanup", "--dry-run",
            studio_root=cli_studio_root,
        )
        assert result.returncode == 0


class TestCLIValidate:
    def test_validate_with_artifacts(self, cli_studio_root):
        # Prepare a run
        prep = _run_cli(
            "prepare", "--phase", "market",
            "--text", "Test validation",
            "--no-scopes",
            studio_root=cli_studio_root,
        )
        assert prep.returncode == 0
        run_id = None
        for line in prep.stdout.splitlines():
            if "run_market_" in line:
                for word in line.split():
                    if word.startswith("run_market_"):
                        run_id = word.strip(".")
                        break
        assert run_id is not None

        run_dir = cli_studio_root / "output" / "market" / run_id
        (run_dir / "advocate_1.md").write_text("# Advocate\n\n## Market Analysis\n\nContent here with enough words to pass format check.\n\n## Competition\n\nMore content.")
        (run_dir / "contrarian_1.md").write_text("# Contrarian\n\n## Response\n\nContent here.\n\nVERDICT: APPROVED\n\nGood proposal.")

        result = _run_cli(
            "validate", "--phase", "market",
            "--run-id", run_id,
            studio_root=cli_studio_root,
        )
        # Validate should run without crashing (may have warnings)
        assert result.returncode == 0
