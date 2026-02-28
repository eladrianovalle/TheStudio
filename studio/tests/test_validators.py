#!/usr/bin/env python3
"""Tests for document and code validators."""
import tempfile
from pathlib import Path

import pytest

from validators.document_validator import DocumentValidator, ValidationResult
from validators.code_validator import CodeValidator, CheckResult


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def doc_validator():
    """Create DocumentValidator instance."""
    return DocumentValidator()


@pytest.fixture
def code_validator():
    """Create CodeValidator instance."""
    return CodeValidator(timeout=5)


# Document Validator Tests

def test_validation_result_has_issues():
    """Test ValidationResult.has_issues property."""
    result1 = ValidationResult(passed=True, issues=[], warnings=[])
    assert not result1.has_issues
    
    result2 = ValidationResult(passed=False, issues=["error"], warnings=[])
    assert result2.has_issues
    
    result3 = ValidationResult(passed=True, issues=[], warnings=["warning"])
    assert result3.has_issues


def test_check_completeness_missing_file(doc_validator, temp_dir):
    """Test completeness check with missing file."""
    result = doc_validator.check_completeness(
        temp_dir / "nonexistent.md",
        ["Section 1", "Section 2"]
    )
    
    assert not result.passed
    assert "not found" in result.issues[0].lower()


def test_check_completeness_all_sections_present(doc_validator, temp_dir):
    """Test completeness check with all sections present."""
    doc_path = temp_dir / "test.md"
    doc_path.write_text("""
# Document Title

## Section 1

Content here.

## Section 2

More content.

## Section 3

Even more content.
""")
    
    result = doc_validator.check_completeness(
        doc_path,
        ["Section 1", "Section 2", "Section 3"]
    )
    
    assert result.passed
    assert len(result.issues) == 0


def test_check_completeness_missing_sections(doc_validator, temp_dir):
    """Test completeness check with missing sections."""
    doc_path = temp_dir / "test.md"
    doc_path.write_text("""
# Document Title

## Section 1

Content here.
""")
    
    result = doc_validator.check_completeness(
        doc_path,
        ["Section 1", "Section 2", "Section 3"]
    )
    
    assert not result.passed
    assert "Section 2" in result.issues
    assert "Section 3" in result.issues


def test_check_completeness_partial_match(doc_validator, temp_dir):
    """Test completeness check with partial section name matches."""
    doc_path = temp_dir / "test.md"
    doc_path.write_text("""
# Document Title

## Market Analysis Overview

Content here.

## Competitive Landscape

More content.
""")
    
    result = doc_validator.check_completeness(
        doc_path,
        ["Market Analysis", "Competitive"]
    )
    
    assert result.passed


def test_check_consistency_missing_files(doc_validator, temp_dir):
    """Test consistency check with missing files."""
    result = doc_validator.check_consistency(
        temp_dir / "advocate.md",
        temp_dir / "contrarian.md"
    )
    
    assert not result.passed
    assert len(result.issues) > 0


def test_check_consistency_addresses_points(doc_validator, temp_dir):
    """Test consistency check when contrarian addresses advocate points."""
    advocate_path = temp_dir / "advocate.md"
    advocate_path.write_text("""
# Advocate Proposal

## Key Points

1. **Market opportunity** is significant with $500M TAM
2. **Technical feasibility** is proven with existing libraries
3. **Go-to-market** strategy leverages social media

We should proceed with this approach.
""")
    
    contrarian_path = temp_dir / "contrarian.md"
    contrarian_path.write_text("""
# Contrarian Response

I've reviewed the proposal and have concerns:

The **market opportunity** claim lacks validation data. The $500M TAM needs supporting research.

**Technical feasibility** is overstated - the libraries mentioned are deprecated.

The **go-to-market** strategy is too vague and doesn't address customer acquisition costs.

VERDICT: REJECTED
""")
    
    result = doc_validator.check_consistency(advocate_path, contrarian_path)
    
    # Should pass (always passes, uses warnings)
    assert result.passed
    # Should have few or no warnings since points are addressed
    assert len(result.warnings) <= 3


def test_check_format_valid_document(doc_validator, temp_dir):
    """Test format check with valid document."""
    doc_path = temp_dir / "test.md"
    doc_path.write_text("""
# Document Title

This is a well-formatted document with proper structure.

## Section 1

- Bullet point 1
- Bullet point 2

## Section 2

1. Numbered item 1
2. Numbered item 2

This document has sufficient content and proper formatting.
""")
    
    result = doc_validator.check_format(doc_path)
    
    assert result.passed
    assert len(result.issues) == 0


def test_check_format_too_short(doc_validator, temp_dir):
    """Test format check with too-short document."""
    doc_path = temp_dir / "test.md"
    doc_path.write_text("# Title\n\nShort.")
    
    result = doc_validator.check_format(doc_path)
    
    assert not result.passed
    assert any("too short" in issue.lower() for issue in result.issues)


def test_check_format_missing_title(doc_validator, temp_dir):
    """Test format check with missing title."""
    doc_path = temp_dir / "test.md"
    doc_path.write_text("""
This document has no title header.

It has content but lacks proper structure.
This is enough content to pass the length check but should warn about missing title.
""")
    
    result = doc_validator.check_format(doc_path)
    
    assert any("title" in warning.lower() for warning in result.warnings)


def test_check_format_bad_list_formatting(doc_validator, temp_dir):
    """Test format check with improperly formatted lists."""
    doc_path = temp_dir / "test.md"
    doc_path.write_text("""
# Document Title

Bad numbered list:
1.Missing space after period
2.Another bad item

Bad bullet list:
-Missing space after dash
*Missing space after asterisk

This document has enough content but poor list formatting.
""")
    
    result = doc_validator.check_format(doc_path)
    
    assert len(result.warnings) > 0


def test_check_verdict_approved(doc_validator, temp_dir):
    """Test verdict check with APPROVED verdict."""
    contrarian_path = temp_dir / "contrarian.md"
    contrarian_path.write_text("""
# Contrarian Response

After careful review, the proposal is solid.

VERDICT: APPROVED

Proceed with implementation.
""")
    
    result = doc_validator.check_verdict(contrarian_path)
    
    assert result.passed
    assert len(result.issues) == 0


def test_check_verdict_rejected_with_reasons(doc_validator, temp_dir):
    """Test verdict check with REJECTED verdict and reasons."""
    contrarian_path = temp_dir / "contrarian.md"
    contrarian_path.write_text("""
# Contrarian Response

VERDICT: REJECTED

Reasons:
1. Missing market validation
2. Unclear technical approach
3. No risk mitigation plan
""")
    
    result = doc_validator.check_verdict(contrarian_path)
    
    assert result.passed
    assert len(result.issues) == 0


def test_check_verdict_rejected_without_reasons(doc_validator, temp_dir):
    """Test verdict check with REJECTED verdict but no reasons."""
    contrarian_path = temp_dir / "contrarian.md"
    contrarian_path.write_text("""
# Contrarian Response

VERDICT: REJECTED

This proposal needs more work.
""")
    
    result = doc_validator.check_verdict(contrarian_path)
    
    assert result.passed  # Still passes
    assert len(result.warnings) > 0  # But has warning


def test_check_verdict_missing(doc_validator, temp_dir):
    """Test verdict check with missing verdict."""
    contrarian_path = temp_dir / "contrarian.md"
    contrarian_path.write_text("""
# Contrarian Response

This document has no verdict statement.
""")
    
    result = doc_validator.check_verdict(contrarian_path)
    
    assert not result.passed
    assert any("verdict" in issue.lower() for issue in result.issues)


def test_validate_run_complete(doc_validator, temp_dir):
    """Test full run validation with complete artifacts."""
    # Create advocate and contrarian files
    (temp_dir / "advocate_1.md").write_text("""
# Advocate Proposal

## Market Opportunity

Significant opportunity exists.

## Technical Approach

We will use proven technologies.

## Implementation Plan

Three-phase rollout over 6 months.
""")
    
    (temp_dir / "contrarian_1.md").write_text("""
# Contrarian Response

The **market opportunity** needs more validation.

The **technical approach** is sound but needs detail.

The **implementation plan** timeline is aggressive.

VERDICT: REJECTED

Reasons:
1. Need market research data
2. Need detailed technical spec
""")
    
    result = doc_validator.validate_run(temp_dir, "market")
    
    # Should have some warnings but overall structure is valid
    assert isinstance(result, ValidationResult)


def test_validate_run_missing_files(doc_validator, temp_dir):
    """Test run validation with missing files."""
    result = doc_validator.validate_run(temp_dir, "market")
    
    assert not result.passed
    assert any("advocate" in issue.lower() for issue in result.issues)
    assert any("contrarian" in issue.lower() for issue in result.issues)


# Code Validator Tests

def test_check_result_summary():
    """Test CheckResult.summary property."""
    result1 = CheckResult(check_name="pytest", passed=True, output="All tests passed")
    assert "✓ PASSED" in result1.summary
    assert "pytest" in result1.summary
    
    result2 = CheckResult(check_name="mypy", passed=False, output="Type errors found")
    assert "✗ FAILED" in result2.summary
    assert "mypy" in result2.summary


def test_run_check_success(code_validator, temp_dir):
    """Test running a successful check."""
    result = code_validator.run_check(["echo", "test"], cwd=temp_dir)
    
    assert result.passed
    assert result.check_name == "echo"
    assert "test" in result.output


def test_run_check_failure(code_validator, temp_dir):
    """Test running a failing check."""
    result = code_validator.run_check(["false"], cwd=temp_dir)
    
    assert not result.passed
    assert result.check_name == "false"


def test_run_check_not_found(code_validator, temp_dir):
    """Test running a check with command not found."""
    result = code_validator.run_check(["nonexistent_command_xyz"], cwd=temp_dir)
    
    assert not result.passed
    assert "not found" in result.output.lower()


def test_run_check_timeout(temp_dir):
    """Test check timeout."""
    validator = CodeValidator(timeout=1)
    result = validator.run_check(["sleep", "5"], cwd=temp_dir)
    
    assert not result.passed
    assert "timed out" in result.output.lower()


def test_format_results(code_validator):
    """Test formatting check results."""
    results = [
        CheckResult(check_name="pytest", passed=True, output="5 passed", duration_seconds=1.2),
        CheckResult(check_name="mypy", passed=False, output="Error: type mismatch", duration_seconds=0.5),
    ]
    
    formatted = code_validator.format_results(results)
    
    assert "Code Validation Results" in formatted
    assert "1/2 checks passed" in formatted
    assert "pytest" in formatted
    assert "mypy" in formatted
    assert "✓ PASSED" in formatted
    assert "✗ FAILED" in formatted


def test_validate_implementation_unknown_check(code_validator, temp_dir):
    """Test validation with unknown check name."""
    results = code_validator.validate_implementation(temp_dir, checks=["unknown_check"])
    
    assert len(results) == 1
    assert not results[0].passed
    assert "unknown" in results[0].output.lower()


def test_extract_key_points(doc_validator):
    """Test extracting key points from document."""
    content = """
# Document

## Key Points

1. First important point about market size
2. Second important point about competition

**Bold concept** that matters.

- Bullet point with substantial content here
- Another bullet with enough text to matter

Some regular text that shouldn't be extracted.
"""
    
    points = doc_validator._extract_key_points(content)
    
    assert len(points) > 0
    assert any("market size" in p.lower() for p in points)
    assert any("bold concept" in p.lower() for p in points)


def test_is_addressed(doc_validator):
    """Test checking if point is addressed."""
    point = "Market opportunity is significant with $500M TAM"
    
    contrarian_content1 = """
The market opportunity claim needs validation. The $500M TAM figure
requires supporting research and competitive analysis.
"""
    
    contrarian_content2 = """
The technical approach is sound but the timeline is too aggressive.
We need to consider resource constraints.
"""
    
    # Should be addressed in content1 (has "market" and "opportunity")
    assert doc_validator._is_addressed(point, contrarian_content1)
    
    # Should not be addressed in content2 (missing key terms)
    assert not doc_validator._is_addressed(point, contrarian_content2)
