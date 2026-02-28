#!/usr/bin/env python3
"""
Token usage analysis tools for Studio.

Provides commands to analyze token usage across runs and measure optimization impact.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional

from token_tracker import TokenTracker, analyze_token_savings


def get_output_root() -> Path:
    """Get the output root directory."""
    import os
    studio_root = Path(os.getenv("STUDIO_ROOT", Path.cwd()))
    return studio_root / "output"


def find_runs(phase: Optional[str] = None, limit: int = 10) -> List[Path]:
    """Find recent runs, optionally filtered by phase."""
    output_root = get_output_root()
    
    if phase:
        phase_dir = output_root / phase
        if not phase_dir.exists():
            return []
        runs = sorted(phase_dir.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        runs = []
        for phase_dir in output_root.iterdir():
            if phase_dir.is_dir() and not phase_dir.name.startswith('.'):
                runs.extend(phase_dir.glob("run_*"))
        runs = sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)
    
    return runs[:limit]


def cmd_summary(args):
    """Show token summary for a specific run."""
    run_dir = Path(args.run_dir)
    
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}")
        return 1
    
    tracker = TokenTracker(run_dir)
    
    # Load run metadata
    run_json = run_dir / "run.json"
    if not run_json.exists():
        print(f"Error: run.json not found in {run_dir}")
        return 1
    
    meta = json.loads(run_json.read_text())
    stats = tracker.calculate_stats(meta["run_id"], meta["phase"])
    
    if stats.total_tokens == 0:
        print(f"\n⚠️  No token usage data found for {meta['run_id']}")
        print("Token tracking may not have been enabled for this run.")
        print("\nTo track tokens, log usage during the run:")
        print("  tracker.log_usage('advocate', input_tokens=1000, output_tokens=500, iteration=1)")
        return 0
    
    tracker.print_summary(stats)
    
    if args.save:
        tracker.save_summary(stats)
        print(f"\n✅ Summary saved to: {tracker.summary_file}")
    
    return 0


def cmd_compare(args):
    """Compare token usage between two runs."""
    baseline_dir = Path(args.baseline)
    optimized_dir = Path(args.optimized)
    
    if not baseline_dir.exists():
        print(f"Error: Baseline run not found: {baseline_dir}")
        return 1
    
    if not optimized_dir.exists():
        print(f"Error: Optimized run not found: {optimized_dir}")
        return 1
    
    comparison = analyze_token_savings(baseline_dir, optimized_dir)
    
    print("\n" + "=" * 60)
    print("Token Usage Comparison")
    print("=" * 60)
    
    print(f"\nBaseline: {comparison['baseline']['run_id']}")
    print(f"  Tokens: {comparison['baseline']['total_tokens']:,}")
    print(f"  Cost:   ${comparison['baseline']['cost_usd']:.4f}")
    print(f"  Iterations: {comparison['baseline']['iterations']}")
    
    print(f"\nOptimized: {comparison['optimized']['run_id']}")
    print(f"  Tokens: {comparison['optimized']['total_tokens']:,}")
    print(f"  Cost:   ${comparison['optimized']['cost_usd']:.4f}")
    print(f"  Iterations: {comparison['optimized']['iterations']}")
    
    savings = comparison['savings']
    print(f"\nSavings:")
    print(f"  Tokens: {savings['tokens_saved']:,} ({savings['savings_percentage']:.1f}%)")
    print(f"  Cost:   ${savings['cost_saved_usd']:.4f}")
    
    if savings['tokens_saved'] > 0:
        print(f"\n✅ Optimization successful! Saved {savings['savings_percentage']:.1f}% tokens")
    elif savings['tokens_saved'] < 0:
        print(f"\n⚠️  Optimization increased usage by {abs(savings['savings_percentage']):.1f}%")
    else:
        print(f"\n➡️  No change in token usage")
    
    print("=" * 60)
    
    return 0


def cmd_report(args):
    """Generate a report of token usage across recent runs."""
    runs = find_runs(phase=args.phase, limit=args.limit)
    
    if not runs:
        print(f"No runs found{' for phase: ' + args.phase if args.phase else ''}")
        return 1
    
    print("\n" + "=" * 80)
    print(f"Token Usage Report — Recent {len(runs)} Runs")
    if args.phase:
        print(f"Phase: {args.phase}")
    print("=" * 80)
    
    total_tokens = 0
    total_cost = 0.0
    runs_with_data = 0
    
    print(f"\n{'Run ID':<30} {'Phase':<10} {'Tokens':>12} {'Cost':>10} {'Iter':>5}")
    print("-" * 80)
    
    for run_dir in runs:
        run_json = run_dir / "run.json"
        if not run_json.exists():
            continue
        
        meta = json.loads(run_json.read_text())
        tracker = TokenTracker(run_dir)
        stats = tracker.calculate_stats(meta["run_id"], meta["phase"])
        
        if stats.total_tokens > 0:
            runs_with_data += 1
            total_tokens += stats.total_tokens
            total_cost += stats.total_cost_usd
            
            print(f"{meta['run_id']:<30} {meta['phase']:<10} {stats.total_tokens:>12,} "
                  f"${stats.total_cost_usd:>9.4f} {stats.iterations:>5}")
        else:
            print(f"{meta['run_id']:<30} {meta['phase']:<10} {'(no data)':>12} {'-':>10} {'-':>5}")
    
    print("-" * 80)
    print(f"{'TOTAL':<30} {'':<10} {total_tokens:>12,} ${total_cost:>9.4f}")
    print(f"\nRuns with token data: {runs_with_data}/{len(runs)}")
    
    if runs_with_data > 0:
        avg_tokens = total_tokens / runs_with_data
        avg_cost = total_cost / runs_with_data
        print(f"Average per run: {avg_tokens:,.0f} tokens (${avg_cost:.4f})")
    
    print("=" * 80)
    
    return 0


def cmd_estimate(args):
    """Estimate token usage for a planned run."""
    print("\n" + "=" * 60)
    print("Token Usage Estimator")
    print("=" * 60)
    
    # Get inputs
    iterations = args.iterations
    avg_input = args.avg_input or 2000  # Default: 2K input tokens per iteration
    avg_output = args.avg_output or 1000  # Default: 1K output tokens per iteration
    
    # Calculate estimates
    total_input = iterations * avg_input * 2  # advocate + contrarian
    total_output = iterations * avg_output * 2
    total_tokens = total_input + total_output
    
    # Cost estimates (GPT-4 pricing)
    input_cost = (total_input / 1000) * 0.03
    output_cost = (total_output / 1000) * 0.06
    total_cost = input_cost + output_cost
    
    print(f"\nEstimated for {iterations} iterations:")
    print(f"  Input tokens:  {total_input:,} ({iterations} × {avg_input:,} × 2 roles)")
    print(f"  Output tokens: {total_output:,} ({iterations} × {avg_output:,} × 2 roles)")
    print(f"  Total tokens:  {total_tokens:,}")
    print(f"\nEstimated cost (GPT-4 pricing):")
    print(f"  Input:  ${input_cost:.4f}")
    print(f"  Output: ${output_cost:.4f}")
    print(f"  Total:  ${total_cost:.4f}")
    
    if args.scopes:
        print(f"\n💡 With scope-based iteration (typical 20-30% savings):")
        savings_low = total_tokens * 0.20
        savings_high = total_tokens * 0.30
        cost_low = total_cost * 0.80
        cost_high = total_cost * 0.70
        print(f"  Tokens: {total_tokens - int(savings_high):,} - {total_tokens - int(savings_low):,}")
        print(f"  Cost:   ${cost_high:.4f} - ${cost_low:.4f}")
    
    print("=" * 60)
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze token usage for Studio runs"
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Summary command
    summary_parser = subparsers.add_parser('summary', help='Show token summary for a run')
    summary_parser.add_argument('run_dir', help='Path to run directory')
    summary_parser.add_argument('--save', action='store_true', help='Save summary to file')
    
    # Compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two runs')
    compare_parser.add_argument('baseline', help='Baseline run directory')
    compare_parser.add_argument('optimized', help='Optimized run directory')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Generate usage report')
    report_parser.add_argument('--phase', help='Filter by phase')
    report_parser.add_argument('--limit', type=int, default=10, help='Number of runs to show')
    
    # Estimate command
    estimate_parser = subparsers.add_parser('estimate', help='Estimate token usage')
    estimate_parser.add_argument('--iterations', type=int, required=True, help='Number of iterations')
    estimate_parser.add_argument('--avg-input', type=int, help='Avg input tokens per iteration')
    estimate_parser.add_argument('--avg-output', type=int, help='Avg output tokens per iteration')
    estimate_parser.add_argument('--scopes', action='store_true', help='Show savings with scopes')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == 'summary':
        return cmd_summary(args)
    elif args.command == 'compare':
        return cmd_compare(args)
    elif args.command == 'report':
        return cmd_report(args)
    elif args.command == 'estimate':
        return cmd_estimate(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
