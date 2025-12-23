"""
Helpers that raise a consistent error now that the old Studio autop-run runtime
has been decommissioned in favor of Cascade-only workflows.
"""
from __future__ import annotations

import textwrap


REMOVAL_MESSAGE = textwrap.dedent(
    """
    The legacy Studio runtime (crew.py, iteration.py, etc.) was removed in favor of
    the Cascade-first workflow. Run `python run_phase.py prepare ...` to generate
    instructions, execute them inside Windsurf/Cascade, then finalize with
    `python run_phase.py finalize ...`.
    """
).strip()


class StudioRuntimeRemoved(RuntimeError):
    """Raised when callers try to import the removed runtime modules."""


def raise_runtime_removed(module: str) -> None:
    raise StudioRuntimeRemoved(f"{module} is no longer available. {REMOVAL_MESSAGE}")


__all__ = ["StudioRuntimeRemoved", "raise_runtime_removed", "REMOVAL_MESSAGE"]
