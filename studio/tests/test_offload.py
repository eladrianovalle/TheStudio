"""M1 test suite for the /offload feature — studio.offload pure functions."""
import re


from offload import (
    TIER_ALWAYS_INLINE,
    TIER_REFERENCE_OFFLOADABLE,
    classify_sections,
    detect_embedded_constraints,
    evaluate_protocol_run,
    generate_canary_token,
    generate_report,
    score_pointer_strength,
    verify_canary_isolation,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

IDENTITY_SECTION_GAMESTUDIO = """\
## What This Is

TheGameStudio is an **instruction generator** for structured advocate/contrarian \
debates in game development workflows. It produces run directories with instructions \
that an AI assistant (Claude Code, Windsurf/Cascade) executes, then packages results \
as versioned artifacts. There is no AI runtime — all intelligence lives in the \
assistant's execution.
"""

IDENTITY_SECTION_SYNTHETIC = """\
## What This Is

Foo is a REST API for managing widgets.
"""

CLI_BLOCK_GAMESTUDIO = """\
## CLI Commands

```bash
# Run tests (from studio/ directory)
cd studio && python -m pytest tests/ -v

# Run a single test
cd studio && python -m pytest tests/test_run_phase.py::TestClassName::test_name -v

# Prepare a phase run (manual)
python studio/run_phase.py prepare --phase <market|design|tech|studio> --text "description"

# Prepare in question-surfacing mode
python studio/run_phase.py prepare --phase design --text "description" --mode questions

# Finalize a completed run
python studio/run_phase.py finalize --phase <phase> --run-id <run_id> --status completed --verdict APPROVED
```
"""

CLI_BLOCK_SYNTHETIC = """\
## Commands

```bash
npm install
npm test
npm build
npm lint
npm deploy
```
"""

MODULE_CATALOG_GAMESTUDIO = """\
## Architecture

All source lives under `studio/`.

### Core modules (all in `studio/`)

- **`run_phase.py`** — Primary entrypoint: prepare, finalize, validate.
- **`cleanup.py`** — TTL-based and budget-based run artifact cleanup.
- **`scopes.py`** — Three-tier scope system (alignment / depth / polish).
- **`clarity.py`** — Per-topic Clarity Score tracking.
"""

MODULE_CATALOG_SYNTHETIC = """\
## Modules

- **`app.py`** — Main entry
- **`db.py`** — Database
- **`auth.py`** — Auth
- **`api.py`** — Routes
"""

CONVENTIONS_GAMESTUDIO = """\
## Important Conventions

- **Python 3.10+** required. Uses `tomllib` (3.11+) with `tomli` fallback.
- **No heavy dependencies** — keep `run_phase.py` small and bash-friendly.
- **Never** commit `studio/output/` or `studio/knowledge/`.
"""

CONVENTIONS_SYNTHETIC = """\
## Conventions

- **Never** commit secrets
- **Always** run tests
- Python 3.10+
"""


# =========================================================================
# CLASS — Section classifier tests
# =========================================================================


class TestClassifySectionsIdentity:
    """CLASS-01: Identity sections must be classified as always-inline."""

    def test_class01a_gamestudio_identity(self):
        """Given TheGameStudio's 'What This Is' text,
        When classify_sections is called,
        Then the section tier is 'always-inline'.
        """
        sections = classify_sections(IDENTITY_SECTION_GAMESTUDIO)
        assert len(sections) >= 1
        identity = sections[0]
        assert identity["tier"] == TIER_ALWAYS_INLINE
        assert "What This Is" in identity["name"]

    def test_class01b_synthetic_identity(self):
        """Given a synthetic minimal project identity section,
        When classify_sections is called,
        Then the section tier is 'always-inline'.
        """
        sections = classify_sections(IDENTITY_SECTION_SYNTHETIC)
        assert len(sections) >= 1
        identity = sections[0]
        assert identity["tier"] == TIER_ALWAYS_INLINE
        assert "What This Is" in identity["name"]


class TestClassifySectionsCliBlock:
    """CLASS-02: Large code block sections must be reference-offloadable."""

    def test_class02a_gamestudio_cli_block(self):
        """Given TheGameStudio's CLI commands section with 5+ commands,
        When classify_sections is called,
        Then the section tier is 'reference-offloadable'.
        """
        sections = classify_sections(CLI_BLOCK_GAMESTUDIO)
        assert len(sections) >= 1
        cli = sections[0]
        assert cli["tier"] == TIER_REFERENCE_OFFLOADABLE

    def test_class02b_synthetic_cli_block(self):
        """Given a synthetic CLI section with 5 npm commands,
        When classify_sections is called,
        Then the section tier is 'reference-offloadable'.
        """
        sections = classify_sections(CLI_BLOCK_SYNTHETIC)
        assert len(sections) >= 1
        cli = sections[0]
        assert cli["tier"] == TIER_REFERENCE_OFFLOADABLE


class TestClassifySectionsModuleCatalog:
    """CLASS-03: Module catalogs with 4+ bold-code bullets must be reference-offloadable."""

    def test_class03a_gamestudio_module_catalog(self):
        """Given TheGameStudio's architecture section with bold-code module bullets,
        When classify_sections is called,
        Then the section tier is 'reference-offloadable'.
        """
        sections = classify_sections(MODULE_CATALOG_GAMESTUDIO)
        ref_sections = [s for s in sections if s["tier"] == TIER_REFERENCE_OFFLOADABLE]
        assert len(ref_sections) >= 1

    def test_class03b_synthetic_module_catalog(self):
        """Given a synthetic module catalog with 4 bold-code bullets,
        When classify_sections is called,
        Then the section tier is 'reference-offloadable'.
        """
        sections = classify_sections(MODULE_CATALOG_SYNTHETIC)
        assert len(sections) >= 1
        catalog = sections[0]
        assert catalog["tier"] == TIER_REFERENCE_OFFLOADABLE


class TestClassifySectionsConventions:
    """CLASS-04: Short conventions sections with imperatives must be always-inline."""

    def test_class04a_gamestudio_conventions(self):
        """Given TheGameStudio's 'Important Conventions' section with imperative bullets,
        When classify_sections is called,
        Then the section tier is 'always-inline'.
        """
        sections = classify_sections(CONVENTIONS_GAMESTUDIO)
        assert len(sections) >= 1
        conv = sections[0]
        assert conv["tier"] == TIER_ALWAYS_INLINE

    def test_class04b_synthetic_conventions(self):
        """Given a synthetic conventions section with 'Never'/'Always' imperatives,
        When classify_sections is called,
        Then the section tier is 'always-inline'.
        """
        sections = classify_sections(CONVENTIONS_SYNTHETIC)
        assert len(sections) >= 1
        conv = sections[0]
        assert conv["tier"] == TIER_ALWAYS_INLINE


# =========================================================================
# EMB — Embedded constraint detection tests
# =========================================================================


class TestDetectEmbeddedConstraints:
    """EMB-01 through EMB-03: Detect imperative constraints buried in offloadable sections."""

    def test_emb01_imperatives_detected(self):
        """Given a reference-offloadable section containing 'must' and 'no I/O' imperatives,
        When detect_embedded_constraints is called,
        Then those constraints are detected with appropriate types.
        """
        sections = [
            {
                "name": "Core modules",
                "start_line": 1,
                "end_line": 5,
                "content": (
                    "- **`question_mode.py`** — Pure function library, no I/O.\n"
                    "- **`role_overrides.py`** — must use shallow-merge with manifest roles.\n"
                ),
                "tier": TIER_REFERENCE_OFFLOADABLE,
                "reason": "module catalog",
            }
        ]
        constraints = detect_embedded_constraints(sections)
        assert len(constraints) >= 1
        constraint_texts = [c["text"] for c in constraints]
        assert any("must" in t.lower() or "no I/O" in t for t in constraint_texts)

    def test_emb02a_required_label_detected(self):
        """Given a section with 'Required:' as an imperative label,
        When detect_embedded_constraints is called,
        Then the constraint is detected.
        """
        sections = [
            {
                "name": "Setup",
                "start_line": 1,
                "end_line": 3,
                "content": "Required: Python 3.10+ and pip.\nInstall via pip install .\n",
                "tier": TIER_REFERENCE_OFFLOADABLE,
                "reason": "code block",
            }
        ]
        constraints = detect_embedded_constraints(sections)
        assert len(constraints) >= 1
        assert any("Required" in c["text"] for c in constraints)

    def test_emb02b_required_adjective_not_detected(self):
        """CRITICAL NEGATIVE: Given 'the required dependencies' (adjective usage),
        When detect_embedded_constraints is called,
        Then it is NOT flagged as an imperative constraint.
        """
        sections = [
            {
                "name": "Setup",
                "start_line": 1,
                "end_line": 2,
                "content": "Install the required dependencies via pip.\n",
                "tier": TIER_REFERENCE_OFFLOADABLE,
                "reason": "code block",
            }
        ]
        constraints = detect_embedded_constraints(sections)
        # Should not flag "the required dependencies" as a constraint
        flagged_texts = [c["text"] for c in constraints]
        assert not any("the required dependencies" in t for t in flagged_texts)

    def test_emb03_no_imperatives_empty_result(self):
        """Given a section with no imperative language,
        When detect_embedded_constraints is called,
        Then the result list is empty.
        """
        sections = [
            {
                "name": "File list",
                "start_line": 1,
                "end_line": 3,
                "content": (
                    "- `app.py` — Main entry\n"
                    "- `db.py` — Database layer\n"
                    "- `api.py` — Routes\n"
                ),
                "tier": TIER_REFERENCE_OFFLOADABLE,
                "reason": "module catalog",
            }
        ]
        constraints = detect_embedded_constraints(sections)
        assert constraints == []


# =========================================================================
# REPORT — Report generation test
# =========================================================================


class TestGenerateReport:
    """REPORT-01: generate_report produces a valid structured report."""

    def test_report01_contains_expected_sections(self):
        """Given classified sections, constraints, pointers, canaries, and reconciliation,
        When generate_report is called,
        Then the output contains Summary, Per-Section Classification, and VALIDATION STATUS.
        """
        sections = [
            {
                "name": "What This Is",
                "start_line": 1,
                "end_line": 4,
                "content": "Identity text.",
                "tier": TIER_ALWAYS_INLINE,
                "reason": "identity",
            }
        ]
        constraints = []
        pointers = [
            {
                "inline_stub": "**CLI Commands:** When you need cli commands details, read `studio/docs/cli_commands.md` for the full reference — required for correct implementation.",
                "manifest_entry": {
                    "trigger": "When you need cli commands details",
                    "path": "studio/docs/cli_commands.md",
                    "description": "Full cli commands reference (offloaded from CLAUDE.md)",
                },
                "strength": {
                    "score": 0.8,
                    "has_imperative": True,
                    "has_trigger": True,
                    "has_path": True,
                    "has_consequence": True,
                    "rating": "strong",
                },
            }
        ]
        canaries = {"cli_commands": "CANARY-test-abcd1234"}
        reconciliation = []

        report = generate_report(sections, constraints, pointers, canaries, reconciliation)
        assert isinstance(report, str)
        assert "Summary" in report
        assert "Per-Section Classification" in report or "Classification" in report
        assert "VALIDATION STATUS" in report or "Validation" in report.upper()


# =========================================================================
# CAN — Canary token tests
# =========================================================================


class TestCanaryTokens:
    """CAN-01 through CAN-03: Canary token generation and isolation verification."""

    def test_can01_format(self):
        """Given a slug,
        When generate_canary_token is called,
        Then the result matches CANARY-{slug}-{hex8} format.
        """
        token = generate_canary_token("test-section")
        pattern = r"^CANARY-test-section-[0-9a-f]{8}$"
        assert re.match(pattern, token), f"Token {token!r} does not match expected format"

    def test_can01_uniqueness(self):
        """Successive calls produce different tokens (random hex component)."""
        t1 = generate_canary_token("slug")
        t2 = generate_canary_token("slug")
        assert t1 != t2

    def test_can02_leaked_token_detected(self):
        """Given a CLAUDE.md containing an offloaded canary token,
        When verify_canary_isolation is called,
        Then the leaked token is returned.
        """
        token = generate_canary_token("cli-commands")
        claude_md = f"## What This Is\nSome project.\n\n{token}\n"
        leaked = verify_canary_isolation(claude_md, [token])
        assert token in leaked

    def test_can03_no_leak_passes(self):
        """Given a CLAUDE.md with no canary tokens,
        When verify_canary_isolation is called,
        Then the leaked list is empty.
        """
        token = generate_canary_token("cli-commands")
        claude_md = "## What This Is\nSome project.\n"
        leaked = verify_canary_isolation(claude_md, [token])
        assert leaked == []


# =========================================================================
# VAL — Protocol evaluator tests
# =========================================================================


class TestEvaluateProtocolRun:
    """VAL-01 through VAL-03: Protocol run evaluation with session/echo thresholds."""

    @staticmethod
    def _make_results(n_sessions: int, echo_rate: float) -> list[dict]:
        """Build a list of session result dicts with the given echo rate."""
        n_echo = int(n_sessions * echo_rate)
        results = []
        for i in range(n_sessions):
            results.append({
                "session_id": i,
                "echo_found": i < n_echo,
                "token_matched": i < n_echo,
                "pointer_pattern": "identity",
            })
        return results

    def test_val01_passes_20_sessions_85_pct(self):
        """Given 20 sessions with 85% echo rate,
        When evaluate_protocol_run is called,
        Then passed is True.
        """
        results = self._make_results(20, 0.85)
        evaluation = evaluate_protocol_run(results)
        assert evaluation["passed"] is True
        assert evaluation["total_sessions"] == 20
        assert evaluation["echo_rate"] >= 0.80

    def test_val02_fails_below_20_sessions(self):
        """Given 19 sessions (below minimum n>=20),
        When evaluate_protocol_run is called,
        Then passed is False.
        """
        results = self._make_results(19, 0.90)
        evaluation = evaluate_protocol_run(results)
        assert evaluation["passed"] is False

    def test_val03_fails_below_80_pct_echo(self):
        """Given 20 sessions with 75% echo rate (below 80% threshold),
        When evaluate_protocol_run is called,
        Then passed is False.
        """
        results = self._make_results(20, 0.75)
        evaluation = evaluate_protocol_run(results)
        assert evaluation["passed"] is False
        assert evaluation["echo_rate"] < 0.80


# =========================================================================
# PTR — Pointer scoring tests
# =========================================================================


class TestScorePointerStrength:
    """PTR-01 through PTR-03: Pointer text quality scoring."""

    def test_ptr01_strong_pointer(self):
        """Given a pointer with imperative, trigger, path, and consequence,
        When score_pointer_strength is called,
        Then score >= 0.7 and rating is 'strong'.
        """
        pointer = (
            "When you need CLI commands, read `.studio/docs/cli-reference.md`. "
            "Failure to check this file may cause you to use deprecated flags."
        )
        result = score_pointer_strength(pointer)
        assert result["score"] >= 0.7
        assert result["rating"] == "strong"
        assert result["has_imperative"] is True
        assert result["has_trigger"] is True
        assert result["has_path"] is True
        assert result["has_consequence"] is True

    def test_ptr02_medium_pointer(self):
        """Given a pointer with imperative and path but no trigger,
        When score_pointer_strength is called,
        Then 0.5 <= score < 0.7 and rating is 'medium'.
        """
        pointer = "See `.studio/docs/cli-reference.md` for the full command list."
        result = score_pointer_strength(pointer)
        assert 0.5 <= result["score"] < 0.7
        assert result["rating"] == "medium"
        assert result["has_path"] is True

    def test_ptr03_weak_pointer(self):
        """Given a passive reference with no imperative or trigger,
        When score_pointer_strength is called,
        Then score < 0.5 and rating is 'weak'.
        """
        pointer = "More details are available elsewhere in the documentation."
        result = score_pointer_strength(pointer)
        assert result["score"] < 0.5
        assert result["rating"] == "weak"
