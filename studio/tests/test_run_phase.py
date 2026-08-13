"""Unit tests for run_phase.py core functions."""
import argparse
import json
from pathlib import Path

import pytest

import run_phase
from integrations.slack_digest import INTEGRATIONS_FILENAME, load_integrations_config
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
    assert "hours" not in meta and "cost" not in meta

    index_contents = (studio_root / "output/index.md").read_text(encoding="utf-8")
    assert run_id in index_contents

    log_contents = (studio_root / "knowledge/run_log.md").read_text(encoding="utf-8")
    assert run_id in log_contents
    assert "Hours:" not in log_contents and "Cost:" not in log_contents


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


def test_instruction_doc_has_think_first_checkpoint(studio_root):
    """build_instruction_doc includes the Think-First Checkpoint for advocates."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "Think-First Checkpoint" in instructions
    assert "what you understand the objective to be" in instructions
    assert "correct analysis of the wrong problem" in instructions


def test_instruction_doc_has_contrarian_editor_mandate(studio_root):
    """Deliverable runs carry the always-on contrarian editor mandate."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "Contrarian Mandate" in instructions
    assert "Default to deletion" in instructions


def test_design_phase_has_slop_blacklist_and_goodwill_reservoir(studio_root):
    """Design runs carry the anti-slop blacklist, embarrassment gate, and Goodwill Reservoir."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="design"))
    run_dir = studio_root / "output" / "design" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "AI-slop blacklist" in instructions
    assert "Goodwill Reservoir" in instructions
    assert "embarrassment self-gate" in instructions


def test_market_phase_omits_design_critique_guide(studio_root):
    """The design critique guide is design-only — market runs must not carry it."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="market"))
    run_dir = studio_root / "output" / "market" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "AI-slop blacklist" not in instructions
    assert "Goodwill Reservoir" not in instructions
    assert "embarrassment self-gate" not in instructions


def test_tech_phase_omits_design_critique_guide(studio_root):
    """The design critique guide is design-only — tech runs must not carry it."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="tech"))
    run_dir = studio_root / "output" / "tech" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "AI-slop blacklist" not in instructions
    assert "Goodwill Reservoir" not in instructions
    assert "embarrassment self-gate" not in instructions


def test_instruction_doc_has_open_questions_preflight(studio_root):
    """Deliverable runs open with a required open-questions pre-flight."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "Open-Questions Pre-Flight" in instructions
    assert "Pause on every P0" in instructions


def test_question_mode_omits_editor_mandate_and_preflight(studio_root):
    """Question-surfacing runs must not cut questions or front-load a separate pass."""
    run_id = run_phase.prepare_run(make_prepare_args(mode="questions"))
    run_dir = studio_root / "output" / "market" / run_id
    instructions = (run_dir / "instructions.md").read_text()
    assert "Contrarian Mandate" not in instructions
    assert "Default to deletion" not in instructions
    assert "Open-Questions Pre-Flight" not in instructions


def test_output_root_defaults_to_origin_repo_when_running_outside_studio(tmp_path, monkeypatch):
    # studio_root sits one level down so the caller's repo is genuinely outside the
    # Studio source repo (tmp_path / "studio_src"). A sibling of studio/ would count as
    # part of the source repo and resolve there instead — see the source-repo branch.
    studio_root = tmp_path / "studio_src" / "studio"
    studio_root.mkdir(parents=True)
    project_root = tmp_path / "game_repo"
    project_root.mkdir()

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.chdir(project_root)

    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    output_root = run_phase.get_output_root()
    knowledge_path = run_phase.get_knowledge_log_path()

    assert output_root == project_root / ".studio" / "output"
    assert knowledge_path == project_root / ".studio" / "knowledge" / "run_log.md"


def test_artifact_root_cli_override(tmp_path, monkeypatch):
    """--artifact-root flag overrides cwd and env var."""
    studio_root = tmp_path / "studio"
    studio_root.mkdir()
    explicit_root = tmp_path / "explicit_target"
    explicit_root.mkdir()

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(tmp_path / "should_be_ignored"))
    monkeypatch.chdir(studio_root)  # cwd inside studio — would normally route to studio
    monkeypatch.setattr(run_phase, "_artifact_root_override", explicit_root)

    output_root = run_phase.get_output_root()
    assert output_root == explicit_root / ".studio" / "output"


def _make_source_repo(tmp_path, monkeypatch):
    """Studio's own repo: <repo>/studio holding the running code, plus a bare .studio/.

    Mirrors the real source repo, whose .studio/ deliberately has no VERSION file —
    VERSION is what marks an *installed* repo.
    """
    repo_root = tmp_path / "TheGameStudio"
    studio_root = repo_root / "studio"
    studio_root.mkdir(parents=True)
    (repo_root / ".studio").mkdir()

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)
    monkeypatch.setattr(run_phase, "_artifact_root_warned", False)
    return repo_root, studio_root


def test_artifact_root_is_studio_dir_when_run_from_source_repo_root(tmp_path, monkeypatch):
    """Studio run from its own repo root files artifacts in studio/, not <repo>/.studio/."""
    repo_root, studio_root = _make_source_repo(tmp_path, monkeypatch)
    monkeypatch.chdir(repo_root)

    # Guard against passing for the old reason: this must NOT be the cwd == studio_root
    # branch, which already worked before the source-repo branch existed.
    assert Path.cwd().resolve() != studio_root.resolve()

    assert run_phase.get_artifact_root() == studio_root.resolve()
    assert run_phase.get_output_root() == studio_root.resolve() / "output"


def test_source_repo_resolves_integrations_config_inside_studio(tmp_path, monkeypatch):
    """Where a source-repo run looks for its webhook config, pinned.

    Moving the artifact root moved this too, and it is the one consequence that is
    invisible until it fires: a config sitting at the NEW path is suddenly live, so a
    finalize can start posting digests as a side effect of a path fix. Pin the path so
    that stops being a surprise.
    """
    repo_root, studio_root = _make_source_repo(tmp_path, monkeypatch)
    monkeypatch.chdir(repo_root)

    resolved = run_phase.get_artifact_root() / ".studio" / INTEGRATIONS_FILENAME

    assert resolved == studio_root.resolve() / ".studio" / INTEGRATIONS_FILENAME
    # Not the repo root's .studio/, which is where it resolved before the detection fix.
    assert resolved != repo_root.resolve() / ".studio" / INTEGRATIONS_FILENAME


def test_no_integrations_config_means_no_webhook_post(tmp_path, monkeypatch):
    """A fresh clone has no integrations.toml, and must post nothing.

    `studio/.studio/` is gitignored, so nobody who clones this repo has that file at
    all. The absent case is therefore the common one, and it must resolve to "no
    enabled target" rather than an error or a default-on.
    """
    repo_root, studio_root = _make_source_repo(tmp_path, monkeypatch)
    monkeypatch.chdir(repo_root)
    assert not (studio_root / ".studio" / INTEGRATIONS_FILENAME).exists()

    config = load_integrations_config(run_phase.get_artifact_root())

    assert config == {}
    # This is the exact condition _maybe_notify gates on before posting anything.
    assert not any(config.get(target, {}).get("enabled") for target in ("slack", "n8n"))


def test_artifact_root_is_studio_dir_when_run_from_studio_dir(tmp_path, monkeypatch):
    """The pre-existing cwd-inside-studio branch: same answer, different reason."""
    _repo_root, studio_root = _make_source_repo(tmp_path, monkeypatch)
    monkeypatch.chdir(studio_root)

    assert Path.cwd().resolve() == studio_root.resolve()
    assert run_phase.get_artifact_root() == studio_root.resolve()


def test_artifact_root_is_consuming_repo_for_installed_snapshot(tmp_path, monkeypatch):
    """An installed <repo>/.studio/source snapshot still resolves to the consuming repo."""
    repo_root = tmp_path / "my_game"
    studio_root = repo_root / ".studio" / "source"
    studio_root.mkdir(parents=True)
    (repo_root / ".studio" / "VERSION").write_text("1.0.0\n", encoding="utf-8")

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)
    monkeypatch.setattr(run_phase, "_artifact_root_warned", False)

    monkeypatch.chdir(repo_root)
    assert run_phase.get_artifact_root() == repo_root.resolve()

    # studio_root.parent is <repo>/.studio here, so the source-repo branch must stay out
    # of the way: a snapshot is never its own source repo.
    monkeypatch.chdir(repo_root / ".studio")
    assert run_phase.get_artifact_root() == repo_root.resolve()


def test_artifact_root_is_cwd_for_scaffolded_repo_with_bare_studio_dir(tmp_path, monkeypatch):
    """A repo with .studio/ but no VERSION, unrelated to studio_root, still gets cwd."""
    studio_root = tmp_path / "studio_src" / "studio"
    studio_root.mkdir(parents=True)
    game_repo = tmp_path / "my_game"
    (game_repo / ".studio").mkdir(parents=True)

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)
    monkeypatch.setattr(run_phase, "_artifact_root_warned", False)
    monkeypatch.chdir(game_repo)

    assert run_phase.get_artifact_root() == game_repo.resolve()


def test_artifact_root_flag_and_env_still_win_in_source_repo(tmp_path, monkeypatch):
    """The deliberate overrides outrank the source-repo branch."""
    repo_root, _studio_root = _make_source_repo(tmp_path, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(repo_root)

    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(elsewhere))
    assert run_phase.get_artifact_root() == elsewhere.resolve()

    monkeypatch.setattr(run_phase, "_artifact_root_override", elsewhere)
    assert run_phase.get_artifact_root() == elsewhere.resolve()


def test_source_repo_prepare_writes_no_bridge_doc(tmp_path, monkeypatch):
    """Studio does not scaffold itself a consuming-repo bridge doc."""
    from conftest import _seed_studio_root

    repo_root, studio_root = _make_source_repo(tmp_path, monkeypatch)
    _seed_studio_root(studio_root)
    (studio_root / "docs" / "STUDIO_BRIDGE_TEMPLATE.md").write_text("template", encoding="utf-8")
    monkeypatch.chdir(repo_root)

    run_id = run_phase.prepare_run(make_prepare_args(phase="tech", text="Source repo run"))

    assert (studio_root / "output" / "tech" / run_id / "instructions.md").exists()
    assert not (repo_root / "docs" / "studio-bridge.md").exists()
    assert not (repo_root / ".studio" / "output").exists()


def test_cross_repo_prepare_creates_artifacts_in_caller_repo(tmp_path, monkeypatch):
    """Full prepare from an external repo puts artifacts in that repo, not Studio."""
    from conftest import _seed_studio_root

    studio_root = tmp_path / "studio_src" / "studio"
    studio_root.mkdir(parents=True)
    _seed_studio_root(studio_root)

    game_repo = tmp_path / "my_game"
    game_repo.mkdir()

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.chdir(game_repo)
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    run_id = run_phase.prepare_run(make_prepare_args(phase="market", text="Test cross-repo"))

    # Artifacts should be in game_repo, NOT studio
    run_dir = game_repo / ".studio" / "output" / "market" / run_id
    assert run_dir.exists(), f"Expected run dir at {run_dir}"
    assert (run_dir / "instructions.md").exists()
    assert (run_dir / "run.json").exists()

    # Studio's own output should NOT have this run
    studio_output = studio_root / "output" / "market" / run_id
    assert not studio_output.exists(), "Artifacts should NOT be in Studio repo"

    # Index should be in game_repo
    index_path = game_repo / ".studio" / "output" / "index.md"
    assert index_path.exists()
    assert run_id in index_path.read_text()


def test_cross_repo_scaffold_creates_bridge_doc(tmp_path, monkeypatch):
    """First prepare from external repo creates .studio/ and bridge doc."""
    from conftest import _seed_studio_root

    studio_root = tmp_path / "studio_src" / "studio"
    studio_root.mkdir(parents=True)
    _seed_studio_root(studio_root)

    # Also need the bridge template to exist
    template_dir = studio_root / "docs"
    template_dir.mkdir(exist_ok=True)
    (template_dir / "STUDIO_BRIDGE_TEMPLATE.md").write_text(
        "# Studio Bridge\nexport STUDIO_ROOT=\"/path/to/studio\"\n", encoding="utf-8"
    )

    game_repo = tmp_path / "my_game2"
    game_repo.mkdir()

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.chdir(game_repo)
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    run_phase.prepare_run(make_prepare_args(phase="market", text="Scaffold test"))

    # .studio/ should exist
    assert (game_repo / ".studio").is_dir()
    assert (game_repo / ".studio" / "output").is_dir()
    assert (game_repo / ".studio" / "knowledge").is_dir()

    # Bridge doc should be created with Studio root injected
    bridge = game_repo / "docs" / "studio-bridge.md"
    assert bridge.exists()
    content = bridge.read_text()
    assert str(studio_root.resolve()) in content


def test_cross_repo_scaffold_skips_existing_bridge(tmp_path, monkeypatch):
    """Scaffold does not overwrite an existing bridge doc."""
    from conftest import _seed_studio_root

    studio_root = tmp_path / "studio_src" / "studio"
    studio_root.mkdir(parents=True)
    _seed_studio_root(studio_root)
    (studio_root / "docs").mkdir(exist_ok=True)
    (studio_root / "docs" / "STUDIO_BRIDGE_TEMPLATE.md").write_text("template", encoding="utf-8")

    game_repo = tmp_path / "my_game3"
    game_repo.mkdir()

    # Pre-create a custom bridge doc
    (game_repo / "docs").mkdir()
    (game_repo / "docs" / "studio-bridge.md").write_text("CUSTOM BRIDGE", encoding="utf-8")

    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.chdir(game_repo)
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    run_phase.prepare_run(make_prepare_args(phase="market", text="Existing bridge test"))

    # Custom bridge should be preserved
    bridge = game_repo / "docs" / "studio-bridge.md"
    assert bridge.read_text() == "CUSTOM BRIDGE"


def test_instructions_finalize_snippet_uses_absolute_path(studio_root):
    """The finalize command in instructions.md should use an absolute path to run_phase.py."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="market", text="Absolute path test"))
    run_dir = studio_root / "output" / "market" / run_id
    instructions = (run_dir / "instructions.md").read_text()

    # Should contain absolute path, not just "python run_phase.py"
    assert "/run_phase.py" in instructions
    assert "finalize --phase market" in instructions


def test_finalize_updates_status_to_completed(studio_root):
    """finalize_run should update run.json status from PENDING to COMPLETED."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id

    # Verify initial PENDING status
    meta_before = run_phase.load_json(run_dir / "run.json")
    assert meta_before["status"] == "PENDING"

    # Create required artifacts
    (run_dir / "advocate_1.md").write_text("Advocate output", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("Contrarian output", encoding="utf-8")
    (run_dir / "summary.md").write_text("Summary output", encoding="utf-8")

    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    meta_after = run_phase.load_json(run_dir / "run.json")
    assert meta_after["status"] == "COMPLETED"
    assert meta_after["verdict"] == "APPROVED"
    assert meta_after["iterations_run"] == 1


def test_finalize_updates_status_to_rejected(studio_root):
    """finalize_run with REJECTED verdict records it correctly."""
    run_id = run_phase.prepare_run(make_prepare_args(phase="design"))
    run_dir = studio_root / "output" / "design" / run_id

    (run_dir / "advocate_1.md").write_text("Advocate output", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("Contrarian output", encoding="utf-8")
    (run_dir / "summary.md").write_text("Summary output", encoding="utf-8")

    run_phase.finalize_run(
        make_finalize_args(phase="design", run_id=run_id, verdict="REJECTED")
    )

    meta_after = run_phase.load_json(run_dir / "run.json")
    assert meta_after["status"] == "COMPLETED"
    assert meta_after["verdict"] == "REJECTED"


def test_prepare_with_scopes_integration(studio_root):
    """prepare_run with scopes enabled embeds scope content in instructions."""
    # Create scopes.toml in the studio root
    scopes_dir = studio_root / ".studio"
    scopes_dir.mkdir(parents=True, exist_ok=True)
    (scopes_dir / "scopes.toml").write_text(
        '[scopes.high_level]\n'
        'focus = "Architecture and strategic decisions"\n'
        'max_iterations = 3\n'
        '\n'
        '[scopes.implementation]\n'
        'focus = "Detailed design and API contracts"\n'
        'max_iterations = 2\n',
        encoding="utf-8",
    )

    run_id = run_phase.prepare_run(
        make_prepare_args(no_scopes=False, max_iterations=5)
    )
    run_dir = studio_root / "output" / "market" / run_id

    instructions = (run_dir / "instructions.md").read_text(encoding="utf-8")
    assert "high_level" in instructions.lower() or "High Level" in instructions


# ---------------------------------------------------------------------------
# Cross-run stats
# ---------------------------------------------------------------------------


class _DP:
    """Minimal DecisionPoint stand-in for aggregate_stats tests."""

    def __init__(self, priority, answer=None):
        self.priority = priority
        self.answer = answer


def test_aggregate_stats_empty():
    """No runs yields a zeroed summary."""
    agg = run_phase.aggregate_stats([])
    assert agg["total_runs"] == 0
    assert agg["approval_rate"] is None
    assert "ratings" not in agg


def test_aggregate_stats_full():
    """aggregate_stats rolls up phases, verdicts, decisions."""
    runs = [
        {
            "run_id": "run_market_1", "phase": "market", "status": "COMPLETED",
            "verdict": "APPROVED",
            "_decisions": [_DP("P0", answer="yes"), _DP("P2")],
        },
        {
            "run_id": "run_market_2", "phase": "market", "status": "COMPLETED",
            "verdict": "REJECTED",
            "_decisions": [_DP("P1")],
        },
        {
            "run_id": "run_tech_1", "phase": "tech", "status": "PENDING",
            "verdict": "UNKNOWN",
            "_decisions": [],
        },
    ]
    agg = run_phase.aggregate_stats(runs)

    assert agg["total_runs"] == 3
    assert agg["by_phase"] == {"market": 2, "tech": 1}
    assert agg["by_status"] == {"COMPLETED": 2, "PENDING": 1}
    assert agg["verdicts"] == {"APPROVED": 1, "REJECTED": 1, "UNKNOWN": 1}
    assert agg["approval_rate"] == 0.5  # 1 approved of 2 decided

    assert agg["decisions"]["total"] == 3
    assert agg["decisions"]["by_priority"] == {"P0": 1, "P1": 1, "P2": 1}
    assert agg["decisions"]["answered"] == 1
    assert agg["decisions"]["answer_rate"] == 1 / 3


def test_parse_usage_log():
    """_parse_usage_log resurrects the prepare log into counts."""
    text = (
        "2026-01-01T00:00:00 | prepare | market | deliverables | roles= | scoped=false\n"
        "2026-01-02T00:00:00 | prepare | studio | deliverables | roles=product,design | scoped=true\n"
        "2026-01-03T00:00:00 | prepare | market | questions | roles= | scoped=false\n"
        "garbage line that should be skipped\n"
    )
    usage = run_phase._parse_usage_log(text)
    assert usage["total"] == 3
    assert usage["by_phase"] == {"market": 2, "studio": 1}
    assert usage["by_mode"] == {"deliverables": 2, "questions": 1}
    assert usage["scoped"] == {"true": 1, "false": 2}


def test_format_stats_smoke():
    """format_stats renders the dashboard shell without any optional block."""
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "_decisions": []},
    ])
    out = run_phase.format_stats(agg)
    assert "Studio Cross-Run Stats" in out
    assert "Total runs: 1" in out


# --- Shipped features (read off spec frontmatter) ---

def _spec(status="shipped", *, slug="a-feature", impact="minor", changed="it changed a thing"):
    """A spec file's text: frontmatter first, then prose that must not be parsed."""
    return (
        "---\n"
        f"feature: A Feature\n"
        f"slug: {slug}\n"
        f"status: {status}\n"
        f"shipped_impact: {impact}\n"
        f"shipped_changed: {changed}\n"
        "---\n\n"
        "# A Feature\n\nProse that says status: shipped without meaning it.\n"
    )


def test_summarize_shipped_specs_empty():
    """No shipped specs yields a zeroed summary, not a missing key."""
    from stats import summarize_shipped_specs
    summary = summarize_shipped_specs([])
    assert summary["records"] == 0
    assert summary["impact"] == {"none": 0, "minor": 0, "major": 0}
    assert summary["recent_changed"] == []


def test_summarize_shipped_specs_tallies_impact_and_keeps_change_lines():
    """Each record counts once in its bucket and contributes its change line."""
    from stats import summarize_shipped_specs
    summary = summarize_shipped_specs([
        {"slug": "one", "impact": "major", "changed": "cut lobby scope in half"},
        {"slug": "two", "impact": "minor", "changed": "docs stopped lying"},
        {"slug": "three", "impact": "major", "changed": ""},
        {"slug": "four", "impact": "huge", "changed": "unrecognized bucket"},
    ])
    assert summary["records"] == 4
    assert summary["impact"] == {"none": 0, "minor": 1, "major": 2}
    assert [item["slug"] for item in summary["recent_changed"]] == ["one", "two", "four"]


def test_summarize_shipped_specs_keeps_only_the_last_eight_change_lines():
    """The dashboard shows recent changes, not the whole history."""
    from stats import summarize_shipped_specs
    summary = summarize_shipped_specs([
        {"slug": f"spec-{i}", "impact": "minor", "changed": f"change {i}"}
        for i in range(12)
    ])
    assert summary["records"] == 12
    assert [item["slug"] for item in summary["recent_changed"]] == [
        f"spec-{i}" for i in range(4, 12)
    ]


def test_format_stats_renders_the_shipped_specs_block():
    """The block names its source, counts the specs, tallies impact, lists changes."""
    from stats import summarize_shipped_specs
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "tech", "status": "COMPLETED",
         "verdict": "APPROVED", "_decisions": []},
    ])
    shipped = summarize_shipped_specs([
        {"slug": "doc-parity-tests", "impact": "minor",
         "changed": "a new CLI command can no longer ship undocumented"},
    ])
    out = run_phase.format_stats(agg, shipped_specs=shipped)
    assert "Shipped features (from specs/):" in out
    assert "1 spec(s) at status: shipped" in out
    assert "Impact:  none=0 minor=1 major=0" in out
    assert "[doc-parity-tests] a new CLI command can no longer ship undocumented" in out


def test_format_stats_truncates_a_long_change_line():
    """A rambling change line is cut to 80 characters so the block stays readable."""
    from stats import summarize_shipped_specs
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "tech", "status": "COMPLETED",
         "verdict": "APPROVED", "_decisions": []},
    ])
    shipped = summarize_shipped_specs([
        {"slug": "long", "impact": "major", "changed": "x" * 200},
    ])
    out = run_phase.format_stats(agg, shipped_specs=shipped)
    rendered = next(line for line in out.splitlines() if "[long]" in line)
    assert rendered.strip() == f"[long] {'x' * 77}..."


def test_format_stats_shipped_specs_empty_state_is_one_line():
    """The empty state says how a line gets here, in a single line."""
    from stats import summarize_shipped_specs
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "tech", "status": "COMPLETED",
         "verdict": "APPROVED", "_decisions": []},
    ])
    out = run_phase.format_stats(agg, shipped_specs=summarize_shipped_specs([]))
    empty_state = [line for line in out.splitlines() if "No shipped features recorded yet" in line]
    assert empty_state == [
        "  No shipped features recorded yet — a spec gains a line here when its "
        "frontmatter says status: shipped."
    ]


def test_format_stats_shows_shipped_specs_with_no_runs_at_all():
    """A repo can have shipped features before its first finalized run."""
    from stats import summarize_shipped_specs
    shipped = summarize_shipped_specs([
        {"slug": "first-thing", "impact": "major", "changed": "the very first landing"},
    ])
    out = run_phase.format_stats(run_phase.aggregate_stats([]), shipped_specs=shipped)
    assert "No local runs found yet" in out
    assert "Shipped features (from specs/):" in out
    assert "[first-thing] the very first landing" in out


def test_get_specs_dir_climbs_out_of_studio_in_the_source_repo(tmp_path, monkeypatch):
    """specs/ sits beside studio/, so the source-repo branch has to climb one level."""
    studio_root = tmp_path / "TheGameStudio" / "studio"
    studio_root.mkdir(parents=True)
    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(studio_root))
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    assert run_phase.get_specs_dir() == studio_root.parent / "specs"


def test_get_specs_dir_is_studio_local_in_a_consuming_repo(tmp_path, monkeypatch):
    """In a repo that installed Studio, /spec writes under .studio/specs."""
    repo, snapshot = _installed(tmp_path, monkeypatch)
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(repo))

    assert run_phase.get_specs_dir() == repo / ".studio" / "specs"
    assert snapshot not in run_phase.get_specs_dir().parents


def test_shipped_spec_records_reads_only_shipped_specs(tmp_path, monkeypatch):
    """Frontmatter decides: draft and approved specs contribute nothing."""
    studio_root = tmp_path / "TheGameStudio" / "studio"
    studio_root.mkdir(parents=True)
    specs = studio_root.parent / "specs"
    specs.mkdir()
    (specs / "shipped-one.md").write_text(
        _spec(slug="shipped-one", impact="major", changed="cut the volunteer path"),
        encoding="utf-8",
    )
    (specs / "still-approved.md").write_text(_spec("approved", slug="still-approved"), encoding="utf-8")
    (specs / "shipped-one-eval-results.md").write_text(_spec(slug="eval"), encoding="utf-8")
    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(studio_root))
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    records = run_phase._shipped_spec_records()

    assert records == [
        {"slug": "shipped-one", "impact": "major", "changed": "cut the volunteer path"}
    ]


def test_shipped_spec_records_is_empty_without_a_specs_dir(tmp_path, monkeypatch):
    """A repo that never ran /spec gets an empty list, not an exception."""
    studio_root = tmp_path / "TheGameStudio" / "studio"
    studio_root.mkdir(parents=True)
    monkeypatch.setenv("STUDIO_ROOT", str(studio_root))
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(studio_root))
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)

    assert run_phase._shipped_spec_records() == []


# --- Session health (auto-measured trends from session.json) ---

def _session(
    *,
    p0_surfaced=0,
    p0_assumed=0,
    iterations=1,
    rejections=0,
    mean_before=None,
    mean_after=None,
    answered_by_user=0,
    answered_by_assumption=0,
    finalized_iso="2026-01-01",
):
    """Build a minimal session.json-shaped record for the health tests."""
    return {
        "finalized_iso": finalized_iso,
        "convergence": {"iterations": iterations, "rejections": rejections},
        "decisions": {
            "surfaced": {"P0": p0_surfaced, "P1": 0, "P2": 0},
            "answered_by_user": answered_by_user,
            "answered_by_assumption": answered_by_assumption,
            "p0_assumed": p0_assumed,
        },
        "clarity": {"mean_before": mean_before, "mean_after": mean_after},
    }


def _legacy_session(*, total_tokens=0, shrink_ratio=0.0, **kwargs):
    """A session record from before the volunteer-fed measurements were retired.

    Old files on disk still carry ``cost`` and ``editor`` blocks. There is no
    migration, so the health signals have to keep reading these records exactly
    as they read new ones and simply ignore the retired blocks.
    """
    record = _session(**kwargs)
    record["cost"] = {"total_tokens": total_tokens, "tokens_per_settled_decision": 999}
    record["editor"] = {"shrink_ratio": shrink_ratio}
    return record


def test_summarize_session_health_empty():
    """No records yields all-None signals, zero count, and no trend."""
    from stats import summarize_session_health
    h = summarize_session_health([])
    assert h["records"] == 0
    assert h["assumed_p0_rate"] is None
    assert h["convergence"]["median_iterations"] is None
    assert h["convergence"]["rejection_rate"] is None
    assert h["clarity_gain"] is None
    assert h["trend"] is None


def test_summarize_session_health_reports_only_computed_signals():
    """The retired volunteer-fed signals are gone from the roll-up entirely."""
    from stats import summarize_session_health
    h = summarize_session_health([_session(p0_surfaced=1, p0_assumed=1)])
    assert set(h) == {
        "records", "assumed_p0_rate", "convergence", "clarity_gain", "trend",
    }


def test_summarize_session_health_normal_set():
    """A normal set of records rolls the three signals up correctly."""
    from stats import summarize_session_health
    records = [
        _session(p0_surfaced=2, p0_assumed=1, iterations=3, rejections=2,
                 mean_before=0.4, mean_after=0.7,
                 answered_by_user=2, answered_by_assumption=1),
        _session(p0_surfaced=2, p0_assumed=0, iterations=1, rejections=0,
                 mean_before=0.5, mean_after=0.5,
                 answered_by_user=1, answered_by_assumption=0),
    ]
    h = summarize_session_health(records)
    assert h["records"] == 2
    # 1 assumed of 4 surfaced P0
    assert h["assumed_p0_rate"] == 0.25
    # median of [3, 1]
    assert h["convergence"]["median_iterations"] == 2
    # 1 of 2 sessions had a rejection
    assert h["convergence"]["rejection_rate"] == 0.5
    # mean of (0.3, 0.0)
    assert h["clarity_gain"] == pytest.approx(0.15)
    assert h["trend"] is None  # under 6 records


def test_summarize_session_health_reads_records_written_before_the_cut():
    """Old records still carrying cost/editor blocks compute exactly the same.

    No migration was written, so a mixed history of old and new files has to
    roll up as one set. The retired blocks are simply never read.
    """
    from stats import summarize_session_health
    old = _legacy_session(
        p0_surfaced=2, p0_assumed=1, iterations=3, rejections=2,
        mean_before=0.4, mean_after=0.7, total_tokens=6000,
        answered_by_user=2, answered_by_assumption=1, shrink_ratio=0.3,
    )
    new = _session(
        p0_surfaced=2, p0_assumed=0, iterations=1, rejections=0,
        mean_before=0.5, mean_after=0.5,
        answered_by_user=1, answered_by_assumption=0,
    )
    assert "cost" in old and "editor" in old  # the fixture is genuinely old-shaped

    mixed = summarize_session_health([old, new])
    assert mixed["records"] == 2
    assert mixed["assumed_p0_rate"] == 0.25
    assert mixed["convergence"]["median_iterations"] == 2
    assert mixed["convergence"]["rejection_rate"] == 0.5
    assert mixed["clarity_gain"] == pytest.approx(0.15)

    # An all-old history is indistinguishable from the same history with the
    # retired blocks stripped out.
    stripped = {k: v for k, v in old.items() if k not in ("cost", "editor")}
    assert summarize_session_health([old]) == summarize_session_health([stripped])


def test_summarize_session_health_tolerates_missing_fields():
    """Missing clarity/decisions blocks never raise; they drop out cleanly."""
    from stats import summarize_session_health
    records = [
        {"convergence": {"iterations": 2}},  # no decisions, no clarity
        {"decisions": {}, "clarity": {}},
        _session(mean_before=0.2, mean_after=0.6),  # only this has both clarity ends
    ]
    h = summarize_session_health(records)
    assert h["records"] == 3
    assert h["assumed_p0_rate"] is None  # no P0 surfaced anywhere
    # clarity_gain averages only the one record with both ends present
    assert h["clarity_gain"] == pytest.approx(0.4)


def test_summarize_session_health_assumed_p0_divide_by_zero():
    """assumed_p0_rate is None when no P0 surfaced, even if p0_assumed is set."""
    from stats import summarize_session_health
    # p0_assumed nonzero but surfaced zero must not divide by zero.
    h = summarize_session_health([_session(p0_surfaced=0, p0_assumed=0)])
    assert h["assumed_p0_rate"] is None
    # And a real ratio when P0s are surfaced.
    h2 = summarize_session_health([_session(p0_surfaced=4, p0_assumed=3)])
    assert h2["assumed_p0_rate"] == 0.75


def test_summarize_session_health_trend_split():
    """With >= 6 records a trend block splits the list into earlier and recent halves."""
    from stats import summarize_session_health
    earlier = [_session(p0_surfaced=1, p0_assumed=1, iterations=4) for _ in range(3)]
    recent = [_session(p0_surfaced=1, p0_assumed=0, iterations=1) for _ in range(3)]
    h = summarize_session_health(earlier + recent)
    assert h["trend"] is not None
    assert h["trend"]["earlier"]["records"] == 3
    assert h["trend"]["recent"]["records"] == 3
    # Assumed-P0 rate improved 100% -> 0% across the halves.
    assert h["trend"]["earlier"]["assumed_p0_rate"] == 1.0
    assert h["trend"]["recent"]["assumed_p0_rate"] == 0.0
    assert h["trend"]["earlier"]["convergence"]["median_iterations"] == 4
    assert h["trend"]["recent"]["convergence"]["median_iterations"] == 1


def _session_health_lines(out):
    """The Session health block's own lines, header and blank line dropped."""
    block = out.split("Session health (auto-measured at finalize):")[1]
    lines = []
    for line in block.splitlines()[1:]:
        if not line.startswith("  "):
            break
        lines.append(line.strip())
    return lines


def test_format_stats_renders_session_health():
    """The block is the record count plus exactly the three computed signals."""
    from stats import summarize_session_health
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "_rating": None, "_decisions": []},
    ])
    health = summarize_session_health([
        _session(p0_surfaced=2, p0_assumed=1, mean_before=0.3, mean_after=0.6,
                 answered_by_user=2),
    ])
    out = run_phase.format_stats(agg, session_health=health)
    assert "Session health" in out
    assert "Assumed-P0 rate: 50%" in out

    lines = _session_health_lines(out)
    assert len(lines) == 4  # record count + three signals, nothing else
    assert lines[0] == "1 finalized session(s) on record"
    assert [line.split(":")[0] for line in lines[1:]] == [
        "Assumed-P0 rate", "Convergence", "Clarity gain",
    ]


def test_format_stats_session_health_trend_needs_six_records():
    """With 6+ records the block adds the earlier-vs-recent trend, and only then."""
    from stats import summarize_session_health
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "_rating": None, "_decisions": []},
    ])
    records = [_session(p0_surfaced=1, p0_assumed=1, iterations=3) for _ in range(3)]
    records += [_session(p0_surfaced=1, p0_assumed=0, iterations=1) for _ in range(3)]

    five = run_phase.format_stats(agg, session_health=summarize_session_health(records[:5]))
    assert "Trend" not in five
    assert len(_session_health_lines(five)) == 4

    six = run_phase.format_stats(agg, session_health=summarize_session_health(records))
    lines = _session_health_lines(six)
    assert len(lines) == 7  # count + three signals + trend header + two trend rows
    assert lines[4].startswith("Trend (recent 3 vs earlier 3)")
    assert "Assumed-P0 rate: 100% -> 0%" in lines[5]
    assert "Median iterations: 3 -> 1" in lines[6]


def test_format_stats_omits_session_health_when_empty():
    """No session records means no Session health block."""
    from stats import summarize_session_health
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "metrics": {}, "_rating": None, "_decisions": []},
    ])
    out = run_phase.format_stats(agg, session_health=summarize_session_health([]))
    assert "Session health" not in out


class _FakeStdin:
    """Stands in for sys.stdin so a test can claim to be (or not be) a terminal."""

    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


def test_finalize_asks_for_nothing_even_at_a_terminal(studio_root, monkeypatch, capsys):
    """finalize never stops to ask for a score, and writes no rating.json.

    The TTY is what carries this: the retired prompt was interactive at a
    terminal and only printed a nudge otherwise, so a non-TTY test would pass
    against the old code too.
    """
    monkeypatch.setattr(run_phase.sys, "stdin", _FakeStdin(True))
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("finalize asked for input"))

    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    (run_dir / "advocate_1.md").write_text("a", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("c", encoding="utf-8")
    (run_dir / "summary.md").write_text("s", encoding="utf-8")

    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    out = capsys.readouterr().out
    assert f"Finalized {run_id}" in out, "finalize never ran, so it proves nothing"
    assert "Rate this run" not in out
    assert "rate --run-dir" not in out
    assert not (run_dir / "rating.json").exists()


# ---------------------------------------------------------------------------
# Fresh run context reset tests
# ---------------------------------------------------------------------------


class TestIsSameObjective:
    """Tests for _is_same_objective helper."""

    def test_same_input_returns_true(self, tmp_path):
        run_dir = tmp_path / "run_market_001"
        run_dir.mkdir()
        run_phase.write_json(run_dir / "run.json", {"input": "Build a farming sim"})
        assert run_phase._is_same_objective(run_dir, "Build a farming sim") is True

    def test_different_input_returns_false(self, tmp_path):
        run_dir = tmp_path / "run_market_001"
        run_dir.mkdir()
        run_phase.write_json(run_dir / "run.json", {"input": "Build a farming sim"})
        assert run_phase._is_same_objective(run_dir, "Add multiplayer lobby") is False

    def test_case_insensitive(self, tmp_path):
        run_dir = tmp_path / "run_market_001"
        run_dir.mkdir()
        run_phase.write_json(run_dir / "run.json", {"input": "Build a Farming Sim"})
        assert run_phase._is_same_objective(run_dir, "build a farming sim") is True

    def test_whitespace_normalized(self, tmp_path):
        run_dir = tmp_path / "run_market_001"
        run_dir.mkdir()
        run_phase.write_json(run_dir / "run.json", {"input": "Build  a   farming   sim"})
        assert run_phase._is_same_objective(run_dir, "Build a farming sim") is True

    def test_missing_run_json_returns_false(self, tmp_path):
        run_dir = tmp_path / "run_market_001"
        run_dir.mkdir()
        assert run_phase._is_same_objective(run_dir, "anything") is False

    def test_missing_input_key_returns_false(self, tmp_path):
        run_dir = tmp_path / "run_market_001"
        run_dir.mkdir()
        run_phase.write_json(run_dir / "run.json", {"phase": "market"})
        assert run_phase._is_same_objective(run_dir, "anything") is False

    def test_empty_input_returns_false(self, tmp_path):
        run_dir = tmp_path / "run_market_001"
        run_dir.mkdir()
        run_phase.write_json(run_dir / "run.json", {"input": ""})
        assert run_phase._is_same_objective(run_dir, "") is False


class TestFreshRunClarityReset:
    """Tests that prepare resets clarity when objective changes."""

    def test_fresh_run_clears_stale_clarity(self, studio_root):
        """A new objective should reset the clarity.json from the previous run."""
        import time

        # Run 1: create a run with objective A
        run_phase.prepare_run(make_prepare_args(text="Objective A"))

        # Simulate clarity data from run 1
        clarity_path = studio_root / ".studio" / "clarity.json"
        clarity_path.parent.mkdir(parents=True, exist_ok=True)
        clarity_path.write_text('{"run_id": "old", "topics": [], "context": {"scope_label": "broad", "scope_description": "Objective A"}, "created_iso": "2026-01-01T00:00:00"}', encoding="utf-8")
        assert clarity_path.is_file()

        time.sleep(1.1)  # avoid timestamp collision

        # Run 2: different objective — should reset clarity
        run_phase.prepare_run(make_prepare_args(text="Objective B"))
        assert not clarity_path.is_file(), "clarity.json should be cleared for a fresh run"

    def test_same_objective_preserves_clarity(self, studio_root):
        """A rerun of the same objective should keep clarity.json."""
        import time

        clarity_path = studio_root / ".studio" / "clarity.json"
        clarity_path.parent.mkdir(parents=True, exist_ok=True)

        # Run 1
        run_phase.prepare_run(make_prepare_args(text="Same objective"))

        # Write clarity after run 1 (using correct schema field names)
        clarity_path.write_text('{"run_id": "existing", "topics": [{"topic": "core_loop", "display_name": "Core Loop", "score": 0.8, "answered_count": 3, "total_count": 5, "challenged_count": 0}], "context": {"scope_label": "broad", "scope_description": "Same objective"}, "created_iso": "2026-01-01T00:00:00"}', encoding="utf-8")

        time.sleep(1.1)  # avoid timestamp collision

        # Run 2: same objective — should preserve clarity
        run_phase.prepare_run(make_prepare_args(text="Same objective"))
        assert clarity_path.is_file(), "clarity.json should be preserved for same-objective rerun"

    def test_cross_phase_objective_change_clears_clarity(self, studio_root):
        """Stale clarity from a different phase's objective must be cleared.

        Regression: previous-run detection is phase-scoped, but clarity.json
        is project-level. A 'maze' objective run under one phase used to leak
        into a different objective run under another phase.
        """
        import time

        # Prior run under the 'design' phase wrote project-level clarity.
        clarity_path = studio_root / ".studio" / "clarity.json"
        clarity_path.parent.mkdir(parents=True, exist_ok=True)
        run_phase.prepare_run(make_prepare_args(phase="design", text="A maze game"))
        clarity_path.write_text('{"run_id": "maze", "topics": [], "context": {"scope_label": "broad", "scope_description": "A maze game"}, "created_iso": "2026-01-01T00:00:00"}', encoding="utf-8")

        time.sleep(1.1)

        # New run under a *different* phase with a different objective.
        run_phase.prepare_run(make_prepare_args(phase="tech", text="Build multiplayer lobby"))
        assert not clarity_path.is_file(), "cross-phase stale clarity should be cleared"

    def test_corrupt_clarity_self_heals(self, studio_root):
        """A corrupt clarity.json is treated as absent so prepare doesn't crash.

        Regression: load_project_clarity is now called unconditionally at the
        top of prepare's reset block. An interrupted/truncated write used to
        crash every subsequent prepare (incl. the reset that would clean it up).
        """
        import time

        clarity_path = studio_root / ".studio" / "clarity.json"
        clarity_path.parent.mkdir(parents=True, exist_ok=True)
        run_phase.prepare_run(make_prepare_args(phase="tech", text="Objective A"))
        # Simulate a truncated/interrupted write.
        clarity_path.write_text('{"run_id": "x", "topics": [], "cont', encoding="utf-8")

        time.sleep(1.1)

        # Must not raise; the corrupt file is treated as absent and rebuilt.
        run_phase.prepare_run(make_prepare_args(phase="tech", text="Objective B"))
        assert not clarity_path.is_file(), "corrupt clarity should be cleared, not crash"

    def test_global_same_objective_does_not_inject_cross_objective_rerun(self, studio_root):
        """Global (clarity) same-objective must not pull rerun context from a
        phase-local previous run that targeted a *different* objective."""
        import time

        # Prior tech run for objective A, rejected.
        run_id_a = run_phase.prepare_run(make_prepare_args(phase="tech", text="Build lobby A"))
        run_dir_a = studio_root / "output" / "tech" / run_id_a
        (run_dir_a / "contrarian_1.md").write_text(
            "VERDICT: REJECTED\n1. This is terrible\n", encoding="utf-8"
        )

        # Project clarity says the current objective is B (e.g. reset by an
        # intervening different-phase run) — matches the new run's text, so the
        # cross-phase comparison yields same_objective=True.
        clarity_path = studio_root / ".studio" / "clarity.json"
        clarity_path.parent.mkdir(parents=True, exist_ok=True)
        clarity_path.write_text('{"run_id": "b", "topics": [], "context": {"scope_label": "broad", "scope_description": "Build lobby B"}, "created_iso": "2026-01-01T00:00:00"}', encoding="utf-8")

        time.sleep(1.1)

        # New tech run, objective B: global same_objective is True, but the
        # phase-local previous run was objective A — no rerun context allowed.
        run_id_b = run_phase.prepare_run(make_prepare_args(phase="tech", text="Build lobby B"))
        run_dir_b = studio_root / "output" / "tech" / run_id_b
        instructions = (run_dir_b / "instructions.md").read_text()
        assert "This is terrible" not in instructions

    def test_fresh_run_skips_rerun_context(self, studio_root):
        """A new objective should not inject rerun context from the previous run."""
        # Run 1: create and add a rejected contrarian
        run_id_1 = run_phase.prepare_run(make_prepare_args(text="Old objective"))
        run_dir_1 = studio_root / "output" / "market" / run_id_1
        (run_dir_1 / "contrarian_1.md").write_text(
            "VERDICT: REJECTED\n1. This is terrible\n", encoding="utf-8"
        )

        import time
        time.sleep(1.1)  # Ensure different timestamp

        # Run 2: different objective
        run_id_2 = run_phase.prepare_run(make_prepare_args(text="New objective"))
        run_dir_2 = studio_root / "output" / "market" / run_id_2
        instructions = (run_dir_2 / "instructions.md").read_text()

        # Should NOT contain rerun context from the old objective
        assert "This is terrible" not in instructions
        assert "Prior Run" not in instructions


# --- Cross-repo CLI hardening (installed-layout path resolution) ---

def _installed(tmp_path, monkeypatch, *, version=True):
    """Set up an installed-layout repo: <repo>/.studio/source as STUDIO_ROOT."""
    repo = tmp_path / "repo"
    snapshot = repo / ".studio" / "source"
    snapshot.mkdir(parents=True)
    if version:
        (repo / ".studio" / "VERSION").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("STUDIO_ROOT", str(snapshot))
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    monkeypatch.setattr(run_phase, "_artifact_root_override", None)
    return repo, snapshot


def test_artifact_root_from_inside_snapshot_returns_repo_root(tmp_path, monkeypatch):
    """Running from inside <repo>/.studio/source resolves to the repo root, not the snapshot."""
    repo, snapshot = _installed(tmp_path, monkeypatch)
    monkeypatch.chdir(snapshot)
    assert run_phase.get_artifact_root() == repo


def test_artifact_root_walks_up_to_installed_root(tmp_path, monkeypatch):
    """A CLI call from a monorepo subdirectory resolves to the repo root via .studio/VERSION."""
    repo, _ = _installed(tmp_path, monkeypatch)
    subdir = repo / "packages" / "app"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    assert run_phase.get_artifact_root() == repo


def test_scopes_config_read_from_artifact_root(tmp_path, monkeypatch):
    """Project-local .studio/scopes.toml is read from the artifact root, not the source snapshot."""
    repo, _ = _installed(tmp_path, monkeypatch)
    (repo / ".studio" / "scopes.toml").write_text(
        '[scopes.alignment]\nfocus = "x"\nmax_iterations = 99\n', encoding="utf-8"
    )
    monkeypatch.chdir(repo)
    _, _, meta = run_phase._resolve_scopes(
        argparse.Namespace(scopes=None, no_scopes=False, max_iterations=6)
    )
    assert meta is not None
    assert meta["config_path"] == (repo / ".studio" / "scopes.toml").as_posix()


def test_bridge_doc_created_even_when_studio_dir_exists(tmp_path):
    """init'd repos (where .studio/ already exists) still get a bridge doc on scaffold."""
    studio_root = tmp_path / "studio"
    (studio_root / "docs").mkdir(parents=True)
    (studio_root / "docs" / "STUDIO_BRIDGE_TEMPLATE.md").write_text("# Bridge\n", encoding="utf-8")
    repo = tmp_path / "repo"
    (repo / ".studio").mkdir(parents=True)  # simulates an init'd repo
    run_phase._scaffold_external_repo(repo, studio_root)
    assert (repo / "docs" / "studio-bridge.md").is_file()


# --- CLI ergonomics: --json output + --phase derivable from run_id ---

def test_phase_from_run_id():
    assert run_phase._phase_from_run_id("run_market_20260101_120000") == "market"
    assert run_phase._phase_from_run_id("run_studio_20260101_120000") == "studio"
    with pytest.raises(ValueError):
        run_phase._phase_from_run_id("not_a_valid_id")


def test_prepare_json_output(studio_root, capsys):
    """prepare --json emits a parseable object as the final stdout line."""
    run_phase.prepare_run(make_prepare_args(text="json test", json=True))
    lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln.strip()]
    payload = json.loads(lines[-1])
    assert payload["phase"] == "market"
    assert payload["run_id"].startswith("run_market_")
    assert payload["run_dir"] and payload["instructions"]


def test_finalize_derives_phase_when_omitted(studio_root):
    """finalize works with --phase omitted (derived from run_id)."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    (run_dir / "advocate_1.md").write_text("a", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("c", encoding="utf-8")
    (run_dir / "summary.md").write_text("s", encoding="utf-8")
    run_phase.finalize_run(make_finalize_args(phase=None, run_id=run_id))
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert meta["status"] == "COMPLETED"


def test_extract_decisions_json_emits_count(studio_root, capsys):
    """extract-decisions --json always emits {count, decisions} (count, not empty stdout, gates)."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    capsys.readouterr()  # discard prepare's prose so we read only extract's output
    run_phase.extract_decisions(
        argparse.Namespace(run_dir=run_dir, scope=None, show_all=False, json=True)
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"count": 0, "decisions": []}


def test_setup_defaults_step_count_ignores_retired_steps(tmp_path, capsys):
    """A SETUP.json still listing the retired `scopes` step doesn't inflate the count."""
    import setup

    (tmp_path / ".studio").mkdir()
    setup.apply_defaults(tmp_path)
    setup_path = tmp_path / ".studio" / setup.SETUP_FILE
    state = json.loads(setup_path.read_text(encoding="utf-8"))
    state["completed_steps"]["scopes"] = 1
    setup_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    capsys.readouterr()
    run_phase._do_setup(
        argparse.Namespace(
            target=tmp_path, status=False, defaults=True, answers=None,
            role_pack=None, roles=None,
        )
    )
    out = capsys.readouterr().out
    assert f"({len(setup.SETUP_STEPS)} steps)" in out
    assert "Pending:" not in out
