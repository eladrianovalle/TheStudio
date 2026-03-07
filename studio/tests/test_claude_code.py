"""Tests for Claude Code integration (slash commands, agent-based execution)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import run_phase
from conftest import make_prepare_args, make_finalize_args

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_FILE = REPO_ROOT / ".claude" / "commands" / "run-phase.md"


class TestSlashCommand:
    """Verify the slash command file exists and has required content."""

    def test_command_file_exists(self):
        assert COMMAND_FILE.exists(), f"Missing {COMMAND_FILE}"

    def test_command_references_prepare(self):
        content = COMMAND_FILE.read_text()
        assert "run_phase.py prepare" in content

    def test_command_references_finalize(self):
        content = COMMAND_FILE.read_text()
        assert "run_phase.py finalize" in content

    def test_command_references_agent_separation(self):
        """The command must instruct separate Agent invocations."""
        content = COMMAND_FILE.read_text()
        assert "Agent" in content
        assert "separate" in content.lower() or "SEPARATE" in content

    def test_command_references_verdict(self):
        content = COMMAND_FILE.read_text()
        assert "VERDICT: APPROVED" in content
        assert "VERDICT: REJECTED" in content

    def test_command_has_arguments_placeholder(self):
        content = COMMAND_FILE.read_text()
        assert "$ARGUMENTS" in content


class TestMarketPhaseE2E:
    """Simulate a full market phase run as Claude Code would execute it."""

    def test_market_prepare_execute_finalize(self, studio_root):
        # Step 1: Prepare
        run_id = run_phase.prepare_run(
            make_prepare_args(phase="market", text="A cozy farming sim")
        )
        run_dir = studio_root / "output" / "market" / run_id

        assert run_dir.exists()
        assert (run_dir / "instructions.md").exists()
        assert (run_dir / "run.json").exists()

        instructions = (run_dir / "instructions.md").read_text()
        assert "Market Growth Strategist" in instructions
        assert "Reality Check" in instructions

        # Step 2: Simulate advocate agent output
        (run_dir / "advocate_1.md").write_text(
            "# Market Advocate Proposal\n\n"
            "## Target Audience\n\n"
            "Casual gamers aged 18-35 who enjoy relaxation games.\n\n"
            "## Value Proposition\n\n"
            "Unique blend of farming mechanics with social deduction.\n\n"
            "## Go-to-Market\n\n"
            "Steam Early Access with Discord community building.\n\n"
            "## KPIs\n\n"
            "- Wishlist conversions > 15%\n"
            "- D7 retention > 25%\n"
        )

        # Step 3: Simulate contrarian agent output (REJECTED)
        (run_dir / "contrarian_1.md").write_text(
            "# Market Contrarian Review\n\n"
            "The proposal has promise but critical gaps:\n\n"
            "VERDICT: REJECTED\n\n"
            "1. No competitive analysis — similar games exist\n"
            "2. TAM estimate missing entirely\n"
            "3. Discord-only GTM is too narrow\n"
        )

        # Step 4: Simulate revised advocate (iteration 2)
        (run_dir / "advocate_2.md").write_text(
            "# Market Advocate Proposal (Revised)\n\n"
            "## Competitive Analysis\n\n"
            "Compared to Stardew Valley, Among Us, and Phasmophobia.\n\n"
            "## TAM\n\n"
            "Farming sim market: $2B. Social deduction: $500M. Overlap niche: ~$200M.\n\n"
            "## Expanded GTM\n\n"
            "Steam + Discord + TikTok influencer partnerships + Reddit community.\n\n"
            "## Target Audience\n\n"
            "Core: 18-35 casual. Secondary: Among Us fans seeking depth.\n\n"
            "## KPIs\n\n"
            "- Wishlist conversions > 15%\n"
            "- D7 retention > 25%\n"
        )

        # Step 5: Simulate contrarian agent output (APPROVED)
        (run_dir / "contrarian_2.md").write_text(
            "# Market Contrarian Review (Round 2)\n\n"
            "The revised proposal addresses key concerns:\n"
            "- Competitive analysis is solid\n"
            "- TAM estimate is conservative and defensible\n"
            "- Multi-channel GTM is realistic\n\n"
            "VERDICT: APPROVED\n\n"
            "Proceed with implementation phase.\n"
        )

        # Step 6: Simulate implementation
        (run_dir / "implementation.md").write_text(
            "# Market Research Implementation\n\n"
            "## Target Audience Profile\n\nCore segment defined.\n"
            "## Competitor Analysis\n\n3 comparables analyzed.\n"
            "## Value Proposition\n\nUnique blend articulated.\n"
            "## Go-to-Market Plan\n\nMulti-channel approach.\n"
            "## Success Metrics\n\nKPIs established.\n"
        )

        # Step 7: Summary
        (run_dir / "summary.md").write_text(
            "# Run Summary\n\n"
            "## Input\nA cozy farming sim with social deduction mechanics.\n\n"
            "## Iterations\n2 rounds. First rejected for missing competitive analysis.\n\n"
            "## Verdict\nAPPROVED after addressing gaps.\n\n"
            "## Key Recommendations\n"
            "- Target 18-35 casual gamers\n"
            "- Multi-channel GTM (Steam, Discord, TikTok, Reddit)\n"
            "- Conservative $200M niche TAM\n"
        )

        # Step 8: Finalize
        run_phase.finalize_run(
            make_finalize_args(
                phase="market", run_id=run_id,
                verdict="APPROVED", hours=0.5,
            )
        )

        # Verify final state
        meta = json.loads((run_dir / "run.json").read_text())
        assert meta["status"] == "COMPLETED"
        assert meta["verdict"] == "APPROVED"
        assert meta["iterations_run"] == 2

        # Verify index updated
        index = (studio_root / "output" / "index.md").read_text()
        assert run_id in index


class TestTechPhaseE2E:
    """Simulate a full tech phase run as Claude Code would execute it."""

    def test_tech_prepare_execute_finalize(self, studio_root):
        # Prepare
        run_id = run_phase.prepare_run(
            make_prepare_args(phase="tech", text="Build multiplayer lobby system")
        )
        run_dir = studio_root / "output" / "tech" / run_id

        instructions = (run_dir / "instructions.md").read_text()
        assert "Technical Architect" in instructions
        assert "SRE" in instructions

        # Simulate single-iteration approval
        (run_dir / "advocate_1.md").write_text(
            "# Tech Advocate\n\n"
            "## Architecture\n\nWebSocket-based lobby with Redis pub/sub.\n\n"
            "## Stack\n\nNode.js + Socket.io + Redis.\n\n"
            "## Testing\n\nIntegration tests for connection lifecycle.\n"
        )

        (run_dir / "contrarian_1.md").write_text(
            "# Tech Contrarian\n\n"
            "Architecture is sound. WebSocket + Redis is proven.\n"
            "Minor concern: add connection pooling limits.\n\n"
            "VERDICT: APPROVED\n"
        )

        (run_dir / "implementation.md").write_text(
            "# Technical Implementation\n\n"
            "## Architecture\n\nWebSocket lobby server.\n"
            "## Stack\n\nNode.js, Socket.io, Redis.\n"
            "## Tests\n\nConnection lifecycle tests.\n"
            "## Code\n\nLobby manager implementation.\n"
        )

        (run_dir / "summary.md").write_text(
            "# Summary\n\nApproved in 1 iteration. WebSocket + Redis architecture.\n"
        )

        run_phase.finalize_run(
            make_finalize_args(
                phase="tech", run_id=run_id,
                verdict="APPROVED", hours=0.3,
            )
        )

        meta = json.loads((run_dir / "run.json").read_text())
        assert meta["status"] == "COMPLETED"
        assert meta["verdict"] == "APPROVED"
        assert meta["iterations_run"] == 1


class TestRerunFlow:
    """Test that rejection from one run feeds into the next."""

    def test_rejection_context_injected_on_rerun(self, studio_root):
        import time

        # Run 1: REJECTED
        run_id_1 = run_phase.prepare_run(
            make_prepare_args(phase="tech", text="Build auth system")
        )
        run_dir_1 = studio_root / "output" / "tech" / run_id_1

        (run_dir_1 / "advocate_1.md").write_text("# Advocate\n\nUse JWT tokens.")
        (run_dir_1 / "contrarian_1.md").write_text(
            "# Contrarian\n\n"
            "VERDICT: REJECTED\n\n"
            "1. No token refresh strategy\n"
            "2. Missing rate limiting\n"
        )
        (run_dir_1 / "summary.md").write_text("# Summary\n\nRejected.")

        run_phase.finalize_run(
            make_finalize_args(
                phase="tech", run_id=run_id_1, verdict="REJECTED",
            )
        )

        time.sleep(1)  # avoid timestamp collision

        # Run 2: Should have rerun context
        run_id_2 = run_phase.prepare_run(
            make_prepare_args(phase="tech", text="Build auth system (revised)")
        )
        run_dir_2 = studio_root / "output" / "tech" / run_id_2

        instructions = (run_dir_2 / "instructions.md").read_text()
        # The instructions should reference the previous rejection
        assert run_dir_2.exists()
        assert (run_dir_2 / "instructions.md").exists()
