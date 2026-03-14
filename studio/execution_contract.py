"""
Execution interface contract for Studio backends.

Any AI assistant backend (Claude Code, Windsurf/Cascade, etc.) that executes
Studio runs must implement this contract. The contract defines what a backend
receives, what it must produce, and the lifecycle it follows.

This module is documentation-as-code: it defines the data structures that flow
between the shared core (run_phase.py) and any execution backend, but does NOT
contain runtime logic. Backends import these types for clarity, not enforcement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# 1. Inputs: what the backend receives from `prepare_run`
# ---------------------------------------------------------------------------

@dataclass
class RunContext:
    """Everything a backend needs to execute a Studio run.

    Created by `run_phase.prepare_run()` and persisted as `run.json` +
    `instructions.md` in the run directory.
    """
    run_id: str
    phase: str                          # market | design | tech | studio
    run_dir: Path                       # absolute path to run directory
    instructions_path: Path             # path to instructions.md
    input_text: str                     # user's seed text
    max_iterations: int
    # Studio-phase only
    invited_roles: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. Outputs: what the backend must produce
# ---------------------------------------------------------------------------

@dataclass
class RunArtifacts:
    """Artifacts a backend must produce before `finalize_run` can succeed.

    Simple phases (market, design, tech):
        - At least one advocate_<N>.md
        - At least one contrarian_<N>.md
        - summary.md
        - implementation.md (tech phase, after APPROVED)

    Studio phase:
        - At least one advocate--<role>--<NN>.md per invited role
        - At least one contrarian--<role>--<NN>.md per invited role
        - integrator.md (after all roles approve)
        - summary.md
    """
    advocate_files: List[Path] = field(default_factory=list)
    contrarian_files: List[Path] = field(default_factory=list)
    summary_path: Optional[Path] = None
    implementation_path: Optional[Path] = None   # simple phases
    integrator_path: Optional[Path] = None       # studio phase


# ---------------------------------------------------------------------------
# 3. Lifecycle: the steps every backend follows
# ---------------------------------------------------------------------------
#
# 1. PREPARE  — User runs `run_phase.py prepare`. Shared core creates run_dir,
#               instructions.md, and run.json. Returns RunContext.
#
# 2. EXECUTE  — Backend-specific. The backend reads instructions.md and
#               produces artifacts in run_dir following the advocate/contrarian
#               loop described in the instructions.
#
#               Each iteration:
#                 a. Generate advocate output  → advocate_<N>.md
#                 b. Generate contrarian output → contrarian_<N>.md
#                 c. If VERDICT: REJECTED and iterations remain, loop to (a)
#                 d. If VERDICT: APPROVED, run implementer/integrator
#
#               The backend decides HOW to separate advocate/contrarian
#               (e.g., Claude Code uses Agent tool, Windsurf uses context
#               switching). The shared core does not care.
#
# 3. FINALIZE — User runs `run_phase.py finalize`. Shared core validates
#               artifacts exist, updates run.json, rebuilds index.md,
#               and appends to run_log.md.
#
# 4. VALIDATE — Optional. User runs `run_phase.py validate` to check
#               document quality and code correctness.
#
# ---------------------------------------------------------------------------
# Backend-specific implementation notes:
#
# Claude Code:
#   - Uses slash commands (.claude/commands/) to trigger prepare/execute/finalize
#   - Uses Agent tool to spawn separate advocate and contrarian subagents
#   - Each subagent gets its role prompt but NOT the other's output history
#
# Windsurf/Cascade:
#   - Uses Cascade rules or manual interaction
#   - Single context with role-switching prompts
#   - See docs/WINDSURF_USAGE.md for details
# ---------------------------------------------------------------------------
