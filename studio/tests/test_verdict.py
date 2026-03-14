#!/usr/bin/env python3
"""Tests for extract_verdict() — the core APPROVED/REJECTED decision point."""
from verdict import extract_verdict


def test_approved_verdict():
    """Given text with 'VERDICT: APPROVED', returns 'APPROVED'."""
    text = "After careful review:\n\nVERDICT: APPROVED\n\nThe proposal is solid."
    assert extract_verdict(text) == "APPROVED"


def test_rejected_verdict():
    """Given text with 'VERDICT: REJECTED', returns 'REJECTED'."""
    text = "Several critical issues found.\n\nVERDICT: REJECTED\n\n1. Missing data."
    assert extract_verdict(text) == "REJECTED"


def test_mixed_case_verdict_approved():
    """Given text with verdict in mixed case, returns uppercased result."""
    text = "Verdict: Approved"
    assert extract_verdict(text) == "APPROVED"


def test_mixed_case_verdict_rejected():
    """Given text with verdict keyword in various cases, returns uppercased result."""
    text = "verdict: rejected"
    assert extract_verdict(text) == "REJECTED"


def test_no_verdict_returns_unknown():
    """Given text with no verdict string, returns 'UNKNOWN'."""
    text = "This is a regular document with no decision rendered."
    assert extract_verdict(text) == "UNKNOWN"


def test_multiple_verdicts_first_wins():
    """Given text with multiple verdict strings, the first match wins."""
    text = (
        "Round 1:\nVERDICT: REJECTED\n\n"
        "Round 2:\nVERDICT: APPROVED\n"
    )
    assert extract_verdict(text) == "REJECTED"


def test_verdict_buried_in_markdown():
    """Given text with verdict buried in markdown context, extracts correctly."""
    text = """# Contrarian Response — Tech Phase

## Analysis

The architecture has several concerning aspects that need attention.

### Scalability

The proposed monolith will not scale past 10k concurrent users.

### Security

No mention of authentication or authorization.

## Decision

After weighing all factors:

VERDICT: REJECTED

### Reasons for Rejection

1. Missing horizontal scaling strategy
2. No auth layer defined
3. Unrealistic timeline
"""
    assert extract_verdict(text) == "REJECTED"


def test_empty_string_returns_unknown():
    """Given an empty string, returns 'UNKNOWN'."""
    assert extract_verdict("") == "UNKNOWN"


def test_verdict_with_extra_whitespace():
    """Given verdict with extra whitespace between colon and value, handles correctly."""
    text = "VERDICT:   APPROVED"
    assert extract_verdict(text) == "APPROVED"


def test_verdict_with_tab_whitespace():
    """Given verdict with tab whitespace, handles correctly."""
    text = "VERDICT:\tREJECTED"
    assert extract_verdict(text) == "REJECTED"


def test_verdict_word_without_colon_ignored():
    """Given text mentioning APPROVED/REJECTED without 'VERDICT:' prefix, returns UNKNOWN."""
    text = "The proposal was APPROVED by the committee in the last meeting."
    assert extract_verdict(text) == "UNKNOWN"
