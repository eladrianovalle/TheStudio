# Studio Architecture

## Overview

The Studio is a **centralized multi-agent system** built on CrewAI that provides reusable AI agents for evaluating ideas, designs, and technical implementations. It uses a debate-driven pattern where specialized agents argue for and against concepts to surface insights.

## Design Philosophy

### 1. Centralization
All agents are defined in one place, making them:
- Easy to maintain and update
- Consistent across all projects
- Version-controlled and auditable

### 2. Phase-Based Evaluation
Ideas progress through distinct phases:
```
Market Phase → Design Phase → Tech Phase
```

Each phase has its own specialized agents that understand domain-specific concerns.

### 3. Debate-Driven Quality
Every phase uses two agents:
- **Advocate**: Steel-mans the idea (presents strongest possible case)
- **Contrarian**: Attacks the idea (finds critical flaws)

This ensures balanced, thorough evaluation.

## System Components

### Core Classes

#### `StudioCrew` (`src/studio/crew.py`)
The main orchestrator class that:
- Initializes LLM configuration
- Loads phase-specific agents from YAML
- Defines task execution patterns
- Manages crew assembly and execution

```python
@CrewBase
class StudioCrew():
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'
    
    def __init__(self, phase='market'):
        self.phase = phase
        self.google_llm = LLM(model="gemini-2.5-flash", api_key=api_key)
```

**Key Features:**
- Phase-agnostic design (works with any phase defined in YAML)
- Automatic agent loading via `{phase}_advocate` and `{phase}_contrarian` naming
- Shared LLM configuration across all agents

### Configuration Files

#### `config/agents.yaml`
Defines agent personalities, roles, and expertise:

```yaml
market_advocate:
  role: "Market Growth Strategist"
  goal: "Steel-man the game idea {game_idea} into a high-virality Steam hook."
  backstory: "You specialize in indie trends and 'screenshot-ability'."
```

**Structure:**
- `{phase}_{role}` naming convention
- `role`: Agent's job title/identity
- `goal`: What the agent tries to achieve
- `backstory`: Context that shapes agent behavior

#### `config/tasks.yaml`
Defines task patterns and expected outputs:

```yaml
steel_man_task:
  description: >
    Take the initial idea: {game_idea} and present its strongest possible form.
  expected_output: "A high-conviction proposal document."
```

**Structure:**
- Generic task definitions (not phase-specific)
- Input variables via `{variable_name}` syntax
- Clear output expectations

### Execution Flow

```
1. Project calls StudioCrew(phase='market')
   ↓
2. StudioCrew.__init__() loads agents for 'market' phase
   ↓
3. crew() method assembles agents and tasks
   ↓
4. kickoff(inputs) starts execution
   ↓
5. Advocate runs steel_man_task
   ↓
6. Contrarian runs attack_task (sees advocate's output)
   ↓
7. Final verdict returned to calling project
```

## Integration Patterns

### Pattern 1: Direct Import (Development)

Best for: Local development, same workspace

```python
import sys
sys.path.append('/path/to/studio/src')
from studio.crew import StudioCrew

result = StudioCrew(phase='market').crew().kickoff(inputs={'game_idea': 'concept'})
```

**Pros:**
- No installation needed
- Easy to modify and test
- Direct access to source

**Cons:**
- Path management required
- Not portable across machines

### Pattern 2: Editable Install (Recommended)

Best for: Active development, multiple projects

```bash
pip install -e /path/to/studio
```

```python
from studio.crew import StudioCrew
result = StudioCrew(phase='design').crew().kickoff(inputs={'game_idea': 'concept'})
```

**Pros:**
- Clean imports
- Changes reflected immediately
- Works across projects

**Cons:**
- Requires pip install step
- Virtual environment considerations

### Pattern 3: API Service (Production)

Best for: Production, remote access, microservices

```python
# In studio/api.py (you would create this)
from fastapi import FastAPI
from studio.crew import StudioCrew

app = FastAPI()

@app.post("/evaluate/{phase}")
async def evaluate(phase: str, game_idea: str):
    result = StudioCrew(phase=phase).crew().kickoff(
        inputs={'game_idea': game_idea}
    )
    return {"result": str(result)}
```

**Pros:**
- Language-agnostic (any project can call via HTTP)
- Centralized execution
- Scalable

**Cons:**
- Requires service management
- Network overhead
- More complex setup

## Data Flow

### Input Processing
```
External Project Input
    ↓
StudioCrew(phase='X')
    ↓
Load {phase}_advocate & {phase}_contrarian from YAML
    ↓
Inject inputs into task descriptions
    ↓
Execute tasks sequentially
```

### Output Structure
```
Advocate Output (Steel Man)
    ↓
Passed to Contrarian as context
    ↓
Contrarian Output (Attack + Verdict)
    ↓
Returned to calling project
```

## Extensibility

### Adding New Phases

1. **Define agents** in `config/agents.yaml`:
```yaml
prototype_advocate:
  role: "Rapid Prototyper"
  goal: "Create a minimal playable prototype plan"
  backstory: "Expert in MVP development"

prototype_contrarian:
  role: "Quality Gatekeeper"
  goal: "Ensure prototype won't create technical debt"
  backstory: "Senior architect focused on maintainability"
```

2. **Use immediately** (no code changes needed):
```python
result = StudioCrew(phase='prototype').crew().kickoff(inputs={'game_idea': 'concept'})
```

The `StudioCrew` class automatically discovers and loads agents based on phase name.

### Adding New Task Patterns

Modify `config/tasks.yaml` to create new interaction patterns:

```yaml
brainstorm_task:
  description: "Generate 10 variations of: {game_idea}"
  expected_output: "List of 10 distinct variations"

filter_task:
  description: "Rank the variations by feasibility"
  expected_output: "Ranked list with justifications"
```

Then add corresponding `@task` methods to `StudioCrew`.

### Custom LLM Providers

The Studio uses CrewAI's `LLM` class, which supports:
- Google Gemini (current)
- OpenAI GPT models
- Anthropic Claude
- Azure OpenAI
- Local models via Ollama

Change in `crew.py`:
```python
# OpenAI
self.llm = LLM(model="gpt-4", api_key=openai_key)

# Anthropic
self.llm = LLM(model="claude-3-opus-20240229", api_key=anthropic_key)

# Local
self.llm = LLM(model="ollama/llama2")
```

## Performance Considerations

### Token Usage
- Each phase uses 2 agents (Advocate + Contrarian)
- Sequential execution means Contrarian sees full Advocate output
- Typical token usage: 2,000-5,000 tokens per phase
- Cost: ~$0.01-0.05 per evaluation (with Gemini Flash)

### Execution Time
- Market phase: 30-60 seconds
- Design phase: 45-90 seconds
- Tech phase: 60-120 seconds
- Total pipeline: 2-5 minutes

### Optimization Strategies
1. **Parallel phases**: Run independent phases concurrently
2. **Caching**: Cache results for identical inputs
3. **Streaming**: Use streaming responses for faster perceived performance
4. **Model selection**: Use Flash for speed, Pro for quality

## Security Considerations

### API Key Management
- Never commit `.env` files
- Use environment variables
- Consider secret management services (AWS Secrets Manager, etc.)

### Input Validation
- Sanitize user inputs before passing to agents
- Set token limits to prevent abuse
- Implement rate limiting for API service pattern

### Output Filtering
- Review agent outputs before displaying to end users
- Implement content moderation if needed
- Log all interactions for audit trails

## Monitoring & Debugging

### Enable Tracing
```bash
# In .env
CREWAI_TRACING_ENABLED=true
```

### Verbose Output
```python
StudioCrew(phase='market').crew().kickoff(inputs=inputs)
# Already set to verbose=True in crew definition
```

### Replay Executions
```bash
crewai replay <execution_id>
```

## Future Enhancements

### Potential Additions
1. **Agent Memory**: Persist learnings across evaluations
2. **Tool Integration**: Give agents access to web search, code analysis, etc.
3. **Multi-Model Support**: Use different models for different phases
4. **Async Execution**: Non-blocking agent operations
5. **Result Caching**: Store and reuse previous evaluations
6. **Agent Training**: Fine-tune agents on domain-specific data

### Scalability Path
```
Current: Single-machine, synchronous
    ↓
Next: API service with queue
    ↓
Future: Distributed agent execution
    ↓
Advanced: Multi-tenant SaaS platform
```

## Related Documentation

- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Step-by-step integration examples
- **[AGENTS_REFERENCE.md](./AGENTS_REFERENCE.md)** - Complete agent documentation
- **[API.md](./API.md)** - API reference for service pattern
