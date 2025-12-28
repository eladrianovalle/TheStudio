# Agents Reference (Cascade Edition)

Studio no longer spins up its own agents. Instead, we describe every persona in Markdown/JSON so Windsurf/Cascade can roleplay them deterministically during the prepare → execute → finalize loop. Use this file to understand what each phase expects and how to extend or override roles safely.

---

## 1. Phases & Canonical Roles

The non-studio phases each follow a single Advocate ↔ Contrarian loop, then hand off to an implementer checklist. Studio phase invites multiple disciplines simultaneously via role packs. Tables below mirror `PHASE_DETAILS` inside `run_phase.py` and the default Studio manifest.

### Market Phase

| Persona | Description |
| --- | --- |
| Advocate – Market Growth Strategist | Steel-man the idea into a high-virality Steam hook. Focus on audience segments, unique hooks, and low-cost launch tactics. |
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
| Advocate – Three.js Technical Architect | Define performant architecture, stack, and modules for WebGL delivery. |
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
| qa | Release QA & Launch Ops Lead | Validation strategy, telemetry | Coverage gaps, environment readiness | Test matrix, rollback plan, instrumentation gaps |

Each invited role writes `advocate--<role>--NN.md` and `contrarian--<role>--NN.md` until the contrarian issues `VERDICT: APPROVED`. After all critical roles approve, the Integrator runs a capped duel (two passes max) inside `integrator.md`.

---

## 2. Role Menu & Prompt Docs

- `run_phase.py prepare --phase studio` renders a **Role Menu** listing every invited role, deliverables, filenames, and a link to its prompt doc (`docs/role_prompts/<role>.md`).
- Prompt docs hold the long-form guidance that used to clog instructions. Update them whenever you change a role’s responsibilities.
- Escalation cues in the manifest tell Cascade when to invite additional roles (e.g., Marketing escalates Legal when policies are at risk).

---

## 3. Artifact Expectations

| Phase | Advocate Files | Contrarian Files | Post-approval artifact |
| --- | --- | --- | --- |
| Market/Design/Tech | `advocate_<n>.md` | `contrarian_<n>.md` | `implementation.md` |
| Studio | `advocate--<role>--<n>.md` | `contrarian--<role>--<n>.md` | `integrator.md` (with duel sections) |

Contrarians must always end with `VERDICT: APPROVED` or `VERDICT: REJECTED`. Finalize will flag missing files per role and record `completed`/`missing` lists in `run.json["studio_roles"]`.

---

## 4. Customizing Roles

1. **Update `studio.manifest.json`**  
   - Add new roles, tweak focuses, amend deliverables, or adjust escalation cues.  
   - Keep `prompt_doc` paths in sync with `docs/role_prompts/`.
2. **Adjust role packs (`role_packs/*.json`)**  
   - Create additional packs (e.g., `liveops_hotfix.json` or `monetization_review.json`).  
   - Operators select them via `--role-pack` and override attendance with `--roles +foo -bar`.
3. **Document changes**  
   - Update README, Interaction Guide, API, and Bridge Template whenever roles or packs shift.  
   - Mention the new pack in downstream bridge docs so Cascade loads it explicitly.

Because everything is declarative, there’s no hidden CrewAI config to edit—just JSON + Markdown.

---

## 5. Best Practices for Operators

1. **Always cite Role Menu entries** when asking Cascade to write artifacts (“Use the Marketing role definition from instructions”).  
2. **Loop until VERDICT: APPROVED** per role; avoid skipping contrarian passes because finalize will block completion.  
3. **Use `roles_needed.md` (optional)** to track escalations when a contrarian says “bring Security in.” You can schedule a follow-up run with `--roles +security`.  
4. **Summaries should list confidence per role** (e.g., `marketing_confidence: 0.7`) so downstream readers know which pods need follow-up.  
5. **Keep prompt docs concise but specific**. Point to canonical examples, KPIs, and failure modes. Cascade will reference them verbatim.

---

## 6. Troubleshooting

| Issue | Fix |
| --- | --- |
| Contrarian forgets VERDICT | Remind Cascade mid-run; instructions require it. If missing, add a short follow-up prompt to capture `VERDICT: ...` and append to the same file. |
| Role pack missing expected expert | Update the pack JSON or call `prepare` with `--roles +<role>`. |
| Finalize says roles are missing | Inspect `run.json["studio_roles"]["missing"]` for the guilty roles. Either add the artifacts or document why they’re intentionally absent before re-running finalize. |
| Prompt doc drift | Every manifest change should ship with updated `docs/role_prompts/*.md` and doc references. |

---

## 7. Related Docs

- [README.md](../README.md) – overall workflow and testing notes.  
- [STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md) – day-to-day instructions.  
- [WINDSURF_USAGE.md](./WINDSURF_USAGE.md) – prompts + palette shortcuts.  
- [API.md](./API.md) – CLI/reference schema.  
- [ARCHITECTURE.md](./ARCHITECTURE.md) – system view of prepare → execute → finalize.  

Keep these aligned whenever you adjust roles, packs, or artifact expectations—Studio has no runtime beyond what’s described here.
