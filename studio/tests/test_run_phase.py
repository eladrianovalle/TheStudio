"""Unit tests for run_phase.py core functions."""
import pytest

import run_phase
from conftest import make_prepare_args, make_finalize_args


def test_prepare_and_finalize_creates_index_and_log(studio_root):
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id

    assert run_dir.exists()
    assert (run_dir / "instructions.md").exists()

    # Simulate produced artifacts
    (run_dir / "advocate_1.md").write_text("Advocate output", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("Contrarian output", encoding="utf-8")
    (run_dir / "summary.md").write_text("Summary output", encoding="utf-8")

    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    meta = run_phase.load_json(run_dir / "run.json")
    assert meta["iterations_run"] == 1
    assert meta["hours"] == 1.0

    index_contents = (studio_root / "output/index.md").read_text(encoding="utf-8")
    assert run_id in index_contents

    log_contents = (studio_root / "knowledge/run_log.md").read_text(encoding="utf-8")
    assert run_id in log_contents
    assert "Hours: 1.0" in log_contents


def test_finalize_requires_required_artifacts(studio_root):
    run_id = run_phase.prepare_run(make_prepare_args(phase="design"))
    run_dir = studio_root / "output" / "design" / run_id

    # Only summary exists; advocate/contrarian missing
    (run_dir / "summary.md").write_text("Summary only", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        run_phase.finalize_run(
            make_finalize_args(
                phase="design",
                run_id=run_id,
                verdict="REJECTED",
                hours=None,
                cost=None,
            )
        )


def test_parse_cli_args_normalizes_prepare_roles_tokens():
    args = run_phase.parse_cli_args(
        [
            "prepare",
            "--phase",
            "studio",
            "--text",
            "Role selection check",
            "--roles",
            "+product",
            "+engineering",
            "+qa",
            "-marketing",
            "--max-iterations",
            "3",
        ]
    )

    assert args.command == "prepare"
    assert args.roles == ["+product", "+engineering", "+qa", "-marketing"]


def test_resolve_studio_roles_returns_none_for_non_studio(studio_root):
    """_resolve_studio_roles returns (None, None) for non-studio phases."""
    args = make_prepare_args(phase="market")
    role_meta, role_details = run_phase._resolve_studio_roles(args)
    assert role_meta is None
    assert role_details is None


def test_resolve_studio_roles_returns_roles_for_studio(studio_root):
    """_resolve_studio_roles returns role metadata for studio phase."""
    args = make_prepare_args(phase="studio")
    role_meta, role_details = run_phase._resolve_studio_roles(args)
    assert role_meta is not None
    assert "invited" in role_meta
    assert len(role_meta["invited"]) > 0
    assert role_details is not None
    assert len(role_details) == len(role_meta["invited"])


def test_resolve_scopes_disabled_with_no_scopes_flag(studio_root):
    """_resolve_scopes returns all None when --no-scopes is set."""
    args = make_prepare_args(no_scopes=True)
    config, alloc, meta = run_phase._resolve_scopes(args)
    assert config is None
    assert alloc is None
    assert meta is None


def test_build_run_meta_structure(studio_root):
    """_build_run_meta returns well-formed metadata dict."""
    now = run_phase.utc_now()
    meta = run_phase._build_run_meta(
        phase="tech", text="Build API", now=now,
        run_id="run_tech_20260307_120000",
        args=make_prepare_args(phase="tech"),
        studio_role_meta=None, scopes_meta=None,
    )
    assert meta["run_id"] == "run_tech_20260307_120000"
    assert meta["phase"] == "tech"
    assert meta["input"] == "Build API"
    assert meta["status"] == "PENDING"
    assert "storage" in meta


def test_instruction_doc_uses_generic_title(studio_root):
    """build_instruction_doc should NOT contain 'Cascade' in the title."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "Studio Instructions" in instructions
    assert "Cascade" not in instructions


def test_output_root_defaults_to_origin_repo_when_running_outside_studio(tmp_path, monkeypatch):
    studio_root = tmp_path / "studio"
    studio_root.mkdir()
    project_root = tmp_path / "game_repo"
    project_root.mkdir()

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.chdir(project_root)

    output_root = run_phase.get_output_root()
    knowledge_path = run_phase.get_knowledge_log_path()

    assert output_root == project_root / ".studio" / "output"
    assert knowledge_path == project_root / ".studio" / "knowledge" / "run_log.md"
