#!/usr/bin/env python3
"""Tests for the /message-draft linter.

Each test is a draft a person might really produce, and what the linter must say about it.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from message_lint import CHARACTER_CEILING, PLATFORMS, check_draft

LINTER = Path(__file__).resolve().parent.parent / "message_lint.py"

GOOD_DRAFT = """Point: the nightly build is green again after the cache fix.
Ask: none
---8<---
The nightly build is green again. The cache key now includes the lockfile, so a stale cache can't mask a dependency bump.

• Three green nights in a row since the fix
• Build time is back to 6 minutes
https://example.com/builds/nightly
"""


def draft(message: str, header: str = "Point: one thing.\nAsk: none\n") -> str:
    return f"{header}---8<---\n{message}"


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_short_point_first_draft_is_clean_everywhere(platform):
    assert check_draft(GOOD_DRAFT, platform) == []


def test_a_draft_with_no_point_or_ask_is_flagged():
    issues = check_draft("Just the message, no header.\n", "plain")
    assert any("Point:" in issue for issue in issues)


def test_a_header_missing_the_ask_is_flagged():
    issues = check_draft(draft("Short message.\n", header="Point: one thing.\n"), "plain")
    assert any("Ask:" in issue for issue in issues)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_message_too_long_for_one_discord_message_fails_on_every_platform(platform):
    # Short lines and no filler, so the only thing wrong is the length.
    long_message = "\n".join(["Short line of words here."] * 100)
    assert len(long_message) > CHARACTER_CEILING
    issues = check_draft(draft(long_message), platform)
    assert any("characters" in issue and "Discord" in issue for issue in issues)


def test_a_rambling_message_is_flagged_by_word_count():
    issues = check_draft(draft("word " * 151 + "\n"), "github")
    assert any("151 words" in issue for issue in issues)


def test_slack_rejects_markdown_that_does_not_survive_the_paste():
    message = "**Bold** lead.\n\n# Heading\n\n- dash bullet\n\nSee [the doc](https://example.com).\n"
    issues = check_draft(draft(message), "slack")
    assert "**bold** (Slack uses *bold*)" in issues
    assert "# heading (use a short bold label)" in issues
    assert "dash bullet (use •)" in issues
    assert "[text](url) link (paste the bare URL)" in issues


def test_github_accepts_the_same_markdown():
    message = "**Bold** lead.\n\n- dash bullet\n\nSee [the doc](https://example.com).\n"
    assert check_draft(draft(message), "github") == []


def test_discord_accepts_markdown_but_not_tables():
    assert check_draft(draft("**Bold** lead.\n\n- one\n- two\n"), "discord") == []
    issues = check_draft(draft("Lead.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"), "discord")
    assert "table (pastes as pipes)" in issues


def test_plain_text_rejects_backticks_and_bold():
    issues = check_draft(draft("Run `make` and **then** check.\n"), "plain")
    assert "`code` (plain text shows the backticks)" in issues
    assert "**bold** (plain text shows the asterisks)" in issues


def test_formatting_inside_a_code_block_is_not_flagged():
    message = "Lead line.\n\n```\n| not | a table |\n# not a heading\n```\n"
    assert check_draft(draft(message), "slack") == []


def test_more_than_three_bullets_is_flagged():
    message = "Lead.\n\n• one\n• two\n• three\n• four\n"
    issues = check_draft(draft(message), "slack")
    assert any("4 bullets" in issue for issue in issues)


def test_opening_with_a_label_instead_of_the_lead_is_flagged():
    issues = check_draft(draft("*Summary*\nThe lead comes too late.\n"), "slack")
    assert "opens with a label, not the lead" in issues


def test_filler_phrases_are_flagged():
    issues = check_draft(draft("Just wanted to say we leverage the cache now. I hope this helps!\n"), "plain")
    assert 'filler: "just wanted to"' in issues
    assert 'filler: "leverage"' in issues
    assert 'filler: "i hope this helps"' in issues


def test_a_word_containing_a_filler_word_is_not_flagged():
    # "robustly" is not "robust"; only whole words and phrases count.
    assert check_draft(draft("It now retries robustly.\n"), "plain") == []


def test_more_than_one_em_dash_is_flagged():
    issues = check_draft(draft("Lead — with a dash — and another — here.\n"), "plain")
    assert any("3 em dashes" in issue for issue in issues)


def test_the_command_line_exits_1_on_issues_and_0_when_clean(tmp_path):
    clean = tmp_path / "clean.txt"
    clean.write_text(GOOD_DRAFT, encoding="utf-8")
    messy = tmp_path / "messy.txt"
    messy.write_text("No header at all.\n", encoding="utf-8")

    clean_run = subprocess.run([sys.executable, str(LINTER), str(clean), "--to", "slack"], capture_output=True, text=True)
    messy_run = subprocess.run([sys.executable, str(LINTER), str(messy)], capture_output=True, text=True)

    assert clean_run.returncode == 0, clean_run.stdout
    assert clean_run.stdout.startswith("clean")
    assert messy_run.returncode == 1
    assert messy_run.stdout.startswith("x ")


def test_a_long_paragraph_is_flagged_as_one_to_shorten_not_wrap():
    paragraph = "This sentence keeps going. " * 12
    assert len(paragraph) > 250
    issues = check_draft(draft(paragraph + "\n"), "plain")
    assert any("paragraph over 250 characters" in issue and "don't wrap" in issue for issue in issues)


def test_a_header_with_no_message_after_the_separator_is_flagged():
    issues = check_draft("Point: one thing.\nAsk: none\n---8<---\n", "plain")
    assert "no message after the ---8<--- line" in issues


def test_an_empty_point_is_flagged_even_with_a_line_after_it():
    issues = check_draft("Point:\nAsk: none\n---8<---\nReady.\n", "plain")
    assert any("Point:" in issue for issue in issues)


def test_a_separator_inside_a_header_line_does_not_count():
    # The copy command looks for the separator on a line of its own, so this copies nothing.
    issues = check_draft("Point: Ready.\nAsk: none---8<---\nReady.\n", "plain")
    assert any("Point:" in issue for issue in issues)


def test_bold_bullets_are_bullets_not_labels():
    issues = check_draft(draft("Lead.\n\n* **One**\n* **Two**\n* **Three**\n"), "github")
    assert issues == []


def test_a_code_block_still_counts_toward_the_word_and_line_limits():
    message = "Lead.\n\n```\n" + "word " * 151 + "\n```\n"
    issues = check_draft(draft(message), "github")
    assert any("words" in issue for issue in issues)
    assert any("paragraph over 250 characters" in issue for issue in issues)


def test_plain_text_rejects_single_asterisk_and_underscore_emphasis():
    issues = check_draft(draft("This is *really* done and _also_ shipped.\n"), "plain")
    assert "*emphasis* (plain text shows the asterisks)" in issues
    assert "_emphasis_ (plain text shows the underscores)" in issues


def test_plain_text_accepts_asterisks_and_underscores_that_are_not_emphasis():
    message = "Set max_retry_count to 3 * 2 for https://example.com/a_b_c.\n"
    assert check_draft(draft(message), "plain") == []


def test_plain_text_rejects_single_character_underscore_emphasis():
    issues = check_draft(draft("Choose _x_ next.\n"), "plain")
    assert "_emphasis_ (plain text shows the underscores)" in issues


@pytest.mark.parametrize("platform", ["slack", "plain"])
def test_bare_urls_are_not_read_as_emphasis(platform):
    message = "See https://example.com/_draft_/ and https://example.com/*x*/ for both.\n"
    assert check_draft(draft(message), platform) == []


def test_a_markdown_link_is_still_flagged_with_a_url_inside():
    issues = check_draft(draft("See [the draft](https://example.com/_draft_/).\n"), "plain")
    assert "[text](url) link (paste the bare URL)" in issues


@pytest.mark.parametrize(
    "platform, message, warning",
    [
        ("slack", "See **https://example.com**.\n", "**bold** (Slack uses *bold*)"),
        ("plain", "Run `https://example.com`.\n", "`code` (plain text shows the backticks)"),
        ("plain", "Read _https://example.com_ first.\n", "_emphasis_ (plain text shows the underscores)"),
        ("plain", "| site |https://example.com|\n", "table (pastes as pipes)"),
    ],
)
def test_markup_around_a_url_is_still_flagged(platform, message, warning):
    assert warning in check_draft(draft(message), platform)
