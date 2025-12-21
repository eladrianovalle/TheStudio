from __future__ import annotations

from typing import Any, Callable, Dict, List, MutableMapping, Union

from studio.telemetry import model_manager, rate_limit_monitor
from studio.verdict import extract_verdict

IterationInputs = Dict[str, Any]
CrewFactory = Callable[[], Any]


def _safe_max_iterations(raw_value: Union[int, str, None]) -> int:
    """Convert env/user provided iteration cap to a positive int with fallback."""
    try:
        parsed = int(raw_value) if raw_value is not None else 0
    except (TypeError, ValueError):
        parsed = 0
    return parsed if parsed > 0 else 3


def run_iterative_kickoff(
    crew_factory: CrewFactory,
    phase: str,
    base_inputs: IterationInputs,
    max_iterations: Union[int, str, None] = None,
) -> Dict[str, Any]:
    """
    Execute crew kickoff repeatedly until verdict APPROVED or iteration cap hit.

    Args:
        crew_factory: Callable returning a fresh Crew instance with kickoff(inputs=...).
        phase: Current Studio phase (market/design/tech/studio).
        base_inputs: Inputs passed to the crew.
        max_iterations: Optional cap (default resolved to 3 if invalid/missing).

    Returns:
        dict containing final result, verdict, iterations run, history, and acceptance flag.
    """
    iteration_cap = _safe_max_iterations(max_iterations)
    history: List[Dict[str, Any]] = []
    verdict = "UNKNOWN"

    for iteration in range(1, iteration_cap + 1):
        iteration_inputs: MutableMapping[str, Any] = dict(base_inputs)
        iteration_inputs["iteration"] = iteration

        if history:
            iteration_inputs["previous_result"] = history[-1]["result"]
            iteration_inputs["previous_verdict"] = history[-1]["verdict"]

        crew = crew_factory()
        result = crew.kickoff(inputs=iteration_inputs)
        result_str = str(result)

        if phase != "studio":
            verdict = extract_verdict(result_str)

        history.append(
            {
                "iteration": iteration,
                "result": result_str,
                "verdict": verdict if phase != "studio" else "UNKNOWN",
            }
        )

        if phase == "studio" or verdict == "APPROVED":
            break

    final = history[-1]
    accepted = verdict == "APPROVED"
    limit_reached = len(history) >= iteration_cap and not accepted and phase != "studio"

    return {
        "result": final["result"],
        "verdict": final["verdict"],
        "iterations_run": len(history),
        "history": history,
        "accepted": accepted,
        "limit_reached": limit_reached,
        "max_iterations": iteration_cap,
        "rate_limits": rate_limit_monitor.snapshot(),
        "model_strategy": model_manager.serialize(),
    }
