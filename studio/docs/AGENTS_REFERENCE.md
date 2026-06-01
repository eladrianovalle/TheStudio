# Agents Reference

Studio no longer spins up its own agents. Instead, we describe every persona in Markdown/JSON so an AI assistant (Claude Code, Windsurf/the assistant, etc.) can roleplay them deterministically during the prepare → execute → finalize loop. Use this file to understand what each phase expects and how to extend or override roles safely.

---

## 1. Phases & Canonical Roles

The non-studio phases each follow a single Advocate ↔ Contrarian loop, then hand off to an implementer checklist. Studio phase invites multiple disciplines simultaneously via role packs. Tables below mirror `PHASE_DETAILS` inside `run_phase.py` and the default Studio manifest.

### Market Phase

| Persona | Description |
| --- | --- |
| Advocate – Market Growth Strategist | Steel-man the idea into a high-virality launch hook for its target platform. Focus on audience segments, unique hooks, and low-cost launch tactics. |
| Contrarian – The Reality Check | Attack market size, competition, cost realism, and virality claims. Must end with `VERDICT: APPROVED/REJECTED`. |
| Implementer – Market Research Analyst | After approval, produces audience profiles, competitor tables, UVP, GTM plan, and KPI list. |

### Design Phase

| Persona | Description |
| --- | --- |
| Advocate – Lead Systems Designer | Build the Minimum Viable Fun core loop, mechanics, and constraints. |
| Contrarian – Scope-Creep Police | Challenge complexity, missing UX safeguards, and timeline realism; returns VERDICT. |
| Implementer – Game Design Documenter | Provides gameplay loop diagram, progression outline, key mechanics, UI/UX notes, and constraint checklist. |

### Tech Phase

| Persona | Description |
| --- | --- |
| Advocate – Technical Architect | Define a performant, idiomatic architecture, stack, and modules for the project's stack. |
| Contrarian – Senior SRE | Flag performance, compatibility, ops toil, and reliability concerns (with VERDICT). |
| Implementer – Technical Architect & Code Generator | Produces architecture description, stack, module plan, data-structure notes, and a starter code fragment. |

### Studio Phase (Role Packs)

Studio phase now hosts as many Advocate↔Contrarian duos as needed. The default `studio_core` pack includes:

| Role Key | Title | Advocate Focus | Contrarian Focus | Deliverables (examples) |
| --- | --- | --- | --- | --- |
| marketing | Head of Growth Marketing | Viral hook + audience segmentation | TAM/TAR realism, UA cost scrutiny | Hook ladders, launch swim lanes, KPI instrumentation |
| product | Group Product Manager | Roadmap sequencing, staffing, success metrics | Opportunity cost, ownership gaps | Milestone plan, kill metrics, dependency map |
| design | Lead Systems Designer | Experience pillars, core loop | Scope control, UX clarity | Loop sketch, risks list |
| art | Art Director | Visual north star, references | Production feasibility, tooling readiness | Mood board, style guardrails |
| engineering | Principal Gameplay Engineer | Architecture, integrations, performance | Ops toil, technical risk | System outline, stack choices, ops checklist |
| test_engineer | Staff Test Engineer — AI-TDD Integrity | Scenario-first test design, stack boundaries, mutation verification | Self-mocking tests, hallucinated assertions, green checkmark trap | Test spec (GWT), context boundary, mutation plan, anti-pattern audit |
| qa | Release QA & Launch Ops Lead | Validation strategy, telemetry | Coverage breadth, environment readiness, support gaps | Test matrix, rollback plan, instrumentation gaps |
| web_engineering | Lead Web Engineer — Next.js & Static Export | Architecture for App Router, static export, route structure | Hydration mismatches, route conflicts, static export limitations | Architecture evaluation, route validation, export verification |
| web_test_engineer | Staff Test Engineer — Web & Static Export | Scenario-first testing for static export, route generation | False-confidence tests, dev-only passes, missing content verification | Static export test spec, route accessibility plan, SEO checklist |
| web_qa | Release QA Lead — Static Site Deployment | GitHub Pages validation, route resolution, asset loading | Missing routes, broken asset paths, cache invalidation gaps | Deployment smoke test matrix, export completeness checklist |
| ai_engineer | Staff AI Engineer — Prompt Architecture & Agent Optimization | Prompt structures, context management, token efficiency | Fragile prompt assumptions, context window blind spots, silent failures | Prompt architecture analysis, context efficiency, failure mode catalog |

**Role dependencies:** The manifest declares co-requirements — `engineering → test_engineer`. When engineering is present, test_engineer is automatically injected after it. This ensures test integrity is always debated when technical work is proposed. Override with `-test_engineer` only when explicitly unwanted.

### Three-Tier Scoped Debate (Default)

Studio runs use a scoped flow by default (override with `--no-scopes`):

1. **Alignment** — All roles debate in parallel, ~500-word cap. Catches directional problems cheaply before deep dives. File naming: `advocate--<role>--S1-NN.md`
2. **Depth** — Each role debates sequentially with full deliverables, no word cap. Starts focused because alignment context is available. File naming: `advocate--<role>--S2-NN.md`
3. **Polish** — All roles in parallel, ~300-word cap, single pass. Cross-discipline gut-check. File naming: `advocate--<role>--S3-NN.md`
4. **Integrator** — After all roles approve in polish, synthesizes into `integrator.md` with capped duel (two passes max).

In flat mode (`--no-scopes`), each role writes `advocate--<role>--NN.md` and `contrarian--<role>--NN.md` until approved, then the Integrator runs.

---

## 2. Role Menu & Prompt Docs

- `run_phase.py prepare --phase studio` renders a **Role Menu** listing every invited role, deliverables, filenames, and a link to its prompt doc (`docs/role_prompts/<role>.md`).
- Prompt docs hold the long-form guidance that used to clog instructions. Update them whenever you change a role’s responsibilities.
- Escalation cues in the manifest tell the assistant when to invite additional roles (e.g., Marketing escalates Legal when policies are at risk).

---

## 3. Artifact Expectations

| Phase | Advocate Files | Contrarian Files | Post-approval artifact |
| --- | --- | --- | --- |
| Market/Design | `advocate_<n>.md` | `contrarian_<n>.md` | `summary.md` (discussion phases) |
| Tech | `advocate_<n>.md` | `contrarian_<n>.md` | `implementation.md` (with tests) |
| Studio (flat) | `advocate--<role>--<n>.md` | `contrarian--<role>--<n>.md` | `integrator.md` (with duel sections) |
| Studio (scoped) | `advocate--<role>--S1-<n>.md` etc. | `contrarian--<role>--S1-<n>.md` etc. | `integrator.md` (with duel sections) |

Contrarians must always end with `VERDICT: APPROVED` or `VERDICT: REJECTED`. Finalize will flag missing files per role and record `completed`/`missing` lists in `run.json["studio_roles"]`.

---

## 4. Customizing Roles

1. **Update `studio.manifest.json`**  
   - Add new roles, tweak focuses, amend deliverables, or adjust escalation cues.  
   - Keep `prompt_doc` paths in sync with `docs/role_prompts/`.
2. **Adjust role packs (`role_packs/*.json`)**  
   - Create additional packs (e.g., `liveops_hotfix.json` or `monetization_review.json`).  
   - Operators select them via `--role-pack` and override attendance with `--roles` tokens (typically additions like `+product +engineering +qa`; use `-role` only when you need to remove one).
3. **Document changes**  
   - Update README, Interaction Guide, API, and Bridge Template whenever roles or packs shift.  
   - Mention the new pack in downstream bridge docs so the assistant loads it explicitly.

Because everything is declarative, there’s no hidden CrewAI config to edit—just JSON + Markdown.

### Methodology Enforcement

Roles enforce two methodologies via their contrarian focuses and escalation triggers:

- **MVI (Minimum Viable Interaction)**: Product, Engineering, and Design contrarians reject plans where milestones, sprints, or tasks end in unusable states. "Build a skateboard, not a wheel." See [MVI_METHODOLOGY.md](./MVI_METHODOLOGY.md).
- **AI-TDD**: Test Engineer and Engineering contrarians enforce scenario-first test design, mutation verification, and anti-pattern detection. See [AI_TDD_METHODOLOGY.md](./AI_TDD_METHODOLOGY.md).

---

## 5. Best Practices for Operators

1. **Always cite Role Menu entries** when asking the assistant to write artifacts (“Use the Marketing role definition from instructions”).  
2. **Loop until VERDICT: APPROVED** per role; avoid skipping contrarian passes because finalize will block completion.  
3. **Use `roles_needed.md` (optional)** to track escalations when a contrarian says “bring Security in.” You can schedule a follow-up run with `--roles +security`.  
4. **Summaries should list confidence per role** (e.g., `marketing_confidence: 0.7`) so downstream readers know which pods need follow-up.  
5. **Keep prompt docs concise but specific**. Point to canonical examples, KPIs, and failure modes. the assistant will reference them verbatim.

---

## 6. Troubleshooting

| Issue | Fix |
| --- | --- |
| Contrarian forgets VERDICT | Remind the assistant mid-run; instructions require it. If missing, add a short follow-up prompt to capture `VERDICT: ...` and append to the same file. |
| Role pack missing expected expert | Update the pack JSON or call `prepare` with `--roles +<role>`. |
| Finalize says roles are missing | Inspect `run.json["studio_roles"]["missing"]` for the guilty roles. Either add the artifacts or document why they’re intentionally absent before re-running finalize. |
| Prompt doc drift | Every manifest change should ship with updated `docs/role_prompts/*.md` and doc references. |

---

## 7. Related Docs

- [README.md](../../README.md) – overall workflow and testing notes.
- [CLAUDE_CODE_USAGE.md](./CLAUDE_CODE_USAGE.md) – Claude Code slash commands and workflow.
- [windsurf/USAGE.md](./windsurf/USAGE.md) – Windsurf/Cascade-specific workflow.  
- [API.md](./API.md) – CLI/reference schema.  
- [ARCHITECTURE.md](./ARCHITECTURE.md) – system view of prepare → execute → finalize.  

Keep these aligned whenever you adjust roles, packs, or artifact expectations—Studio has no runtime beyond what’s described here.
