# Studio Workflow Reference Guide

## What is the Studio Workflow?

When you request a "Studio run" or ask to "trigger the Studio workflow", this means executing a structured multi-disciplinary team review process from `/Users/orcpunk/Repos/_TheGameStudio`.

## Workflow Structure

### Location
- **Working Directory**: `/Users/orcpunk/Repos/_TheGameStudio`
- **Configuration**: `.studio/projects.json`
- **Knowledge Base**: `.studio/knowledge/`
- **Output Directory**: `.studio/output/`

### Key Components

#### 1. Project Configuration
```json
{
  "_TheGameStudio": {
    "project_name": "_TheGameStudio",
    "monthly_budget_usd": 50.0,
    "phase_allocations": {
      "market": 0.15,
      "design": 0.2,
      "tech": 0.25,
      "studio": 0.4
    },
    "scope_allocations": {
      "high_level": 0.4,
      "implementation": 0.4,
      "polish": 0.2
    }
  }
}
```

#### 2. Role-Based Analysis
The Studio workflow uses specific roles for comprehensive analysis:

| Role | Focus | Deliverables |
|------|-------|--------------|
| **Group Product Manager** | Roadmap sequencing, measurable outcomes, staffing | Milestone plan, success metrics, dependency map |
| **Lead Systems Designer** | Fantasy, core loop, experiential pillars | Experience pillars, core loop sketch, risk mitigations |
| **Principal Gameplay Engineer** | Technical architecture, integrations, performance | Architecture outline, tech stack choices, ops checklist |
| **Release QA & Launch Ops Lead** | Validation strategy, tooling, telemetry | Test matrix, rollback plan, instrumentation gaps |
| **Head of Growth Marketing** | Viral hooks, audience segmentation, GTM | Audience ladder, GTM swim lanes, launch KPIs |
| **Art Director** | Visual north star, mood boards, asset expectations | Mood board, style guardrails, production risks |

#### 3. Iteration Process

**Standard Loop:**
1. **Advocate Phase**: Each role creates an optimistic vision
2. **Contrarian Phase**: Each role challenges feasibility and costs
3. **Integrator Phase**: Merge inspiration + constraints into pragmatic plan
4. **Summary**: Final verdict and next steps

**Iteration Logic:**
- Start at iteration 1
- Run Advocate → Contrarian for each role
- If Contrarian returns `VERDICT: REJECTED`, iterate with feedback
- Continue until `VERDICT: APPROVED`
- Move to Integrator for final roadmap

#### 4. Scope-Based Allocation

**High Level (40% of iterations):**
- Focus: Architecture, plans, strategic decisions
- Max iterations: 1

**Implementation (40% of iterations):**
- Focus: Detailed design, API contracts, core implementation
- Max iterations: 1

**Polish (20% of iterations):**
- Focus: Documentation, final review, minor refinements
- Max iterations: 1

## How to Execute a Studio Run

### Step 1: Initialize the Run
```bash
cd /Users/orcpunk/Repos/_TheGameStudio
python run_phase.py studio --input "Your request description"
```

### Step 2: Follow the Generated Instructions
The system creates a run directory like:
```
.studio/output/studio/run_studio_YYYYMMDD_HHMMSS/
├── instructions.md          # Detailed execution guide
├── run.json                 # Run metadata
├── advocate--<role>--01.md  # Role advocate outputs
├── contrarian--<role>--01.md # Role contrarian outputs
├── integrator.md            # Final integrated plan
└── summary.md               # Run summary
```

### Step 3: Execute Role-Based Analysis
For each participating role:

1. **Advocate Analysis**: Create `advocate--<role>--<iteration>.md`
2. **Contrarian Analysis**: Create `contrarian--<role>--<iteration>.md`
3. **Check Verdict**: Look for `VERDICT: APPROVED/REJECTED`
4. **Iterate if Needed**: Use contrarian feedback for next iteration

### Step 4: Integrator Duel (After Approval)
Inside `integrator.md`:
1. `### Integrator Advocate` - Summarize fused plan
2. `### Integrator Contrarian` - Critique feasibility, end with verdict
3. `### Integrated Plan` - Synthesize both perspectives

### Step 5: Finalize the Run
```bash
python run_phase.py finalize --phase studio --run-id <run-id> --status completed --verdict <APPROVED|REJECTED|N/A>
```

## File Structure Reference

### Input Files
- `instructions.md` - Execution guide and role menu
- `run.json` - Run metadata and configuration

### Output Files (Per Role)
- `advocate--<role>--<n>.md` - Optimistic vision and recommendations
- `contrarian--<role>--<n>.md` - Reality check and constraints

### Integration Files
- `integrator.md` - Final merged roadmap
- `summary.md` - Complete run summary and next steps

### Tracking Files
- `.studio/knowledge/run_log.md` - Historical run log
- `.studio/output/index.md` - Master index of all runs

## Best Practices

### 1. Clear Input Definition
Be specific about:
- **Problem Statement**: What needs to be solved
- **Success Criteria**: How success will be measured
- **Constraints**: Budget, timeline, technical limitations
- **Roles Needed**: Which perspectives are required

### 2. Iteration Management
- **Don't Force Approval**: If contrarian rejects, genuinely address concerns
- **Scope Control**: Stay within allocated iterations per scope
- **Role Relevance**: Only include roles that add value to the problem

### 3. Quality Standards
- **Specific Recommendations**: Avoid vague suggestions
- **Actionable Steps**: Each recommendation should have clear next steps
- **Risk Assessment**: Identify and mitigate potential issues
- **Resource Planning**: Include realistic time and cost estimates

### 4. Documentation
- **Complete Summaries**: Capture all key decisions and rationale
- **Next Steps**: Clear actionable items after approval
- **Lessons Learned**: Document insights for future runs

## Example Usage

### User Request:
"Run a Studio workflow to analyze the TMP migration enhancement requirements"

### Expected Execution:
1. **Initialize**: `python run_phase.py studio --input "TMP migration enhancement analysis"`
2. **Role Selection**: Engineering, QA, Design (Product)
3. **Analysis**: Each role provides advocate/contrarian perspectives
4. **Integration**: Merge into comprehensive proposal
5. **Decision**: Approve/reject based on integrated analysis

### Expected Output:
- Technical feasibility assessment
- Risk analysis and mitigation strategies
- Implementation timeline and resource requirements
- Validation strategy and success criteria
- Business case and ROI analysis

## Common Patterns

### Technical Problems
- **Roles**: Engineering, QA, Product
- **Focus**: Architecture, validation, roadmap
- **Output**: Technical specs, test plans, implementation timeline

### Product Features
- **Roles**: Product, Design, Engineering, Marketing
- **Focus**: User value, feasibility, GTM strategy
- **Output**: Product requirements, design specs, launch plan

### Strategic Decisions
- **Roles**: All roles
- **Focus**: Business case, market fit, operational readiness
- **Output**: Strategic plan, resource allocation, success metrics

## Troubleshooting

### Common Issues
1. **Run Directory Not Created**: Check input format and permissions
2. **Role Files Missing**: Verify role selection in instructions.md
3. **Integration Failure**: Ensure all roles have APPROVED verdicts
4. **Finalization Error**: Check run.json format and file paths

### Recovery Steps
1. **Check Instructions**: Review `instructions.md` for specific requirements
2. **Verify Outputs**: Ensure all required files are created
3. **Validate Verdicts**: Confirm APPROVED status before integration
4. **Review Logs**: Check `run_log.md` for historical patterns

---

## Quick Reference Commands

```bash
# Initialize Studio run
cd /Users/orcpunk/Repos/_TheGameStudio
python run_phase.py studio --input "Your request"

# Check run status
ls .studio/output/studio/

# Finalize completed run
python run_phase.py finalize --phase studio --run-id <run-id> --status completed --verdict APPROVED

# View run history
cat .studio/knowledge/run_log.md
```

This guide ensures consistent execution of Studio workflows across all projects and maintains the quality standards established in the Studio system.
