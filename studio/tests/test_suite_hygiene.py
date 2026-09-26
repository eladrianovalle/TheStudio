"""Nothing in a test file may sit after its ``if __name__ == "__main__"`` block.

Python reads the whole module before running anything, so under pytest a class defined
below that block is collected and run like any other. Run the same file directly and
``unittest.main()`` executes at the point it appears, discovers only what has been defined
so far, and exits — silently, reporting OK on a subset.

That is how three tests added to `test_command_descriptions.py` came to run under pytest
and not under `python tests/test_command_descriptions.py`: 7 tests there, 10 here, and the
direct run said OK. Appending to a file is the natural way to add a test, which is exactly
why this needs a check rather than a convention.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

TEST_FILES = sorted(path for path in TESTS_DIR.glob("test_*.py"))


def _main_guard_line(tree: ast.Module) -> int | None:
    """The line of the module-level ``if __name__ == "__main__":``, or None."""
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        ):
            return node.lineno
    return None


@pytest.mark.parametrize("path", TEST_FILES, ids=lambda p: p.name)
def test_nothing_is_stranded_after_the_main_guard(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guard_line = _main_guard_line(tree)
    if guard_line is None:
        return  # No guard, nothing can be stranded behind it.

    stranded = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno > guard_line
    ]
    assert not stranded, (
        f"{path.name} defines {stranded} after its `if __name__ == \"__main__\"` block. "
        f"pytest runs them; `python tests/{path.name}` does not, and says OK anyway. "
        f"Move the block to the end of the file."
    )
