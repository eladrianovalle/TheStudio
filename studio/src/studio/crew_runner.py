#!/usr/bin/env python
"""
Isolated crew runner for subprocess execution.
This module runs in a separate process to isolate litellm crashes.
"""
import json
import os
import sys


def run_crew_isolated():
    """Run the crew in an isolated subprocess context."""
    # Apply solo mode env vars before any imports
    solo_mode = os.environ.get("STUDIO_SOLO_MODE", "true").lower() not in {"false", "0", "no"}
    if solo_mode:
        os.environ.setdefault("LITELLM_LOGGING", "false")
        os.environ.setdefault("LITELLM_PROXY_SERVER", "false")
        os.environ.setdefault("LITELLM_SAVE_RAW_OUTPUT", "false")
        os.environ.setdefault("LITELLM_LOG_DB_QUERIES", "false")
        os.environ.setdefault("PYTHONWARNINGS", "ignore::UserWarning")
    
    # Now safe to import crew helpers
    from studio.crew import StudioCrew
    from studio.iteration import run_iterative_kickoff
    
    phase = os.environ.get("STUDIO_PHASE", "market").lower()
    
    if phase == "studio":
        objective = os.environ.get(
            "STUDIO_OBJECTIVE",
            "How do we make Studio the best always-on cofounder for a solo dev with tiny capital and big ambitions?"
        )
        budget_cap = os.environ.get("STUDIO_BUDGET_CAP", "$0-20/mo")
        inputs = {
            'objective': objective,
            'budget_cap': budget_cap,
        }
    else:
        inputs = {
            'game_idea': os.environ.get(
                "STUDIO_GAME_IDEA",
                "A 3D stealth horror roguelike for the web"
            )
        }

    max_iterations = os.environ.get("STUDIO_MAX_ITERATIONS")

    def crew_factory():
        return StudioCrew(phase=phase).crew()

    iteration_result = run_iterative_kickoff(
        crew_factory=crew_factory,
        phase=phase,
        base_inputs=inputs,
        max_iterations=max_iterations,
    )
    
    # Output result as JSON for parent process to capture
    output = {
        "success": True,
        "phase": phase,
        "inputs": inputs,
        "result": iteration_result["result"],
        "verdict": iteration_result["verdict"],
        "iterations_run": iteration_result["iterations_run"],
        "history": iteration_result["history"],
        "accepted": iteration_result["accepted"],
        "limit_reached": iteration_result["limit_reached"],
        "max_iterations": iteration_result["max_iterations"],
    }
    print("__STUDIO_RESULT_START__")
    print(json.dumps(output))
    print("__STUDIO_RESULT_END__")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_crew_isolated())
    except Exception as e:
        import traceback
        error_output = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "phase": os.environ.get("STUDIO_PHASE", "market")
        }
        print("__STUDIO_RESULT_START__")
        print(json.dumps(error_output))
        print("__STUDIO_RESULT_END__")
        sys.exit(1)
