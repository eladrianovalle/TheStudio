# API Reference

Complete API reference for programmatic use of the Studio agent system.

## Core Classes

### `StudioCrew`

Main class for orchestrating agent evaluations.

```python
from studio.crew import StudioCrew
```

#### Constructor

```python
StudioCrew(phase: str = 'market')
```

**Parameters:**
- `phase` (str): Evaluation phase name. Must match agent definitions in `config/agents.yaml`
  - Default: `'market'`
  - Available: `'market'`, `'design'`, `'tech'`
  - Extensible: Add custom phases via YAML configuration

**Raises:**
- `ValueError`: If `GEMINI_API_KEY` environment variable not found

**Example:**
```python
crew = StudioCrew(phase='market')
```

#### Methods

##### `crew() -> Crew`

Assembles and returns the configured Crew instance.

**Returns:**
- `Crew`: CrewAI Crew object with agents and tasks configured

**Example:**
```python
crew_instance = StudioCrew(phase='market').crew()
```

##### `advocate() -> Agent`

Returns the Advocate agent for the current phase.

**Returns:**
- `Agent`: CrewAI Agent configured from `{phase}_advocate` in YAML

**Example:**
```python
studio = StudioCrew(phase='design')
advocate_agent = studio.advocate()
```

##### `contrarian() -> Agent`

Returns the Contrarian agent for the current phase.

**Returns:**
- `Agent`: CrewAI Agent configured from `{phase}_contrarian` in YAML

**Example:**
```python
studio = StudioCrew(phase='tech')
contrarian_agent = studio.contrarian()
```

##### `steel_man_task() -> Task`

Returns the steel-manning task (Advocate's task).

**Returns:**
- `Task`: CrewAI Task configured from `steel_man_task` in YAML

##### `attack_task() -> Task`

Returns the attack task (Contrarian's task).

**Returns:**
- `Task`: CrewAI Task configured from `attack_task` in YAML

#### Properties

##### `agents_config`

Path to agents configuration file.

**Type:** `str`  
**Value:** `'config/agents.yaml'`

##### `tasks_config`

Path to tasks configuration file.

**Type:** `str`  
**Value:** `'config/tasks.yaml'`

##### `phase`

Current evaluation phase.

**Type:** `str`

##### `google_llm`

Configured LLM instance.

**Type:** `LLM`

## Usage Patterns

### Basic Evaluation

```python
from studio.crew import StudioCrew

# Create crew for specific phase
crew = StudioCrew(phase='market')

# Run evaluation
result = crew.crew().kickoff(inputs={'game_idea': 'Your concept'})

# Get result as string
result_str = str(result)

# Check verdict
is_approved = "APPROVED" in result_str
```

### Multi-Phase Pipeline

```python
from studio.crew import StudioCrew

def evaluate_concept(game_idea: str) -> dict:
    """Run full evaluation pipeline."""
    phases = ['market', 'design', 'tech']
    results = {}
    
    for phase in phases:
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': game_idea})
        results[phase] = str(result)
        
        # Stop if rejected
        if "REJECTED" in results[phase]:
            break
    
    return results
```

### Custom Input Variables

```python
# If you've extended tasks.yaml with custom variables
crew = StudioCrew(phase='market')
result = crew.crew().kickoff(inputs={
    'game_idea': 'Your concept',
    'target_platform': 'Steam',
    'budget': '$50k',
    'timeline': '6 months'
})
```

## Input Specification

### Required Inputs

All evaluations require at minimum:

```python
inputs = {
    'game_idea': str  # Description of the game concept
}
```

### Input Format Guidelines

**Minimum viable input:**
```python
inputs = {'game_idea': 'A horror game'}
```

**Recommended input:**
```python
inputs = {
    'game_idea': 'A 3D stealth horror roguelike for the web where an AI enemy learns from player behavior, featuring procedural environments and a Fear & Focus mechanic that affects gameplay'
}
```

**Best practice:**
- Be specific about genre, platform, and core mechanics
- Include unique selling points
- Mention target audience if relevant
- Keep under 500 characters for optimal performance

## Output Specification

### Return Type

```python
result: CrewOutput
```

The `kickoff()` method returns a `CrewOutput` object. Convert to string for text:

```python
result = crew.crew().kickoff(inputs=inputs)
result_str = str(result)
```

### Output Structure

Each phase returns text containing:

1. **Advocate Section**: Steel-manned proposal
2. **Contrarian Section**: Critical analysis with 3 flaws
3. **Verdict**: `VERDICT: APPROVED` or `VERDICT: REJECTED`

**Example output structure:**
```
[Advocate output - optimistic proposal]

[Contrarian output - critical analysis]
1. Fatal flaw one...
2. Fatal flaw two...
3. Fatal flaw three...

VERDICT: REJECTED
```

### Parsing Results

```python
def parse_result(result: str) -> dict:
    """Parse evaluation result."""
    return {
        'verdict': 'APPROVED' if 'APPROVED' in result else 'REJECTED',
        'full_text': result,
        'is_approved': 'APPROVED' in result
    }

result = crew.crew().kickoff(inputs={'game_idea': 'concept'})
parsed = parse_result(str(result))
```

## Error Handling

### Common Exceptions

#### `ValueError: GEMINI_API_KEY not found`

**Cause:** Missing API key in environment variables

**Solution:**
```python
import os
os.environ['GEMINI_API_KEY'] = 'your_key_here'

# Or use .env file
from dotenv import load_dotenv
load_dotenv()
```

#### `KeyError: '{phase}_advocate'`

**Cause:** Phase not defined in `config/agents.yaml`

**Solution:**
- Verify phase name matches YAML keys
- Check YAML syntax
- Ensure both `{phase}_advocate` and `{phase}_contrarian` exist

#### `APIError` from Google Gemini

**Cause:** API rate limits, invalid key, or network issues

**Solution:**
```python
from google.genai.errors import APIError

try:
    result = crew.crew().kickoff(inputs={'game_idea': 'concept'})
except APIError as e:
    print(f"API Error: {e}")
    # Implement retry logic or fallback
```

### Robust Error Handling

```python
from studio.crew import StudioCrew
from google.genai.errors import APIError

def safe_evaluate(game_idea: str, phase: str = 'market') -> dict:
    """Safely evaluate with comprehensive error handling."""
    try:
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': game_idea})
        
        return {
            'success': True,
            'phase': phase,
            'result': str(result),
            'verdict': 'APPROVED' if 'APPROVED' in str(result) else 'REJECTED'
        }
        
    except ValueError as e:
        return {
            'success': False,
            'error': 'configuration_error',
            'message': str(e)
        }
        
    except APIError as e:
        return {
            'success': False,
            'error': 'api_error',
            'message': str(e)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': 'unknown_error',
            'message': str(e)
        }
```

## Environment Variables

### Required

| Variable | Type | Description |
|----------|------|-------------|
| `GEMINI_API_KEY` | string | Google Gemini API key |

### Optional

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MODEL` | string | `gemini-2.5-flash` | Gemini model name |
| `GOOGLE_CLOUD_PROJECT` | string | None | For Vertex AI integration |
| `GOOGLE_CLOUD_LOCATION` | string | `us-central1` | Vertex AI location |
| `GOOGLE_GENAI_USE_VERTEXAI` | boolean | `false` | Use Vertex AI instead of API |
| `CREWAI_TRACING_ENABLED` | boolean | `false` | Enable execution tracing |

### Setting Environment Variables

**Via Python:**
```python
import os
os.environ['GEMINI_API_KEY'] = 'your_key'
os.environ['CREWAI_TRACING_ENABLED'] = 'true'
```

**Via .env file:**
```bash
GEMINI_API_KEY=your_key_here
MODEL=gemini-2.5-flash
CREWAI_TRACING_ENABLED=true
```

**Via shell:**
```bash
export GEMINI_API_KEY=your_key
export CREWAI_TRACING_ENABLED=true
```

## Configuration Files

### `config/agents.yaml`

Defines agent personalities and behaviors.

**Structure:**
```yaml
{phase}_advocate:
  role: string           # Agent's job title
  goal: string          # What agent tries to achieve (supports {variables})
  backstory: string     # Context shaping behavior

{phase}_contrarian:
  role: string
  goal: string
  backstory: string
```

**Example:**
```yaml
market_advocate:
  role: "Market Growth Strategist"
  goal: "Steel-man the game idea {game_idea} into a high-virality Steam hook."
  backstory: "You specialize in indie trends and 'screenshot-ability'."
```

### `config/tasks.yaml`

Defines task patterns and expected outputs.

**Structure:**
```yaml
task_name:
  description: string    # Task instructions (supports {variables})
  expected_output: string  # Output format specification
```

**Example:**
```yaml
steel_man_task:
  description: >
    Take the initial idea: {game_idea} and present its strongest possible form.
    Pre-emptively solve obvious problems.
  expected_output: "A high-conviction proposal document."
```

## Advanced Usage

### Custom LLM Configuration

```python
from studio.crew import StudioCrew
from crewai import LLM
import os

class CustomStudioCrew(StudioCrew):
    def __init__(self, phase='market', model='gemini-2.5-pro'):
        self.phase = phase
        api_key = os.environ.get("GEMINI_API_KEY")
        
        # Use custom model
        self.google_llm = LLM(
            model=model,
            api_key=api_key,
            temperature=0.7  # Custom temperature
        )
```

### Accessing Individual Agents

```python
crew = StudioCrew(phase='market')

# Get agents directly
advocate = crew.advocate()
contrarian = crew.contrarian()

# Use agents independently
advocate_response = advocate.execute_task(
    task=crew.steel_man_task(),
    context="Custom context"
)
```

### Custom Task Execution

```python
from crewai import Task

crew = StudioCrew(phase='market')

# Create custom task
custom_task = Task(
    description="Analyze market trends for {game_idea}",
    expected_output="Market analysis report",
    agent=crew.advocate()
)

# Execute
result = custom_task.execute(context={'game_idea': 'Your concept'})
```

### Parallel Phase Execution

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

def evaluate_phase(phase: str, game_idea: str) -> tuple[str, str]:
    """Evaluate single phase."""
    crew = StudioCrew(phase=phase)
    result = crew.crew().kickoff(inputs={'game_idea': game_idea})
    return phase, str(result)

def parallel_evaluate(game_idea: str) -> dict:
    """Evaluate all phases in parallel."""
    phases = ['market', 'design', 'tech']
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(evaluate_phase, phase, game_idea)
            for phase in phases
        ]
        
        results = {}
        for future in futures:
            phase, result = future.result()
            results[phase] = result
        
        return results
```

## Performance Optimization

### Caching Results

```python
import hashlib
import json
from pathlib import Path

class CachedStudioCrew:
    def __init__(self, cache_dir: str = '.studio_cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _cache_key(self, game_idea: str, phase: str) -> str:
        """Generate cache key."""
        return hashlib.md5(f"{game_idea}:{phase}".encode()).hexdigest()
    
    def evaluate(self, game_idea: str, phase: str) -> str:
        """Evaluate with caching."""
        cache_file = self.cache_dir / f"{self._cache_key(game_idea, phase)}.json"
        
        # Check cache
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)['result']
        
        # Evaluate
        crew = StudioCrew(phase=phase)
        result = str(crew.crew().kickoff(inputs={'game_idea': game_idea}))
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump({'game_idea': game_idea, 'phase': phase, 'result': result}, f)
        
        return result
```

### Rate Limiting

```python
import time
from functools import wraps

def rate_limit(calls_per_minute: int = 10):
    """Rate limit decorator."""
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            wait_time = min_interval - elapsed
            
            if wait_time > 0:
                time.sleep(wait_time)
            
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        
        return wrapper
    return decorator

@rate_limit(calls_per_minute=10)
def evaluate_with_rate_limit(game_idea: str, phase: str) -> str:
    """Evaluate with rate limiting."""
    crew = StudioCrew(phase=phase)
    return str(crew.crew().kickoff(inputs={'game_idea': game_idea}))
```

## Testing

### Unit Testing

```python
import unittest
from studio.crew import StudioCrew

class TestStudioCrew(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.test_idea = "A 3D stealth horror roguelike"
    
    def test_crew_initialization(self):
        """Test crew initializes correctly."""
        crew = StudioCrew(phase='market')
        self.assertEqual(crew.phase, 'market')
        self.assertIsNotNone(crew.google_llm)
    
    def test_agent_loading(self):
        """Test agents load from YAML."""
        crew = StudioCrew(phase='market')
        advocate = crew.advocate()
        contrarian = crew.contrarian()
        
        self.assertIsNotNone(advocate)
        self.assertIsNotNone(contrarian)
    
    def test_evaluation_returns_result(self):
        """Test evaluation returns valid result."""
        crew = StudioCrew(phase='market')
        result = crew.crew().kickoff(inputs={'game_idea': self.test_idea})
        
        self.assertIsNotNone(result)
        result_str = str(result)
        self.assertTrue(len(result_str) > 0)
        self.assertTrue('VERDICT' in result_str)
```

### Integration Testing

```python
def test_full_pipeline():
    """Test complete evaluation pipeline."""
    game_idea = "A 3D stealth horror roguelike"
    phases = ['market', 'design', 'tech']
    
    for phase in phases:
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': game_idea})
        result_str = str(result)
        
        # Verify result structure
        assert 'VERDICT' in result_str
        assert 'APPROVED' in result_str or 'REJECTED' in result_str
        
        print(f"✓ {phase} phase completed")
```

## Related Documentation

- **[README.md](../README.md)** - Getting started guide
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System design and patterns
- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Integration examples
- **[AGENTS_REFERENCE.md](./AGENTS_REFERENCE.md)** - Agent documentation

## External Resources

- **CrewAI Documentation**: [docs.crewai.com](https://docs.crewai.com)
- **Google Gemini API**: [ai.google.dev/gemini-api/docs](https://ai.google.dev/gemini-api/docs)
- **Python Type Hints**: [docs.python.org/3/library/typing.html](https://docs.python.org/3/library/typing.html)
