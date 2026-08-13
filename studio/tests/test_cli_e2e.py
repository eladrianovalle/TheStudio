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


class TestCLIOutcomes:
    """The rate -> export-outcomes -> import-outcomes -> stats bridge."""

    def _seed_rated_run(self, root: Path) -> Path:
        run_dir = root / "output" / "studio" / "run_studio_20260101_000000"
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(json.dumps({
            "run_id": "run_studio_20260101_000000", "phase": "studio",
            "status": "completed", "verdict": "APPROVED",
        }))
        return run_dir

    def test_rate_records_outcome(self, cli_studio_root):
        run_dir = self._seed_rated_run(cli_studio_root)
        result = _run_cli(
            "rate", "--run-dir", str(run_dir), "--score", "4",
            "--shipped", "yes", "--impact", "major", "--changed", "cut lobby scope",
            studio_root=cli_studio_root,
        )
        assert result.returncode == 0, result.stderr
        rating = json.loads((run_dir / "rating.json").read_text())
        assert rating["outcome"] == {"shipped": "yes", "impact": "major", "changed": "cut lobby scope"}

    def test_export_import_stats_roundtrip(self, cli_studio_root, tmp_path):
        run_dir = self._seed_rated_run(cli_studio_root)
        _run_cli(
            "rate", "--run-dir", str(run_dir), "--score", "4",
            "--shipped", "yes", "--impact", "major", "--changed", "cut lobby scope",
            studio_root=cli_studio_root,
        )
        export_path = tmp_path / "export.jsonl"
        exp = _run_cli(
            "export-outcomes", "--repo", "pictorly", "--out", str(export_path),
            studio_root=cli_studio_root,
        )
        assert exp.returncode == 0, exp.stderr
        records = [json.loads(x) for x in export_path.read_text().splitlines() if x.strip()]
        assert records and records[0]["repo"] == "pictorly"

        imp = _run_cli("import-outcomes", "--from", str(export_path), studio_root=cli_studio_root)
        assert imp.returncode == 0, imp.stderr
        ledger = cli_studio_root / "knowledge" / "outcomes.jsonl"
        assert ledger.is_file()

        # Re-import must dedup, not duplicate.
        _run_cli("import-outcomes", "--from", str(export_path), studio_root=cli_studio_root)
        assert len([x for x in ledger.read_text().splitlines() if x.strip()]) == 1

        stats = _run_cli("stats", studio_root=cli_studio_root)
        assert stats.returncode == 0, stats.stderr
        assert "Outcomes (did it ship" in stats.stdout
        assert "cut lobby scope" in stats.stdout


class TestRetiredMetricsCommands:
    """The volunteer-fed metrics commands are gone, not deprecated."""

    @pytest.mark.parametrize("command", ["record-metrics", "show-metrics"])
    def test_command_is_rejected_as_an_invalid_choice(self, cli_studio_root, command):
        result = _run_cli(command, "--help", studio_root=cli_studio_root)
        assert result.returncode != 0
        assert "invalid choice" in result.stderr
        assert command in result.stderr

    def test_a_command_that_survived_still_works(self, cli_studio_root):
        """Guards the test above: the CLI itself is fine, these two names are not."""
        result = _run_cli("show-clarity", "--help", studio_root=cli_studio_root)
        assert result.returncode == 0, result.stderr


class TestRetiredEfficiencyMetrics:
    """Nothing on the dashboard reports a number a human had to type in.

    ``--hours`` and ``--cost`` were the only way tokens, cost, and hours ever
    reached ``run.json``, and nobody ever passed them. The flags, the numbers they
    fed, and the two dashboard blocks that read them are all gone together.
    """

    def _finalize_a_run(self, root: Path) -> str:
        """Prepare and finalize one real run, returning its run id."""
        prep = _run_cli(
            "prepare", "--phase", "tech", "--text", "Build API", "--no-scopes",
            studio_root=root,
        )
        assert prep.returncode == 0, prep.stderr
        run_id = next(
            word.strip(".")
            for line in prep.stdout.splitlines()
            for word in line.split()
            if word.startswith("run_tech_")
        )
        run_dir = root / "output" / "tech" / run_id
        (run_dir / "advocate_1.md").write_text("# Advocate\nProposal")
        (run_dir / "contrarian_1.md").write_text("# Contrarian\nVERDICT: APPROVED")
        (run_dir / "summary.md").write_text("# Summary\nDone")
        fin = _run_cli(
            "finalize", "--phase", "tech", "--run-id", run_id,
            "--status", "completed", "--verdict", "APPROVED",
            studio_root=root,
        )
        assert fin.returncode == 0, fin.stderr
        return run_id

    def test_finalize_rejects_the_retired_flags(self, cli_studio_root):
        """argparse refuses the flags before finalize runs, so no run is needed.

        The stderr assertion is what carries this: it pins the failure to the
        retired flags rather than to anything about the run itself.
        """
        result = _run_cli(
            "finalize", "--phase", "tech", "--run-id", "run_tech_20260101_000000",
            "--cost", "5", "--hours", "2",
            studio_root=cli_studio_root,
        )
        assert result.returncode != 0
        assert "unrecognized arguments: --cost 5 --hours 2" in result.stderr

    def test_finalize_writes_no_hours_or_cost(self, cli_studio_root):
        run_id = self._finalize_a_run(cli_studio_root)

        meta = json.loads(
            (cli_studio_root / "output" / "tech" / run_id / "run.json").read_text()
        )
        assert "hours" not in meta and "cost" not in meta

        run_log = (cli_studio_root / "knowledge" / "run_log.md").read_text()
        assert run_id in run_log, "the run never reached the log, so it proves nothing"
        assert "Hours:" not in run_log and "Cost:" not in run_log

    def test_dashboard_has_no_efficiency_or_trend_block(self, cli_studio_root):
        self._finalize_a_run(cli_studio_root)

        dashboard = _run_cli("stats", studio_root=cli_studio_root)
        assert dashboard.returncode == 0, dashboard.stderr
        assert "Total runs: 1" in dashboard.stdout, "no finalized run reached stats"
        assert "Efficiency" not in dashboard.stdout
        assert "Trend Alerts" not in dashboard.stdout

    def test_json_dashboard_drops_the_retired_keys(self, cli_studio_root):
        self._finalize_a_run(cli_studio_root)

        result = _run_cli("stats", "--json", studio_root=cli_studio_root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["total_runs"] == 1
        for key in ("tokens", "cost", "hours", "trend_alerts"):
            assert key not in payload

    def test_trend_alerts_is_gone_from_stats(self):
        """The whole feature, not just its inputs: importing it must fail."""
        with pytest.raises(ImportError):
            from stats import detect_trend_alerts  # noqa: F401
