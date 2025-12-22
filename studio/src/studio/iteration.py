from __future__ import annotations

import sys
from typing import Any, Callable, Dict, List, MutableMapping, Union

from studio.implementation import _run_implementation_phase
from studio.telemetry import model_manager, rate_limit_monitor
from studio.verdict import extract_verdict

IterationInputs = Dict[str, Any]
CrewFactory = Callable[[], Any]
RATE_LIMIT_KEYWORDS = ("rate limit", "rate_limit", "quota", "exceeded")
OVERLOAD_KEYWORDS = ("temperature", "overloaded", "busy", "unavailable", "capacity")


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

    candidate_snapshot = model_manager.serialize().get("candidates") or []
    max_model_attempts = max(1, len(candidate_snapshot) or 1)

    for iteration in range(1, iteration_cap + 1):
        iteration_inputs: MutableMapping[str, Any] = dict(base_inputs)
        iteration_inputs["iteration"] = iteration
        iteration_inputs["max_iterations"] = iteration_cap

        if history:
            previous_entry = history[-1]
            iteration_inputs["previous_result"] = previous_entry["result"]
            iteration_inputs["previous_verdict"] = previous_entry["verdict"]
            
            if previous_entry["verdict"] == "REJECTED":
                iteration_inputs["previous_feedback"] = (
                    f"PREVIOUS REJECTION (Iteration {previous_entry['iteration']}):\n"
                    f"{previous_entry['result']}\n\n"
                    "Address these concerns in your revised proposal."
                )
            else:
                iteration_inputs["previous_feedback"] = ""
        else:
            iteration_inputs["previous_feedback"] = ""

        model_attempt = 0
        result = None
        while model_attempt < max_model_attempts:
            crew = crew_factory()
            try:
                result = crew.kickoff(inputs=iteration_inputs)
                break
            except Exception as exc:  # noqa: BLE001
                model_attempt += 1
                handled = _handle_model_failure(exc)
                if handled and model_attempt < max_model_attempts:
                    continue
                raise

        if result is None:
            raise RuntimeError("All configured models failed before producing a result.") from None
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
    
    if verdict == "APPROVED" and phase != "studio":
        implementation_result = _run_implementation_phase(phase, base_inputs, final["result"])
        if implementation_result:
            history.append({
                "iteration": len(history) + 1,
                "result": implementation_result,
                "verdict": "IMPLEMENTATION",
                "phase": "implementation",
            })
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


def _handle_model_failure(exc: Exception) -> bool:
    """
    Attempt to classify a provider failure and mark the active model accordingly.

    Returns True when the exception was handled and we should retry with another
    candidate, False otherwise.
    """
    if exc is None:
        return False

    model = model_manager.current_model()
    if not model:
        return False

    message = (str(exc) or "").lower()
    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    try:
        status_int = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status_int = None

    retry_after = getattr(exc, "retry_after", None)
    try:
        retry_after_int = int(retry_after) if retry_after is not None else None
    except (TypeError, ValueError):
        retry_after_int = None

    def _log(reason: str):
        print(
            f"[ModelFallback] {model} failed ({reason}). Trying next cascade candidate...",
            file=sys.stderr,
        )

    is_rate_limited = (status_int == 429) or any(
        keyword in message for keyword in RATE_LIMIT_KEYWORDS
    )
    if is_rate_limited:
        model_manager.mark_cooldown(
            model,
            retry_after_int,
            reason="rate_limit_exception",
        )
        _log("rate limited")
        return True

    is_overloaded = (
        (status_int and status_int >= 500)
        or any(keyword in message for keyword in OVERLOAD_KEYWORDS)
    )
    if is_overloaded:
        model_manager.mark_overheated(
            model,
            reason=f"exception: {message[:60] or status_int}",
        )
        _log("overheated")
        return True

    return False
