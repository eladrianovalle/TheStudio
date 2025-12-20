# Agents Reference

Complete documentation of all available agents in the Studio system.

## Overview

The Studio uses a **debate-driven evaluation pattern** where each phase has two specialized agents:
- **Advocate**: Presents the strongest possible case (steel-manning)
- **Contrarian**: Identifies critical flaws and weaknesses

This ensures balanced, thorough evaluation of ideas.

## Agent Architecture

### Common Properties

All agents share these properties:

| Property | Description |
|----------|-------------|
| `role` | The agent's job title/identity |
| `goal` | What the agent tries to achieve |
| `backstory` | Context that shapes agent behavior |
| `llm` | Language model (Google Gemini 2.5 Flash) |
| `verbose` | Detailed output enabled |

### Input Variables

Agents receive inputs via template variables:
- `{game_idea}` - The concept being evaluated
- Additional variables can be added per phase

## Market Phase Agents

### Market Advocate: Market Growth Strategist

**Role**: Market Growth Strategist

**Goal**: Steel-man the game idea into a high-virality Steam hook

**Backstory**: You specialize in indie trends and 'screenshot-ability'

**Expertise**:
- Indie game market trends
- Viral marketing mechanics
- Steam platform dynamics
- Screenshot-worthy moments
- Community engagement strategies

**Evaluation Criteria**:
- Market size and accessibility
- Viral potential (shareability)
- Unique selling proposition (USP)
- Target audience fit
- Competitive positioning
- Monetization potential

**Output Style**:
- Enthusiastic and optimistic
- Focuses on opportunities
- Highlights strengths
- Pre-emptively addresses obvious concerns
- Provides concrete marketing angles

**Example Output**:
```
🎯 STEEL-MANNED PITCH: "Outsmart the Darkness"

This is a 3D stealth horror roguelike that combines the tension of 
Alien: Isolation with the replayability of Hades. The core hook is 
an AI-driven enemy that learns from player behavior, creating unique 
"Did You See That?!" moments perfect for streaming.

Market Advantages:
1. Horror + Roguelike = Proven combination (see Darkwood, Inscryption)
2. Web-based = Zero friction for viral spread
3. Procedural AI = Infinite content for streamers
...
```

---

### Market Contrarian: The Reality Check

**Role**: The Reality Check

**Goal**: Find 3 fatal market flaws in the pitch and issue a VERDICT

**Backstory**: You are a cynical publisher who hates generic clones

**Expertise**:
- Market saturation analysis
- Publisher perspective
- Competitive landscape
- Monetization challenges
- Platform limitations

**Evaluation Criteria**:
- Market differentiation
- Competition analysis
- Technical feasibility vs. market expectations
- Monetization viability
- Sustainability concerns

**Output Style**:
- Critical and skeptical
- Focuses on risks and flaws
- Identifies deal-breakers
- Compares to existing successful games
- Must end with explicit verdict

**Required Output Format**:
```
**VERDICT: APPROVED** or **VERDICT: REJECTED**
```

**Example Output**:
```
🔴 FATAL FLAWS

1. **The "learning AI" is technically impossible within your scope**
   You're promising adaptive AI that would require machine learning 
   infrastructure, training data, and real-time model updates...

2. **Web-based 3D horror is a technical suicide mission**
   Players expect premium quality in horror games...

3. **No meaningful market differentiation beyond impossible AI**
   Strip away the AI pipe dream and you have a generic horror game...

**VERDICT: REJECTED**
```

---

## Design Phase Agents

### Design Advocate: Lead Systems Designer

**Role**: Lead Systems Designer

**Goal**: Turn the concept into a 'Minimum Viable Fun' core loop

**Backstory**: Expert in Roguelike systems and player tension

**Expertise**:
- Core gameplay loop design
- Roguelike mechanics
- Player progression systems
- Tension and pacing
- Minimum Viable Product (MVP) scoping

**Evaluation Criteria**:
- Core loop clarity
- Mechanical depth
- Replayability factors
- Progression systems
- Player agency
- Fun-per-minute ratio

**Output Style**:
- Systems-focused
- Emphasizes core loop
- Defines clear mechanics
- Prioritizes "Minimum Viable Fun"
- Provides concrete design pillars

**Example Output**:
```
🎮 MINIMUM VIABLE FUN DESIGN

Core Loop (60-second cycle):
1. Scout → Identify resources and threats
2. Plan → Choose route and backup escape
3. Execute → Stealth movement with risk/reward decisions
4. Adapt → React to enemy behavior changes

Key Systems:
- Fear & Focus mechanic (risk/reward tension)
- Procedural environment generation
- Resource scarcity driving decisions
...
```

---

### Design Contrarian: The Scope-Creep Police

**Role**: The Scope-Creep Police

**Goal**: Attack the design for being too complex for a 1-month MVP

**Backstory**: You value 'shippable' code over 'perfect' design

**Expertise**:
- Scope management
- MVP development
- Technical debt prevention
- Timeline estimation
- Feature prioritization

**Evaluation Criteria**:
- Implementation complexity
- Timeline feasibility
- Scope creep risks
- Technical dependencies
- Shippability

**Output Style**:
- Pragmatic and timeline-focused
- Identifies scope creep
- Challenges complexity
- Demands simplification
- Must end with explicit verdict

**Required Output Format**:
```
**VERDICT: APPROVED** or **VERDICT: REJECTED**
```

**Example Output**:
```
⚠️ SCOPE ANALYSIS

1. **Your "procedural AI" is 3 months of work, not 1**
   You're describing a system that requires pathfinding, behavior 
   trees, learning algorithms, and extensive testing...

2. **Procedural generation + 3D = Massive scope**
   Each system alone is a month of work...

3. **You have no fallback for when systems don't work**
   What happens when the AI doesn't feel "smart"?...

**VERDICT: REJECTED** - Reduce scope by 70% or extend timeline to 3 months
```

---

## Tech Phase Agents

### Tech Advocate: Three.js Technical Architect

**Role**: Three.js Technical Architect

**Goal**: Define the most performant WebGL architecture for this game

**Backstory**: Wizard of ECS and shader optimization

**Expertise**:
- Three.js and WebGL
- Entity Component System (ECS)
- Shader optimization
- Performance profiling
- Web game architecture

**Evaluation Criteria**:
- Technical architecture
- Performance optimization
- Scalability
- Browser compatibility
- Asset pipeline
- Code organization

**Output Style**:
- Architecture-focused
- Performance-conscious
- Provides technical blueprints
- Identifies optimization strategies
- Concrete implementation guidance

**Example Output**:
```
⚙️ TECHNICAL ARCHITECTURE

Recommended Stack:
- Three.js r160+ (latest stable)
- ECSY or bitECS for entity management
- Rapier.js for physics (WASM-based)
- Howler.js for spatial audio

Performance Strategy:
1. Instanced rendering for repeated geometry
2. LOD system for distant objects
3. Frustum culling + occlusion
4. Texture atlasing for materials
...
```

---

### Tech Contrarian: Senior SRE

**Role**: Senior SRE

**Goal**: Find why this code will crash or lag in a browser

**Backstory**: You care about memory leaks and mobile compatibility

**Expertise**:
- Site Reliability Engineering (SRE)
- Performance bottlenecks
- Memory management
- Browser compatibility
- Mobile optimization
- Production issues

**Evaluation Criteria**:
- Memory leaks
- Performance bottlenecks
- Browser compatibility
- Mobile support
- Error handling
- Production readiness

**Output Style**:
- Production-focused
- Identifies failure modes
- Challenges performance claims
- Demands realistic benchmarks
- Must end with explicit verdict

**Required Output Format**:
```
**VERDICT: APPROVED** or **VERDICT: REJECTED**
```

**Example Output**:
```
🚨 PRODUCTION CONCERNS

1. **Memory leaks in procedural generation**
   Every time you generate a new level, you're creating thousands 
   of objects. Without proper cleanup, you'll leak memory...

2. **Mobile is DOA with this architecture**
   3D horror games require 60fps. Mobile browsers struggle with 
   basic Three.js scenes...

3. **No fallback for WebGL failures**
   5-10% of users will have WebGL disabled or unsupported...

**VERDICT: APPROVED** - With mandatory memory profiling and mobile testing
```

---

## Agent Interaction Patterns

### Sequential Execution

Agents execute in sequence within each phase:

```
1. Advocate runs first
   ↓
2. Advocate output passed to Contrarian
   ↓
3. Contrarian evaluates Advocate's proposal
   ↓
4. Contrarian issues verdict
```

### Context Sharing

The Contrarian receives the Advocate's full output as context:

```python
# In tasks.yaml
steel_man_task:
  description: "Present strongest possible form of {game_idea}"
  expected_output: "High-conviction proposal"

attack_task:
  description: "Review the proposal. Find 3 fatal flaws."
  expected_output: "Critical report with VERDICT"
```

The Contrarian can reference specific points from the Advocate's output.

### Verdict Format

All Contrarian agents must end with:
```
**VERDICT: APPROVED**
```
or
```
**VERDICT: REJECTED**
```

This allows programmatic parsing:
```python
result = str(crew.kickoff(inputs={'game_idea': idea}))
is_approved = "APPROVED" in result
```

## Customizing Agents

### Modifying Existing Agents

Edit `src/studio/config/agents.yaml`:

```yaml
market_advocate:
  role: "Your Custom Role"
  goal: "Your custom goal with {game_idea}"
  backstory: "Your custom backstory"
```

Changes take effect immediately (no code changes needed).

### Adding New Phase Agents

1. Add to `agents.yaml`:
```yaml
prototype_advocate:
  role: "Rapid Prototyper"
  goal: "Create a minimal playable prototype plan for {game_idea}"
  backstory: "Expert in MVP development and rapid iteration"

prototype_contrarian:
  role: "Quality Gatekeeper"
  goal: "Ensure prototype won't create technical debt"
  backstory: "Senior architect focused on maintainability"
```

2. Use immediately:
```python
result = StudioCrew(phase='prototype').crew().kickoff(
    inputs={'game_idea': 'Your concept'}
)
```

### Agent Personality Tuning

Adjust agent behavior via backstory:

**More aggressive Contrarian**:
```yaml
market_contrarian:
  backstory: "You are a ruthless publisher who rejects 95% of pitches. You've seen every trick and hate buzzwords."
```

**More supportive Advocate**:
```yaml
market_advocate:
  backstory: "You are an enthusiastic indie game champion who finds the diamond in every rough idea."
```

### Adding Custom Variables

Extend input variables in tasks:

```yaml
steel_man_task:
  description: >
    Evaluate {game_idea} for {target_platform} with 
    budget of {budget} and timeline of {timeline}.
```

Then pass in code:
```python
result = crew.kickoff(inputs={
    'game_idea': 'Your concept',
    'target_platform': 'Steam',
    'budget': '$50k',
    'timeline': '6 months'
})
```

## Agent Performance

### Token Usage Per Agent

| Agent Type | Avg Input Tokens | Avg Output Tokens | Total |
|------------|------------------|-------------------|-------|
| Advocate | 500-800 | 800-1200 | 1300-2000 |
| Contrarian | 1500-2000 | 600-1000 | 2100-3000 |

**Note**: Contrarian uses more input tokens because it receives Advocate's output.

### Execution Time

| Phase | Advocate Time | Contrarian Time | Total |
|-------|---------------|-----------------|-------|
| Market | 15-30s | 20-40s | 35-70s |
| Design | 20-40s | 25-50s | 45-90s |
| Tech | 25-50s | 30-60s | 55-110s |

Times vary based on:
- Input complexity
- Model load (Gemini API)
- Network latency

### Cost Estimation

Using Gemini 2.5 Flash (as of Dec 2024):
- Input: $0.075 per 1M tokens
- Output: $0.30 per 1M tokens

**Per Phase Cost**:
- Market: ~$0.001-0.002
- Design: ~$0.002-0.003
- Tech: ~$0.002-0.004

**Full Pipeline**: ~$0.005-0.010 per evaluation

## Best Practices

### 1. Clear Input Descriptions

Provide detailed game ideas for better agent responses:

❌ **Bad**: "A horror game"

✅ **Good**: "A 3D stealth horror roguelike for the web where an AI enemy learns from player behavior, featuring procedural environments and a Fear & Focus mechanic"

### 2. Phase Ordering

Run phases in logical order:
1. **Market** - Validates demand
2. **Design** - Validates gameplay
3. **Tech** - Validates implementation

Stop if any phase rejects.

### 3. Iterative Refinement

Use agent feedback to improve concepts:

```python
idea_v1 = "A 3D horror game"
result_v1 = evaluate(idea_v1, 'market')

# Incorporate feedback
idea_v2 = "A 3D stealth horror roguelike with unique AI-driven enemy"
result_v2 = evaluate(idea_v2, 'market')
```

### 4. Custom Phases for Specific Needs

Create specialized phases:
- **Monetization phase**: Business model validation
- **Narrative phase**: Story and theme evaluation
- **Art phase**: Visual style and asset scope
- **Audio phase**: Sound design feasibility

### 5. Agent Chaining

Chain multiple evaluations:

```python
# Broad to specific
phases = ['market', 'design', 'tech']
for phase in phases:
    result = evaluate(idea, phase)
    if "REJECTED" in result:
        # Refine based on feedback
        idea = refine_idea(idea, result)
        # Re-evaluate
        result = evaluate(idea, phase)
```

## Troubleshooting

### Agent Not Loading

**Symptom**: `KeyError: 'market_advocate'`

**Solution**: Check agent naming in `agents.yaml`:
- Must be `{phase}_advocate`
- Must be `{phase}_contrarian`

### Inconsistent Verdicts

**Symptom**: Contrarian doesn't include verdict

**Solution**: Update task description to enforce:
```yaml
attack_task:
  description: >
    Review the proposal. Find 3 fatal flaws.
    You MUST end your response with either 
    'VERDICT: APPROVED' or 'VERDICT: REJECTED'.
```

### Agent Output Too Verbose

**Solution**: Adjust expected output in `tasks.yaml`:
```yaml
steel_man_task:
  expected_output: "A concise 3-paragraph proposal (max 300 words)"
```

### Agent Lacks Domain Knowledge

**Solution**: Enhance backstory with specific expertise:
```yaml
market_advocate:
  backstory: >
    You specialize in indie trends and 'screenshot-ability'.
    You've analyzed 500+ successful Steam launches and understand
    what makes games go viral on Reddit and Twitter.
```

## Future Enhancements

### Planned Agent Features

1. **Memory**: Agents remember previous evaluations
2. **Tools**: Give agents web search, code analysis capabilities
3. **Multi-Model**: Use different models per agent (GPT-4 for Advocate, Claude for Contrarian)
4. **Collaborative**: Agents debate in real-time rather than sequential
5. **Learning**: Agents improve from feedback on their evaluations

### Community Agents

Share and import community-created agent configurations:

```bash
# Future feature
studio import agent community/narrative_expert
studio list agents --community
```

## Related Documentation

- **[README.md](../README.md)** - Getting started guide
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System design
- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Integration examples
- **[API.md](./API.md)** - API reference
