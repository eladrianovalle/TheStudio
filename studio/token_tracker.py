#!/usr/bin/env python3
"""
Token usage tracking for Studio runs.

Tracks token consumption across iterations to measure and optimize usage.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


@dataclass
class TokenUsage:
    """Token usage for a single iteration or operation."""
    timestamp: str
    operation: str  # "advocate", "contrarian", "integrator", "validation", etc.
    iteration: Optional[int]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: Optional[str] = None
    cost_usd: Optional[float] = None
    
    @property
    def cost_estimate(self) -> float:
        """Estimate cost based on typical pricing if not provided."""
        if self.cost_usd is not None:
            return self.cost_usd
        
        # Rough estimates (update with actual pricing)
        # GPT-4: ~$0.03/1K input, ~$0.06/1K output
        # Claude: ~$0.015/1K input, ~$0.075/1K output
        input_cost = (self.input_tokens / 1000) * 0.03
        output_cost = (self.output_tokens / 1000) * 0.06
        return input_cost + output_cost


@dataclass
class RunTokenStats:
    """Aggregated token statistics for a run."""
    run_id: str
    phase: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_usd: float
    iterations: int
    operations: List[TokenUsage]
    
    @property
    def avg_tokens_per_iteration(self) -> float:
        """Average tokens per iteration."""
        return self.total_tokens / self.iterations if self.iterations > 0 else 0
    
    @property
    def cost_per_iteration(self) -> float:
        """Average cost per iteration."""
        return self.total_cost_usd / self.iterations if self.iterations > 0 else 0


class TokenTracker:
    """Tracks token usage for Studio runs."""
    
    def __init__(self, run_dir: Path):
        """Initialize tracker for a run directory."""
        self.run_dir = Path(run_dir)
        self.tokens_file = self.run_dir / "tokens.jsonl"
        self.summary_file = self.run_dir / "token_summary.json"
    
    def log_usage(
        self,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        iteration: Optional[int] = None,
        model: Optional[str] = None,
        cost_usd: Optional[float] = None
    ) -> None:
        """
        Log token usage for an operation.
        
        Args:
            operation: Type of operation (advocate, contrarian, etc.)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            iteration: Iteration number (if applicable)
            model: Model name (e.g., "gpt-4", "claude-3-opus")
            cost_usd: Actual cost in USD (if known)
        """
        usage = TokenUsage(
            timestamp=datetime.utcnow().isoformat(),
            operation=operation,
            iteration=iteration,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=model,
            cost_usd=cost_usd
        )
        
        # Append to JSONL file
        with open(self.tokens_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(usage)) + '\n')
    
    def load_usage(self) -> List[TokenUsage]:
        """Load all token usage records."""
        if not self.tokens_file.exists():
            return []
        
        usages = []
        with open(self.tokens_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    usages.append(TokenUsage(**data))
        return usages
    
    def calculate_stats(self, run_id: str, phase: str) -> RunTokenStats:
        """Calculate aggregated statistics."""
        usages = self.load_usage()
        
        if not usages:
            return RunTokenStats(
                run_id=run_id,
                phase=phase,
                total_input_tokens=0,
                total_output_tokens=0,
                total_tokens=0,
                total_cost_usd=0.0,
                iterations=0,
                operations=[]
            )
        
        total_input = sum(u.input_tokens for u in usages)
        total_output = sum(u.output_tokens for u in usages)
        total_cost = sum(u.cost_estimate for u in usages)
        
        # Count unique iterations
        iterations = len(set(u.iteration for u in usages if u.iteration is not None))
        if iterations == 0:
            iterations = 1  # At least one iteration
        
        return RunTokenStats(
            run_id=run_id,
            phase=phase,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_input + total_output,
            total_cost_usd=total_cost,
            iterations=iterations,
            operations=usages
        )
    
    def save_summary(self, stats: RunTokenStats) -> None:
        """Save summary statistics to JSON."""
        summary = {
            "run_id": stats.run_id,
            "phase": stats.phase,
            "total_input_tokens": stats.total_input_tokens,
            "total_output_tokens": stats.total_output_tokens,
            "total_tokens": stats.total_tokens,
            "total_cost_usd": round(stats.total_cost_usd, 4),
            "iterations": stats.iterations,
            "avg_tokens_per_iteration": round(stats.avg_tokens_per_iteration, 2),
            "cost_per_iteration": round(stats.cost_per_iteration, 4),
            "breakdown_by_operation": self._breakdown_by_operation(stats.operations),
            "breakdown_by_iteration": self._breakdown_by_iteration(stats.operations),
        }
        
        with open(self.summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
    
    def _breakdown_by_operation(self, operations: List[TokenUsage]) -> Dict:
        """Break down usage by operation type."""
        breakdown = {}
        for op in operations:
            if op.operation not in breakdown:
                breakdown[op.operation] = {
                    "count": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0
                }
            breakdown[op.operation]["count"] += 1
            breakdown[op.operation]["total_tokens"] += op.total_tokens
            breakdown[op.operation]["total_cost"] += op.cost_estimate
        
        # Round costs
        for op_type in breakdown:
            breakdown[op_type]["total_cost"] = round(breakdown[op_type]["total_cost"], 4)
        
        return breakdown
    
    def _breakdown_by_iteration(self, operations: List[TokenUsage]) -> Dict:
        """Break down usage by iteration."""
        breakdown = {}
        for op in operations:
            if op.iteration is None:
                continue
            
            iter_key = str(op.iteration)
            if iter_key not in breakdown:
                breakdown[iter_key] = {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "operations": []
                }
            breakdown[iter_key]["total_tokens"] += op.total_tokens
            breakdown[iter_key]["total_cost"] += op.cost_estimate
            breakdown[iter_key]["operations"].append(op.operation)
        
        # Round costs
        for iter_key in breakdown:
            breakdown[iter_key]["total_cost"] = round(breakdown[iter_key]["total_cost"], 4)
        
        return breakdown
    
    def print_summary(self, stats: RunTokenStats) -> None:
        """Print a formatted summary to console."""
        print("\n" + "=" * 60)
        print(f"Token Usage Summary — {stats.run_id}")
        print("=" * 60)
        print(f"Phase: {stats.phase}")
        print(f"Iterations: {stats.iterations}")
        print(f"\nTotal Tokens: {stats.total_tokens:,}")
        print(f"  Input:  {stats.total_input_tokens:,}")
        print(f"  Output: {stats.total_output_tokens:,}")
        print(f"\nEstimated Cost: ${stats.total_cost_usd:.4f}")
        print(f"  Per iteration: ${stats.cost_per_iteration:.4f}")
        print(f"  Avg tokens/iteration: {stats.avg_tokens_per_iteration:,.0f}")
        
        # Breakdown by operation
        breakdown = self._breakdown_by_operation(stats.operations)
        if breakdown:
            print(f"\nBreakdown by operation:")
            for op_type, data in sorted(breakdown.items()):
                print(f"  {op_type:15s}: {data['total_tokens']:>8,} tokens (${data['total_cost']:.4f})")
        
        print("=" * 60)


def analyze_token_savings(
    baseline_run: Path,
    optimized_run: Path
) -> Dict:
    """
    Compare token usage between baseline and optimized runs.
    
    Args:
        baseline_run: Path to baseline run directory
        optimized_run: Path to optimized run directory
    
    Returns:
        Dictionary with comparison metrics
    """
    baseline_tracker = TokenTracker(baseline_run)
    optimized_tracker = TokenTracker(optimized_run)
    
    baseline_meta = json.loads((baseline_run / "run.json").read_text())
    optimized_meta = json.loads((optimized_run / "run.json").read_text())
    
    baseline_stats = baseline_tracker.calculate_stats(
        baseline_meta["run_id"],
        baseline_meta["phase"]
    )
    optimized_stats = optimized_tracker.calculate_stats(
        optimized_meta["run_id"],
        optimized_meta["phase"]
    )
    
    tokens_saved = baseline_stats.total_tokens - optimized_stats.total_tokens
    cost_saved = baseline_stats.total_cost_usd - optimized_stats.total_cost_usd
    
    savings_pct = (tokens_saved / baseline_stats.total_tokens * 100) if baseline_stats.total_tokens > 0 else 0
    
    return {
        "baseline": {
            "run_id": baseline_stats.run_id,
            "total_tokens": baseline_stats.total_tokens,
            "cost_usd": baseline_stats.total_cost_usd,
            "iterations": baseline_stats.iterations
        },
        "optimized": {
            "run_id": optimized_stats.run_id,
            "total_tokens": optimized_stats.total_tokens,
            "cost_usd": optimized_stats.total_cost_usd,
            "iterations": optimized_stats.iterations
        },
        "savings": {
            "tokens_saved": tokens_saved,
            "cost_saved_usd": cost_saved,
            "savings_percentage": round(savings_pct, 2)
        }
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python token_tracker.py <run_directory>")
        sys.exit(1)
    
    run_dir = Path(sys.argv[1])
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}")
        sys.exit(1)
    
    tracker = TokenTracker(run_dir)
    
    # Load run metadata
    run_json = run_dir / "run.json"
    if not run_json.exists():
        print(f"Error: run.json not found in {run_dir}")
        sys.exit(1)
    
    meta = json.loads(run_json.read_text())
    stats = tracker.calculate_stats(meta["run_id"], meta["phase"])
    
    tracker.print_summary(stats)
    tracker.save_summary(stats)
    
    print(f"\nSummary saved to: {tracker.summary_file}")
