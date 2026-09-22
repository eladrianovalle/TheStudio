"""Studio imports the standard library and nothing else.

CLAUDE.md states the constraint — "No heavy dependencies: stdlib only (plus `tomli` on
Python 3.10)" — and until now nothing enforced it. A reviewer on a consuming repo's update
asked whether newly-snapshotted modules pulled in anything that `versions.lock` would not
cover, and the only way to answer was to read their imports by hand. This answers it once,
for every module and every future review.

`tomli` is the one allowance, and it is conditional: Python 3.11 ships `tomllib`, so the
import sits behind a version check rather than at module top level.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_STUDIO = Path(__file__).resolve().parents[1]

# The one non-stdlib name Studio may import, and only as a fallback for Python 3.10.
_ALLOWED_THIRD_PARTY = {"tomli"}


def _studio_modules() -> list[Path]:
    """Every Studio module, excluding the tests and the vendored source snapshot."""
    return sorted(
        path
        for path in _STUDIO.rglob("*.py")
        if "tests" not in path.parts and ".studio" not in path.parts
    )


def _imported_roots(path: Path) -> set[str]:
    """Top-level package names imported by one module, however the import is spelled."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module of its own to resolve.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _is_local(name: str) -> bool:
    """True for Studio's own modules and packages, which sit beside the importer."""
    return (_STUDIO / f"{name}.py").exists() or (_STUDIO / name / "__init__.py").exists()


def test_every_studio_module_imports_only_the_standard_library():
    offenders: dict[str, set[str]] = {}
    for path in _studio_modules():
        outside = {
            name
            for name in _imported_roots(path)
            if name not in sys.stdlib_module_names
            and name not in _ALLOWED_THIRD_PARTY
            and not _is_local(name)
        }
        if outside:
            offenders[str(path.relative_to(_STUDIO))] = outside
    assert not offenders, (
        "Studio is stdlib-only (plus tomli on Python 3.10), and these imports are neither "
        f"stdlib, tomli, nor a Studio module: {offenders}. Adding a dependency means a "
        "consuming repo's lockfile no longer covers what Studio needs — decide that "
        "deliberately and update CLAUDE.md, rather than letting an import decide it."
    )


def test_the_modules_it_walks_are_actually_there():
    """A guard that finds nothing proves nothing — fail loudly if the glob goes empty."""
    modules = _studio_modules()
    assert len(modules) > 20, f"only found {len(modules)} Studio modules; the glob is wrong"
    assert any(path.name == "run_phase.py" for path in modules)
