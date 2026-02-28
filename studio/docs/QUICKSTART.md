# Quick Start Guide

Get your Studio agents running in other projects in 5 minutes.

## What is the Studio?

A **centralized agent system** that you can use across all your projects in Windsurf. Define agents once, use them everywhere.

## 3 Ways to Use Studio

### 1. Direct Import (Fastest)

```python
# In any project file
import sys
sys.path.append('/Users/orcpunk/Repos/_TheGameStudio/studio/src')

from studio.crew import StudioCrew

result = StudioCrew(phase='market').crew().kickoff(
    inputs={'game_idea': 'Your concept here'}
)
print(result)
```

### 2. Package Install (Recommended)

```bash
# One-time setup in your project
pip install -e /Users/orcpunk/Repos/_TheGameStudio/studio
```

```python
# Then use anywhere
from studio.crew import StudioCrew

result = StudioCrew(phase='design').crew().kickoff(
    inputs={'game_idea': 'Your concept'}
)
```

### 3. API Service (Advanced)

See [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md#method-3-api-service-advanced)

## Available Phases

- **`market`** - Validates market viability
- **`design`** - Validates gameplay design
- **`tech`** - Validates technical feasibility

## Example: Full Pipeline

```python
from studio.crew import StudioCrew

idea = "A 3D stealth horror roguelike for the web"

# Run all phases
for phase in ['market', 'design', 'tech']:
    print(f"\n=== {phase.upper()} PHASE ===")
    
    crew = StudioCrew(phase=phase)
    result = crew.crew().kickoff(inputs={'game_idea': idea})
    
    print(result)
    
    # Stop if rejected
    if "REJECTED" in str(result):
        print(f"\n❌ Rejected in {phase} phase")
        break
```

## Environment Setup

Create `.env` in your project or use Studio's:

```bash
GEMINI_API_KEY=your_api_key_here
```

## Windsurf Workflow (Recommended)

Studio now includes a **Cascade-powered workflow** with:
- **Scope-based iteration** (enabled by default) - 20-30% token savings
- **Automatic rerun context** - Faster convergence on rejections
- **Validation** - Automated quality checks

See **[../STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md)** for the complete workflow.

## Next Steps

- **[../STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md)** - Windsurf workflow (recommended)
- **[SCOPES_GUIDE.md](./SCOPES_GUIDE.md)** - Scope-based iteration guide
- **[VALIDATION_GUIDE.md](./VALIDATION_GUIDE.md)** - Validation guide
- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Detailed integration examples
- **[AGENTS_REFERENCE.md](./AGENTS_REFERENCE.md)** - Agent documentation
- **[API.md](./API.md)** - Complete API reference
