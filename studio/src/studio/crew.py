import importlib.util
import os
from typing import Dict, Optional, Tuple

from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

from studio.health import check_ollama_health
from studio.telemetry import configured_model_candidates, model_manager

@CrewBase
class StudioCrew():
    """Studio crew for multi-phase game development"""
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    REQUIRED_MODULES = {
        "email_validator": 'pip install "pydantic[email]" or "pip install email-validator"',
    }

    def __init__(self, phase='market'):
        self.phase = phase
        self._run_preflight_checks()

        model_name, api_key, extra_kwargs, selection_info = self._select_llm_configuration()
        self._active_model = model_name
        self._active_model_info = selection_info

        self.google_llm = LLM(
            model=model_name,
            api_key=api_key,
            **extra_kwargs,
        )
        self._log_active_model()

    def _log_active_model(self):
        descriptor = self._active_model_info.get("descriptor") or self._active_model
        provider = self._active_model_info.get("provider", "unknown")
        print(
            f"[StudioCrew] {self.phase.title()} agents thinking with {descriptor} "
            f"(provider: {provider})"
        )

    def _select_llm_configuration(self) -> Tuple[str, Optional[str], Dict, Dict]:
        provider_env_map = {
            "gemini": "GEMINI_API_KEY",
            "google": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "azure": "AZURE_OPENAI_API_KEY",
        }

        model_manager.configure_candidates(configured_model_candidates())
        candidates = model_manager.serialize().get("candidates") or ["gemini-2.5-flash"]
        tested = set()

        for _ in range(len(candidates)):
            candidate = model_manager.select_model()
            if candidate in tested:
                break
            tested.add(candidate)

            provider = candidate.split("/", 1)[0].lower() if "/" in candidate else "gemini"
            env_var = provider_env_map.get(provider)

            if provider == "ollama":
                base_url = os.environ.get("STUDIO_OLLAMA_BASE_URL", "http://localhost:11434")
                healthy, detail = check_ollama_health(candidate, base_url)
                if not healthy:
                    print(f"[StudioCrew] Ollama health check failed for {candidate}: {detail}")
                    model_manager.mark_overheated(candidate, reason=detail, cooldown_seconds=60)
                    continue
                descriptor = f"{candidate} via Ollama ({base_url})"
                print(f"[StudioCrew] Ollama health check passed: {detail}")
                return (
                    candidate,
                    None,
                    {"base_url": base_url},
                    {
                        "provider": provider,
                        "descriptor": descriptor,
                        "detail": detail,
                        "base_url": base_url,
                    },
                )

            api_key = os.environ.get(env_var) if env_var else None
            if env_var and not api_key:
                print(f"[StudioCrew] Missing {env_var} for model {candidate}, trying next fallback.")
                model_manager.mark_cooldown(
                    candidate,
                    retry_after=600,
                    reason=f"missing {env_var}",
                )
                continue

            descriptor = f"{candidate} (cloud provider: {provider})"
            return candidate, api_key, {}, {
                "provider": provider,
                "descriptor": descriptor,
            }

        raise EnvironmentError(
            "No usable LLM provider configured. Please set an API key (e.g. GEMINI_API_KEY) "
            "or install/configure Ollama with STUDIO_OLLAMA_MODEL."
        )

    def _run_preflight_checks(self):
        missing = []
        for module, remedy in self.REQUIRED_MODULES.items():
            if importlib.util.find_spec(module) is None:
                missing.append(f"{module} → {remedy}")

        if missing:
            details = "\n  - ".join(missing)
            raise ImportError(
                "Studio preflight check failed. Install the missing dependencies before running:\n"
                f"  - {details}"
            )

    @agent
    def advocate(self) -> Agent:
        return Agent(
            config=self.agents_config[f'{self.phase}_advocate'],
            verbose=True,
            llm=self.google_llm
        )

    @agent
    def contrarian(self) -> Agent:
        return Agent(
            config=self.agents_config[f'{self.phase}_contrarian'],
            verbose=True,
            llm=self.google_llm
        )

    def integrator(self) -> Agent:
        if self.phase != 'studio':
            raise ValueError(f"Integrator agent only available for studio phase, not {self.phase}")
        return Agent(
            config=self.agents_config[f'{self.phase}_integrator'],
            verbose=True,
            llm=self.google_llm
        )

    @task
    def steel_man_task(self) -> Task:
        return Task(
            config=self.tasks_config['steel_man_task'],
            agent=self.advocate()
        )

    @task
    def attack_task(self) -> Task:
        return Task(
            config=self.tasks_config['attack_task'],
            agent=self.contrarian()
        )

    def studio_vision_task(self) -> Task:
        return Task(
            config=self.tasks_config['studio_vision_task'],
            agent=self.advocate()
        )

    def studio_constraints_task(self) -> Task:
        return Task(
            config=self.tasks_config['studio_constraints_task'],
            agent=self.contrarian()
        )

    def studio_integration_task(self) -> Task:
        return Task(
            config=self.tasks_config['studio_integration_task'],
            agent=self.integrator()
        )

    @crew
    def crew(self) -> Crew:
        if self.phase == 'studio':
            agents = [self.advocate(), self.contrarian(), self.integrator()]
            tasks = [
                self.studio_vision_task(),
                self.studio_constraints_task(),
                self.studio_integration_task()
            ]
        else:
            agents = [self.advocate(), self.contrarian()]
            tasks = [self.steel_man_task(), self.attack_task()]

        return Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True
        )