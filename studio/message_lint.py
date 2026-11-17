#!/usr/bin/env python3
"""Check a /message-draft draft before the user pastes and sends it.

A draft file is a header, a ``---8<---`` line, then the message:

    Point: the one takeaway, in one sentence
    Ask: the one action wanted from the reader, or none
    ---8<---
    The message itself.

The checks hold the message to what /message-draft promises: the point and the ask come
first, the message is short enough to read in one pass, it pastes cleanly into the
platform it is going to, and it never exceeds 2,000 characters, which is Discord's limit
for a standard account. That ceiling applies on every platform, so any draft can be
pasted anywhere.

The linter cannot judge the argument. A clean result means the shape is right; the lead
still has to be reread by a person.

Usage:
    python3 message_lint.py <draft file> [--to slack|discord|github|plain]

Exit status is 0 when the draft is clean, 1 when there is something to fix.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

SEPARATOR = "---8<---"
PLATFORMS = ("slack", "discord", "github", "plain")

CHARACTER_CEILING = 2000  # Discord's per-message limit for a standard account
WORD_TARGET = 150
LINE_LENGTH_LIMIT = 250
LABEL_LIMIT = 2
BULLET_LIMIT = 3

# Formatting that does not survive the paste, per platform. Each entry is a pattern and
# what to tell the writer when it matches. GitHub renders all of it, so it has none.
_TABLE = (r"^\s*\|.*\|\s*$", "table (pastes as pipes)")
_HEADING = (r"^\s{0,3}#{1,6}\s", "# heading (use a short bold label)")
_MARKDOWN_LINK = (r"\[[^\]\n]+\]\([^)\n]+\)", "[text](url) link (paste the bare URL)")

PASTE_CHECKS = {
    "slack": [
        _TABLE,
        (r"\*\*[^*\n]+\*\*", "**bold** (Slack uses *bold*)"),
        (r"(?<![\w`])_[^_\n]{2,}_(?![\w`])", "_italic_ (does not render on paste)"),
        _HEADING,
        _MARKDOWN_LINK,
        (r"^\s*[-*+]\s+\S", "dash bullet (use •)"),
        (r"<@U[A-Z0-9]{6,}>", "<@UID> (pastes as text, pings nobody)"),
    ],
    "discord": [
        _TABLE,
    ],
    "github": [],
    "plain": [
        _TABLE,
        (r"\*\*[^*\n]+\*\*", "**bold** (plain text shows the asterisks)"),
        _HEADING,
        _MARKDOWN_LINK,
        (r"`[^`\n]+`", "`code` (plain text shows the backticks)"),
        (r"(?<![\w*])\*[^*\s][^*\n]*\*(?![\w*])", "*emphasis* (plain text shows the asterisks)"),
        (r"(?<![\w`])_[^_\n]+_(?![\w`])", "_emphasis_ (plain text shows the underscores)"),
    ],
}

# Phrases that read as machine-written or as padding. A short list on purpose: each entry
# is something a person would cut on a reread, not a style preference.
FILLER_PHRASES = [
    "i hope this helps",
    "i hope this message finds you",
    "just wanted to",
    "just a quick",
    "great question",
    "it's worth noting",
    "it is worth noting",
    "it's important to note",
    "needless to say",
    "at the end of the day",
    "let me know if you have any questions",
    "feel free to reach out",
    "in summary",
    "to summarize",
    "delve",
    "leverage",
    "utilize",
    "seamless",
    "robust",
]

EM_DASH_LIMIT = 1


def split_draft(text: str) -> Tuple[str, str]:
    """Return the header and the message.

    The separator only counts on a line of its own, since that is the line the copy command
    looks for. With no such line, the whole text is the message.
    """
    lines = text.split("\n")
    if SEPARATOR not in lines:
        return "", text
    at = lines.index(SEPARATOR)
    return "\n".join(lines[:at]), "\n".join(lines[at + 1:])


def without_code_blocks(message: str) -> str:
    return re.sub(r"```.*?```", "", message, flags=re.S)


def without_urls(text: str) -> str:
    """Stand a placeholder in for each URL, so its underscores and asterisks aren't markup."""
    return re.sub(r"https?://[^\s)>]+", "URL", text)


def is_label(line: str) -> bool:
    """A label is a short line that is only bold text, like *Why* or **Why**, not a bullet."""
    return re.fullmatch(r"(\*\*?)[^*\s](?:[^*]*[^*\s])?\1", line.strip()) is not None


def is_bullet(line: str) -> bool:
    return re.match(r"^\s*([-*+•]|\d+[.)])\s+\S", line) is not None and not is_label(line)


def check_header(header: str) -> List[str]:
    has_point = re.search(r"^Point:[ \t]*\S", header, re.M) is not None
    has_ask = re.search(r"^Ask:[ \t]*\S", header, re.M) is not None
    if has_point and has_ask:
        return []
    return [f"header needs Point: and Ask: lines above a {SEPARATOR} line"]


def check_message(message: str, platform: str) -> List[str]:
    issues: List[str] = []

    if not message.strip():
        return [f"no message after the {SEPARATOR} line"]

    if len(message.strip()) > CHARACTER_CEILING:
        issues.append(
            f"{len(message.strip())} characters (over the {CHARACTER_CEILING} that fit "
            "in one Discord message; split it or cut it)"
        )

    prose = without_code_blocks(message)
    for pattern, warning in PASTE_CHECKS[platform]:
        if re.search(pattern, without_urls(prose), re.M):
            issues.append(warning)

    for line in message.splitlines():
        if len(line) > LINE_LENGTH_LIMIT:
            issues.append(
                f"paragraph over {LINE_LENGTH_LIMIT} characters (shorten it, don't wrap it): "
                f"{line[:50]}..."
            )

    lines = [line for line in prose.splitlines() if line.strip()]
    labels = [line for line in lines if is_label(line)]
    if len(labels) > LABEL_LIMIT:
        issues.append(f"{len(labels)} labels (at most {LABEL_LIMIT})")
    if lines and is_label(lines[0]):
        issues.append("opens with a label, not the lead")

    bullets = [line for line in lines if is_bullet(line)]
    if len(bullets) > BULLET_LIMIT:
        issues.append(f"{len(bullets)} bullets (at most {BULLET_LIMIT} pieces of evidence)")

    word_count = len(message.split())
    if word_count > WORD_TARGET:
        issues.append(f"{word_count} words (aim for {WORD_TARGET} or fewer)")

    lowered = prose.lower()
    for phrase in FILLER_PHRASES:
        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            issues.append(f'filler: "{phrase}"')

    em_dashes = prose.count("—")
    if em_dashes > EM_DASH_LIMIT:
        issues.append(f"{em_dashes} em dashes (at most {EM_DASH_LIMIT}; use a period or a comma)")

    return issues


def check_draft(text: str, platform: str) -> List[str]:
    header, message = split_draft(text)
    return check_header(header) + check_message(message, platform)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a /message-draft draft.")
    parser.add_argument("draft", type=Path, help="the draft file")
    parser.add_argument("--to", choices=PLATFORMS, default="plain", help="where it will be pasted")
    args = parser.parse_args(argv)

    issues = check_draft(args.draft.read_text(encoding="utf-8"), args.to)
    if issues:
        print("\n".join(f"x {issue}" for issue in issues))
        return 1
    print("clean (the linter can't judge the argument; reread the lead)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
