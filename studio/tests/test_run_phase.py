"""Unit tests for run_phase.py core functions."""
import argparse
import json

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
    studio_root = tmp_path / "studio"
    studio_root.mkdir()
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


def test_cross_repo_prepare_creates_artifacts_in_caller_repo(tmp_path, monkeypatch):
    """Full prepare from an external repo puts artifacts in that repo, not Studio."""
    from conftest import _seed_studio_root

    studio_root = tmp_path / "studio"
    studio_root.mkdir()
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

    studio_root = tmp_path / "studio"
    studio_root.mkdir()
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

    studio_root = tmp_path / "studio"
    studio_root.mkdir()
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
# Agent metrics tracking
# ---------------------------------------------------------------------------


def test_record_and_load_metrics(tmp_path):
    """record-metrics writes entries to metrics.json."""
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()

    args = argparse.Namespace(
        run_dir=run_dir, agent="advocate", total_tokens=5000,
        tool_uses=10, duration_ms=30000, role="marketing", scope="alignment",
    )
    run_phase.record_metrics(args)

    entries = run_phase._load_metrics(run_dir)
    assert len(entries) == 1
    assert entries[0]["agent"] == "advocate"
    assert entries[0]["total_tokens"] == 5000
    assert entries[0]["role"] == "marketing"
    assert entries[0]["scope"] == "alignment"

    # Append a second entry
    args2 = argparse.Namespace(
        run_dir=run_dir, agent="contrarian", total_tokens=3000,
        tool_uses=5, duration_ms=20000, role="marketing", scope="alignment",
    )
    run_phase.record_metrics(args2)
    entries = run_phase._load_metrics(run_dir)
    assert len(entries) == 2


def test_summarize_metrics():
    """_summarize_metrics aggregates by scope and role."""
    entries = [
        {"agent": "advocate", "total_tokens": 10000, "tool_uses": 15, "duration_ms": 40000, "role": "marketing", "scope": "alignment"},
        {"agent": "contrarian", "total_tokens": 8000, "tool_uses": 10, "duration_ms": 30000, "role": "marketing", "scope": "alignment"},
        {"agent": "advocate", "total_tokens": 30000, "tool_uses": 40, "duration_ms": 120000, "role": "engineering", "scope": "depth"},
    ]
    summary = run_phase._summarize_metrics(entries)

    assert summary["agents"] == 3
    assert summary["total_tokens"] == 48000
    assert summary["total_tool_uses"] == 65
    assert summary["total_duration_ms"] == 190000

    assert "alignment" in summary["by_scope"]
    assert summary["by_scope"]["alignment"]["agents"] == 2
    assert summary["by_scope"]["alignment"]["total_tokens"] == 18000

    assert "depth" in summary["by_scope"]
    assert summary["by_scope"]["depth"]["agents"] == 1

    assert "marketing" in summary["by_role"]
    assert summary["by_role"]["marketing"]["total_tokens"] == 18000
    assert "engineering" in summary["by_role"]


def test_show_metrics_empty(tmp_path, capsys):
    """show-metrics handles empty/missing metrics gracefully."""
    run_dir = tmp_path / "run_empty"
    run_dir.mkdir()

    args = argparse.Namespace(run_dir=run_dir)
    run_phase.show_metrics(args)
    assert "No metrics recorded" in capsys.readouterr().out


def test_finalize_aggregates_metrics(studio_root):
    """Finalize includes metrics summary in run.json when metrics.json exists."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id

    # Simulate artifacts
    (run_dir / "advocate_1.md").write_text("Advocate output", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("Contrarian output", encoding="utf-8")
    (run_dir / "summary.md").write_text("Summary output", encoding="utf-8")

    # Write metrics
    run_phase._save_metrics(run_dir, [
        {"agent": "advocate", "total_tokens": 12000, "tool_uses": 20, "duration_ms": 50000},
        {"agent": "contrarian", "total_tokens": 9000, "tool_uses": 12, "duration_ms": 35000},
    ])

    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    meta = run_phase.load_json(run_dir / "run.json")
    assert "metrics" in meta
    assert meta["metrics"]["agents"] == 2
    assert meta["metrics"]["total_tokens"] == 21000


# ---------------------------------------------------------------------------
# Human quality ratings & cross-run stats
# ---------------------------------------------------------------------------


def test_record_rating_writes_rating_json(tmp_path):
    """rate writes score + note + timestamp to rating.json."""
    run_dir = tmp_path / "run_market_001"
    run_dir.mkdir()

    run_phase.record_rating(argparse.Namespace(run_dir=run_dir, score=4, note="solid market read"))

    rating = run_phase._load_rating(run_dir)
    assert rating["score"] == 4
    assert rating["note"] == "solid market read"
    assert "rated_iso" in rating


def test_record_rating_overwrites(tmp_path):
    """Re-rating a run replaces the prior rating."""
    run_dir = tmp_path / "run_market_001"
    run_dir.mkdir()
    run_phase.record_rating(argparse.Namespace(run_dir=run_dir, score=2, note=""))
    run_phase.record_rating(argparse.Namespace(run_dir=run_dir, score=5, note="much better on rerun"))

    rating = run_phase._load_rating(run_dir)
    assert rating["score"] == 5
    assert rating["note"] == "much better on rerun"


def test_load_rating_absent(tmp_path):
    """_load_rating returns None when no rating exists."""
    run_dir = tmp_path / "run_market_001"
    run_dir.mkdir()
    assert run_phase._load_rating(run_dir) is None


def test_record_rating_missing_dir(tmp_path):
    """rate raises on a non-existent run directory."""
    with pytest.raises(FileNotFoundError):
        run_phase.record_rating(argparse.Namespace(run_dir=tmp_path / "nope", score=3, note=None))


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
    assert agg["ratings"]["count"] == 0


def test_aggregate_stats_full():
    """aggregate_stats rolls up phases, verdicts, ratings, tokens, decisions."""
    runs = [
        {
            "run_id": "run_market_1", "phase": "market", "status": "COMPLETED",
            "verdict": "APPROVED", "metrics": {"total_tokens": 10000}, "cost": 1.5,
            "_rating": {"score": 4, "note": "good"},
            "_decisions": [_DP("P0", answer="yes"), _DP("P2")],
        },
        {
            "run_id": "run_market_2", "phase": "market", "status": "COMPLETED",
            "verdict": "REJECTED", "metrics": {"total_tokens": 20000},
            "_rating": {"score": 2, "note": "thin"},
            "_decisions": [_DP("P1")],
        },
        {
            "run_id": "run_tech_1", "phase": "tech", "status": "PENDING",
            "verdict": "UNKNOWN", "metrics": {},
            "_rating": None, "_decisions": [],
        },
    ]
    agg = run_phase.aggregate_stats(runs)

    assert agg["total_runs"] == 3
    assert agg["by_phase"] == {"market": 2, "tech": 1}
    assert agg["by_status"] == {"COMPLETED": 2, "PENDING": 1}
    assert agg["verdicts"] == {"APPROVED": 1, "REJECTED": 1, "UNKNOWN": 1}
    assert agg["approval_rate"] == 0.5  # 1 approved of 2 decided

    assert agg["ratings"]["count"] == 2
    assert agg["ratings"]["avg"] == 3.0
    assert agg["ratings"]["by_phase_avg"]["market"] == 3.0
    assert agg["ratings"]["lowest"][0]["score"] == 2  # lowest first

    assert agg["tokens"]["total"] == 30000
    assert agg["tokens"]["runs"] == 2  # tech run had no tokens
    assert agg["tokens"]["avg"] == 15000
    assert agg["cost"]["total"] == 1.5

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
    """format_stats renders without error and surfaces a rating hint when unrated."""
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "metrics": {"total_tokens": 5000},
         "_rating": None, "_decisions": []},
    ])
    out = run_phase.format_stats(agg)
    assert "Studio Cross-Run Stats" in out
    assert "No runs rated yet" in out


# --- Outcome capture (quantify + qualify run results) ---

def test_summarize_outcomes_empty():
    """No records yields a zeroed outcome summary with no ship rate."""
    from stats import summarize_outcomes
    s = summarize_outcomes([])
    assert s["records"] == 0
    assert s["ship_rate"] is None
    assert s["recent_changed"] == []


def test_summarize_outcomes_counts_and_rate():
    """summarize_outcomes tallies shipped/impact, computes ship rate, keeps notes."""
    from stats import summarize_outcomes
    records = [
        {"repo": "a", "run_id": "r1", "shipped": "yes", "impact": "major", "changed": "shipped X"},
        {"repo": "a", "run_id": "r2", "shipped": "no", "impact": "none"},
        {"repo": "b", "run_id": "r3", "shipped": "partial", "impact": "minor", "changed": "half of Y"},
        {"repo": "b", "run_id": "r4"},  # rated but no outcome fields
    ]
    s = summarize_outcomes(records)
    assert s["records"] == 4
    assert s["with_outcome"] == 3
    assert s["by_repo"] == {"a": 2, "b": 2}
    assert s["shipped"] == {"yes": 1, "no": 1, "partial": 1}
    assert s["ship_rate"] == 1 / 3
    assert s["impact"] == {"none": 1, "minor": 1, "major": 1}
    assert [c["changed"] for c in s["recent_changed"]] == ["shipped X", "half of Y"]


def test_write_rating_records_outcome_block(tmp_path):
    """_write_rating stores shipped/impact/changed under an outcome block."""
    rating = run_phase._write_rating(
        tmp_path, 4, "solid", shipped="yes", impact="major", changed="  cut scope  "
    )
    assert rating["outcome"] == {"shipped": "yes", "impact": "major", "changed": "cut scope"}
    on_disk = json.loads((tmp_path / "rating.json").read_text())
    assert on_disk["outcome"]["changed"] == "cut scope"


def test_write_rating_omits_empty_outcome(tmp_path):
    """A rating with no outcome fields carries no outcome block."""
    rating = run_phase._write_rating(tmp_path, 3, "")
    assert "outcome" not in rating


def test_outcome_record_from_run_includes_unrated():
    """Unrated runs still yield a record (null score/outcome); rated runs flatten it."""
    unrated = run_phase._outcome_record_from_run(
        {"run_id": "r", "phase": "market", "verdict": "APPROVED",
         "status": "completed", "_rating": None},
        "repo",
    )
    assert unrated["repo"] == "repo"
    assert unrated["run_id"] == "r"
    assert unrated["phase"] == "market"
    assert unrated["verdict"] == "APPROVED"
    assert unrated["score"] is None
    assert unrated["shipped"] is None
    assert unrated["rated_iso"] is None
    rec = run_phase._outcome_record_from_run(
        {
            "run_id": "run_studio_1", "phase": "studio", "verdict": "APPROVED",
            "status": "completed", "metrics": {"total_tokens": 900},
            "_rating": {"score": 5, "outcome": {"shipped": "yes", "impact": "minor"}},
        },
        "pictorly",
    )
    assert rec["repo"] == "pictorly"
    assert rec["shipped"] == "yes"
    assert rec["total_tokens"] == 900
    assert rec["changed"] is None


def test_merge_outcomes_local_wins_on_dedup():
    """_merge_outcomes dedups by (repo, run_id); local record overrides the ledger."""
    ledger = [{"repo": "a", "run_id": "r1", "shipped": "no"}]
    local = [{"repo": "a", "run_id": "r1", "shipped": "yes"}, {"repo": "a", "run_id": "r2"}]
    merged = run_phase._merge_outcomes(ledger, local)
    by_id = {r["run_id"]: r for r in merged}
    assert len(merged) == 2
    assert by_id["r1"]["shipped"] == "yes"  # local won


def test_format_stats_renders_outcomes_section():
    """format_stats includes the outcomes block when given a summary."""
    from stats import summarize_outcomes
    agg = run_phase.aggregate_stats([])
    outcomes = summarize_outcomes([
        {"repo": "pictorly", "run_id": "r1", "shipped": "yes", "impact": "major", "changed": "did a thing"},
    ])
    out = run_phase.format_stats(agg, outcomes=outcomes)
    assert "Outcomes (did it ship" in out
    assert "ship rate 100%" in out
    assert "did a thing" in out


# --- Session health (auto-measured trends from session.json) ---

def _session(
    *,
    p0_surfaced=0,
    p0_assumed=0,
    iterations=1,
    rejections=0,
    mean_before=None,
    mean_after=None,
    total_tokens=0,
    answered_by_user=0,
    answered_by_assumption=0,
    shrink_ratio=0.0,
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
        "cost": {"total_tokens": total_tokens},
        "editor": {"shrink_ratio": shrink_ratio},
    }


def test_summarize_session_health_empty():
    """No records yields all-None signals, zero count, and no trend."""
    from stats import summarize_session_health
    h = summarize_session_health([])
    assert h["records"] == 0
    assert h["assumed_p0_rate"] is None
    assert h["convergence"]["median_iterations"] is None
    assert h["convergence"]["rejection_rate"] is None
    assert h["clarity_gain"] is None
    assert h["tokens_per_settled_decision"] is None
    assert h["editor_liveness"] is None
    assert h["trend"] is None


def test_summarize_session_health_normal_set():
    """A normal set of records rolls the five signals up correctly."""
    from stats import summarize_session_health
    records = [
        _session(p0_surfaced=2, p0_assumed=1, iterations=3, rejections=2,
                 mean_before=0.4, mean_after=0.7, total_tokens=6000,
                 answered_by_user=2, answered_by_assumption=1, shrink_ratio=0.3),
        _session(p0_surfaced=2, p0_assumed=0, iterations=1, rejections=0,
                 mean_before=0.5, mean_after=0.5, total_tokens=4000,
                 answered_by_user=1, answered_by_assumption=0, shrink_ratio=0.0),
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
    # 10000 tokens / 4 settled decisions
    assert h["tokens_per_settled_decision"] == 2500
    # 1 of 2 sessions shrank
    assert h["editor_liveness"] == 0.5
    assert h["trend"] is None  # under 6 records


def test_summarize_session_health_tolerates_missing_fields():
    """Missing clarity/decisions/editor blocks never raise; they drop out cleanly."""
    from stats import summarize_session_health
    records = [
        {"convergence": {"iterations": 2}},  # no decisions/clarity/cost/editor
        {"decisions": {}, "clarity": {}, "cost": {}, "editor": {}},
        _session(mean_before=0.2, mean_after=0.6),  # only this has both clarity ends
    ]
    h = summarize_session_health(records)
    assert h["records"] == 3
    assert h["assumed_p0_rate"] is None  # no P0 surfaced anywhere
    # clarity_gain averages only the one record with both ends present
    assert h["clarity_gain"] == pytest.approx(0.4)
    # no settled decisions anywhere
    assert h["tokens_per_settled_decision"] is None
    # no shrink_ratio > 0 anywhere
    assert h["editor_liveness"] == 0.0


def test_summarize_session_health_assumed_p0_divide_by_zero():
    """assumed_p0_rate is None when no P0 surfaced, even if p0_assumed is set."""
    from stats import summarize_session_health
    # p0_assumed nonzero but surfaced zero must not divide by zero.
    h = summarize_session_health([_session(p0_surfaced=0, p0_assumed=0)])
    assert h["assumed_p0_rate"] is None
    # And a real ratio when P0s are surfaced.
    h2 = summarize_session_health([_session(p0_surfaced=4, p0_assumed=3)])
    assert h2["assumed_p0_rate"] == 0.75


def test_summarize_session_health_editor_liveness_math():
    """editor_liveness is the fraction of records whose doc shrank (ratio > 0)."""
    from stats import summarize_session_health
    records = [
        _session(shrink_ratio=0.4),   # shrank
        _session(shrink_ratio=0.0),   # flat
        _session(shrink_ratio=-0.1),  # grew (negative) — not liveness
        _session(shrink_ratio=0.2),   # shrank
    ]
    h = summarize_session_health(records)
    assert h["editor_liveness"] == 0.5  # 2 of 4


def test_summarize_session_health_tokens_per_settled_zero_guard():
    """Tokens spent but nothing settled yields None, not a divide-by-zero."""
    from stats import summarize_session_health
    h = summarize_session_health([
        _session(total_tokens=5000, answered_by_user=0, answered_by_assumption=0),
    ])
    assert h["tokens_per_settled_decision"] is None


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


def test_format_stats_renders_session_health():
    """format_stats shows the Session health block when records are present."""
    from stats import summarize_session_health
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "metrics": {"total_tokens": 5000},
         "_rating": None, "_decisions": []},
    ])
    health = summarize_session_health([
        _session(p0_surfaced=2, p0_assumed=1, mean_before=0.3, mean_after=0.6,
                 total_tokens=4000, answered_by_user=2, shrink_ratio=0.25),
    ])
    out = run_phase.format_stats(agg, session_health=health)
    assert "Session health" in out
    assert "Assumed-P0 rate: 50%" in out
    assert "Editor liveness" in out


def test_format_stats_omits_session_health_when_empty():
    """No session records means no Session health block."""
    from stats import summarize_session_health
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "metrics": {}, "_rating": None, "_decisions": []},
    ])
    out = run_phase.format_stats(agg, session_health=summarize_session_health([]))
    assert "Session health" not in out


# --- Trend alerts (delta-based, 2+-consecutive-run persistence) ---

def _trend_run(created_iso, *, score=None, tokens=None, cost=None, run_id=None):
    """Build a minimal enriched run dict for detect_trend_alerts tests.

    created_iso orders the runs; score/tokens/cost each become a per-run point in
    that metric's series (left off when None, mirroring an unrated or unmetered
    run).
    """
    run = {"run_id": run_id or f"run_{created_iso}", "created_iso": created_iso}
    if score is not None:
        run["_rating"] = {"score": score}
    if tokens is not None:
        run["metrics"] = {"total_tokens": tokens}
    if cost is not None:
        run["cost"] = cost
    return run


def test_detect_trend_alerts_empty():
    """No runs yields no alerts and does not crash."""
    from stats import detect_trend_alerts
    assert detect_trend_alerts([]) == []


def test_detect_trend_alerts_single_dip_is_a_blip():
    """One worsening step (a single-run dip) must NOT alert."""
    from stats import detect_trend_alerts
    runs = [
        _trend_run("2026-01-01", score=5),
        _trend_run("2026-01-02", score=4),  # one dip only
    ]
    assert detect_trend_alerts(runs) == []


def test_detect_trend_alerts_two_consecutive_regressions_fire():
    """A rating falling across 2+ consecutive runs alerts with the slide window."""
    from stats import detect_trend_alerts
    runs = [
        _trend_run("2026-01-01", score=5),
        _trend_run("2026-01-02", score=4),
        _trend_run("2026-01-03", score=3),
    ]
    alerts = detect_trend_alerts(runs)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["metric"] == "rating"
    assert alert["direction"] == "down"
    assert alert["consecutive"] == 2
    assert alert["from_value"] == 5
    assert alert["to_value"] == 3
    assert alert["pct_change"] == pytest.approx(-0.4)
    assert alert["runs"] == ["run_2026-01-01", "run_2026-01-02", "run_2026-01-03"]


def test_detect_trend_alerts_improving_never_fires():
    """A metric moving the good way (rating up, tokens down) raises no alert."""
    from stats import detect_trend_alerts
    runs = [
        _trend_run("2026-01-01", score=3, tokens=30000),
        _trend_run("2026-01-02", score=4, tokens=20000),
        _trend_run("2026-01-03", score=5, tokens=10000),
    ]
    assert detect_trend_alerts(runs) == []


def test_detect_trend_alerts_recovery_breaks_the_streak():
    """A dip that recovers on the newest run is not a persistent regression."""
    from stats import detect_trend_alerts
    runs = [
        _trend_run("2026-01-01", score=5),
        _trend_run("2026-01-02", score=3),  # dipped
        _trend_run("2026-01-03", score=4),  # recovered — streak broken at the tail
    ]
    assert detect_trend_alerts(runs) == []


def test_detect_trend_alerts_not_enough_history():
    """A single rated run cannot form a run-over-run trend; no alert, no crash."""
    from stats import detect_trend_alerts
    assert detect_trend_alerts([_trend_run("2026-01-01", score=2)]) == []


def test_detect_trend_alerts_tokens_rising_fire():
    """Tokens climbing across 2+ consecutive runs alerts with direction up."""
    from stats import detect_trend_alerts
    runs = [
        _trend_run("2026-01-01", tokens=10000),
        _trend_run("2026-01-02", tokens=12000),
        _trend_run("2026-01-03", tokens=15000),
    ]
    alerts = detect_trend_alerts(runs)
    assert len(alerts) == 1
    assert alerts[0]["metric"] == "tokens"
    assert alerts[0]["direction"] == "up"
    assert alerts[0]["from_value"] == 10000
    assert alerts[0]["to_value"] == 15000


def test_detect_trend_alerts_ignores_sub_threshold_noise():
    """Moves below the relative-change floor are noise, not a regression."""
    from stats import detect_trend_alerts
    runs = [
        _trend_run("2026-01-01", tokens=10000),
        _trend_run("2026-01-02", tokens=10100),  # +1%
        _trend_run("2026-01-03", tokens=10200),  # +1%
    ]
    assert detect_trend_alerts(runs) == []


def test_detect_trend_alerts_orders_by_created_iso():
    """Out-of-order input is sorted chronologically before the trend is read."""
    from stats import detect_trend_alerts
    runs = [
        _trend_run("2026-01-03", score=3),
        _trend_run("2026-01-01", score=5),
        _trend_run("2026-01-02", score=4),
    ]
    alerts = detect_trend_alerts(runs)
    assert len(alerts) == 1
    assert alerts[0]["from_value"] == 5
    assert alerts[0]["to_value"] == 3


def test_format_stats_renders_trend_alerts():
    """format_stats shows the Trend Alerts block when alerts are present."""
    from stats import detect_trend_alerts
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "metrics": {}, "_rating": None, "_decisions": []},
    ])
    alerts = detect_trend_alerts([
        _trend_run("2026-01-01", score=5),
        _trend_run("2026-01-02", score=4),
        _trend_run("2026-01-03", score=3),
    ])
    out = run_phase.format_stats(agg, trend_alerts=alerts)
    assert "Trend Alerts" in out
    assert "Human rating falling" in out


def test_format_stats_omits_trend_alerts_when_empty():
    """No alerts means no Trend Alerts block."""
    agg = run_phase.aggregate_stats([
        {"run_id": "r1", "phase": "market", "status": "COMPLETED",
         "verdict": "APPROVED", "metrics": {}, "_rating": None, "_decisions": []},
    ])
    out = run_phase.format_stats(agg, trend_alerts=[])
    assert "Trend Alerts" not in out


class _FakeStdin:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


def test_prompt_for_rating_nudge_when_non_tty(tmp_path, monkeypatch, capsys):
    """Non-interactive finalize prints a copy-paste nudge, never blocks, writes nothing."""
    run_dir = tmp_path / "run_market_001"
    run_dir.mkdir()
    monkeypatch.setattr(run_phase.sys, "stdin", _FakeStdin(False))

    run_phase._prompt_for_rating(run_dir)

    out = capsys.readouterr().out
    assert "rate --run-dir" in out
    assert run_phase._load_rating(run_dir) is None


def test_prompt_for_rating_interactive_records(tmp_path, monkeypatch):
    """At a TTY, a valid score + note is recorded."""
    run_dir = tmp_path / "run_market_001"
    run_dir.mkdir()
    monkeypatch.setattr(run_phase.sys, "stdin", _FakeStdin(True))
    answers = iter(["4", "solid positioning"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    run_phase._prompt_for_rating(run_dir)

    rating = run_phase._load_rating(run_dir)
    assert rating["score"] == 4
    assert rating["note"] == "solid positioning"


def test_prompt_for_rating_skip_blank(tmp_path, monkeypatch):
    """Pressing Enter at the prompt skips without writing a rating."""
    run_dir = tmp_path / "run_market_001"
    run_dir.mkdir()
    monkeypatch.setattr(run_phase.sys, "stdin", _FakeStdin(True))
    monkeypatch.setattr("builtins.input", lambda *a: "")

    run_phase._prompt_for_rating(run_dir)
    assert run_phase._load_rating(run_dir) is None


def test_prompt_for_rating_out_of_range_skips(tmp_path, monkeypatch):
    """An out-of-range score is rejected, not clamped."""
    run_dir = tmp_path / "run_market_001"
    run_dir.mkdir()
    monkeypatch.setattr(run_phase.sys, "stdin", _FakeStdin(True))
    monkeypatch.setattr("builtins.input", lambda *a: "9")

    run_phase._prompt_for_rating(run_dir)
    assert run_phase._load_rating(run_dir) is None


def test_finalize_prints_rate_nudge_by_default(studio_root, capsys):
    """finalize closes with a rating nudge unless suppressed."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    (run_dir / "advocate_1.md").write_text("a", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("c", encoding="utf-8")
    (run_dir / "summary.md").write_text("s", encoding="utf-8")

    run_phase.finalize_run(make_finalize_args(run_id=run_id))
    assert "Rate this run" in capsys.readouterr().out


def test_finalize_no_rate_prompt_flag(studio_root, capsys):
    """--no-rate-prompt suppresses the closing nudge (used by the slash commands)."""
    run_id = run_phase.prepare_run(make_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id
    (run_dir / "advocate_1.md").write_text("a", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("c", encoding="utf-8")
    (run_dir / "summary.md").write_text("s", encoding="utf-8")

    args = make_finalize_args(run_id=run_id)
    args.no_rate_prompt = True
    run_phase.finalize_run(args)
    assert "Rate this run" not in capsys.readouterr().out


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
