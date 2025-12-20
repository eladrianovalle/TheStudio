import os
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

@CrewBase
class StudioCrew():
    """Studio crew for multi-phase game development"""
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    def __init__(self, phase='market'):
        self.phase = phase
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        self.google_llm = LLM(
            model="gemini-2.5-flash", 
            api_key=api_key
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

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
        )