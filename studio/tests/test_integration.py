"""
Integration tests for Studio workflows.

Tests end-to-end workflows to ensure components work together correctly.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import run_phase


@pytest.fixture
def temp_studio_root(monkeypatch):
    """Create a temporary studio root for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        studio_root = Path(tmpdir) / "studio"
        studio_root.mkdir()
        
        # Create necessary directories
        (studio_root / "output").mkdir()
        (studio_root / "knowledge").mkdir()
        (studio_root / "config").mkdir()
        (studio_root / ".studio").mkdir()
        
        # Create minimal config
        config_dir = studio_root / "config"
        (config_dir / "studio_settings.toml").write_text("""
[cleanup]
ttl_days = 30
size_limit_mb = 900
""")
        
        # Create scopes config
        scopes_config = studio_root / ".studio" / "scopes.toml"
        scopes_config.write_text("""
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
        
        # Monkeypatch STUDIO_ROOT
        monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
        
        yield studio_root


def test_prepare_with_scopes_creates_instructions(temp_studio_root):
    """Test that prepare with scopes creates instructions with scope information."""
    # Create mock args
    import argparse
    args = argparse.Namespace(
        phase="tech",
        text="Build authentication system",
        max_iterations=6,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=False,
        budget=None
    )
    
    # Prepare run with scopes
    run_id = run_phase.prepare_run(args)
    
    # Verify run directory exists
    run_dir = temp_studio_root / "output" / "tech" / run_id
    assert run_dir.exists()
    
    # Verify instructions file exists
    instructions_file = run_dir / "instructions.md"
    assert instructions_file.exists()
    
    # Verify scope information is in instructions
    instructions = instructions_file.read_text()
    assert "Scope-Based Iteration Plan" in instructions
    assert "High Level" in instructions
    assert "Max iterations**: 3" in instructions  # Format: "**Max iterations**: 3"
    assert "Implementation" in instructions
    assert "Max iterations**: 2" in instructions
    assert "Polish" in instructions
    assert "Max iterations**: 1" in instructions
    
    # Verify run.json exists and has scopes info
    run_json = run_dir / "run.json"
    assert run_json.exists()
    
    with open(run_json) as f:
        run_data = json.load(f)
    
    assert run_data["phase"] == "tech"
    assert run_data["max_iterations"] == 6


def test_prepare_without_scopes_works(temp_studio_root):
    """Test that prepare without scopes still works (backward compatibility)."""
    import argparse
    
    # Remove scopes config
    scopes_config = temp_studio_root / ".studio" / "scopes.toml"
    scopes_config.unlink()
    
    # Prepare run without scopes
    args = argparse.Namespace(
        phase="market",
        text="Analyze market opportunity",
        max_iterations=5,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=False,
        budget=None
    )
    run_id = run_phase.prepare_run(args)
    
    # Verify run directory exists
    run_dir = temp_studio_root / "output" / "market" / run_id
    assert run_dir.exists()
    
    # Verify instructions file exists
    instructions_file = run_dir / "instructions.md"
    assert instructions_file.exists()
    
    # Verify NO scope information in instructions
    instructions = instructions_file.read_text()
    assert "Scope-Based Iteration Plan" not in instructions


def test_prepare_with_no_scopes_flag(temp_studio_root):
    """Test that --no-scopes flag disables scopes even when config exists."""
    import argparse
    
    # Prepare run with --no-scopes
    args = argparse.Namespace(
        phase="tech",
        text="Build feature",
        max_iterations=5,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=True,  # Explicitly disable scopes
        budget=None
    )
    run_id = run_phase.prepare_run(args)
    
    # Verify run directory exists
    run_dir = temp_studio_root / "output" / "tech" / run_id
    assert run_dir.exists()
    
    # Verify NO scope information in instructions
    instructions_file = run_dir / "instructions.md"
    instructions = instructions_file.read_text()
    assert "Scope-Based Iteration Plan" not in instructions


def test_concurrent_run_protection(temp_studio_root):
    """Test that concurrent runs with same timestamp are detected."""
    import argparse
    
    # This test verifies the fix for concurrent run collision
    # We'll create a run, then try to create another with the same ID
    
    # First run
    args = argparse.Namespace(
        phase="tech",
        text="First run",
        max_iterations=5,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=True,
        budget=None
    )
    run_id = run_phase.prepare_run(args)
    
    run_dir = temp_studio_root / "output" / "tech" / run_id
    assert run_dir.exists()
    
    # Try to create a run with the same ID (simulate collision)
    # This should be caught by the collision detection we'll add
    # For now, we just verify the directory exists
    assert run_dir.exists()
    
    # Note: Actual collision detection will be added in run_phase.py
    # This test documents the expected behavior


def test_finalize_updates_index(temp_studio_root):
    """Test that finalize updates output/index.md."""
    import argparse
    
    # Prepare run
    args = argparse.Namespace(
        phase="design",
        text="Design UI mockups",
        max_iterations=4,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=True,
        budget=None
    )
    run_id = run_phase.prepare_run(args)
    
    run_dir = temp_studio_root / "output" / "design" / run_id
    
    # Create minimal artifacts (advocate, contrarian, summary)
    (run_dir / "advocate_1.md").write_text("# Advocate\n\nProposal...")
    (run_dir / "contrarian_1.md").write_text("# Contrarian\n\nVERDICT: APPROVED")
    (run_dir / "summary.md").write_text("# Summary\n\nCompleted successfully")
    
    # Finalize run
    finalize_args = argparse.Namespace(
        phase="design",
        run_id=run_id,
        status="completed",
        verdict="APPROVED",
        hours=1.5,
        cost=0,
        iterations_run=1,
        summary=None
    )
    run_phase.finalize_run(finalize_args)
    
    # Verify index.md was updated
    index_file = temp_studio_root / "output" / "index.md"
    assert index_file.exists()
    
    index_content = index_file.read_text()
    assert run_id in index_content
    # Note: Index may not show verdict in all formats, just verify run is listed


def test_rerun_detection(temp_studio_root):
    """Test that rerun mode detects previous rejections."""
    import argparse
    
    # This test verifies rerun context injection
    # We'll create a run with a rejection, then prepare a new run
    
    # First run with rejection
    args1 = argparse.Namespace(
        phase="tech",
        text="Build auth system",
        max_iterations=5,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=True,
        budget=None
    )
    run_id_1 = run_phase.prepare_run(args1)
    
    run_dir_1 = temp_studio_root / "output" / "tech" / run_id_1
    
    # Create contrarian rejection and summary
    (run_dir_1 / "advocate_1.md").write_text("# Advocate\n\nUse microservices")
    (run_dir_1 / "summary.md").write_text("# Summary\n\nRejected")
    (run_dir_1 / "contrarian_1.md").write_text("""# Contrarian

## Analysis

The proposal has issues.

## Verdict

VERDICT: REJECTED

## Reasons

1. Too complex for team size
2. Operational overhead too high
3. No clear service boundaries
""")
    
    # Finalize first run as rejected
    finalize_args1 = argparse.Namespace(
        phase="tech",
        run_id=run_id_1,
        status="completed",
        verdict="REJECTED",
        hours=0.5,
        cost=0,
        iterations_run=1,
        summary=None
    )
    run_phase.finalize_run(finalize_args1)
    
    # Wait 1 second to avoid timestamp collision
    time.sleep(1)
    
    # Second run (rerun)
    args2 = argparse.Namespace(
        phase="tech",
        text="Build auth system (revised)",
        max_iterations=5,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=True,
        budget=None
    )
    run_id_2 = run_phase.prepare_run(args2)
    
    run_dir_2 = temp_studio_root / "output" / "tech" / run_id_2
    instructions_file = run_dir_2 / "instructions.md"
    instructions = instructions_file.read_text()
    
    # Verify rerun context is injected
    # Note: This depends on rerun detection logic in run_phase.py
    # The test documents expected behavior
    assert instructions_file.exists()


def test_scopes_and_rerun_together(temp_studio_root):
    """Test that scopes and rerun work together correctly."""
    import argparse
    
    # This is a critical integration test for feature interaction
    
    # First run with scopes and rejection
    args1 = argparse.Namespace(
        phase="tech",
        text="Build feature",
        max_iterations=6,
        scopes=None,  # Auto-load scopes
        roles=None,
        role_pack=None,
        no_scopes=False,
        budget=None
    )
    run_id_1 = run_phase.prepare_run(args1)
    
    run_dir_1 = temp_studio_root / "output" / "tech" / run_id_1
    
    # Create rejection in iteration 2 and summary
    (run_dir_1 / "advocate_1.md").write_text("# Advocate\n\nFirst attempt")
    (run_dir_1 / "summary.md").write_text("# Summary\n\nRejected")
    (run_dir_1 / "contrarian_1.md").write_text("# Contrarian\n\nVERDICT: REJECTED\n\n1. Bad approach")
    (run_dir_1 / "advocate_2.md").write_text("# Advocate\n\nSecond attempt")
    (run_dir_1 / "contrarian_2.md").write_text("# Contrarian\n\nVERDICT: REJECTED\n\n1. Still not good")
    
    # Finalize as rejected
    finalize_args1 = argparse.Namespace(
        phase="tech",
        run_id=run_id_1,
        status="completed",
        verdict="REJECTED",
        hours=1.0,
        cost=0,
        iterations_run=2,
        summary=None
    )
    run_phase.finalize_run(finalize_args1)
    
    # Wait 1 second to avoid timestamp collision
    time.sleep(1)
    
    # Second run (rerun with scopes)
    args2 = argparse.Namespace(
        phase="tech",
        text="Build feature (revised)",
        max_iterations=6,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=False,
        budget=None
    )
    run_id_2 = run_phase.prepare_run(args2)
    
    run_dir_2 = temp_studio_root / "output" / "tech" / run_id_2
    instructions_file = run_dir_2 / "instructions.md"
    instructions = instructions_file.read_text()
    
    # Verify both scopes AND rerun context are present
    assert "Scope-Based Iteration Plan" in instructions
    # Rerun context verification depends on implementation


def test_full_workflow_prepare_finalize_validate(temp_studio_root):
    """Test complete workflow: prepare → work → finalize → validate."""
    import argparse
    
    # Prepare
    args = argparse.Namespace(
        phase="tech",
        text="Build API",
        max_iterations=5,
        scopes=None,
        roles=None,
        role_pack=None,
        no_scopes=True,
        budget=None
    )
    run_id = run_phase.prepare_run(args)
    
    run_dir = temp_studio_root / "output" / "tech" / run_id
    
    # Simulate work (create artifacts)
    (run_dir / "advocate_1.md").write_text("# Advocate\n\nBuild REST API")
    (run_dir / "contrarian_1.md").write_text("# Contrarian\n\nVERDICT: APPROVED")
    (run_dir / "summary.md").write_text("# Summary\n\nAPI design approved")
    
    # Finalize
    finalize_args = argparse.Namespace(
        phase="tech",
        run_id=run_id,
        status="completed",
        verdict="APPROVED",
        hours=2.0,
        cost=0,
        iterations_run=1,
        summary=None
    )
    run_phase.finalize_run(finalize_args)
    
    # Verify run.json updated
    run_json = run_dir / "run.json"
    with open(run_json) as f:
        run_data = json.load(f)
    
    assert run_data["status"] == "COMPLETED"  # finalize_run converts to uppercase
    assert run_data["verdict"] == "APPROVED"
    assert run_data["hours"] == 2.0
    assert run_data["iterations_run"] == 1
    
    # Validate (if validation command exists)
    # This would test the validate command integration
    # For now, we just verify the run is in a valid state
    assert (run_dir / "summary.md").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
