#!/usr/bin/env python3
"""Tests for rerun mode detection and failure context injection."""
import tempfile
from pathlib import Path

import pytest

from rerun import (
    RejectionContext,
    detect_rerun_mode,
    extract_rejection_reasons,
    find_latest_rejection,
    generate_rerun_instructions,
    inject_context_into_prompt,
    load_rejection_context,
)


@pytest.fixture
def temp_run_dir():
    """Create a temporary run directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_rejection_context_format_for_prompt():
    """Test formatting rejection context for prompt injection."""
    context = RejectionContext(
        iteration=2,
        role="product",
        reasons=[
            "Missing market validation",
            "Unclear target audience",
            "No competitive analysis"
        ],
        full_text="Full contrarian response..."
    )
    
    formatted = context.format_for_prompt()
    
    assert "Previous iteration was REJECTED" in formatted
    assert "1. Missing market validation" in formatted
    assert "2. Unclear target audience" in formatted
    assert "3. No competitive analysis" in formatted
    assert "address these concerns" in formatted.lower()


def test_rejection_context_empty_reasons():
    """Test formatting with no reasons."""
    context = RejectionContext(
        iteration=1,
        role=None,
        reasons=[],
        full_text="VERDICT: REJECTED"
    )
    
    formatted = context.format_for_prompt()
    assert formatted == ""


def test_detect_rerun_mode_no_files(temp_run_dir):
    """Test rerun detection with no existing files."""
    assert detect_rerun_mode(temp_run_dir) is False


def test_detect_rerun_mode_with_contrarian_files(temp_run_dir):
    """Test rerun detection with existing contrarian files."""
    (temp_run_dir / "contrarian_1.md").write_text("VERDICT: APPROVED")
    assert detect_rerun_mode(temp_run_dir) is True


def test_detect_rerun_mode_nonexistent_dir():
    """Test rerun detection with nonexistent directory."""
    assert detect_rerun_mode(Path("/nonexistent/path")) is False


def test_find_latest_rejection_no_files(temp_run_dir):
    """Test finding rejection with no files."""
    result = find_latest_rejection(temp_run_dir)
    assert result is None


def test_find_latest_rejection_only_approved(temp_run_dir):
    """Test finding rejection when all verdicts are approved."""
    (temp_run_dir / "contrarian_1.md").write_text("VERDICT: APPROVED")
    (temp_run_dir / "contrarian_2.md").write_text("VERDICT: APPROVED")
    
    result = find_latest_rejection(temp_run_dir)
    assert result is None


def test_find_latest_rejection_finds_most_recent(temp_run_dir):
    """Test finding the most recent rejection."""
    (temp_run_dir / "contrarian_1.md").write_text("VERDICT: REJECTED\nOld rejection")
    (temp_run_dir / "contrarian_2.md").write_text("VERDICT: APPROVED")
    (temp_run_dir / "contrarian_3.md").write_text("VERDICT: REJECTED\nRecent rejection")
    
    result = find_latest_rejection(temp_run_dir)
    assert result is not None
    assert result.name == "contrarian_3.md"
    assert "Recent rejection" in result.read_text()


def test_find_latest_rejection_with_role(temp_run_dir):
    """Test finding rejection for specific role in studio phase."""
    (temp_run_dir / "contrarian--product--01.md").write_text("VERDICT: REJECTED\nProduct rejection")
    (temp_run_dir / "contrarian--engineering--01.md").write_text("VERDICT: REJECTED\nEngineering rejection")
    
    result = find_latest_rejection(temp_run_dir, role="product")
    assert result is not None
    assert "product" in result.name
    assert "Product rejection" in result.read_text()


def test_extract_rejection_reasons_numbered_list():
    """Test extracting reasons from numbered list format."""
    content = """
# Contrarian Response

VERDICT: REJECTED

Reasons for rejection:

1. Missing market validation data
2. Unclear target audience definition
3. No competitive analysis provided
4. Budget estimates are unrealistic

Please address these concerns.
"""
    
    reasons = extract_rejection_reasons(content)
    
    assert len(reasons) == 4
    assert "Missing market validation data" in reasons
    assert "Unclear target audience definition" in reasons
    assert "No competitive analysis provided" in reasons
    assert "Budget estimates are unrealistic" in reasons


def test_extract_rejection_reasons_bullet_points():
    """Test extracting reasons from bullet point format."""
    content = """
VERDICT: REJECTED

Key concerns:

- Architecture is too complex for MVP
- Missing error handling strategy
- No monitoring plan included
- Performance benchmarks not defined
"""
    
    reasons = extract_rejection_reasons(content)
    
    assert len(reasons) == 4
    assert any("Architecture is too complex" in r for r in reasons)
    assert any("error handling" in r for r in reasons)


def test_extract_rejection_reasons_reasons_section():
    """Test extracting from explicit 'Reasons:' section."""
    content = """
VERDICT: REJECTED

Reasons:
Missing user research
No A/B testing plan
Unclear success metrics
Timeline is too aggressive
"""
    
    reasons = extract_rejection_reasons(content)
    
    assert len(reasons) >= 2
    assert any("user research" in r.lower() for r in reasons)
    assert any("testing plan" in r.lower() for r in reasons)


def test_extract_rejection_reasons_paragraph_format():
    """Test extracting from paragraph format (fallback)."""
    content = """
VERDICT: REJECTED

The proposed approach has several critical flaws that must be addressed.

First, there is no market validation to support the claimed TAM of $500M.

Second, the competitive analysis is superficial and misses key players.

Third, the go-to-market strategy relies on unproven channels.
"""
    
    reasons = extract_rejection_reasons(content)
    
    # Should extract at least some paragraphs
    assert len(reasons) > 0
    assert any("market validation" in r.lower() for r in reasons)


def test_extract_rejection_reasons_no_rejection():
    """Test extracting from approved verdict."""
    content = """
VERDICT: APPROVED

The proposal looks solid. Proceed with implementation.
"""
    
    reasons = extract_rejection_reasons(content)
    assert len(reasons) == 0


def test_extract_rejection_reasons_limits_to_five():
    """Test that extraction limits to top 5 reasons."""
    content = """
VERDICT: REJECTED

1. Reason one
2. Reason two
3. Reason three
4. Reason four
5. Reason five
6. Reason six
7. Reason seven
"""
    
    reasons = extract_rejection_reasons(content)
    assert len(reasons) <= 5


def test_extract_rejection_reasons_cleans_markdown():
    """Test that markdown formatting is cleaned from reasons."""
    content = """
VERDICT: REJECTED

1. **Missing** market *validation* data with `code snippets`
2. Unclear **target audience** definition
"""
    
    reasons = extract_rejection_reasons(content)
    
    # Should remove markdown formatting
    assert "**" not in reasons[0]
    assert "*" not in reasons[0]
    assert "`" not in reasons[0]
    assert "Missing" in reasons[0]
    assert "validation" in reasons[0]


def test_load_rejection_context_success(temp_run_dir):
    """Test loading rejection context successfully."""
    rejection_content = """
# Contrarian Response - Iteration 2

VERDICT: REJECTED

Critical issues:

1. Missing technical feasibility analysis
2. No risk mitigation strategy
3. Timeline is unrealistic
"""
    
    (temp_run_dir / "contrarian_2.md").write_text(rejection_content)
    
    context = load_rejection_context(temp_run_dir)
    
    assert context is not None
    assert context.iteration == 2
    assert context.role is None
    assert len(context.reasons) == 3
    assert "technical feasibility" in context.reasons[0].lower()


def test_load_rejection_context_with_role(temp_run_dir):
    """Test loading rejection context for specific role."""
    rejection_content = """
VERDICT: REJECTED

1. Missing user personas
2. No journey mapping
"""
    
    (temp_run_dir / "contrarian--design--03.md").write_text(rejection_content)
    
    context = load_rejection_context(temp_run_dir, role="design")
    
    assert context is not None
    assert context.iteration == 3
    assert context.role == "design"
    assert len(context.reasons) == 2


def test_load_rejection_context_no_rejection(temp_run_dir):
    """Test loading when no rejection exists."""
    (temp_run_dir / "contrarian_1.md").write_text("VERDICT: APPROVED")
    
    context = load_rejection_context(temp_run_dir)
    assert context is None


def test_inject_context_into_prompt_with_context():
    """Test injecting context into advocate prompt."""
    base_prompt = """
# Advocate Prompt

Your task is to propose a solution.

## Deliverables

- Proposal document
- Implementation plan
"""
    
    context = RejectionContext(
        iteration=1,
        role=None,
        reasons=["Missing cost analysis", "No timeline provided"],
        full_text="..."
    )
    
    modified = inject_context_into_prompt(base_prompt, context)
    
    assert "Previous iteration was REJECTED" in modified
    assert "Missing cost analysis" in modified
    assert "No timeline provided" in modified
    assert "## Deliverables" in modified  # Original content preserved
    # Context should be injected before deliverables
    context_pos = modified.find("Previous iteration")
    deliverables_pos = modified.find("## Deliverables")
    assert context_pos < deliverables_pos


def test_inject_context_into_prompt_no_context():
    """Test that prompt is unchanged when no context provided."""
    base_prompt = "# Advocate Prompt\n\nYour task..."
    
    modified = inject_context_into_prompt(base_prompt, None)
    assert modified == base_prompt


def test_inject_context_into_prompt_empty_reasons():
    """Test that prompt is unchanged when context has no reasons."""
    base_prompt = "# Advocate Prompt\n\nYour task..."
    context = RejectionContext(iteration=1, role=None, reasons=[], full_text="...")
    
    modified = inject_context_into_prompt(base_prompt, context)
    assert modified == base_prompt


def test_generate_rerun_instructions_with_rejection(temp_run_dir):
    """Test generating rerun instructions with rejection context."""
    rejection_content = """
VERDICT: REJECTED

1. Missing market data
2. Unclear value proposition
"""
    
    (temp_run_dir / "contrarian_1.md").write_text(rejection_content)
    
    instructions = generate_rerun_instructions(temp_run_dir)
    
    assert "Rerun Mode Detected" in instructions
    assert "REJECTED" in instructions
    assert "Missing market data" in instructions
    assert "Unclear value proposition" in instructions
    assert "Next Steps" in instructions


def test_generate_rerun_instructions_with_role(temp_run_dir):
    """Test generating rerun instructions for specific role."""
    rejection_content = """
VERDICT: REJECTED

1. Architecture too complex
"""
    
    (temp_run_dir / "contrarian--engineering--02.md").write_text(rejection_content)
    
    instructions = generate_rerun_instructions(temp_run_dir, role="engineering")
    
    assert "engineering" in instructions.lower()
    assert "Architecture too complex" in instructions


def test_generate_rerun_instructions_no_rejection(temp_run_dir):
    """Test generating instructions when no rejection found."""
    instructions = generate_rerun_instructions(temp_run_dir)
    
    assert "No previous rejections found" in instructions
    assert "Starting fresh iteration" in instructions


def test_integration_full_workflow(temp_run_dir):
    """Integration test: full rerun workflow."""
    # Setup: Create initial rejection
    rejection_content = """
# Contrarian Response - Tech Phase

After reviewing the advocate's proposal, I must issue:

VERDICT: REJECTED

Critical concerns:

1. The proposed architecture lacks horizontal scalability
2. No database migration strategy is defined
3. Error handling is insufficient for production use
4. Missing observability and monitoring plan
5. Security considerations are not addressed

Please revise the proposal to address these fundamental issues.
"""
    
    (temp_run_dir / "contrarian_2.md").write_text(rejection_content)
    
    # Step 1: Detect rerun mode
    assert detect_rerun_mode(temp_run_dir) is True
    
    # Step 2: Load rejection context
    context = load_rejection_context(temp_run_dir)
    assert context is not None
    assert context.iteration == 2
    assert len(context.reasons) == 5
    
    # Step 3: Generate rerun instructions
    instructions = generate_rerun_instructions(temp_run_dir)
    assert "Rerun Mode Detected" in instructions
    assert "horizontal scalability" in instructions
    
    # Step 4: Inject context into advocate prompt
    base_prompt = """
# Tech Advocate Prompt

Propose a technical architecture for the system.

## Deliverables

- Architecture diagram
- Technology stack
- Implementation plan
"""
    
    modified_prompt = inject_context_into_prompt(base_prompt, context)
    
    # Verify context is injected
    assert "Previous iteration was REJECTED" in modified_prompt
    assert "horizontal scalability" in modified_prompt
    assert "database migration" in modified_prompt
    
    # Verify original content preserved
    assert "## Deliverables" in modified_prompt
    assert "Architecture diagram" in modified_prompt
    
    # Verify injection order (context before deliverables)
    assert modified_prompt.index("REJECTED") < modified_prompt.index("## Deliverables")
