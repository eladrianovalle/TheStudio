#!/usr/bin/env python3
"""Tests for iterative scoped debate features.

Covers:
- generate_scope_prompt() in scopes.py
- extract-decisions CLI subcommand
- inject-context CLI subcommand
- check_decision_points() in DocumentValidator
- Strengthened decision point protocol in instructions.md
"""
import json
import tempfile
from pathlib import Path

import pytest

from scopes import ScopeConfig, ScopesConfig, generate_scope_prompt
from validators.document_validator import DocumentValidator


# ---------------------------------------------------------------------------
# generate_scope_prompt tests
# ---------------------------------------------------------------------------


class TestGenerateScopePrompt:
    """Tests for scopes.generate_scope_prompt()."""

    def _alignment_scope(self):
        return ScopeConfig(
            name="alignment",
            focus="Directional alignment — approach, fatal flaws, high-level trade-offs only.",
            max_iterations=2,
            output_budget=500,
            debate_mode="all_roles",
        )

    def _depth_scope(self):
        return ScopeConfig(
            name="depth",
            focus="Full analysis — detailed deliverables, edge cases.",
            max_iterations=3,
            debate_mode="per_role",
        )

    def _polish_scope(self):
        return ScopeConfig(
            name="polish",
            focus="Cross-discipline conflicts only.",
            max_iterations=1,
            output_budget=300,
            debate_mode="all_roles",
        )

    def test_alignment_advocate_basic(self):
        prompt = generate_scope_prompt(
            scope=self._alignment_scope(),
            scope_index=0,
            role_title="Marketing",
            stance="advocate",
            run_dir="/tmp/run_studio_001",
            advocate_focus="Market viability",
            contrarian_focus="Market risks",
            deliverables=["Market analysis", "Competitor review"],
            user_text="A cozy farming sim",
            decisions_md_exists=False,
        )
        assert "ALIGNMENT" in prompt
        assert "Marketing" in prompt
        assert "Market viability" in prompt
        assert "under 500 words" in prompt
        assert "Do NOT produce full deliverables" in prompt
        assert "DECISION [P0]" in prompt
        assert "MUST surface at least 1 decision point" in prompt

    def test_alignment_contrarian_has_verdict(self):
        prompt = generate_scope_prompt(
            scope=self._alignment_scope(),
            scope_index=0,
            role_title="Engineering",
            stance="contrarian",
            run_dir="/tmp/run",
            advocate_focus="Tech architecture",
            contrarian_focus="Ops risks",
            deliverables=[],
            user_text="Build a lobby system",
            decisions_md_exists=False,
        )
        assert "VERDICT: APPROVED" in prompt
        assert "VERDICT: REJECTED" in prompt
        assert "Ops risks" in prompt
        assert "MUST flag it as a decision point" in prompt

    def test_depth_no_word_cap(self):
        prompt = generate_scope_prompt(
            scope=self._depth_scope(),
            scope_index=1,
            role_title="Design",
            stance="advocate",
            run_dir="/tmp/run",
            advocate_focus="Systems design",
            contrarian_focus="Scope creep",
            deliverables=["Core loop diagram", "Progression outline"],
            user_text="Farming sim",
            decisions_md_exists=False,
        )
        assert "DEPTH" in prompt
        assert "Word cap" not in prompt
        assert "Core loop diagram" in prompt
        assert "Progression outline" in prompt

    def test_depth_with_s1_files(self):
        prompt = generate_scope_prompt(
            scope=self._depth_scope(),
            scope_index=1,
            role_title="Design",
            stance="advocate",
            run_dir="/tmp/run",
            advocate_focus="Design",
            contrarian_focus="Scope",
            deliverables=[],
            user_text="test",
            decisions_md_exists=False,
            s1_files=["advocate--design--S1-01.md", "contrarian--design--S1-01.md"],
        )
        assert "advocate--design--S1-01.md" in prompt
        assert "Prior-scope context" in prompt

    def test_polish_scope_guidance(self):
        prompt = generate_scope_prompt(
            scope=self._polish_scope(),
            scope_index=2,
            role_title="Cross-Discipline",
            stance="advocate",
            run_dir="/tmp/run",
            advocate_focus="Integration",
            contrarian_focus="Conflicts",
            deliverables=[],
            user_text="test",
            decisions_md_exists=False,
        )
        assert "POLISH" in prompt
        assert "cross-discipline" in prompt.lower()
        assert "under 300 words" in prompt

    def test_settled_decisions_included(self):
        prompt = generate_scope_prompt(
            scope=self._depth_scope(),
            scope_index=1,
            role_title="Engineering",
            stance="advocate",
            run_dir="/tmp/run",
            advocate_focus="Tech",
            contrarian_focus="Ops",
            deliverables=[],
            user_text="test",
            decisions_md_exists=True,
        )
        assert "decisions.md" in prompt
        assert "hard constraints" in prompt

    def test_rejection_context_included(self):
        prompt = generate_scope_prompt(
            scope=self._depth_scope(),
            scope_index=1,
            role_title="Design",
            stance="advocate",
            run_dir="/tmp/run",
            advocate_focus="Design",
            contrarian_focus="Scope",
            deliverables=[],
            user_text="test",
            decisions_md_exists=False,
            rejection_context="1. Core loop too complex\n2. Missing UX safeguards",
        )
        assert "Prior rejection context" in prompt
        assert "Core loop too complex" in prompt

    def test_s2_brief_referenced(self):
        prompt = generate_scope_prompt(
            scope=self._depth_scope(),
            scope_index=1,
            role_title="QA",
            stance="contrarian",
            run_dir="/tmp/run",
            advocate_focus="QA",
            contrarian_focus="Coverage",
            deliverables=[],
            user_text="test",
            decisions_md_exists=False,
            s2_brief_exists=True,
        )
        assert "S2-brief.md" in prompt


# ---------------------------------------------------------------------------
# check_decision_points tests
# ---------------------------------------------------------------------------


class TestCheckDecisionPoints:
    """Tests for DocumentValidator.check_decision_points()."""

    def test_warns_when_no_decisions(self, tmp_path):
        doc = tmp_path / "advocate_1.md"
        doc.write_text("# Proposal\n\nThis is a great idea.\n\n## Details\nLots of details here.")

        validator = DocumentValidator()
        result = validator.check_decision_points(doc)
        assert result.passed  # Warning only, not failure
        assert len(result.warnings) == 1
        assert "No decision points found" in result.warnings[0]

    def test_passes_when_decisions_present(self, tmp_path):
        doc = tmp_path / "advocate_1.md"
        doc.write_text(
            "# Proposal\n\n"
            "> **DECISION [P0]:** Should we use real-time or turn-based?\n"
            "> **Unblocks:** Core loop design\n"
        )

        validator = DocumentValidator()
        result = validator.check_decision_points(doc)
        assert result.passed
        assert len(result.warnings) == 0

    def test_handles_missing_file(self, tmp_path):
        doc = tmp_path / "nonexistent.md"
        validator = DocumentValidator()
        result = validator.check_decision_points(doc)
        assert result.passed  # Warning only
        assert len(result.warnings) == 1


# ---------------------------------------------------------------------------
# CLI subcommand tests (extract-decisions, inject-context)
# ---------------------------------------------------------------------------


class TestExtractDecisionsCLI:
    """Tests for the extract-decisions CLI subcommand."""

    def test_extract_from_run_dir(self, tmp_path):
        """extract-decisions finds decision points in agent files."""
        run_dir = tmp_path / "run_studio_001"
        run_dir.mkdir()

        (run_dir / "advocate--marketing--S1-01.md").write_text(
            "# Marketing Proposal\n\n"
            "> **DECISION [P0]:** Target casual or hardcore?\n"
            "> **Unblocks:** Marketing strategy\n"
            "> **Options:** (a) Casual (b) Hardcore\n"
        )
        (run_dir / "contrarian--marketing--S1-01.md").write_text(
            "# Marketing Critique\n\nVERDICT: APPROVED\n"
        )

        from run_phase import parse_cli_args, extract_decisions
        import argparse

        args = argparse.Namespace(run_dir=run_dir, scope=None, show_all=False)
        # Should not raise
        extract_decisions(args)

    def test_extract_with_scope_filter(self, tmp_path):
        """extract-decisions --scope S1 filters to S1 files."""
        run_dir = tmp_path / "run_studio_002"
        run_dir.mkdir()

        (run_dir / "advocate--design--S1-01.md").write_text(
            "> **DECISION [P1]:** Core loop question?\n"
            "> **Unblocks:** Design\n"
        )
        (run_dir / "advocate--design--S2-01.md").write_text(
            "> **DECISION [P0]:** Depth question?\n"
            "> **Unblocks:** Implementation\n"
        )

        import argparse

        # Filter to S1 — should only find the P1
        args = argparse.Namespace(run_dir=run_dir, scope="S1", show_all=False)
        from run_phase import extract_decisions
        # Just verify it runs without error (output is printed)
        extract_decisions(args)

    def test_extract_empty_run(self, tmp_path):
        """extract-decisions with no agent files produces no output."""
        run_dir = tmp_path / "run_studio_003"
        run_dir.mkdir()

        import argparse
        from run_phase import extract_decisions
        args = argparse.Namespace(run_dir=run_dir, scope=None, show_all=False)
        # Should complete silently
        extract_decisions(args)

    def test_extract_filters_settled_by_default(self, tmp_path, capsys):
        """extract-decisions hides settled decisions unless --all is passed."""
        import argparse
        from decision_points import DecisionPoint, save_decisions_json
        from run_phase import extract_decisions

        run_dir = tmp_path / "run_studio_004"
        run_dir.mkdir()

        (run_dir / "advocate--design--01.md").write_text(
            "> **DECISION [P0]:** Already settled question?\n"
            "> **Unblocks:** Something\n"
        )

        save_decisions_json(run_dir, [DecisionPoint(
            priority="P0",
            question="Already settled question?",
            unblocks="Something",
            source_file="advocate--design--01.md",
            answer="Yes",
            answered_by="user",
        )])

        # Default (show_all=False): settled decision should be filtered out
        args = argparse.Namespace(run_dir=run_dir, scope=None, show_all=False)
        extract_decisions(args)
        assert "Already settled question?" not in capsys.readouterr().out

        # With --all: settled decision should appear
        args = argparse.Namespace(run_dir=run_dir, scope=None, show_all=True)
        extract_decisions(args)
        assert "Already settled question?" in capsys.readouterr().out


class TestInjectContextCLI:
    """Tests for the inject-context CLI subcommand."""

    def test_inject_context_basic(self, tmp_path, monkeypatch):
        """inject-context generates context for a scoped agent."""
        run_dir = tmp_path / "run_studio_010"
        run_dir.mkdir()

        # Create run.json with scopes meta pointing to the real scopes.toml
        studio_root = Path(__file__).resolve().parent.parent
        scopes_path = studio_root / "config" / "scopes.toml"

        meta = {
            "run_id": "run_studio_010",
            "phase": "studio",
            "input": "A cozy farming sim",
            "max_iterations": 6,
            "scopes": {
                "config_path": str(scopes_path),
                "scopes": [
                    {"name": "alignment", "focus": "Directional", "allocated_iterations": 2},
                    {"name": "depth", "focus": "Detail", "allocated_iterations": 3},
                    {"name": "polish", "focus": "Conflicts", "allocated_iterations": 1},
                ],
                "total_iterations": 6,
            },
        }
        (run_dir / "run.json").write_text(json.dumps(meta))

        # Monkeypatch to avoid artifact root issues
        monkeypatch.setenv("STUDIO_ROOT", str(studio_root))

        import argparse
        from run_phase import inject_context, set_artifact_root
        set_artifact_root(tmp_path)

        args = argparse.Namespace(
            run_dir=run_dir,
            scope="alignment",
            role="marketing",
            stance="advocate",
            artifact_root=tmp_path,
        )
        # Should run without error
        inject_context(args)

    def test_inject_context_with_decisions(self, tmp_path, monkeypatch):
        """inject-context includes settled decisions reference when decisions.md exists."""
        run_dir = tmp_path / "run_studio_011"
        run_dir.mkdir()

        studio_root = Path(__file__).resolve().parent.parent
        scopes_path = studio_root / "config" / "scopes.toml"

        meta = {
            "run_id": "run_studio_011",
            "phase": "studio",
            "input": "Build lobby system",
            "max_iterations": 6,
            "scopes": {
                "config_path": str(scopes_path),
                "scopes": [
                    {"name": "depth", "focus": "Detail", "allocated_iterations": 3},
                ],
                "total_iterations": 3,
            },
        }
        (run_dir / "run.json").write_text(json.dumps(meta))
        (run_dir / "decisions.md").write_text("# Settled Decisions\n\n| # | Decision |\n")

        monkeypatch.setenv("STUDIO_ROOT", str(studio_root))

        import argparse
        from run_phase import inject_context, set_artifact_root
        set_artifact_root(tmp_path)

        args = argparse.Namespace(
            run_dir=run_dir,
            scope="depth",
            role="engineering",
            stance="advocate",
            artifact_root=tmp_path,
        )
        inject_context(args)

    def test_inject_context_missing_run_dir(self, tmp_path):
        """inject-context raises on missing run directory."""
        import argparse
        from run_phase import inject_context

        args = argparse.Namespace(
            run_dir=tmp_path / "nonexistent",
            scope="depth",
            role="design",
            stance="advocate",
            artifact_root=tmp_path,
        )
        with pytest.raises(FileNotFoundError):
            inject_context(args)


# ---------------------------------------------------------------------------
# Strengthened decision point protocol in build_instruction_doc
# ---------------------------------------------------------------------------


class TestStrengthenedDecisionProtocol:
    """Verify that build_instruction_doc produces stronger decision point language."""

    def test_advocate_must_surface(self, tmp_path):
        """Advocate instructions now say MUST surface decision points."""
        from run_phase import build_instruction_doc

        meta = {
            "run_id": "test_run",
            "phase": "design",
            "input": "A farming sim",
            "max_iterations": 3,
            "budget_cap": "",
            "created_display": "2026-01-01 00:00",
            "output_type": "deliverables",
        }
        doc = build_instruction_doc(meta, tmp_path)
        assert "You MUST surface at least 1 decision point" in doc

    def test_contrarian_must_flag(self, tmp_path):
        """Contrarian instructions now say MUST flag unsettled assumptions."""
        from run_phase import build_instruction_doc

        meta = {
            "run_id": "test_run",
            "phase": "tech",
            "input": "Build lobby",
            "max_iterations": 3,
            "budget_cap": "",
            "created_display": "2026-01-01 00:00",
            "output_type": "deliverables",
        }
        doc = build_instruction_doc(meta, tmp_path)
        assert "you MUST flag it as a decision point" in doc

    def test_scope_templates_included(self, tmp_path):
        """Instructions with scopes include inject-context/extract-decisions templates."""
        from run_phase import build_instruction_doc
        from scopes import ScopesConfig, ScopeConfig, allocate_iterations

        scopes_config = ScopesConfig(scopes=[
            ScopeConfig("alignment", "Directional", 2, output_budget=500, debate_mode="all_roles"),
            ScopeConfig("depth", "Detail", 3, debate_mode="per_role"),
        ])
        allocations = allocate_iterations(scopes_config)

        meta = {
            "run_id": "test_scoped",
            "phase": "studio",
            "input": "Farming sim",
            "max_iterations": 5,
            "budget_cap": "$0-20/mo",
            "created_display": "2026-01-01 00:00",
            "output_type": "deliverables",
            "studio_roles": {"pack": "studio_core", "overrides": [], "invited": ["marketing"]},
        }
        doc = build_instruction_doc(meta, tmp_path, scopes_config=scopes_config, scopes_allocations=allocations)
        assert "inject-context" in doc
        assert "extract-decisions" in doc


# ---------------------------------------------------------------------------
# CLI argument parsing for new subcommands
# ---------------------------------------------------------------------------


class TestNewSubcommandParsing:
    """Test that the new subcommands parse correctly."""

    def test_extract_decisions_parse(self):
        from run_phase import parse_cli_args
        args = parse_cli_args(["extract-decisions", "--run-dir", "/tmp/test"])
        assert args.command == "extract-decisions"
        assert args.run_dir == Path("/tmp/test")

    def test_extract_decisions_with_scope(self):
        from run_phase import parse_cli_args
        args = parse_cli_args(["extract-decisions", "--run-dir", "/tmp/test", "--scope", "S1"])
        assert args.scope == "S1"

    def test_inject_context_parse(self):
        from run_phase import parse_cli_args
        args = parse_cli_args([
            "inject-context",
            "--run-dir", "/tmp/test",
            "--scope", "depth",
            "--role", "marketing",
            "--stance", "advocate",
        ])
        assert args.command == "inject-context"
        assert args.scope == "depth"
        assert args.role == "marketing"
        assert args.stance == "advocate"

    def test_inject_context_invalid_stance(self):
        from run_phase import parse_cli_args
        with pytest.raises(SystemExit):
            parse_cli_args([
                "inject-context",
                "--run-dir", "/tmp/test",
                "--scope", "depth",
                "--role", "marketing",
                "--stance", "invalid",
            ])
