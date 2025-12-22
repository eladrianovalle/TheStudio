"""Implementation phase logic for generating concrete artifacts after approval."""
from __future__ import annotations

from typing import Any, Dict, Optional

from crewai import Agent, Task


def _run_implementation_phase(
    phase: str,
    base_inputs: Dict[str, Any],
    approved_concept: str,
) -> Optional[str]:
    """
    Run the implementation phase after a concept is approved.
    
    Args:
        phase: The phase that was approved (market/design/tech)
        base_inputs: Original inputs from the approval phase
        approved_concept: The approved concept text
        
    Returns:
        Implementation result string, or None if phase doesn't support implementation
    """
    from studio.crew import StudioCrew
    
    if phase not in ("market", "design", "tech"):
        return None
    
    crew_instance = StudioCrew(phase=phase)
    
    # Get the implementer agent
    if phase == "market":
        implementer = Agent(
            config=crew_instance.agents_config["market_implementer"],
            verbose=True,
            llm=crew_instance.google_llm,
        )
        task_key = "market_implementation_task"
    elif phase == "design":
        implementer = Agent(
            config=crew_instance.agents_config["design_implementer"],
            verbose=True,
            llm=crew_instance.google_llm,
        )
        task_key = "design_implementation_task"
    else:  # tech
        implementer = Agent(
            config=crew_instance.agents_config["tech_implementer"],
            verbose=True,
            llm=crew_instance.google_llm,
        )
        task_key = "tech_implementation_task"
    
    # Create implementation task
    task_config = crew_instance.tasks_config[task_key]
    implementation_task = Task(
        description=task_config["description"],
        expected_output=task_config["expected_output"],
        agent=implementer,
    )
    
    # Prepare inputs
    impl_inputs = dict(base_inputs)
    impl_inputs["approved_concept"] = approved_concept
    
    # Execute implementation
    from crewai import Crew, Process
    
    impl_crew = Crew(
        agents=[implementer],
        tasks=[implementation_task],
        process=Process.sequential,
        verbose=True,
    )
    
    result = impl_crew.kickoff(inputs=impl_inputs)
    return str(result)


__all__ = ["_run_implementation_phase"]
