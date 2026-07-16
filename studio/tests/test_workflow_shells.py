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
