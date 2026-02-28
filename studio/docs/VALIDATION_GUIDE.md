# Studio Validation Guide

## Overview

Studio validation provides automated quality checks for run outputs. It validates documents during the discussion phase and code during the implementation phase, ensuring consistent quality across all runs.

## Quick Start

### 1. Run Validation

After completing a Studio run:

```bash
python run_phase.py validate --phase tech --run-id run_tech_20260227_184406
```

### 2. Review Results

```
============================================================
Validating run_tech_20260227_184406 (tech phase)
============================================================

## Discussion Phase Validation

✓ All document checks PASSED

## Implementation Phase Validation

Running code checks: pytest, mypy, ruff

Results: 3/3 checks passed

  ✓ pytest - PASSED (2.34s)
  ✓ mypy - PASSED (1.12s)
  ✓ ruff - PASSED (0.45s)

============================================================
Validation complete
============================================================
```

## Phase-Appropriate Validation

### Discussion Phase (All Phases)

Validates **documents** (advocate/contrarian Markdown files):

- **Completeness**: Required sections present
- **Consistency**: Contrarian addresses advocate's key points
- **Format**: Proper markdown structure
- **Verdict**: Valid APPROVED/REJECTED with reasons

**Applies to**: Market, Design, Tech, Studio phases

### Implementation Phase (Tech/Studio Only)

Validates **code** (integrator/implementation outputs):

- **pytest**: Unit tests pass
- **mypy**: Type checking passes
- **ruff**: Linting passes
- **black**: Code formatting (optional)

**Applies to**: Tech and Studio phases only

## Configuration

### Default Config

Studio includes a default validation config at `.studio/validation.toml`:

```toml
# Market Phase
[market_phase.discussion]
required_sections = [
    "Target Audience",
    "Competitors",
    "Unique Value Proposition",
    "Go-to-Market Plan",
    "Success Metrics"
]

# Tech Phase
[tech_phase.discussion]
required_sections = [
    "Architecture",
    "Technology Stack",
    "File Structure",
    "Performance",
    "Deployment"
]

[tech_phase.implementation]
checks = ["pytest", "mypy", "ruff"]
timeout = 60
```

### Custom Config

Create your own validation rules:

```bash
# Create custom config
cp .studio/validation.toml my-validation.toml

# Edit rules
vim my-validation.toml

# Use custom config
python run_phase.py validate --phase tech --run-id run_tech_20260227_184406 \
  --config my-validation.toml
```

### Config Format

```toml
# Discussion phase validation
[<phase>_phase.discussion]
required_sections = [
    "Section 1",
    "Section 2",
    # ...
]

# Implementation phase validation
[<phase>_phase.implementation]
checks = ["pytest", "mypy", "ruff", "black"]
timeout = 60  # seconds
```

## Validation Checks

### Document Checks

#### Completeness

Verifies all required sections are present in documents.

**Example**:
```toml
[tech_phase.discussion]
required_sections = ["Architecture", "Technology Stack"]
```

**Behavior**:
- Checks for section headers (case-insensitive)
- Allows partial matches ("Architecture Overview" matches "Architecture")
- Reports missing sections as issues

#### Consistency

Ensures contrarian addresses advocate's key points.

**How it works**:
1. Extracts key points from advocate (numbered lists, bullets, bold text)
2. Checks if contrarian content mentions those points
3. Warns if >3 points are unaddressed

**Note**: Uses warnings, not hard failures (contrarian may address points implicitly)

#### Format

Validates markdown structure and formatting.

**Checks**:
- Document has top-level title (`# Title`)
- No excessive blank lines (>3 consecutive)
- Proper list formatting (space after `1.` or `-`)
- Minimum document length (>100 characters)

#### Verdict

Confirms contrarian has valid verdict.

**Requirements**:
- Must contain `VERDICT: APPROVED` or `VERDICT: REJECTED`
- If REJECTED, should include reasons (warns if missing)

### Code Checks

#### pytest

Runs unit tests using pytest.

**Command**: `pytest -v`

**Pass criteria**: Exit code 0 (all tests pass)

#### mypy

Runs static type checking.

**Command**: `mypy . --strict`

**Pass criteria**: Exit code 0 (no type errors)

#### ruff

Runs fast Python linting.

**Command**: `ruff check .`

**Pass criteria**: Exit code 0 (no lint errors)

#### black

Checks code formatting (optional).

**Command**: `black . --check`

**Pass criteria**: Exit code 0 (code is formatted)

## Usage Examples

### Example 1: Validate Market Phase

```bash
python run_phase.py validate --phase market --run-id run_market_20260227_120000
```

**Output**:
```
## Discussion Phase Validation

Checking for required sections: Target Audience, Competitors, Unique Value Proposition, Go-to-Market Plan, Success Metrics

✓ All document checks PASSED

Warnings:
  ⚠ Missing section: "Success Metrics"
```

### Example 2: Validate Tech Phase with Code

```bash
python run_phase.py validate --phase tech --run-id run_tech_20260227_130000
```

**Output**:
```
## Discussion Phase Validation

✓ All document checks PASSED

## Implementation Phase Validation

Running code checks: pytest, mypy, ruff

Results: 2/3 checks passed

  ✓ pytest - PASSED (2.34s)
  ✓ mypy - PASSED (1.12s)
  ✗ ruff - FAILED (0.45s)
      src/main.py:42:80: E501 Line too long (85 > 79 characters)
```

### Example 3: Custom Validation Config

```bash
# Create strict validation config
cat > strict-validation.toml << 'EOF'
[tech_phase.discussion]
required_sections = [
    "Architecture Overview",
    "Technology Stack",
    "File Structure",
    "Performance Considerations",
    "Deployment Strategy",
    "Security Considerations",
    "Monitoring Plan",
    "Rollback Strategy"
]

[tech_phase.implementation]
checks = ["pytest", "mypy", "ruff", "black"]
timeout = 120
EOF

# Use strict config
python run_phase.py validate --phase tech --run-id run_tech_20260227_130000 \
  --config strict-validation.toml
```

## Integration with Other Features

### With Scopes (Phase 1)

Validation works seamlessly with scope-based runs:

```bash
# Run with scopes
python run_phase.py prepare --phase tech --text "Build auth" \
  --scopes .studio/scopes.toml

# Validate scoped run
python run_phase.py validate --phase tech --run-id run_tech_20260227_140000
```

### With Rerun (Phase 2)

Validation failures can feed into rerun context:

1. **Validate run**: `python run_phase.py validate --phase tech --run-id run_tech_20260227_140000`
2. **Validation fails**: Missing sections, code errors
3. **Contrarian references failures**: "VERDICT: REJECTED - Missing Architecture section, pytest failures"
4. **Rerun detects rejection**: Extracts validation failures as reasons
5. **Next iteration**: Advocate sees specific validation issues to fix

**Automated feedback loop**: validate → fail → extract → inject → retry

## Troubleshooting

### Issue: "Validation config not found"

**Cause**: No `.studio/validation.toml` file

**Solution**:
```bash
# Create default config
mkdir -p .studio
cat > .studio/validation.toml << 'EOF'
[tech_phase.discussion]
required_sections = ["Architecture", "Technology Stack"]

[tech_phase.implementation]
checks = ["pytest"]
timeout = 60
EOF
```

### Issue: "Command not found: pytest"

**Cause**: Code check tool not installed

**Solution**:
```bash
# Install missing tools
pip install pytest mypy ruff black
```

### Issue: "No implementation artifacts found"

**Cause**: No `implementation.md` or `integrator.md` in run directory

**Solution**: This is expected if the run hasn't reached implementation phase yet. Code validation is skipped automatically.

### Issue: Too many warnings

**Cause**: Strict validation rules

**Solution**: Adjust config to be less strict:
```toml
[tech_phase.discussion]
# Reduce required sections
required_sections = ["Architecture", "Technology Stack"]
```

## Best Practices

### 1. Validate After Finalize

Always run validation after finalizing a run:

```bash
# Standard workflow
python run_phase.py prepare --phase tech --text "Build feature"
# ... run advocate/contrarian loop ...
python run_phase.py finalize --phase tech --run-id run_tech_20260227_150000 --status completed --verdict APPROVED
python run_phase.py validate --phase tech --run-id run_tech_20260227_150000
```

### 2. Start with Minimal Config

Begin with few required sections, add more as needed:

```toml
# Start simple
[tech_phase.discussion]
required_sections = ["Architecture", "Technology Stack"]

# Expand over time
[tech_phase.discussion]
required_sections = [
    "Architecture",
    "Technology Stack",
    "Performance",
    "Security",
    "Monitoring"
]
```

### 3. Use Warnings, Not Failures

Configure checks to warn rather than fail for non-critical issues:

- Consistency checks use warnings by default
- Format checks warn about minor issues
- Only completeness and verdict checks cause hard failures

### 4. Customize Per-Project

Different projects need different validation:

```bash
# Game project
.studio/game-validation.toml

# Web app project
.studio/webapp-validation.toml

# Use appropriate config
python run_phase.py validate --phase tech --run-id run_tech_20260227_150000 \
  --config .studio/game-validation.toml
```

### 5. Automate in CI/CD

Add validation to your CI pipeline:

```yaml
# .github/workflows/studio-validate.yml
name: Validate Studio Runs

on: [push]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Validate latest run
        run: |
          python run_phase.py validate --phase tech --run-id $LATEST_RUN_ID
```

## FAQ

### Q: Is validation required?

**A**: No, validation is optional. Run it manually when you want quality checks.

### Q: Can I auto-run validation on finalize?

**A**: Not currently, but you can add it to your workflow:
```bash
python run_phase.py finalize ... && python run_phase.py validate ...
```

### Q: What if a check fails?

**A**: Validation reports failures but doesn't block anything. Review the output and decide whether to fix issues or proceed.

### Q: Can I add custom checks?

**A**: Yes, extend `CodeValidator` class in `validators/code_validator.py` to add new check methods.

### Q: Does validation work with Studio phase?

**A**: Yes, validates multi-role documents and integrator code if configured.

### Q: How long does validation take?

**A**: Document validation: <1s. Code validation: 2-60s depending on project size.

### Q: Can I skip certain checks?

**A**: Yes, remove them from the `checks` list in config:
```toml
[tech_phase.implementation]
checks = ["pytest"]  # Only run pytest, skip mypy and ruff
```

## See Also

- [STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md) - Standard Studio workflow
- [SCOPES_GUIDE.md](./SCOPES_GUIDE.md) - Scope-based iteration allocation
- [IMPLEMENTATION_PLAN.md](../output/studio/run_studio_20260227_174319/IMPLEMENTATION_PLAN.md) - Full implementation details
