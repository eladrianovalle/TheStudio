"""Tests for contrarian finding parsing, formatting, and extraction.

Tests cover:
  - parse_findings: single/multiple/missing-Impact/malformed markers
  - format_finding: round-trip of template, example, and formatted output
  - confidence-band parsing (high/medium/low, mixed case)
  - save_findings_json / load_findings_json: round trip and missing file
  - extract_findings_from_run: contrarian-only scanning
  - CONTRARIAN_MANDATE carries the FINDING emit instruction
"""
from findings import (
    FINDING_BLOCK_EXAMPLE,
    FINDING_BLOCK_TEMPLATE,
    Finding,
    extract_findings_from_run,
    format_finding,
    load_findings_json,
    parse_findings,
    save_findings_json,
)


# ---------------------------------------------------------------------------
# Sample finding text blocks (blockquote format)
# ---------------------------------------------------------------------------

SINGLE_MEDIUM = """\
Some preamble text.

> **FINDING [confidence: medium]:** The retry loop never backs off between attempts.
> **Quote:** `worker.py:88` — "for attempt in range(retries): call()"
> **Impact:** A flapping dependency turns into a tight hammering loop.

Some trailing text.
"""

MULTI_CONFIDENCE = """\
> **FINDING [confidence: low]:** Naming feels inconsistent across modules.
> **Quote:** `util.py:12` — "def do_thing()"
> **Impact:** Minor readability cost.

> **FINDING [confidence: high]:** The token is logged in plaintext.
> **Quote:** `auth.py:40` — "log.info(f'token={token}')"
> **Impact:** Secrets leak into shared log storage.

> **FINDING [confidence: medium]:** No timeout on the outbound call.
> **Quote:** `client.py:5` — "requests.get(url)"
> **Impact:** A hung upstream stalls every worker.
"""

MISSING_IMPACT = """\
> **FINDING [confidence: high]:** Off-by-one in the slice bound.
> **Quote:** `pager.py:22` — "items[start:end+1]"
"""

EXTRA_WHITESPACE = """\
> **FINDING [confidence:  medium ]:**   The cache key ignores the tenant id.
> **Quote:**    `cache.py:9` — "key = f'user:{user_id}'"
> **Impact:**  Cross-tenant cache collisions.
"""

# Alternate format: flaw inside the bold markers (what agents naturally produce).
# Leading prose forces the block to match mid-document, so the parser genuinely
# needs re.MULTILINE rather than an accidental match at string start.
ALT_FORMAT_INSIDE_BOLD = """\
Preamble prose before the finding.

> **FINDING [confidence: high]: The migration drops the column before copying it.**
> **Quote:** `migrate.py:30` — "drop_column('email'); copy_email()"
> **Impact:** Irreversible data loss on deploy.
"""

# Mixed-case tag
MIXED_CASE_TAG = """\
> **finding [CONFIDENCE: Medium]:** Pagination resets on every filter change.
> **Quote:** `list.py:14` — "page = 1"
> **Impact:** Users lose their place in long lists.
"""

# Malformed: no blockquote prefix — should not be parsed
MALFORMED_NO_BLOCKQUOTE = """\
**FINDING [confidence: high]:** Orphan finding without blockquote prefix
**Quote:** `x.py:1` — "code"
**Impact:** Nothing
"""


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

class TestParseFindings:
    """Tests for parse_findings()."""

    def test_parse_single_medium(self):
        results = parse_findings(SINGLE_MEDIUM)

        assert len(results) == 1
        f = results[0]
        assert f.confidence == "medium"
        assert "never backs off" in f.flaw
        assert "worker.py:88" in f.quote
        assert "hammering loop" in f.impact

    def test_parse_multiple_in_document_order(self):
        results = parse_findings(MULTI_CONFIDENCE)

        assert len(results) == 3
        assert [f.confidence for f in results] == ["low", "high", "medium"]

    def test_parse_missing_impact_field(self):
        results = parse_findings(MISSING_IMPACT)

        assert len(results) == 1
        f = results[0]
        assert f.confidence == "high"
        assert "Off-by-one" in f.flaw
        assert "pager.py:22" in f.quote
        assert f.impact == ""

    def test_parse_extra_whitespace(self):
        results = parse_findings(EXTRA_WHITESPACE)

        assert len(results) == 1
        f = results[0]
        assert f.confidence == "medium"
        assert "tenant id" in f.flaw
        assert "cache.py:9" in f.quote
        assert "collisions" in f.impact

    def test_parse_alt_format_flaw_inside_bold(self):
        results = parse_findings(ALT_FORMAT_INSIDE_BOLD)

        assert len(results) == 1
        f = results[0]
        assert f.confidence == "high"
        assert "drops the column" in f.flaw
        assert "migrate.py:30" in f.quote

    def test_parse_mixed_case_tag(self):
        results = parse_findings(MIXED_CASE_TAG)

        assert len(results) == 1
        assert results[0].confidence == "medium"

    def test_parse_missing_quote_field(self):
        """A finding with no Quote line parses with an empty quote string."""
        text = (
            "> **FINDING [confidence: low]:** Something feels off in the layout.\n"
            "> **Impact:** Minor visual glitch.\n"
        )
        results = parse_findings(text)
        assert len(results) == 1
        assert results[0].quote == ""
        assert "visual glitch" in results[0].impact

    def test_parse_no_findings(self):
        assert parse_findings("Just a normal document with no markers.") == []

    def test_parse_empty_string(self):
        assert parse_findings("") == []

    def test_parse_malformed_no_blockquote(self):
        assert parse_findings(MALFORMED_NO_BLOCKQUOTE) == []

    def test_source_file_attribution(self):
        results = parse_findings(SINGLE_MEDIUM, source_file="contrarian--design--01.md")
        assert results[0].source_file == "contrarian--design--01.md"

    def test_source_file_default_none(self):
        results = parse_findings(SINGLE_MEDIUM)
        assert results[0].source_file is None

    def test_verdict_fields_default_none(self):
        """parse leaves the Unit 2 placeholder fields unset."""
        f = parse_findings(SINGLE_MEDIUM)[0]
        assert f.verdict is None
        assert f.verified_confidence is None


# ---------------------------------------------------------------------------
# Format tests
# ---------------------------------------------------------------------------

class TestFormatFinding:
    """Tests for format_finding()."""

    def test_format_round_trip(self):
        original = parse_findings(SINGLE_MEDIUM)
        assert len(original) == 1

        formatted = format_finding(original[0])
        reparsed = parse_findings(formatted + "\n")

        assert len(reparsed) == 1
        assert reparsed[0].confidence == original[0].confidence
        assert reparsed[0].flaw == original[0].flaw
        assert reparsed[0].quote == original[0].quote
        assert reparsed[0].impact == original[0].impact

    def test_format_omits_impact_when_empty(self):
        f = Finding(confidence="high", flaw="Bug", quote="`x.py:1` — \"code\"", impact="")
        rendered = format_finding(f)
        assert "Impact" not in rendered
        reparsed = parse_findings(rendered + "\n")
        assert len(reparsed) == 1
        assert reparsed[0].impact == ""


# ---------------------------------------------------------------------------
# Canonical contract guard: emit format and parse format share one definition.
# ---------------------------------------------------------------------------

def test_canonical_example_parses():
    """The shared FINDING_BLOCK_EXAMPLE must parse into exactly one finding."""
    findings = parse_findings(FINDING_BLOCK_EXAMPLE)
    assert len(findings) == 1
    f = findings[0]
    assert f.confidence == "medium"
    assert "backs off" in f.flaw
    assert "worker.py:88" in f.quote
    assert f.impact


def test_canonical_template_parses():
    """The placeholder template is structurally valid too (parses as one block)."""
    findings = parse_findings(FINDING_BLOCK_TEMPLATE)
    assert len(findings) == 1
    f = findings[0]
    assert f.confidence == "medium"
    # All three fields of the template must parse, so a stray edit to the Quote
    # or Impact line of the canonical block fails loudly instead of silently.
    assert f.flaw
    assert "path/to/file.py:42" in f.quote
    assert f.impact


# ---------------------------------------------------------------------------
# Run extraction tests
# ---------------------------------------------------------------------------

class TestExtractFindingsFromRun:
    """Tests for extract_findings_from_run()."""

    def _write_file(self, directory, name, content):
        filepath = directory / name
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_extract_from_contrarian_files(self, tmp_path):
        run_dir = tmp_path / "run_studio_20260716_100000"
        run_dir.mkdir()

        self._write_file(run_dir, "contrarian_1.md", SINGLE_MEDIUM)
        self._write_file(run_dir, "contrarian--design--01.md", MISSING_IMPACT)

        results = extract_findings_from_run(run_dir)

        assert len(results) == 2
        sources = {f.source_file for f in results}
        assert "contrarian_1.md" in sources
        assert "contrarian--design--01.md" in sources

    def test_extract_ignores_advocate_files(self, tmp_path):
        """Findings come only from the contrarian; advocate files are skipped."""
        run_dir = tmp_path / "run_studio_20260716_100000"
        run_dir.mkdir()

        self._write_file(run_dir, "advocate_1.md", SINGLE_MEDIUM)
        self._write_file(run_dir, "contrarian_1.md", MISSING_IMPACT)

        results = extract_findings_from_run(run_dir)

        assert len(results) == 1
        assert results[0].source_file == "contrarian_1.md"

    def test_extract_from_empty_run_directory(self, tmp_path):
        run_dir = tmp_path / "run_studio_20260716_100000"
        run_dir.mkdir()
        assert extract_findings_from_run(run_dir) == []

    def test_extract_missing_directory(self, tmp_path):
        assert extract_findings_from_run(tmp_path / "does_not_exist") == []


# ---------------------------------------------------------------------------
# Save / load JSON tests
# ---------------------------------------------------------------------------

class TestSaveLoadFindingsJson:
    """Tests for save_findings_json() and load_findings_json()."""

    def test_save_and_load_round_trip(self, tmp_path):
        findings = [
            Finding(
                confidence="medium",
                flaw="No timeout on the call.",
                quote="`client.py:5` — \"requests.get(url)\"",
                impact="A hung upstream stalls every worker.",
                source_file="contrarian_1.md",
            ),
            Finding(
                confidence="high",
                flaw="Token logged in plaintext.",
                quote="`auth.py:40` — \"log.info(token)\"",
                impact="Secrets leak.",
            ),
        ]
        save_findings_json(tmp_path, findings)
        loaded = load_findings_json(tmp_path)

        assert len(loaded) == 2
        assert loaded[0].confidence == "medium"
        assert loaded[0].flaw == "No timeout on the call."
        assert loaded[0].source_file == "contrarian_1.md"
        assert loaded[1].confidence == "high"
        assert loaded[1].source_file is None

    def test_save_preserves_verifier_fields(self, tmp_path):
        """verdict / verified_confidence persist for the Unit 2 write-back."""
        findings = [
            Finding(
                confidence="medium",
                flaw="Flaw",
                quote="`x.py:1` — \"code\"",
                impact="Breaks",
                verdict="confirmed",
                verified_confidence="high",
            ),
        ]
        save_findings_json(tmp_path, findings)
        loaded = load_findings_json(tmp_path)

        assert loaded[0].verdict == "confirmed"
        assert loaded[0].verified_confidence == "high"

    def test_load_missing_file(self, tmp_path):
        assert load_findings_json(tmp_path) == []

    def test_load_without_verifier_fields(self, tmp_path):
        """Old JSON without verdict/verified_confidence loads with None."""
        import json
        old_data = [
            {
                "confidence": "low",
                "flaw": "Old finding",
                "quote": "`x.py:1` — \"code\"",
                "impact": "Something",
                "source_file": None,
            }
        ]
        (tmp_path / "findings.json").write_text(
            json.dumps(old_data, indent=2), encoding="utf-8"
        )
        loaded = load_findings_json(tmp_path)

        assert len(loaded) == 1
        assert loaded[0].verdict is None
        assert loaded[0].verified_confidence is None


# ---------------------------------------------------------------------------
# Contrarian mandate carries the emit instruction
# ---------------------------------------------------------------------------

def test_contrarian_mandate_contains_finding_emit_instruction():
    """CONTRARIAN_MANDATE must tell the contrarian to emit FINDING blocks."""
    from scopes import CONTRARIAN_MANDATE

    text = "\n".join(CONTRARIAN_MANDATE)
    assert "FINDING block" in text
    # The canonical block itself is embedded, so the emit and parse formats
    # cannot silently drift apart.
    assert "**FINDING [confidence: medium]:**" in text
