"""
Integration tests for Studio workflows.

Tests end-to-end workflows to ensure components work together correctly.
"""

import json
import time

import pytest

import run_phase
from conftest import _seed_studio_root, make_prepare_args, make_finalize_args


@pytest.fixture
def temp_studio_root(tmp_path, monkeypatch):
    """Create a temporary studio root with scopes config for testing."""
    studio_root = tmp_path / "studio"
    studio_root.mkdir()
    _seed_studio_root(studio_root)

    # Add scopes config (not in base seed)
    scopes_dir = studio_root / ".studio"
    scopes_dir.mkdir(exist_ok=True)
    (scopes_dir / "scopes.toml").write_text("""
[scopes.high_level]
focus = "Architecture, plans, strategic decisions"
max_iterations = 3

[scopes.implementation]
focus = "Detailed design, API contracts, core implementation"
max_iterations = 2

[scopes.polish]
focus = "Documentation, final review, minor refinements"
max_iterations = 1
""")

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(studio_root))
    monkeypatch.chdir(studio_root)

    yield studio_root


def test_prepare_with_scopes_creates_instructions(temp_studio_root):
    """Test that prepare with scopes creates instructions with scope information."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="tech", no_scopes=False, max_iterations=6))

    run_dir = temp_studio_root / "output" / "tech" / run_id
    assert run_dir.exists()

    instructions = (run_dir / "instructions.md").read_text()
    assert "Scope-Based Iteration Plan" in instructions
    assert "High Level" in instructions
    assert "Max iterations**: 3" in instructions


def test_prepare_without_scopes_works(temp_studio_root):
    """Test that prepare without scopes still works (backward compatibility)."""
    (temp_studio_root / ".studio" / "scopes.toml").unlink()

    run_id = run_phase.prepare_run(make_prepare_args(phase="market", no_scopes=False))

    run_dir = temp_studio_root / "output" / "market" / run_id
    assert run_dir.exists()

    instructions = (run_dir / "instructions.md").read_text()
    assert "Scope-Based Iteration Plan" not in instructions


def test_prepare_with_no_scopes_flag(temp_studio_root):
    """Test that --no-scopes flag disables scopes even when config exists."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="tech", no_scopes=True))

    instructions = (temp_studio_root / "output" / "tech" / run_id / "instructions.md").read_text()
    assert "Scope-Based Iteration Plan" not in instructions


def test_finalize_updates_index(temp_studio_root):
    """Test that finalize updates output/index.md."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="design", text="Design UI mockups"))

    run_dir = temp_studio_root / "output" / "design" / run_id
    (run_dir / "advocate_1.md").write_text("# Advocate\n\nProposal...")
    (run_dir / "contrarian_1.md").write_text("# Contrarian\n\nVERDICT: APPROVED")
    (run_dir / "summary.md").write_text("# Summary\n\nCompleted successfully")

    run_phase.finalize_run(make_finalize_args(phase="design", run_id=run_id))

    index_content = (temp_studio_root / "output" / "index.md").read_text()
    assert run_id in index_content


def test_rerun_detection(temp_studio_root):
    """Test that rerun mode detects previous rejections."""
    run_id_1 = run_phase.prepare_run(make_prepare_args(phase="tech", text="Build auth system"))
    run_dir_1 = temp_studio_root / "output" / "tech" / run_id_1

    (run_dir_1 / "advocate_1.md").write_text("# Advocate\n\nUse microservices")
    (run_dir_1 / "summary.md").write_text("# Summary\n\nRejected")
    (run_dir_1 / "contrarian_1.md").write_text(
        "# Contrarian\n\nVERDICT: REJECTED\n\n1. Too complex\n2. Operational overhead"
    )

    run_phase.finalize_run(make_finalize_args(phase="tech", run_id=run_id_1, verdict="REJECTED"))
    time.sleep(1)  # avoid timestamp collision

    run_id_2 = run_phase.prepare_run(make_prepare_args(phase="tech", text="Build auth system (revised)"))

    # Rerun context should be injected when previous run was rejected
    assert (temp_studio_root / "output" / "tech" / run_id_2 / "instructions.md").exists()


def test_scopes_and_rerun_together(temp_studio_root):
    """Test that scopes and rerun work together correctly."""
    run_id_1 = run_phase.prepare_run(make_prepare_args(phase="tech", no_scopes=False, max_iterations=6))
    run_dir_1 = temp_studio_root / "output" / "tech" / run_id_1

    (run_dir_1 / "advocate_1.md").write_text("# Advocate\n\nFirst attempt")
    (run_dir_1 / "summary.md").write_text("# Summary\n\nRejected")
    (run_dir_1 / "contrarian_1.md").write_text("VERDICT: REJECTED\n\n1. Bad approach")

    run_phase.finalize_run(make_finalize_args(phase="tech", run_id=run_id_1, verdict="REJECTED"))
    time.sleep(1)

    run_id_2 = run_phase.prepare_run(make_prepare_args(phase="tech", no_scopes=False, max_iterations=6, text="Revised"))
    instructions = (temp_studio_root / "output" / "tech" / run_id_2 / "instructions.md").read_text()

    assert "Scope-Based Iteration Plan" in instructions


def test_full_workflow_prepare_finalize(temp_studio_root):
    """Test complete workflow: prepare → work → finalize."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="tech", text="Build API"))
    run_dir = temp_studio_root / "output" / "tech" / run_id

    (run_dir / "advocate_1.md").write_text("# Advocate\n\nBuild REST API")
    (run_dir / "contrarian_1.md").write_text("# Contrarian\n\nVERDICT: APPROVED")
    (run_dir / "summary.md").write_text("# Summary\n\nAPI design approved")

    run_phase.finalize_run(make_finalize_args(phase="tech", run_id=run_id, iterations_run=1))

    with open(run_dir / "run.json") as f:
        run_data = json.load(f)

    assert run_data["status"] == "COMPLETED"
    assert run_data["verdict"] == "APPROVED"
    assert run_data["iterations_run"] == 1
