from studio._runtime_removed import raise_runtime_removed


def _run_implementation_phase(*_, **__):
    raise_runtime_removed("studio.implementation")


__all__ = ["_run_implementation_phase"]
