# Integration Guide

This guide provides step-by-step instructions for integrating the Studio agents into your projects within Windsurf.

## Table of Contents
- [Quick Integration](#quick-integration)
- [Method 1: Direct Import](#method-1-direct-import-development)
- [Method 2: Editable Package Install](#method-2-editable-package-install-recommended)
- [Method 3: API Service](#method-3-api-service-advanced)
- [Real-World Examples](#real-world-examples)
- [Troubleshooting](#troubleshooting)

## Quick Integration

The fastest way to use Studio agents in another project:

```python
# In your project file
import sys
sys.path.append('/Users/orcpunk/Repos/_TheGameStudio/studio/src')

from studio.crew import StudioCrew

# Evaluate your idea
result = StudioCrew(phase='market').crew().kickoff(
    inputs={'game_idea': 'Your game concept here'}
)

print(result)
```

## Method 1: Direct Import (Development)

### When to Use
- Quick prototyping
- Single project development
- Testing Studio changes immediately

### Setup Steps

1. **In your project file**, add the Studio path:

```python
import sys
import os

# Add Studio to Python path
studio_path = '/Users/orcpunk/Repos/_TheGameStudio/studio/src'
if studio_path not in sys.path:
    sys.path.append(studio_path)

from studio.crew import StudioCrew
```

2. **Set up environment variables**:

```python
# Option A: Load from Studio's .env
from dotenv import load_dotenv
load_dotenv('/Users/orcpunk/Repos/_TheGameStudio/studio/.env')

# Option B: Set in your project's .env
# GEMINI_API_KEY=your_key_here
```

3. **Use the agents**:

```python
def validate_game_idea(idea: str) -> dict:
    """Validate a game idea through all phases."""
    results = {}
    
    # Market phase
    market_crew = StudioCrew(phase='market')
    results['market'] = market_crew.crew().kickoff(
        inputs={'game_idea': idea}
    )
    
    # Design phase
    design_crew = StudioCrew(phase='design')
    results['design'] = design_crew.crew().kickoff(
        inputs={'game_idea': idea}
    )
    
    # Tech phase
    tech_crew = StudioCrew(phase='tech')
    results['tech'] = tech_crew.crew().kickoff(
        inputs={'game_idea': idea}
    )
    
    return results

# Use it
results = validate_game_idea("A 3D stealth horror roguelike for the web")
print(results['market'])
```

### Pros & Cons

✅ **Pros:**
- No installation required
- See Studio changes immediately
- Easy to debug

❌ **Cons:**
- Path management can be fragile
- Not portable across different machines
- Requires manual path configuration

## Method 2: Editable Package Install (Recommended)

### When to Use
- Multiple projects using Studio
- Team development
- Production-ready integration

### Setup Steps

1. **Install Studio as editable package**:

```bash
# From your project directory
pip install -e /Users/orcpunk/Repos/_TheGameStudio/studio
```

Or add to your `requirements.txt`:
```txt
-e /Users/orcpunk/Repos/_TheGameStudio/studio
```

2. **Import and use** (no path manipulation needed):

```python
from studio.crew import StudioCrew

# Use directly
result = StudioCrew(phase='market').crew().kickoff(
    inputs={'game_idea': 'Your concept'}
)
```

3. **Create a wrapper class** for your project:

```python
# game_validator.py
from studio.crew import StudioCrew
from typing import Literal

Phase = Literal['market', 'design', 'tech']

class GameValidator:
    """Wrapper for Studio agents specific to game validation."""
    
    def __init__(self):
        self.phases = ['market', 'design', 'tech']
    
    def validate_phase(self, phase: Phase, game_idea: str) -> str:
        """Validate a single phase."""
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': game_idea})
        return str(result)
    
    def validate_all(self, game_idea: str) -> dict[str, str]:
        """Run all validation phases."""
        results = {}
        for phase in self.phases:
            print(f"Running {phase} phase...")
            results[phase] = self.validate_phase(phase, game_idea)
            
            # Stop if rejected
            if "REJECTED" in results[phase]:
                print(f"❌ Rejected in {phase} phase")
                break
        
        return results
    
    def get_verdict(self, phase_result: str) -> bool:
        """Extract verdict from phase result."""
        return "APPROVED" in phase_result

# Usage
validator = GameValidator()
results = validator.validate_all("A 3D stealth horror roguelike")

if validator.get_verdict(results.get('tech', '')):
    print("✅ Concept approved for development!")
```

### Pros & Cons

✅ **Pros:**
- Clean imports everywhere
- Changes to Studio reflected immediately
- Works across multiple projects
- Professional setup

❌ **Cons:**
- Requires pip install step
- Virtual environment management

## Method 3: API Service (Advanced)

### When to Use
- Non-Python projects
- Remote access needed
- Microservices architecture
- Multiple teams/services

### Setup Steps

1. **Create API service** in Studio:

```python
# studio/api.py (create this file)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from studio.crew import StudioCrew
import os

app = FastAPI(title="Studio Agent API")

class EvaluationRequest(BaseModel):
    game_idea: str
    phase: str = "market"

class EvaluationResponse(BaseModel):
    phase: str
    result: str
    verdict: str

@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_idea(request: EvaluationRequest):
    """Evaluate a game idea using Studio agents."""
    try:
        crew = StudioCrew(phase=request.phase)
        result = crew.crew().kickoff(
            inputs={'game_idea': request.game_idea}
        )
        
        result_str = str(result)
        verdict = "APPROVED" if "APPROVED" in result_str else "REJECTED"
        
        return EvaluationResponse(
            phase=request.phase,
            result=result_str,
            verdict=verdict
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.get("/phases")
async def list_phases():
    """List available evaluation phases."""
    return {
        "phases": ["market", "design", "tech"],
        "description": "Available evaluation phases"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

2. **Run the service**:

```bash
cd /Users/orcpunk/Repos/_TheGameStudio/studio
python api.py
```

3. **Use from any project** (Python example):

```python
import requests

def evaluate_via_api(game_idea: str, phase: str = "market") -> dict:
    """Call Studio API to evaluate an idea."""
    response = requests.post(
        "http://localhost:8000/evaluate",
        json={"game_idea": game_idea, "phase": phase}
    )
    response.raise_for_status()
    return response.json()

# Use it
result = evaluate_via_api("A 3D stealth horror roguelike", phase="market")
print(f"Verdict: {result['verdict']}")
print(f"Details: {result['result']}")
```

4. **Use from JavaScript/TypeScript**:

```typescript
// In your JavaScript/TypeScript project
async function evaluateIdea(gameIdea: string, phase: string = 'market') {
    const response = await fetch('http://localhost:8000/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_idea: gameIdea, phase })
    });
    
    if (!response.ok) {
        throw new Error(`Evaluation failed: ${response.statusText}`);
    }
    
    return await response.json();
}

// Use it
const result = await evaluateIdea('A 3D stealth horror roguelike', 'market');
console.log(`Verdict: ${result.verdict}`);
```

### Pros & Cons

✅ **Pros:**
- Language-agnostic (use from any language)
- Centralized execution
- Easy to scale
- Can be deployed remotely

❌ **Cons:**
- Requires service management
- Network latency
- More complex setup
- Need to handle service availability

## Real-World Examples

### Example 1: Game Concept Pipeline

```python
# game_pipeline.py
from studio.crew import StudioCrew
from dataclasses import dataclass
from typing import Optional

@dataclass
class GameConcept:
    idea: str
    market_approved: bool = False
    design_approved: bool = False
    tech_approved: bool = False
    market_feedback: Optional[str] = None
    design_feedback: Optional[str] = None
    tech_feedback: Optional[str] = None

def run_concept_pipeline(idea: str) -> GameConcept:
    """Run a game concept through the full Studio pipeline."""
    concept = GameConcept(idea=idea)
    
    # Phase 1: Market
    print("🎯 Phase 1: Market Analysis")
    market_result = StudioCrew(phase='market').crew().kickoff(
        inputs={'game_idea': idea}
    )
    concept.market_feedback = str(market_result)
    concept.market_approved = "APPROVED" in concept.market_feedback
    
    if not concept.market_approved:
        print("❌ Market phase rejected. Stopping pipeline.")
        return concept
    
    # Phase 2: Design
    print("\n🎨 Phase 2: Design Validation")
    design_result = StudioCrew(phase='design').crew().kickoff(
        inputs={'game_idea': idea}
    )
    concept.design_feedback = str(design_result)
    concept.design_approved = "APPROVED" in concept.design_feedback
    
    if not concept.design_approved:
        print("❌ Design phase rejected. Stopping pipeline.")
        return concept
    
    # Phase 3: Tech
    print("\n⚙️ Phase 3: Technical Feasibility")
    tech_result = StudioCrew(phase='tech').crew().kickoff(
        inputs={'game_idea': idea}
    )
    concept.tech_feedback = str(tech_result)
    concept.tech_approved = "APPROVED" in concept.tech_feedback
    
    if concept.tech_approved:
        print("\n✅ Concept approved for development!")
    else:
        print("\n❌ Tech phase rejected.")
    
    return concept

# Usage
concept = run_concept_pipeline("A 3D stealth horror roguelike for the web")

# Save results
with open('concept_evaluation.txt', 'w') as f:
    f.write(f"Game Idea: {concept.idea}\n\n")
    f.write(f"Market: {'✅ APPROVED' if concept.market_approved else '❌ REJECTED'}\n")
    f.write(f"{concept.market_feedback}\n\n")
    if concept.design_feedback:
        f.write(f"Design: {'✅ APPROVED' if concept.design_approved else '❌ REJECTED'}\n")
        f.write(f"{concept.design_feedback}\n\n")
    if concept.tech_feedback:
        f.write(f"Tech: {'✅ APPROVED' if concept.tech_approved else '❌ REJECTED'}\n")
        f.write(f"{concept.tech_feedback}\n\n")
```

### Example 2: Batch Evaluation

```python
# batch_evaluator.py
from studio.crew import StudioCrew
import json
from pathlib import Path

def batch_evaluate_concepts(concepts_file: str, output_file: str):
    """Evaluate multiple game concepts and save results."""
    
    # Load concepts
    with open(concepts_file, 'r') as f:
        concepts = json.load(f)
    
    results = []
    
    for i, concept in enumerate(concepts, 1):
        print(f"\n{'='*60}")
        print(f"Evaluating concept {i}/{len(concepts)}: {concept['name']}")
        print(f"{'='*60}")
        
        # Evaluate market phase only (quick filter)
        crew = StudioCrew(phase='market')
        result = crew.crew().kickoff(
            inputs={'game_idea': concept['description']}
        )
        
        result_str = str(result)
        verdict = "APPROVED" if "APPROVED" in result_str else "REJECTED"
        
        results.append({
            'name': concept['name'],
            'description': concept['description'],
            'verdict': verdict,
            'feedback': result_str
        })
        
        print(f"Result: {verdict}")
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    approved = sum(1 for r in results if r['verdict'] == 'APPROVED')
    print(f"\n{'='*60}")
    print(f"Summary: {approved}/{len(results)} concepts approved")
    print(f"{'='*60}")

# Usage
# Create concepts.json first:
# [
#   {"name": "Concept A", "description": "..."},
#   {"name": "Concept B", "description": "..."}
# ]

batch_evaluate_concepts('concepts.json', 'evaluation_results.json')
```

### Example 3: Interactive CLI Tool

```python
# studio_cli.py
import click
from studio.crew import StudioCrew

@click.group()
def cli():
    """Studio Agent CLI - Evaluate game concepts."""
    pass

@cli.command()
@click.argument('idea')
@click.option('--phase', default='market', help='Evaluation phase')
def evaluate(idea: str, phase: str):
    """Evaluate a game idea."""
    click.echo(f"Evaluating: {idea}")
    click.echo(f"Phase: {phase}\n")
    
    with click.progressbar(length=1, label='Running evaluation') as bar:
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': idea})
        bar.update(1)
    
    click.echo("\n" + "="*60)
    click.echo(str(result))
    click.echo("="*60)

@cli.command()
@click.argument('idea')
def full_pipeline(idea: str):
    """Run full evaluation pipeline."""
    phases = ['market', 'design', 'tech']
    
    for phase in phases:
        click.echo(f"\n{'='*60}")
        click.echo(f"Phase: {phase.upper()}")
        click.echo(f"{'='*60}\n")
        
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': idea})
        result_str = str(result)
        
        click.echo(result_str)
        
        if "REJECTED" in result_str:
            click.echo(f"\n❌ Rejected in {phase} phase. Stopping.")
            break
    else:
        click.echo("\n✅ Passed all phases!")

if __name__ == '__main__':
    cli()

# Usage:
# python studio_cli.py evaluate "A 3D stealth horror roguelike"
# python studio_cli.py full-pipeline "A 3D stealth horror roguelike"
```

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'studio'

**Solution 1** (Direct Import):
```python
import sys
sys.path.append('/Users/orcpunk/Repos/_TheGameStudio/studio/src')
```

**Solution 2** (Editable Install):
```bash
pip install -e /Users/orcpunk/Repos/_TheGameStudio/studio
```

### Issue: GEMINI_API_KEY not found

**Solution**:
```python
# Option 1: Load from Studio's .env
from dotenv import load_dotenv
load_dotenv('/Users/orcpunk/Repos/_TheGameStudio/studio/.env')

# Option 2: Set in your project
import os
os.environ['GEMINI_API_KEY'] = 'your_key_here'

# Option 3: Create .env in your project
# GEMINI_API_KEY=your_key_here
```

### Issue: Agents not loading correctly

**Check**:
1. Verify phase name matches YAML: `market`, `design`, or `tech`
2. Check YAML syntax in `config/agents.yaml`
3. Ensure agent naming: `{phase}_advocate` and `{phase}_contrarian`

### Issue: Slow execution

**Solutions**:
- Use `gemini-2.5-flash` instead of `gemini-2.5-pro`
- Run phases in parallel if independent
- Cache results for repeated evaluations

### Issue: API service not starting

**Check**:
1. FastAPI installed: `pip install fastapi uvicorn`
2. Port 8000 not in use: `lsof -i :8000`
3. Environment variables set correctly

## Best Practices

### 1. Error Handling

```python
from studio.crew import StudioCrew

def safe_evaluate(idea: str, phase: str) -> dict:
    """Safely evaluate with error handling."""
    try:
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': idea})
        return {
            'success': True,
            'result': str(result),
            'verdict': 'APPROVED' if 'APPROVED' in str(result) else 'REJECTED'
        }
    except ValueError as e:
        return {'success': False, 'error': f'Configuration error: {e}'}
    except Exception as e:
        return {'success': False, 'error': f'Evaluation failed: {e}'}
```

### 2. Caching Results

```python
import hashlib
import json
from pathlib import Path

def get_cache_key(idea: str, phase: str) -> str:
    """Generate cache key for idea + phase."""
    return hashlib.md5(f"{idea}:{phase}".encode()).hexdigest()

def cached_evaluate(idea: str, phase: str, cache_dir: str = '.cache') -> str:
    """Evaluate with caching."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(exist_ok=True)
    
    cache_key = get_cache_key(idea, phase)
    cache_file = cache_path / f"{cache_key}.json"
    
    # Check cache
    if cache_file.exists():
        with open(cache_file, 'r') as f:
            return json.load(f)['result']
    
    # Evaluate
    crew = StudioCrew(phase=phase)
    result = str(crew.crew().kickoff(inputs={'game_idea': idea}))
    
    # Save to cache
    with open(cache_file, 'w') as f:
        json.dump({'idea': idea, 'phase': phase, 'result': result}, f)
    
    return result
```

### 3. Logging

```python
import logging
from studio.crew import StudioCrew

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def logged_evaluate(idea: str, phase: str) -> str:
    """Evaluate with logging."""
    logger.info(f"Starting evaluation: phase={phase}, idea={idea[:50]}...")
    
    try:
        crew = StudioCrew(phase=phase)
        result = crew.crew().kickoff(inputs={'game_idea': idea})
        result_str = str(result)
        
        verdict = 'APPROVED' if 'APPROVED' in result_str else 'REJECTED'
        logger.info(f"Evaluation complete: verdict={verdict}")
        
        return result_str
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        raise
```

## Next Steps

- Review **[AGENTS_REFERENCE.md](./AGENTS_REFERENCE.md)** for detailed agent documentation
- Check **[ARCHITECTURE.md](./ARCHITECTURE.md)** for system design details
- See **[API.md](./API.md)** for complete API reference
