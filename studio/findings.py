"""
Contrarian finding parsing and formatting for Studio runs.

The contrarian flags each flaw it raises as a machine-readable FINDING block,
mirroring how decision_points.py captures inline decision points. The format is
a markdown blockquote — readable by humans, AI agents, and any assistant that
handles standard markdown — so a finding can travel from the contrarian's prose
into findings.json and back without losing its shape.

Example finding in contrarian output::

    > **FINDING [confidence: medium]:** The retry loop never backs off.
    > **Quote:** `worker.py:88` — "for attempt in range(retries): call()"
    > **Impact:** A flapping dependency turns into a tight hammering loop.

Mostly a pure function library. The exceptions touch the filesystem:
extract_findings_from_run reads a run directory, and
save_findings_json/load_findings_json write and read findings.json.
"""
from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# --- Canonical emit format (single source of truth) --------------------------
# The contrarian is TOLD to emit this exact blockquote shape, and parse_findings
# READS it back. scopes.py imports FINDING_BLOCK_TEMPLATE into the contrarian's
# instructions instead of hand-writing the format, so "what we ask the contrarian
# to emit" and "what we parse" cannot silently drift apart: the failure mode
# where a doc tweak quietly makes every extraction return nothing. The round-trip
# test in tests/test_findings.py parses both of these (and the output of
# format_finding) to prove they stay in sync.
FINDING_BLOCK_TEMPLATE = (
    "> **FINDING [confidence: medium]:** [the flaw, one line]\n"
    "> **Quote:** `path/to/file.py:42` — \"[the exact text/claim being critiqued]\"\n"
    "> **Impact:** [what breaks if it is real]"
)

FINDING_BLOCK_EXAMPLE = (
    "> **FINDING [confidence: medium]:** The retry loop never backs off between attempts.\n"
    "> **Quote:** `worker.py:88` — \"for attempt in range(retries): call()\"\n"
    "> **Impact:** A flapping dependency turns into a tight hammering loop that makes the outage worse."
)

# Regex to capture a finding blockquote.
# Matches lines starting with "> " where the first line has
# **FINDING [confidence: high|medium|low]:. Handles the two variants agents
# produce, exactly like the DECISION parser:
#   > **FINDING [confidence: medium]:** flaw text     (canonical: colon outside bold)
#   > **FINDING [confidence: medium]: flaw text**      (natural: flaw inside bold)
# and continues as long as lines start with "> ".
_BLOCK_RE = re.compile(
    r"^> \*\*FINDING \[confidence:\s*(high|medium|low)\s*\]:\*\*\s*(.+)\n"
    r"((?:> .+\n?)*)",
    re.MULTILINE | re.IGNORECASE,
)
_BLOCK_RE_ALT = re.compile(
    r"^> \*\*FINDING \[confidence:\s*(high|medium|low)\s*\]:\s*(.+?)\*\*\s*\n"
    r"((?:> .+\n?)*)",
    re.MULTILINE | re.IGNORECASE,
)

# Field extractors inside blockquote body lines (after stripping "> " prefix).
_QUOTE_RE = re.compile(r"\*\*Quote:\*\*\s*(.+)", re.IGNORECASE)
_IMPACT_RE = re.compile(r"\*\*Impact:\*\*\s*(.+)", re.IGNORECASE)


@dataclass
class Finding:
    """A single contrarian finding extracted from agent output.

    verdict and verified_confidence are placeholders the independent verifier
    (Unit 2) fills in later; parse leaves them unset.
    """

    confidence: str  # high, medium, or low
    flaw: str
    quote: str
    impact: str
    source_file: Optional[str] = field(default=None)
    verdict: Optional[str] = field(default=None)
    verified_confidence: Optional[str] = field(default=None)


def parse_findings(text: str, source_file: str | None = None) -> list[Finding]:
    """Parse all findings from contrarian output text.

    Handles extra whitespace, a missing Impact field, and mixed-case tags.
    Returns findings in the order they appear in the text.
    """
    results: list[Finding] = []
    seen_spans: set[tuple[int, int]] = set()

    matches = sorted(
        itertools.chain(_BLOCK_RE.finditer(text), _BLOCK_RE_ALT.finditer(text)),
        key=lambda m: m.start(),
    )
    for match in matches:
        span = (match.start(), match.end())
        if span in seen_spans:
            continue
        seen_spans.add(span)
        confidence = match.group(1).lower()
        flaw = match.group(2).strip()
        body_lines = match.group(3)

        # Strip "> " prefix from body lines
        body = "\n".join(
            line[2:] if line.startswith("> ") else line
            for line in body_lines.splitlines()
        )

        quote_m = _QUOTE_RE.search(body)
        quote = quote_m.group(1).strip() if quote_m else ""

        impact_m = _IMPACT_RE.search(body)
        impact = impact_m.group(1).strip() if impact_m else ""

        results.append(
            Finding(
                confidence=confidence,
                flaw=flaw,
                quote=quote,
                impact=impact,
                source_file=source_file,
            )
        )

    return results


def format_finding(f: Finding) -> str:
    """Render a Finding back to the standard blockquote format."""
    lines = [
        f"> **FINDING [confidence: {f.confidence}]:** {f.flaw}",
        f"> **Quote:** {f.quote}",
    ]
    if f.impact:
        lines.append(f"> **Impact:** {f.impact}")
    return "\n".join(lines)


def extract_findings_from_run(run_dir: Path) -> list[Finding]:
    """Scan contrarian output files in a run directory for findings.

    Reads contrarian_*.md and their studio variants (contrarian--role--NN.md,
    contrarian--role--S1-NN.md). Findings come only from the contrarian, so
    advocate files are skipped. Annotates each Finding with its source file name.
    """
    results: list[Finding] = []
    run_path = Path(run_dir)

    if not run_path.is_dir():
        return results

    for md_file in sorted(run_path.glob("*.md")):
        name = md_file.name
        # Match simple (contrarian_1.md) and studio (contrarian--role--01.md) names.
        if not name.startswith("contrarian"):
            continue

        text = md_file.read_text(encoding="utf-8")
        findings = parse_findings(text, source_file=name)
        results.extend(findings)

    return results


def save_findings_json(run_dir: Path, findings: list[Finding]) -> Path:
    """Save findings to findings.json in the run directory. Returns the path."""
    data = [
        {
            "confidence": f.confidence,
            "flaw": f.flaw,
            "quote": f.quote,
            "impact": f.impact,
            "source_file": f.source_file,
            "verdict": f.verdict,
            "verified_confidence": f.verified_confidence,
        }
        for f in findings
    ]
    path = run_dir / "findings.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_findings_json(run_dir: Path) -> list[Finding]:
    """Load findings from findings.json. Returns empty list if file missing."""
    path = run_dir / "findings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return [
        Finding(
            confidence=d["confidence"],
            flaw=d["flaw"],
            quote=d["quote"],
            impact=d["impact"],
            source_file=d.get("source_file"),
            verdict=d.get("verdict"),
            verified_confidence=d.get("verified_confidence"),
        )
        for d in data
    ]
