# The Game Studio - Centralized AI Agent System

A **centralized multi-agent AI system** designed to provide reusable, specialized agents that can be integrated into any project within your Windsurf workspace. This Studio uses a "Steel Man vs. Contrarian" debate pattern to rigorously evaluate ideas across multiple phases (Market, Design, Tech).

## 🔧 Troubleshooting

### Common Issues

**"ModuleNotFoundError: No module named 'fastapi_sso'" or similar**
- This is expected in Solo Mode and doesn't affect functionality
- The subprocess isolation prevents these errors from crashing your runs
- If you need full litellm proxy features, install optional dependencies: `uv pip install -e ".[proxy]"`

**"RuntimeError: can't register atexit after shutdown"**
- This is a known litellm/apscheduler issue during Python shutdown
- Solo Mode's subprocess isolation prevents this from affecting your workflow
- Your results are still captured and saved even if this error occurs

**Crew execution times out**
- Default timeout is 10 minutes per phase
- For complex analyses, the crew may need more time
- Check `output/{phase}/` for partial results even if timeout occurs

**API key errors**
- Ensure `GEMINI_API_KEY` is set in your environment or `.env` file
- Verify the key is valid and has sufficient quota
- Check the preflight error message for specific remediation steps

### Stability Features

1. **Preflight Checks**: Validates critical dependencies before execution
2. **Subprocess Isolation**: Prevents crashes from affecting parent process
3. **Graceful Error Handling**: Captures and saves partial results on failure
4. **Automatic Retries**: (Coming soon) Retry logic for transient API failures

## 🎯 Core Concept

The Studio acts as a **shared service** that other projects can import and use. Instead of recreating agents for each project, you define them once here and invoke them from anywhere.

### Key Benefits
- **Reusability**: Define agents once, use them across multiple projects
- **Consistency**: Same agent personalities and behaviors everywhere
- **Centralized Configuration**: Update agent behavior in one place
- **Phase-Based Workflows**: Market → Design → Tech evaluation pipeline
- **Debate-Driven Quality**: Advocate vs. Contrarian pattern ensures thorough analysis
- **Iterative Refinement**: Contrarian rejections force advocate revisions with specific feedback
- **Implementation Phase**: After approval, agents generate concrete artifacts (specs, code, docs)

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

**Output:** All crew runs automatically save structured markdown reports to `output/{phase}/{phase}_TIMESTAMP.md` with:
- Input parameters
- Full crew discussion and analysis
- Final verdict (for non-studio phases)
- Success/failure status

Check the `output/` directory after each run for readable reports.

### 🛡️ Solo Mode (Default)

Studio runs in **Solo Mode** by default, optimizing for lightweight local development:

- **Subprocess Isolation**: Crew execution runs in an isolated subprocess to prevent litellm crashes from affecting your workflow
- **Minimal Dependencies**: Disables heavy litellm proxy/logging features that aren't needed for local runs
- **Crash Protection**: Even if litellm encounters shutdown errors, your results are captured and saved
- **Clean Output**: Suppresses unnecessary warnings for a cleaner terminal experience

**To disable Solo Mode** (if you need full litellm features):
```bash
export STUDIO_SOLO_MODE=false
```

**To install optional proxy dependencies** (for advanced litellm features):
```bash
uv pip install -e ".[proxy]"
```

### 📊 Rate Limit Monitoring & Cascade Fallbacks

The Studio “cascade” always tries your best cloud model first (Gemini by default), falls back to Groq, and only then taps the local Ollama model as a last resort. Each rung in the ladder is guarded by telemetry so unstable providers cool off before the next crew iteration:

1. **Headroom tracking** – Every LiteLLM response is parsed for `x-ratelimit-*` headers. Once a model drops under `STUDIO_RATE_LIMIT_WARN_RATIO` (default `0.2`), Studio prints a warning and marks it “low headroom.” Low-headroom models get deprioritized but aren’t completely blocked.
2. **Cooldowns on 429s** – A `429 Too Many Requests` or `retry-after` header triggers `ModelManager` to cool that model for at least `COOLDOWN_MIN_SECONDS` (default 5s) or the provider-supplied duration. During cooldown, the cascade advances to the next candidate.
3. **Overheat guarding** – Repeated 5xx/temperature errors mark the model “overheated” for `STUDIO_OVERHEAT_COOLDOWN_SECONDS` (default 45s). You can tune which HTTP codes count via `STUDIO_OVERHEAT_STATUS_CODES` (comma-separated list).
4. **Ollama health checks** – Before Studio switches to the local fallback it pings `STUDIO_OLLAMA_BASE_URL` (`/api/tags` + `/api/version`). Missing models or unreachable daemons are logged and the fallback is temporarily marked overheated so we don’t loop on a broken local install. The probe timeout is configurable via `STUDIO_OLLAMA_HEALTH_TIMEOUT` (seconds).
5. **Structured telemetry** – Every run returns `rate_limits` and `model_strategy` blobs in the CLI/JSON output so you can see which candidate was chosen, which models are cooling, and how much quota remains.

**Cascade ordering tips**

- `STUDIO_MODEL_PRIORITY` → strict order (e.g., `gemini-2.5-pro,groq/mixtral-8x7b,ollama/llama3.1:8b`)
- `STUDIO_MODEL_CANDIDATES` → fallback list if no explicit priority
- `STUDIO_MODEL` → primary when neither list is set
- `STUDIO_MODEL_FALLBACK` → appended after the above lists
- `STUDIO_OLLAMA_MODEL` → always appended last (defaults to `ollama/llama3.1:8b`)

This ensures the agents “think” with the strongest possible model while automatically downgrading through Groq and finally the local Ollama instance whenever cloud quota or stability is an issue.

### 🔄 Iterative Refinement & Implementation Workflow

Studio implements a **steel-man vs. contrarian** pattern with true iterative refinement:

**Refinement Loop (Debate Phase)**
1. **Advocate** strengthens the idea into its best possible form
2. **Contrarian** attacks the strengthened version, outputs `VERDICT: APPROVED` or `VERDICT: REJECTED`
3. **If REJECTED**: The contrarian's critique is fed back to the advocate for the next iteration
4. **If APPROVED**: Move to implementation phase

**Implementation Phase (After Approval)**

Once a concept is approved, Studio automatically triggers an **implementation phase** where specialized agents generate concrete deliverables:

- **Market Phase** → Market Research Analyst produces:
  - Target audience profile
  - Competitor analysis table
  - Unique value proposition
  - Go-to-market strategy
  - Success metrics (KPIs)

- **Design Phase** → Game Design Documenter produces:
  - Core gameplay loop diagram
  - Player progression system
  - Key game mechanics with rules
  - UI/UX wireframe descriptions
  - Technical constraints checklist

- **Tech Phase** → Technical Architect produces:
  - System architecture diagram
  - Technology stack with justifications
  - File structure and module organization
  - Key algorithms/data structures
  - Starter code scaffold (index.html, main.js, package.json)

**Control Iteration Limits**
```bash
export STUDIO_MAX_ITERATIONS=5  # Default: 3
```

This ensures agents don't just debate—they **produce actionable artifacts** you can immediately use in your project.

## 📦 Using Studio in Other Projects

### Method 1: Cascade-Driven Workflow (Recommended - Zero Cost)

**Run Studio agents directly through Cascade using your Windsurf subscription!**

From any project in your workspace, just ask:

> "Run Studio market phase on: A bite-sized puzzle roguelike for web"

> "Run Studio design phase on: Cozy farming sim with time travel mechanics"

> "Run Studio studio phase on: Critique the Studio tool and identify improvements"

#### Standard flow with `run_phase.py`
1. **Prepare the run** (from anywhere):
   ```bash
   python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
     prepare --phase market \
     --text "A bite-sized puzzle roguelike for web"
   ```
   This creates `output/market/run_market_<timestamp>/` with `instructions.md` tailored to Cascade and records the run in `output/index.md`.
2. **Have Cascade execute the instructions** inside Windsurf chat. Each iteration’s Advocate/Contrarian/Implementer output should be saved inside the run folder named by step 1.
3. **Finalize the run** so the index stays current:
   ```bash
   python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
     finalize --phase market \
     --run-id run_market_<timestamp> \
     --status completed --verdict APPROVED \
     --hours 0.8 --cost 0
   ```
   (Include `--iterations-run N` or custom verdicts if needed.)

Every run now has predictable artifacts (`advocate_n.md`, `contrarian_n.md`, `implementation.md`, `summary.md`) plus a discoverable entry in `output/index.md`, making it easy for Cascade to continue work from any repo.
`finalize` also appends an entry to `knowledge/run_log.md`, giving the team a chronological feed of Studio insights with optional hours/cost tracking.

**Benefits:**
- **Zero API cost** – uses your existing Windsurf subscription
- **Best available model** – whatever you have selected in Windsurf
- **No rate limits** – no per-minute caps like free API tiers
- **Cross-project access** – works from any repo in your workspace
- **Consistent packaging** – `run_phase.py` automates instructions, directories, and indexing
- **Insight propagation** – knowledge log + index keep the rest of the workspace aligned

See `studio/prompts/cascade_workflow.md`, `knowledge/run_log.md`, and the new [Shoestring Preset](./docs/SHOESTRING_PRESET.md) for full workflow details and zero-cost setup tips.

### Method 2: CLI (For Automation/Batch Runs)

If you have API credits configured, use the CLI:

```bash
export PATH="/Users/orcpunk/Repos/_TheGameStudio/studio:$PATH"
```

Then from any project:

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

### Studio Phase (Meta Workflow)
- **Advocate**: Studio Workflow Producer - Crafts a north-star vision for Studio itself
- **Contrarian**: Bootstrapped Reality Auditor - Pressure-tests costs, scope, and ops burden
- **Integrator**: Systems Integrator & Ops Lead - Blends ambition + constraints into a roadmap
- **Input Variables**:
  - `STUDIO_PHASE=studio`
  - `STUDIO_OBJECTIVE` – your current Studio improvement goal
  - `STUDIO_BUDGET_CAP` – hard monthly/annual spend ceiling (e.g., `$0-20/mo`)
- **Output**: Vision brief, constraint analysis, and integration roadmap focused on “always-on, nearly free” usage across every project.

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
| `STUDIO_PHASE` | No | Set to `studio` to run the self-improvement crew |
| `STUDIO_OBJECTIVE` | No | Objective statement for the studio phase |
| `STUDIO_BUDGET_CAP` | No | Human-readable budget ceiling (e.g., `$0-20/mo`) |
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
