# The Game Studio - Centralized AI Agent System

A **centralized multi-agent AI system** designed to provide reusable, specialized agents that can be integrated into any project within your Windsurf workspace. This Studio uses a "Steel Man vs. Contrarian" debate pattern to rigorously evaluate ideas across multiple phases (Market, Design, Tech).

## 🎯 Core Concept

The Studio acts as a **shared service** that other projects can import and use. Instead of recreating agents for each project, you define them once here and invoke them from anywhere.

### Key Benefits
- **Reusability**: Define agents once, use them across multiple projects
- **Consistency**: Same agent personalities and behaviors everywhere
- **Centralized Configuration**: Update agent behavior in one place
- **Phase-Based Workflows**: Market → Design → Tech evaluation pipeline
- **Debate-Driven Quality**: Advocate vs. Contrarian pattern ensures thorough analysis

## 🏗️ Architecture

```
Studio (This Project)
├── Agents (Advocate & Contrarian per phase)
├── Tasks (Steel Man & Attack patterns)
└── LLM Configuration (Google Gemini)

Your Other Projects
├── Import Studio as package
├── Instantiate agents with custom inputs
└── Get structured feedback
```

## 🚀 Quick Start

### 1. Installation

```bash
cd studio
pip install uv
crewai install
```

### 2. Configuration

Create a `.env` file:
```bash
GEMINI_API_KEY=your_api_key_here
MODEL=gemini-2.5-flash
```

### 3. Test the Studio

```bash
crewai run
```

This runs the default market analysis on a sample game idea.

## 📦 Using Studio in Other Projects

### Method 1: Windsurf/Cascade (Recommended for Conversations)

**Talk to your Studio agents from any project in Windsurf!**

1. **One-time setup** - Add to your `~/.zshrc`:
```bash
export PATH="/Users/orcpunk/Repos/_TheGameStudio/studio:$PATH"
```

2. **Use from any project** - Just ask Cascade:

> "Use Studio to evaluate this game idea: A 3D stealth horror roguelike"

> "Run my concept through all Studio phases: A cozy farming sim with time travel"

> "Check the technical feasibility using Studio: A multiplayer card battler"

Cascade will run the Studio agents and show you the evaluation results in chat.

**See [WINDSURF_USAGE.md](./docs/WINDSURF_USAGE.md) for complete guide with examples.**

---

### Method 2: Direct Import (Python Projects)

From any project in your Windsurf workspace:

```python
import sys
sys.path.append('/Users/orcpunk/Repos/_TheGameStudio/studio/src')

from studio.crew import StudioCrew

# Use the Studio agents
inputs = {'game_idea': 'Your project concept here'}
result = StudioCrew(phase='market').crew().kickoff(inputs=inputs)
print(result)
```

### Method 3: Install as Package

```bash
# From your other project
pip install -e /Users/orcpunk/Repos/_TheGameStudio/studio
```

Then use it:
```python
from studio.crew import StudioCrew

result = StudioCrew(phase='design').crew().kickoff(
    inputs={'game_idea': 'Your concept'}
)
```

### Method 4: API Service (Advanced)

Run Studio as a service that other projects can call via HTTP (see `INTEGRATION_GUIDE.md`).

## 🎭 Available Phases

Each phase has an **Advocate** (steel-mans the idea) and a **Contrarian** (finds flaws):

### Market Phase
- **Advocate**: Market Growth Strategist - Optimizes for virality and Steam appeal
- **Contrarian**: Reality Check - Identifies fatal market flaws
- **Output**: Market viability verdict (APPROVED/REJECTED)

### Design Phase  
- **Advocate**: Lead Systems Designer - Creates "Minimum Viable Fun" core loop
- **Contrarian**: Scope-Creep Police - Attacks complexity and timeline feasibility
- **Output**: Design feasibility verdict

### Tech Phase
- **Advocate**: Three.js Technical Architect - Defines optimal WebGL architecture
- **Contrarian**: Senior SRE - Identifies performance and compatibility issues
- **Output**: Technical feasibility verdict

## 🔧 Customization

### Adding New Phases

1. Add agents to `src/studio/config/agents.yaml`:
```yaml
yourphase_advocate:
  role: "Your Advocate Role"
  goal: "Steel-man the concept for [specific aspect]"
  backstory: "Your expertise description"

yourphase_contrarian:
  role: "Your Contrarian Role"
  goal: "Find critical flaws in [specific aspect]"
  backstory: "Your critical perspective"
```

2. The `StudioCrew` class automatically loads agents based on phase name

### Changing the LLM

Edit `src/studio/crew.py`:
```python
self.google_llm = LLM(
    model="gemini-2.5-pro",  # or gemini-2.0-flash
    api_key=api_key
)
```

### Custom Task Patterns

Modify `src/studio/config/tasks.yaml` to change how agents interact.

## 📚 Documentation

- **[WINDSURF_USAGE.md](./docs/WINDSURF_USAGE.md)** - Using Studio from Windsurf/Cascade (START HERE!)
- **[QUICKSTART.md](./docs/QUICKSTART.md)** - 5-minute integration guide
- **[ARCHITECTURE.md](./docs/ARCHITECTURE.md)** - System design and patterns
- **[INTEGRATION_GUIDE.md](./docs/INTEGRATION_GUIDE.md)** - Detailed integration examples
- **[AGENTS_REFERENCE.md](./docs/AGENTS_REFERENCE.md)** - Complete agent documentation
- **[API.md](./docs/API.md)** - API reference for programmatic use

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `MODEL` | No | Model name (default: gemini-2.5-flash) |
| `GOOGLE_CLOUD_PROJECT` | No | For Vertex AI integration |
| `CREWAI_TRACING_ENABLED` | No | Enable execution tracing |

## 🎮 Example: Game Project Integration

```python
# In your game project
from studio.crew import StudioCrew

# Phase 1: Market validation
market_result = StudioCrew(phase='market').crew().kickoff(
    inputs={'game_idea': 'A 3D stealth horror roguelike'}
)

if "APPROVED" in market_result:
    # Phase 2: Design validation
    design_result = StudioCrew(phase='design').crew().kickoff(
        inputs={'game_idea': 'A 3D stealth horror roguelike'}
    )
    
    if "APPROVED" in design_result:
        # Phase 3: Tech validation
        tech_result = StudioCrew(phase='tech').crew().kickoff(
            inputs={'game_idea': 'A 3D stealth horror roguelike'}
        )
```

## 🛠️ Development

```bash
# Run tests
crewai test

# Train agents (if using training data)
crewai train

# Replay previous executions
crewai replay <task_id>
```

## 🤝 Support

- **CrewAI Docs**: [docs.crewai.com](https://docs.crewai.com)
- **Google Gemini**: [ai.google.dev](https://ai.google.dev/gemini-api/docs)
- **Issues**: File issues in this repository

## 📝 License

MIT License - Use this Studio in any of your projects.
