# Studio Interaction Guide

Central reference for working with the Game Studio multi-agent crew from Cascade, the terminal, or other local projects.

## 1. What the Studio Does

- Centralized crew of advocate + contrarian agents (and an integrator for the Studio meta-phase) that evaluate ideas across Market → Design → Tech workflows using the steel-man vs. attack pattern.@/Users/orcpunk/Repos/_TheGameStudio/studio/README.md#36-193
- Every run saves a structured markdown report to `output/{phase}/{phase}_TIMESTAMP.md` containing the inputs, debate transcript, verdict, and status.@/Users/orcpunk/Repos/_TheGameStudio/studio/README.md#87-93

## 2. One-Time Setup

1. Install dependencies inside `studio/`:
   ```bash
   pip install uv
   crewai install
   ```
2. Create `.env` with API credentials:
   ```bash
   GEMINI_API_KEY=your_api_key_here
   MODEL=gemini-2.5-flash
   ```
3. (Recommended) Add Studio CLI to your PATH so Cascade can invoke it from any workspace:
   ```bash
   export PATH="/Users/orcpunk/Repos/_TheGameStudio/studio:$PATH"
   ```
4. Reload your shell (`source ~/.zshrc`) and verify with `studio list-phases`.@/Users/orcpunk/Repos/_TheGameStudio/studio/README.md#61-135 @/Users/orcpunk/Repos/_TheGameStudio/studio/docs/WINDSURF_USAGE.md#11-33

## 3. Core Commands (Cascade or Terminal)

| Goal | Command |
| --- | --- |
| Evaluate a single phase | `studio evaluate "Idea description" --phase [market|design|tech] [--format json]` |
| Run full Market → Design → Tech pipeline | `studio pipeline "Idea description"` |
| Discover available phases | `studio list-phases` |

Cascade usage pattern: “Use the Studio agents to evaluate `<idea>` in `<phase>`.” Cascade runs the CLI and streams the markdown verdict back into chat.@/Users/orcpunk/Repos/_TheGameStudio/studio/studio_cli.py#91-175 @/Users/orcpunk/Repos/_TheGameStudio/studio/docs/WINDSURF_USAGE.md#34-124

### Input Guidelines

- Minimum required key: `game_idea` (rich descriptions yield better debates).@/Users/orcpunk/Repos/_TheGameStudio/studio/docs/API.md#172-200
- Include platform, mechanics, constraints when possible; the crew will reference them directly in steel-man and attack tasks.

### Output Interpretation

- CLI prints agent debate + verdict; `studio_cli` also surfaces `success`, `phase`, and `verdict` when invoked with `--format json`.@/Users/orcpunk/Repos/_TheGameStudio/studio/studio_cli.py#20-88
- Report files live under `output/{phase}/` for historical review or sharing.@/Users/orcpunk/Repos/_TheGameStudio/studio/README.md#87-93

## 4. Running from Other Python Projects

```python
import sys
sys.path.append('/Users/orcpunk/Repos/_TheGameStudio/studio/src')

from studio.crew import StudioCrew

result = StudioCrew(phase='design').crew().kickoff(
    inputs={'game_idea': 'Your concept'}
)
print(result)
```

Stop the manual pipeline when a phase returns `REJECTED` to save tokens/time.@/Users/orcpunk/Repos/_TheGameStudio/studio/README.md#140-280

## 5. Environment & Stability Notes

- Required API env vars depend on `STUDIO_MODEL`; Gemini defaults to `GEMINI_API_KEY`.@/Users/orcpunk/Repos/_TheGameStudio/studio/src/studio/crew.py#16-41
- Preflight check enforces optional dependencies (e.g., `email_validator`). Install missing modules if errors surface before agent kickoff.@/Users/orcpunk/Repos/_TheGameStudio/studio/src/studio/crew.py#12-54
- Solo Mode (default) runs crews in a sandboxed subprocess for resilience; disable by setting `STUDIO_SOLO_MODE=false` only if you need full liteLLM proxy features.@/Users/orcpunk/Repos/_TheGameStudio/studio/README.md#95-113

## 6. Suggested Workflow for Idea Evaluations

1. Draft an input blurb (genre, platform, player fantasy, constraints).
2. Decide scope:
   - Quick check → `market` phase.
   - Production readiness → run `pipeline`.
3. Ask Cascade to run the command or execute it locally.
4. Review the markdown verdict in chat and the saved file; iterate before escalating to the next phase.

## 7. Extending the Studio

- Add or edit agents in `src/studio/config/agents.yaml` and tasks in `src/studio/config/tasks.yaml` to customize roles or add new phases.
- Switch LLM providers by adjusting `STUDIO_MODEL` and supplying the matching API key (`GROQ_API_KEY`, `OPENAI_API_KEY`, etc.).@/Users/orcpunk/Repos/_TheGameStudio/studio/README.md#205-236 @/Users/orcpunk/Repos/_TheGameStudio/studio/src/studio/crew.py#20-53

Keep this guide up to date as workflows evolve so Cascade always has a canonical reference when orchestrating the Studio crew.
