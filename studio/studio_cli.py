#!/usr/bin/env python3
"""
Studio CLI - Command-line interface for Studio agents.
Designed to be called from Windsurf Cascade or other projects.
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add studio to path
studio_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(studio_path))

from studio.crew import StudioCrew
from studio.iteration import run_iterative_kickoff


def evaluate(game_idea: str, phase: str = 'market', output_format: str = 'text') -> dict:
    """
    Evaluate a game idea using Studio agents.
    
    Args:
        game_idea: The game concept to evaluate
        phase: Evaluation phase (market, design, tech)
        output_format: Output format (text, json)
    
    Returns:
        dict with result and verdict
    """
    try:
        max_iterations = os.environ.get("STUDIO_MAX_ITERATIONS")

        def crew_factory():
            return StudioCrew(phase=phase).crew()

        base_inputs = {'game_idea': game_idea}
        if phase == "studio":
            base_inputs.update(
                {
                    'objective': game_idea,
                    'budget_cap': os.environ.get("STUDIO_BUDGET_CAP", "$200/month & <10 dev hours/week"),
                }
            )

        iteration_result = run_iterative_kickoff(
            crew_factory=crew_factory,
            phase=phase,
            base_inputs=base_inputs,
            max_iterations=max_iterations,
        )
        
        return {
            'success': True,
            'phase': phase,
            'game_idea': game_idea,
            'verdict': iteration_result['verdict'],
            'result': iteration_result['result'],
            'iterations_run': iteration_result['iterations_run'],
            'accepted': iteration_result['accepted'],
            'limit_reached': iteration_result['limit_reached'],
            'max_iterations': iteration_result['max_iterations'],
            'history': iteration_result['history'],
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'phase': phase,
            'game_idea': game_idea
        }


def pipeline(game_idea: str, output_format: str = 'text') -> dict:
    """
    Run full evaluation pipeline (all phases).
    
    Args:
        game_idea: The game concept to evaluate
        output_format: Output format (text, json)
    
    Returns:
        dict with results from all phases
    """
    phases = ['market', 'design', 'tech']
    results = {}
    
    for phase in phases:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Running {phase.upper()} phase...", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        phase_result = evaluate(game_idea, phase, output_format)
        results[phase] = phase_result
        
        if not phase_result.get('success', False):
            break
            
        if phase_result.get('verdict') == 'REJECTED':
            print(f"\n❌ Rejected in {phase} phase. Stopping pipeline.\n", file=sys.stderr)
            break
    
    return {
        'game_idea': game_idea,
        'phases_completed': list(results.keys()),
        'results': results
    }


def main():
    parser = argparse.ArgumentParser(
        description='Studio Agent CLI - Evaluate game concepts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate market phase
  %(prog)s evaluate "A 3D stealth horror roguelike" --phase market
  
  # Run full pipeline
  %(prog)s pipeline "A 3D stealth horror roguelike"
  
  # Get JSON output
  %(prog)s evaluate "Your idea" --phase design --format json
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Evaluate command
    eval_parser = subparsers.add_parser('evaluate', help='Evaluate a single phase')
    eval_parser.add_argument('game_idea', help='Game concept to evaluate')
    eval_parser.add_argument('--phase', default='market', 
                            choices=['market', 'design', 'tech', 'studio'],
                            help='Evaluation phase (default: market)')
    eval_parser.add_argument('--format', default='text',
                            choices=['text', 'json'],
                            help='Output format (default: text)')
    
    # Pipeline command
    pipeline_parser = subparsers.add_parser('pipeline', help='Run full evaluation pipeline')
    pipeline_parser.add_argument('game_idea', help='Game concept to evaluate')
    pipeline_parser.add_argument('--format', default='text',
                                choices=['text', 'json'],
                                help='Output format (default: text)')
    
    # List phases command
    list_parser = subparsers.add_parser('list-phases', help='List available phases')
    
    args = parser.parse_args()
    
    if args.command == 'evaluate':
        result = evaluate(args.game_idea, args.phase, args.format)
        
        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            if result['success']:
                print(f"\n{'='*60}")
                print(f"Phase: {result['phase'].upper()}")
                print(f"Verdict: {result['verdict']}")
                print(f"{'='*60}\n")
                print(result['result'])
            else:
                print(f"Error: {result['error']}", file=sys.stderr)
                sys.exit(1)
    
    elif args.command == 'pipeline':
        result = pipeline(args.game_idea, args.format)
        
        if args.format == 'json':
            print(json.dumps(result, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"PIPELINE COMPLETE")
            print(f"{'='*60}")
            print(f"\nPhases completed: {', '.join(result['phases_completed'])}")
            
            for phase, phase_result in result['results'].items():
                if phase_result.get('success'):
                    print(f"\n{phase.upper()}: {phase_result['verdict']}")
    
    elif args.command == 'list-phases':
        phases = {
            'market': 'Market viability analysis',
            'design': 'Gameplay design validation',
            'tech': 'Technical feasibility check'
        }
        
        print("\nAvailable phases:")
        for phase, description in phases.items():
            print(f"  {phase:10} - {description}")
        print()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
