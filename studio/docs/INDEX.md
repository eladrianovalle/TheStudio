# Studio Documentation Index

## Getting Started
- **[README.md](../../README.md)** - Overview, quick start, and workflow

## Architecture & Reference
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System design and extensibility
- **[AGENTS_REFERENCE.md](./AGENTS_REFERENCE.md)** - Agent roles and personas
- **[API.md](./API.md)** - CLI reference for `run_phase.py`
- **[CODING_PRINCIPLES.md](./CODING_PRINCIPLES.md)** - Karpathy-inspired coding principles (injected into target CLAUDE.md on install)

## Workflow Features
- **[SCOPES_GUIDE.md](./SCOPES_GUIDE.md)** - Scope-based iteration allocation
- **[VALIDATION_GUIDE.md](./VALIDATION_GUIDE.md)** - Document and code validation
- **[TEST_DRIVEN_GUIDE.md](./TEST_DRIVEN_GUIDE.md)** - Test-driven discipline for tech phase
- **[AI_TDD_METHODOLOGY.md](./AI_TDD_METHODOLOGY.md)** - Full AI-TDD methodology (scenario-first, stack boundary, mutation verification)
- **[MVI_METHODOLOGY.md](./MVI_METHODOLOGY.md)** - Minimum Viable Interaction — every milestone ends in something usable
- **[IMPLEMENTATION_LOOP_SPEC.md](./IMPLEMENTATION_LOOP_SPEC.md)** - Writer/editor implementation loop (`/studio-implement`): design, gate semantics, config knobs
- **[STORAGE_MANAGEMENT.md](./STORAGE_MANAGEMENT.md)** - Cleanup, TTL, and storage budgets

## Integration
- **[INTEGRATIONS.md](./INTEGRATIONS.md)** - Slack / n8n run-digest webhooks (config, payloads, security)
- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Using Studio from other repos
- **[STUDIO_BRIDGE_TEMPLATE.md](./STUDIO_BRIDGE_TEMPLATE.md)** - Bridge doc template for downstream repos
- **[BRIDGE_COMMANDS_TEMPLATE.md](./BRIDGE_COMMANDS_TEMPLATE.md)** - Slash command files to copy into a downstream repo's `.claude/commands/`
- **[CROSS_REPO_CHECK_MVI.md](./CROSS_REPO_CHECK_MVI.md)** - `check-install` version comparison against the source repo

## Execution Guides
- **[CLAUDE_CODE_USAGE.md](./CLAUDE_CODE_USAGE.md)** - Claude Code slash commands and agent workflow
- **[windsurf/USAGE.md](./windsurf/USAGE.md)** - Windsurf/Cascade-specific execution workflow
- **[windsurf/QUICKREF.md](./windsurf/QUICKREF.md)** - Windsurf quick reference card
- **[windsurf/cascade_workflow.md](./windsurf/cascade_workflow.md)** - Cascade roleplay workflow prompts

## Available Phases

| Phase | Advocate | Contrarian | Focus |
|-------|----------|------------|-------|
| market | Growth Strategist | Reality Check | Viability |
| design | Systems Designer | Scope Police | Gameplay |
| tech | Technical Architect | SRE | Feasibility |
| studio | Multi-role pod | Multi-role pod | Cross-discipline |
