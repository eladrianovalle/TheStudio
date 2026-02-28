# Token Tracking Guide

**Version**: 2.0.1  
**Status**: Production Ready

---

## Overview

Studio's token tracking system helps you **measure and optimize** token usage across runs. Track consumption, compare optimizations, and validate the 20-30% savings claim from scope-based iteration.

---

## Quick Start

### 1. Enable Token Tracking

During a Studio run, log token usage for each operation:

```python
from token_tracker import TokenTracker

# Initialize tracker for your run
tracker = TokenTracker(run_dir)

# Log advocate iteration
tracker.log_usage(
    operation="advocate",
    input_tokens=2500,
    output_tokens=1200,
    iteration=1,
    model="gpt-4",
    cost_usd=0.15  # Optional: actual cost if known
)

# Log contrarian response
tracker.log_usage(
    operation="contrarian",
    input_tokens=3000,
    output_tokens=800,
    iteration=1,
    model="gpt-4"
)
```

### 2. View Token Summary

```bash
python analyze_tokens.py summary output/tech/run_tech_20260228_123456
```

**Output**:
```
============================================================
Token Usage Summary — run_tech_20260228_123456
============================================================
Phase: tech
Iterations: 3

Total Tokens: 18,500
  Input:  11,000
  Output: 7,500

Estimated Cost: $0.6750
  Per iteration: $0.2250
  Avg tokens/iteration: 6,167

Breakdown by operation:
  advocate       :    9,200 tokens ($0.3360)
  contrarian     :    7,800 tokens ($0.2850)
  integrator     :    1,500 tokens ($0.0540)
============================================================
```

### 3. Compare Runs (Measure Optimization)

```bash
python analyze_tokens.py compare \
  output/tech/run_tech_baseline \
  output/tech/run_tech_with_scopes
```

**Output**:
```
============================================================
Token Usage Comparison
============================================================

Baseline: run_tech_baseline
  Tokens: 25,000
  Cost:   $0.9000
  Iterations: 5

Optimized: run_tech_with_scopes
  Tokens: 18,500
  Cost:   $0.6750
  Iterations: 3

Savings:
  Tokens: 6,500 (26.0%)
  Cost:   $0.2250

✅ Optimization successful! Saved 26.0% tokens
============================================================
```

---

## Token Tracking API

### TokenTracker Class

```python
from token_tracker import TokenTracker

tracker = TokenTracker(run_dir)
```

#### Methods

**`log_usage(operation, input_tokens, output_tokens, **kwargs)`**

Log token usage for an operation.

```python
tracker.log_usage(
    operation="advocate",      # Operation type
    input_tokens=2500,         # Input tokens consumed
    output_tokens=1200,        # Output tokens generated
    iteration=1,               # Optional: iteration number
    model="gpt-4",            # Optional: model name
    cost_usd=0.15             # Optional: actual cost
)
```

**`load_usage() -> List[TokenUsage]`**

Load all token usage records.

```python
usages = tracker.load_usage()
for usage in usages:
    print(f"{usage.operation}: {usage.total_tokens} tokens")
```

**`calculate_stats(run_id, phase) -> RunTokenStats`**

Calculate aggregated statistics.

```python
stats = tracker.calculate_stats("run_tech_123", "tech")
print(f"Total: {stats.total_tokens:,} tokens")
print(f"Cost: ${stats.total_cost_usd:.4f}")
```

**`save_summary(stats)`**

Save summary to `token_summary.json`.

```python
stats = tracker.calculate_stats(run_id, phase)
tracker.save_summary(stats)
```

**`print_summary(stats)`**

Print formatted summary to console.

```python
stats = tracker.calculate_stats(run_id, phase)
tracker.print_summary(stats)
```

---

## Analysis Tools

### 1. Summary Command

View detailed token usage for a specific run.

```bash
python analyze_tokens.py summary <run_dir> [--save]
```

**Options**:
- `--save`: Save summary to `token_summary.json`

**Example**:
```bash
python analyze_tokens.py summary output/tech/run_tech_20260228_123456 --save
```

### 2. Compare Command

Compare token usage between two runs.

```bash
python analyze_tokens.py compare <baseline_dir> <optimized_dir>
```

**Example**:
```bash
python analyze_tokens.py compare \
  output/tech/run_tech_baseline \
  output/tech/run_tech_optimized
```

### 3. Report Command

Generate a report of token usage across recent runs.

```bash
python analyze_tokens.py report [--phase <phase>] [--limit <N>]
```

**Options**:
- `--phase`: Filter by phase (market, design, tech, studio)
- `--limit`: Number of runs to show (default: 10)

**Example**:
```bash
python analyze_tokens.py report --phase tech --limit 20
```

**Output**:
```
================================================================================
Token Usage Report — Recent 10 Runs
Phase: tech
================================================================================

Run ID                         Phase      Tokens        Cost  Iter
--------------------------------------------------------------------------------
run_tech_20260228_150000       tech       18,500    $0.6750     3
run_tech_20260228_140000       tech       22,000    $0.8100     4
run_tech_20260228_130000       tech       25,000    $0.9000     5
...
--------------------------------------------------------------------------------
TOTAL                                    185,000    $6.7500

Runs with token data: 10/10
Average per run: 18,500 tokens ($0.6750)
================================================================================
```

### 4. Estimate Command

Estimate token usage for a planned run.

```bash
python analyze_tokens.py estimate --iterations <N> [--scopes]
```

**Options**:
- `--iterations`: Number of planned iterations
- `--avg-input`: Average input tokens per iteration (default: 2000)
- `--avg-output`: Average output tokens per iteration (default: 1000)
- `--scopes`: Show estimated savings with scope-based iteration

**Example**:
```bash
python analyze_tokens.py estimate --iterations 5 --scopes
```

**Output**:
```
============================================================
Token Usage Estimator
============================================================

Estimated for 5 iterations:
  Input tokens:  20,000 (5 × 2,000 × 2 roles)
  Output tokens: 10,000 (5 × 1,000 × 2 roles)
  Total tokens:  30,000

Estimated cost (GPT-4 pricing):
  Input:  $0.6000
  Output: $0.6000
  Total:  $1.2000

💡 With scope-based iteration (typical 20-30% savings):
  Tokens: 21,000 - 24,000
  Cost:   $0.8400 - $0.9600
============================================================
```

---

## Integration with Windsurf Workflow

### During a Run

1. **In advocate prompt**: After generating response, note token usage
2. **In contrarian prompt**: After generating response, note token usage
3. **Log to tracker**: Use `TokenTracker.log_usage()` after each operation

### Example Workflow

```python
# At start of run
from token_tracker import TokenTracker
tracker = TokenTracker(run_dir)

# After advocate iteration 1
tracker.log_usage(
    operation="advocate",
    input_tokens=2500,  # From Cascade usage stats
    output_tokens=1200,
    iteration=1
)

# After contrarian iteration 1
tracker.log_usage(
    operation="contrarian",
    input_tokens=3000,
    output_tokens=800,
    iteration=1
)

# At end of run
stats = tracker.calculate_stats(run_id, phase)
tracker.save_summary(stats)
tracker.print_summary(stats)
```

---

## Data Storage

### tokens.jsonl

JSONL file with one record per operation:

```jsonl
{"timestamp": "2026-02-28T12:00:00", "operation": "advocate", "iteration": 1, "input_tokens": 2500, "output_tokens": 1200, "total_tokens": 3700, "model": "gpt-4", "cost_usd": 0.15}
{"timestamp": "2026-02-28T12:05:00", "operation": "contrarian", "iteration": 1, "input_tokens": 3000, "output_tokens": 800, "total_tokens": 3800, "model": "gpt-4", "cost_usd": null}
```

### token_summary.json

Aggregated statistics:

```json
{
  "run_id": "run_tech_20260228_123456",
  "phase": "tech",
  "total_input_tokens": 11000,
  "total_output_tokens": 7500,
  "total_tokens": 18500,
  "total_cost_usd": 0.675,
  "iterations": 3,
  "avg_tokens_per_iteration": 6166.67,
  "cost_per_iteration": 0.225,
  "breakdown_by_operation": {
    "advocate": {
      "count": 3,
      "total_tokens": 9200,
      "total_cost": 0.336
    },
    "contrarian": {
      "count": 3,
      "total_tokens": 7800,
      "total_cost": 0.285
    }
  },
  "breakdown_by_iteration": {
    "1": {
      "total_tokens": 6500,
      "total_cost": 0.2375,
      "operations": ["advocate", "contrarian"]
    }
  }
}
```

### run.json (Updated)

Run metadata now includes token summary:

```json
{
  "run_id": "run_tech_20260228_123456",
  "phase": "tech",
  "tokens": {
    "total_input": 11000,
    "total_output": 7500,
    "total": 18500,
    "cost_usd": 0.675,
    "tracked": true
  }
}
```

---

## Measuring Scope-Based Iteration Savings

### Baseline Run (No Scopes)

```bash
# Run without scopes
python run_phase.py prepare --phase tech --text "Build auth" --max-iterations 5 --no-scopes

# Track tokens during run
# ...

# View results
python analyze_tokens.py summary output/tech/run_tech_baseline
```

### Optimized Run (With Scopes)

```bash
# Run with scopes
python run_phase.py prepare --phase tech --text "Build auth" --max-iterations 5

# Track tokens during run
# ...

# View results
python analyze_tokens.py summary output/tech/run_tech_optimized
```

### Compare Results

```bash
python analyze_tokens.py compare \
  output/tech/run_tech_baseline \
  output/tech/run_tech_optimized
```

**Expected savings**: 20-30% with scope-based iteration

---

## Cost Estimation

### Default Pricing (GPT-4)

- **Input**: $0.03 per 1K tokens
- **Output**: $0.06 per 1K tokens

### Custom Pricing

Update `TokenUsage.cost_estimate` in `token_tracker.py`:

```python
@property
def cost_estimate(self) -> float:
    if self.cost_usd is not None:
        return self.cost_usd
    
    # Custom pricing
    if self.model == "claude-3-opus":
        input_cost = (self.input_tokens / 1000) * 0.015
        output_cost = (self.output_tokens / 1000) * 0.075
    else:  # Default GPT-4
        input_cost = (self.input_tokens / 1000) * 0.03
        output_cost = (self.output_tokens / 1000) * 0.06
    
    return input_cost + output_cost
```

---

## Best Practices

### 1. Log Every Operation

Track all token-consuming operations:
- Advocate iterations
- Contrarian responses
- Integrator synthesis
- Validation checks (if using LLM)

### 2. Include Iteration Numbers

Always include `iteration` parameter for per-iteration analysis:

```python
tracker.log_usage("advocate", 2500, 1200, iteration=1)
```

### 3. Use Actual Costs When Available

If you have actual API costs, log them:

```python
tracker.log_usage(
    "advocate", 2500, 1200,
    iteration=1,
    cost_usd=0.15  # Actual cost from API
)
```

### 4. Save Summaries

Always save summaries for historical analysis:

```python
stats = tracker.calculate_stats(run_id, phase)
tracker.save_summary(stats)
```

### 5. Compare Before/After Optimizations

When testing optimizations, always compare:

```bash
python analyze_tokens.py compare baseline optimized
```

---

## Troubleshooting

### No Token Data Found

**Problem**: `analyze_tokens.py summary` shows "No token usage data found"

**Solution**: Token tracking must be manually logged during runs. Add `tracker.log_usage()` calls in your workflow.

### Inaccurate Cost Estimates

**Problem**: Cost estimates don't match actual API costs

**Solution**: 
1. Log actual costs: `tracker.log_usage(..., cost_usd=actual_cost)`
2. Update pricing in `TokenUsage.cost_estimate` property

### Missing tokens.jsonl File

**Problem**: `tokens.jsonl` not found in run directory

**Solution**: Token tracking is opt-in. Create tracker and log usage during run.

---

## Future Enhancements

Planned improvements:
- ⏳ Automatic token tracking via API interceptors
- ⏳ Real-time token usage dashboard
- ⏳ Budget alerts (warn when approaching limits)
- ⏳ Historical trend analysis
- ⏳ Model-specific pricing tables

---

## See Also

- **SCOPES_GUIDE.md**: Scope-based iteration allocation
- **VALIDATION_GUIDE.md**: Validation workflows
- **QUICKSTART.md**: Getting started with Studio

---

**Last Updated**: 2026-02-28
