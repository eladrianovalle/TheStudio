"""Guards for the Claude Code Workflow shells (``.claude/workflows/*.js``).

The workflow shells are orchestration JS that the Python suite otherwise never
sees. Two failure modes have already bitten us and only surfaced at runtime
against the live API:

  - an ``agent()`` schema whose top-level ``type`` was ``'array'`` — the Anthropic
    API rejects it (400 input_schema.type), so the verifier Select step failed
    before verifying anything (PR #66 review), and
  - the ``reviewerConcerns`` surfacing, which the pure Python tests can't reach.

These guards catch the schema-shape class *statically* (no live API needed), pin
the reviewerConcerns wiring, and run the JS unit tests (``node:test``) that
exercise the shells' pure helpers against their real source.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude" / "workflows"


def _workflow_files():
    return sorted(_WORKFLOW_DIR.glob("*.js"))


def _top_level_type(src: str, pos: int):
    """Read the ``type: '...'`` declared at brace-depth 1 of an object literal.

    ``pos`` points just inside the object's opening ``{``. We walk forward
    tracking brace depth and return the ``type`` at depth 1 (the object's own),
    NOT merely the first ``type:`` anywhere — a nested property's ``type: 'array'``
    must not be mistaken for the schema's top-level type (that miss is exactly the
    top-level-array 400 this guard exists to catch). Returns None if the object
    declares no top-level type.
    """
    depth = 1  # pos is already inside the opening brace
    i, n = pos, len(src)
    while i < n and depth > 0:
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth == 1 and src.startswith("type", i) and (
            i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")
        ):
            m = re.match(r"type\s*:\s*['\"](\w+)['\"]", src[i:])
            if m:
                return m.group(1)
        i += 1
    return None


def _schema_top_level_types(src: str):
    """Yield the top-level ``type`` of every ``agent()`` schema in a shell.

    Schemas appear two ways: inline ``schema: { ... }`` in an agent() options
    object, and named consts ``const X_HANDOFF = { ... }`` / ``X_SCHEMA`` passed
    by reference. Each is read structurally by brace depth (see _top_level_type),
    so the check does not depend on ``type`` being written as the first key.
    """
    anchors = [m.end() for m in re.finditer(r"schema:\s*\{", src)]
    anchors += [
        m.end()
        for m in re.finditer(r"const\s+\w*(?:HANDOFF|SCHEMA)\w*\s*=\s*\{", src)
    ]
    for pos in anchors:
        t = _top_level_type(src, pos)
        if t is not None:
            yield t


class TestWorkflowSchemas:
    def test_workflow_dir_has_shells(self):
        assert _WORKFLOW_DIR.is_dir()
        assert _workflow_files(), "expected at least one workflow .js file"

    @pytest.mark.parametrize("wf", _workflow_files(), ids=lambda p: p.name)
    def test_agent_schemas_are_objects(self, wf):
        """A custom tool's top-level input schema must be an object; a top-level
        array is a 400 from the Anthropic API (the PR #66 Select-schema bug)."""
        types = list(_schema_top_level_types(wf.read_text()))
        assert types, f"no agent() schema found in {wf.name} (parser drift?)"
        non_object = [t for t in types if t != "object"]
        assert not non_object, (
            f"{wf.name}: agent() schema(s) with non-object top-level type "
            f"{non_object} — the API rejects a top-level array/etc."
        )


class TestSchemaGuardParser:
    """Prove the guard reads the *top-level* type and isn't fooled by a nested
    one — its whole reason to exist. Without this, the guard could silently stop
    catching the top-level-array 400 it was written for (PR #66)."""

    def test_flags_a_top_level_array_schema(self):
        # The exact PR #66 bug: a bare top-level array the Anthropic API rejects.
        src = "await agent(p, { schema: { type: 'array', items: { type: 'object' } } })"
        assert list(_schema_top_level_types(src)) == ["array"]

    def test_reads_top_level_object_past_a_nested_array_and_non_first_type(self):
        # `type` is NOT the first key AND a nested property is an array; the walker
        # must still report the object's own top-level type, not the nested one.
        src = (
            "const X_HANDOFF = { additionalProperties: false, "
            "properties: { xs: { type: 'array', items: { type: 'string' } } }, "
            "type: 'object' }"
        )
        assert list(_schema_top_level_types(src)) == ["object"]

    def test_object_with_no_top_level_type_yields_nothing(self):
        src = "await agent(p, { schema: { properties: { x: { type: 'string' } } } })"
        assert list(_schema_top_level_types(src)) == []


class TestVerifierFirewall:
    """The R1 anti-anchoring firewall lives in finding-verifier.js's Verify prompt:
    it may carry the finding's quote and nothing else from the contrarian. A leak
    of the flaw/impact/reasoning is the one thing the whole feature exists to avoid."""

    def test_verify_prompt_carries_only_the_quote(self):
        src = (_WORKFLOW_DIR / "finding-verifier.js").read_text()
        verify_block = src[src.index("phase('Verify')"):src.index("phase('Write-back')")]
        assert "item.quote" in verify_block, "the quote must reach the verifier"
        # The per-finding item only holds {index, quote}; a future edit that fed
        # the contrarian's fields into the prompt would breach the firewall.
        for leaked in ("item.flaw", "item.impact", "item.reason", "item.confidence"):
            assert leaked not in verify_block, (
                f"Verify prompt references {leaked!r} — the contrarian's reasoning "
                "would leak past the firewall"
            )


class TestReviewerConcernsWiring:
    """Pin that the /forge loop surfaces the editor's unresolved_concerns."""

    def test_surfaced_in_return_with_safe_guard(self):
        src = (_WORKFLOW_DIR / "implementation-loop.js").read_text()
        assert "collectReviewerConcerns" in src
        # Non-array / missing field must default to [], never crash.
        assert "Array.isArray(editor.unresolved_concerns)" in src
        # reviewerConcerns is part of the workflow's return payload.
        assert re.search(r"return\s*\{[\s\S]*?reviewerConcerns[\s\S]*?\}", src), (
            "reviewerConcerns must be in the workflow's return object"
        )


class TestAcceptanceCriteriaWiring:
    """Pin that the /forge loop can grade a unit against acceptance criteria.

    The JS tests cover the prompt behavior. These guard the two pieces that live outside a
    testable function — the editor's schema (a shape the live API either accepts or 400s on)
    and the single call site that reads the returned verdicts.
    """

    def _loop_source(self):
        return (_WORKFLOW_DIR / "implementation-loop.js").read_text()

    def test_criteria_verdicts_declared_but_not_required(self):
        src = self._loop_source()
        handoff = src[src.index("const EDITOR_HANDOFF"):src.index("function writerPrompt")]
        assert "criteria_verdicts" in handoff, "the editor has no way to return per-criterion grades"
        # Optional, exactly like unresolved_concerns: a spec-less run grades nothing, and
        # additionalProperties: false means a required-but-absent field would fail the payload.
        top_level_required = re.search(r"required: \[([^\]]*)\]", handoff).group(1)
        assert "criteria_verdicts" not in top_level_required
        assert "unresolved_concerns" not in top_level_required
        # Each entry carries the criterion, the grade, and the evidence actually checked.
        assert "required: ['criterion', 'verdict', 'evidence']" in handoff
        assert "enum: ['pass', 'fail', 'unverifiable']" in handoff

    def test_verdicts_surfaced_in_log_and_return_with_safe_guard(self):
        src = self._loop_source()
        # Non-array / missing field must default to [], never crash the delivery.
        assert "Array.isArray(editor.criteria_verdicts)" in src
        assert "verdict !== 'pass'" in src, "nothing selects the criteria that didn't pass"
        # The failing criteria are named in the run log, not just counted.
        log_lines = [
            line for line in src.splitlines()
            if "failedCriteria.map" in line and line.strip().startswith("log(")
        ]
        assert log_lines, "the failing criteria must be named in the run log"
        assert "v.criterion" in log_lines[0]
        # The verdicts are part of the workflow's return payload.
        assert re.search(r"return\s*\{[\s\S]*?criteriaVerdicts[\s\S]*?\}", src), (
            "criteriaVerdicts must be in the workflow's return object"
        )

    def test_editor_off_says_criteria_were_not_graded(self):
        src = self._loop_source()
        assert "criteria ungraded (editor off)" in src


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_shell_unit_tests():
    """Run the node:test suite exercising the shells' pure helpers.

    These load helpers from the real shell source (the sandbox can't be
    imported), so they drive the actual code — e.g. collectReviewerConcerns
    against real unresolved_concerns payloads.
    """
    # Pass the test files explicitly: `node --test <dir>` tries to *load* the
    # directory as a module rather than scan it.
    test_files = sorted((_WORKFLOW_DIR / "tests").glob("*.test.mjs"))
    assert test_files, "expected at least one workflow node:test file"
    result = subprocess.run(
        ["node", "--test", *(str(p) for p in test_files)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
