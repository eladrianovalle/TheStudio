"""One place to get a working TOML parser.

Python 3.11+ ships ``tomllib`` in the standard library. On 3.10 it doesn't
exist, so we fall back to the third-party ``tomli`` package (declared as a
dependency for that version). Every module that reads a ``.toml`` config used to
carry its own copy of this import dance, and they had drifted: some exited with
a helpful message when ``tomli`` was missing, others crashed with a raw
``ModuleNotFoundError``. This module is the single copy, and it uses the helpful
message everywhere.

Usage::

    from config_loading import tomllib
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
"""
from __future__ import annotations

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redefine]  # Python 3.10 fallback
    except ModuleNotFoundError:
        raise SystemExit(
            "Studio needs the 'tomli' package on Python 3.10. "
            "Install it with: python -m pip install tomli  (or upgrade to Python 3.11+)."
        )

__all__ = ["tomllib"]
