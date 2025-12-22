# Using Studio Agents from Windsurf/Cascade

This guide explains how to interact with your Studio agents from **any project in Windsurf** using Cascade (the AI assistant).

## 🎯 Core Concept

You can have **conversations with your Studio agents** from any project on your machine by asking Cascade to run Studio commands. The agents will evaluate your ideas and provide feedback through the Windsurf chat interface.

## 🚀 Quick Setup

### 1. Make Studio Globally Accessible

Add Studio to your PATH (one-time setup):

```bash
# Add to your ~/.zshrc or ~/.bashrc
export PATH="/Users/orcpunk/Repos/_TheGameStudio/studio:$PATH"
```

Then reload:
```bash
source ~/.zshrc
```

### 2. Test It Works

From any directory:
```bash
studio list-phases
```

You should see the available phases.

### 3. Quick Cascade Command Snippet (Recommended)

When you want Cascade to run a Studio phase, start by preparing the run folder:
```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  prepare --phase market \
  --text "Describe your idea here"
```
- Cascade will then use the generated `instructions.md` to roleplay Advocate/Contrarian inside chat.
- After saving artifacts, finish with:
  ```bash
  python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
    finalize --phase market \
    --run-id run_market_<timestamp> \
    --status completed --verdict APPROVED \
    --hours 0.8 --cost 0
  ```
This ensures every run is packaged under `output/{phase}/run_*`, logged in `output/index.md`, and tracked in `knowledge/run_log.md` no matter which project triggered it.

### 4. Add a Windsurf Command Palette Action (Optional but Handy)

Make the prepare step a single palette action so you never need to type the command again:

1. In Windsurf press **⌘⇧P** (or **Ctrl+Shift+P**) and run **“Cascade: Configure Command Palette Actions”**.
2. Add the following entry inside the JSON array (adjust the absolute path if your repo lives elsewhere):
   ```json
   {
     "title": "Studio: Prepare Run Folder",
     "description": "Generate instructions + output folder for any Studio phase.",
     "inputs": [
       { "name": "phase", "placeholder": "market / design / tech / studio" },
       { "name": "idea_or_objective", "placeholder": "What should Studio work on?" },
       { "name": "max_iterations", "placeholder": "Advocate↔Contrarian loops (default 3)", "default": "3" }
     ],
     "command": "python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py prepare --phase {{phase}} --text \"{{idea_or_objective}}\" --max-iterations {{max_iterations}}"
   }
   ```
3. Invoke the palette again and type “Studio: Prepare Run Folder”. Windsurf will prompt for the phase, idea/objective, and iteration cap, then run the helper script for you.
4. After Cascade finishes the agent loop and artifacts are saved, run the finalize command (or add another palette action mirroring `run_phase.py finalize`).

## 💬 Using Studio from Windsurf Cascade

### From Any Project

Open any project in Windsurf and chat with Cascade:

**You:** "Use the Studio agents to evaluate this game idea: A 3D stealth horror roguelike for the web"

**Cascade will run:**
```bash
/Users/orcpunk/Repos/_TheGameStudio/studio/studio evaluate "A 3D stealth horror roguelike for the web" --phase market
```

### Example Conversations

#### Market Validation

**You:** "Run the Studio market phase on: A multiplayer card battler with NFT integration"

**Cascade runs:**
```bash
studio evaluate "A multiplayer card battler with NFT integration" --phase market
```

You'll get the Advocate's pitch and Contrarian's critique with a verdict.

---

#### Full Pipeline

**You:** "Run my game idea through all Studio phases: A cozy farming sim with time travel mechanics"

**Cascade runs:**
```bash
studio pipeline "A cozy farming sim with time travel mechanics"
```

You'll get Market → Design → Tech evaluation in sequence.

---

#### Specific Phase

**You:** "I need the Studio design agents to evaluate: A procedural dungeon crawler with deck-building"

**Cascade runs:**
```bash
studio evaluate "A procedural dungeon crawler with deck-building" --phase design
```

---

#### Get JSON Output

**You:** "Run Studio market phase and give me JSON output for: A battle royale with building mechanics"

**Cascade runs:**
```bash
studio evaluate "A battle royale with building mechanics" --phase market --format json
```

## 📋 Available Commands

### Evaluate Single Phase

```bash
studio evaluate "Your game idea" --phase [market|design|tech]
```

**Options:**
- `--phase market` - Market viability (default)
- `--phase design` - Gameplay design
- `--phase tech` - Technical feasibility
- `--format json` - Get JSON output instead of text

### Run Full Pipeline

```bash
studio pipeline "Your game idea"
```

Runs all phases in sequence, stops if any phase rejects.

### List Phases

```bash
studio list-phases
```

Shows all available evaluation phases.

## 🎮 Real-World Workflow

### Scenario: You're in a Game Project

You're working on a game project in Windsurf and want to validate a new feature idea:

**You:** "I'm thinking of adding a new mechanic to my game. Can you run it through the Studio design phase? The idea is: A time-rewind mechanic that lets players undo the last 5 seconds of gameplay"

**Cascade will:**
1. Run the Studio design agents
2. Show you the Advocate's best-case design
3. Show you the Contrarian's scope/complexity concerns
4. Give you the verdict (APPROVED/REJECTED)

You can then discuss the feedback with Cascade and iterate on the idea.

---

### Scenario: Brainstorming Session

**You:** "I have 3 game ideas. Can you run each through Studio's market phase and tell me which one has the best potential?"

**Ideas:**
1. A roguelike deckbuilder in space
2. A cozy puzzle game about organizing a library
3. A survival horror game set in a submarine

**Cascade will:**
1. Run each idea through `studio evaluate "idea" --phase market`
2. Compare the verdicts and feedback
3. Recommend the strongest concept based on agent analysis

---

### Scenario: Technical Validation

You're in a web game project and want to validate a technical approach:

**You:** "Use Studio's tech phase to evaluate: Building a real-time multiplayer 3D game using Three.js and WebRTC with 32 concurrent players"

**Cascade runs:**
```bash
studio evaluate "Building a real-time multiplayer 3D game using Three.js and WebRTC with 32 concurrent players" --phase tech
```

You get the Technical Architect's implementation plan and the SRE's production concerns.

## 🔧 Advanced Usage

### Chaining Evaluations

**You:** "Run this idea through Studio market phase. If it's approved, then run it through design phase: A puzzle platformer with portal mechanics"

Cascade will:
1. Run market phase
2. Check the verdict
3. Only run design phase if market approved

### Iterative Refinement

**You:** "Run this through Studio market phase: A horror game"

*Gets feedback*

**You:** "Based on that feedback, run this refined version: A 3D stealth horror roguelike with AI-driven enemies that learn from player behavior"

### Custom Phases (If You've Added Them)

If you've added custom phases to `config/agents.yaml`:

**You:** "Run Studio's monetization phase on: A free-to-play mobile puzzle game"

```bash
studio evaluate "A free-to-play mobile puzzle game" --phase monetization
```

## 🎯 Prompt Templates for Cascade

### Market Validation
```
"Use Studio to validate the market potential of: [YOUR IDEA]"
"Run Studio market phase on: [YOUR IDEA]"
"Check if this idea is marketable using Studio: [YOUR IDEA]"
```

### Design Validation
```
"Use Studio design agents to evaluate: [YOUR IDEA]"
"Run Studio design phase on: [YOUR IDEA]"
"Check the gameplay feasibility of: [YOUR IDEA]"
```

### Tech Validation
```
"Use Studio tech phase to validate: [YOUR IDEA]"
"Check technical feasibility using Studio: [YOUR IDEA]"
"Run Studio's technical architects on: [YOUR IDEA]"
```

### Full Pipeline
```
"Run [YOUR IDEA] through all Studio phases"
"Validate this concept with Studio: [YOUR IDEA]"
"Use Studio to fully evaluate: [YOUR IDEA]"
```

## 🔍 Understanding the Output

### Advocate Section
The first part shows the **strongest possible version** of your idea:
- Optimistic framing
- Market opportunities
- Best-case scenarios
- Pre-emptive solutions to obvious problems

### Contrarian Section
The second part shows **critical flaws**:
- 3 specific fatal flaws
- Realistic concerns
- Competitive challenges
- Implementation risks

### Verdict
Always ends with:
- `VERDICT: APPROVED` - Concept is viable
- `VERDICT: REJECTED` - Critical flaws identified

## 💡 Tips for Best Results

### 1. Be Specific
❌ "A horror game"
✅ "A 3D stealth horror roguelike for the web with procedural environments"

### 2. Include Context
❌ "A multiplayer game"
✅ "A 4-player co-op game for Steam with 30-minute sessions"

### 3. Mention Constraints
✅ "A mobile puzzle game with 1-month development timeline"
✅ "A web game that must run on mobile browsers"

### 4. Use the Right Phase
- **Market**: Is there demand? Will it sell?
- **Design**: Is the gameplay fun? Is scope reasonable?
- **Tech**: Can we build it? Will it perform?

## 🔄 Iterative Workflow

1. **Initial Idea** → Run market phase
2. **If Rejected** → Refine based on feedback, run again
3. **If Approved** → Run design phase
4. **If Rejected** → Simplify scope, run again
5. **If Approved** → Run tech phase
6. **If Approved** → Proceed with development!

## 🚨 Troubleshooting

### "Command not found: studio"

**Solution:** Add Studio to PATH:
```bash
export PATH="/Users/orcpunk/Repos/_TheGameStudio/studio:$PATH"
```

### "GEMINI_API_KEY not found"

**Solution:** The `.env` file should be loaded automatically, but verify:
```bash
cat /Users/orcpunk/Repos/_TheGameStudio/studio/.env
```

### Slow Response Times

**Normal:** Each phase takes 30-90 seconds
**If slower:** Check your internet connection (API calls to Google Gemini)

### "Phase not found"

**Solution:** Check available phases:
```bash
studio list-phases
```

Only `market`, `design`, and `tech` are available by default.

## 📚 Related Documentation

- **[README.md](../README.md)** - Overview and setup
- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Programmatic integration
- **[AGENTS_REFERENCE.md](./AGENTS_REFERENCE.md)** - Agent details
- **[API.md](./API.md)** - API reference

## 🎓 Example Session

Here's a complete example of using Studio from another project:

**Project:** You're working on a web game in `/Users/orcpunk/Projects/MyGame`

**You:** "I'm thinking about adding a new game mode. Can you use Studio to validate it? The idea is: A battle royale mode where 50 players compete in a shrinking arena, last player standing wins. The game would be browser-based using Three.js."

**Cascade:** *Runs Studio evaluation*

```bash
studio evaluate "A battle royale mode where 50 players compete in a shrinking arena, last player standing wins. Browser-based using Three.js" --phase tech
```

**Output:** Technical Architect provides architecture recommendations, SRE identifies networking and performance concerns, verdict given.

**You:** "The SRE mentioned networking concerns. Can you run a refined version through design phase? Focus on 16 players instead of 50."

**Cascade:** *Runs refined evaluation*

```bash
studio evaluate "A battle royale mode where 16 players compete in a shrinking arena, last player standing wins. Browser-based using Three.js" --phase design
```

**Output:** Design agents evaluate the 16-player scope, provide feedback on feasibility.

**You:** "Great! Now let's check market viability."

**Cascade:** *Runs market phase*

```bash
studio evaluate "A battle royale mode where 16 players compete in a shrinking arena, last player standing wins. Browser-based using Three.js" --phase market
```

**Output:** Market agents evaluate demand and competitive landscape.

---

This workflow lets you **have a conversation with your Studio agents** from any project, getting expert feedback without leaving your current work context.
