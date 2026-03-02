#!/usr/bin/env python3
"""
Studio Budget Tracker
Track and budget Studio workflow resource usage across multiple projects and runs.

Limitations & Guidance
======================
* Estimates are based on expected **output generation only**. Inputs, retries, and
  Cascade system overhead are not observable from the local environment, so real
  usage may be 40–50% higher than the numbers shown here.
* Use estimates for **relative comparison** (e.g., tech vs. studio phase, two vs.
  three iterations) rather than precise billing.
* Post-run validation counts markdown output tokens to provide a sanity check on
  whether a run roughly matched its estimate. This is still an approximation and
  should be treated as informational feedback rather than a billing source of truth.
* When precise accounting is required, consult Windsurf's "View Cascade Usage" to
  review actual Cascade billing data.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

@dataclass
class StudioRunCost:
    """Cost data for a single Studio run."""
    run_id: str
    phase: str
    project: str
    timestamp: str
    estimated_tokens: int
    estimated_cost_usd: float
    iterations: int
    scopes: List[str]
    complexity_score: float  # 1.0 = simple, 2.0 = medium, 3.0 = complex
    
@dataclass
class ProjectBudget:
    """Budget allocation for a specific project."""
    project_name: str
    monthly_budget_usd: float
    daily_budget_usd: float
    phase_allocations: Dict[str, float]  # phase -> percentage
    scope_allocations: Dict[str, float]  # scope -> percentage
    
@dataclass
class StudioBudgetStatus:
    """Current budget status across all projects."""
    total_monthly_budget: float
    total_spent_this_month: float
    total_remaining: float
    project_breakdown: Dict[str, Dict]
    daily_usage_trend: List[Dict]
    recommendations: List[str]
    trend_summary: Optional[Dict[str, float]] = None

OUTPUT_COST_PER_1K_TOKENS = 0.06  # Approximate GPT-4 output pricing
INPUT_OUTPUT_MULTIPLIER = 2.0     # Rough multiplier to account for unseen costs
MAX_DAILY_TOTALS = 60             # Keep at most ~2 months of daily aggregates


class StudioBudgetTracker:
    """Track Studio workflow costs and budgets across projects."""
    
    def __init__(self):
        self.studio_root = Path(__file__).parent.parent
        self.budget_file = self.studio_root / ".studio" / "budget_config.json"
        self.usage_file = self.studio_root / ".studio" / "usage_log.json"
        self.projects_file = self.studio_root / ".studio" / "projects.json"
        
    def initialize_project_budget(self, project_name: str, monthly_budget: float, 
                                 phase_weights: Optional[Dict[str, float]] = None,
                                 scope_weights: Optional[Dict[str, float]] = None) -> ProjectBudget:
        """Initialize budget tracking for a project."""
        
        if not project_name or not project_name.strip():
            raise ValueError("Project name must be provided for budget initialization")
        if monthly_budget <= 0:
            raise ValueError("Monthly budget must be greater than 0")
        
        # Default phase allocations based on typical Studio usage
        default_phase_weights = {
            "market": 0.15,      # Market analysis usually less expensive
            "design": 0.20,      # Design work moderate cost
            "tech": 0.25,        # Technical implementation most expensive
            "studio": 0.40       # Studio phase with multiple roles highest cost
        }
        
        # Default scope allocations
        default_scope_weights = {
            "high_level": 0.40,    # Strategy and planning
            "implementation": 0.40,  # Detailed work
            "polish": 0.20         # Refinement and documentation
        }
        
        phase_weights = phase_weights or default_phase_weights
        scope_weights = scope_weights or default_scope_weights
        
        daily_budget = monthly_budget / 30  # 30-day month
        
        budget = ProjectBudget(
            project_name=project_name,
            monthly_budget_usd=monthly_budget,
            daily_budget_usd=daily_budget,
            phase_allocations=phase_weights,
            scope_allocations=scope_weights
        )
        
        self.save_project_budget(budget)
        return budget
    
    def estimate_run_cost(self, phase: str, iterations: int = 3, 
                         scopes: Optional[List[str]] = None,
                         complexity: float = 1.0) -> StudioRunCost:
        """Estimate cost for a Studio run based on phase and complexity."""
        
        phase = (phase or "").lower()
        if phase not in {"market", "design", "tech", "studio"}:
            raise ValueError("Phase must be one of: market, design, tech, studio")
        if iterations <= 0:
            raise ValueError("Iterations must be >= 1")
        if complexity <= 0:
            raise ValueError("Complexity must be > 0")
        if scopes is not None and not scopes:
            raise ValueError("Scopes list cannot be empty when provided")
        
        # Base cost estimates per phase (from empirical data)
        base_costs = {
            "market": {"tokens": 5000, "cost_usd": 2.50},
            "design": {"tokens": 8000, "cost_usd": 4.00},
            "tech": {"tokens": 12000, "cost_usd": 6.00},
            "studio": {"tokens": 20000, "cost_usd": 10.00}  # Multiple roles
        }
        
        base = base_costs[phase]
        
        # Adjust for iterations
        iteration_multiplier = 1.0 + (iterations - 1) * 0.3
        
        # Adjust for complexity
        complexity_multiplier = complexity
        
        # Adjust for scopes (more scopes = more work)
        scope_multiplier = 1.0
        if scopes:
            scope_multiplier = 1.0 + (len(scopes) - 1) * 0.2
        
        estimated_tokens = int(base["tokens"] * iteration_multiplier * complexity_multiplier * scope_multiplier)
        estimated_cost = base["cost_usd"] * iteration_multiplier * complexity_multiplier * scope_multiplier
        
        return StudioRunCost(
            run_id="",  # Will be set when run is created
            phase=phase,
            project="",  # Will be set based on current directory
            timestamp=datetime.now(timezone.utc).isoformat(),
            estimated_tokens=estimated_tokens,
            estimated_cost_usd=estimated_cost,
            iterations=iterations,
            scopes=scopes or ["high_level"],
            complexity_score=complexity
        )
    
    def check_project_budget(self, project_name: str, planned_run: StudioRunCost) -> Dict:
        """Check if a planned run fits within project budget."""
        
        budget = self.get_project_budget(project_name)
        if not budget:
            return {"error": f"No budget configured for project: {project_name}"}
        
        # Get current usage for this project and month
        current_usage = self.get_project_usage_this_month(project_name)
        
        # Calculate post-run usage
        new_total = current_usage["spent"] + planned_run.estimated_cost_usd
        remaining_budget = budget.monthly_budget_usd - new_total
        
        # Check phase allocation
        phase_usage = self.get_phase_usage_this_month(project_name, planned_run.phase)
        phase_budget = budget.monthly_budget_usd * budget.phase_allocations.get(planned_run.phase, 0.25)
        new_phase_total = phase_usage + planned_run.estimated_cost_usd
        phase_remaining = phase_budget - new_phase_total
        
        # Check daily budget
        today_usage = self.get_project_usage_today(project_name)
        daily_remaining = budget.daily_budget_usd - (today_usage + planned_run.estimated_cost_usd)
        
        status = {
            "project": project_name,
            "run_cost": planned_run.estimated_cost_usd,
            "monthly": {
                "budget": budget.monthly_budget_usd,
                "spent": current_usage["spent"],
                "remaining": remaining_budget,
                "status": "ok" if remaining_budget > 0 else "exceeded"
            },
            "phase": {
                "phase": planned_run.phase,
                "budget": phase_budget,
                "spent": phase_usage,
                "remaining": phase_remaining,
                "status": "ok" if phase_remaining > 0 else "exceeded"
            },
            "daily": {
                "budget": budget.daily_budget_usd,
                "spent": today_usage,
                "remaining": daily_remaining,
                "status": "ok" if daily_remaining > 0 else "exceeded"
            },
            "recommendations": self.generate_recommendations(budget, planned_run, current_usage)
        }
        
        return status
    
    def generate_recommendations(self, budget: ProjectBudget, planned_run: StudioRunCost, 
                               current_usage: Dict) -> List[str]:
        """Generate budget recommendations for planned run."""
        
        recommendations = []
        
        # Check overall budget
        if current_usage["spent"] + planned_run.estimated_cost_usd > budget.monthly_budget_usd:
            recommendations.append(f"❌ This run will exceed your monthly budget of ${budget.monthly_budget_usd:.2f}")
            recommendations.append(f"   Consider reducing iterations or complexity")
        elif current_usage["spent"] + planned_run.estimated_cost_usd > budget.monthly_budget_usd * 0.8:
            recommendations.append(f"⚠️  This run will use {((current_usage['spent'] + planned_run.estimated_cost_usd) / budget.monthly_budget_usd * 100):.1f}% of your monthly budget")
        
        # Check phase allocation
        phase_budget = budget.monthly_budget_usd * budget.phase_allocations.get(planned_run.phase, 0.25)
        phase_usage = self.get_phase_usage_this_month(planned_run.project or "default", planned_run.phase)
        if phase_usage + planned_run.estimated_cost_usd > phase_budget:
            recommendations.append(f"⚠️  This run exceeds your {planned_run.phase} phase allocation")
            recommendations.append(f"   Phase budget: ${phase_budget:.2f}, planned: ${planned_run.estimated_cost_usd:.2f}")
        
        # Check complexity
        if planned_run.complexity_score > 2.0:
            recommendations.append(f"💡 Consider reducing complexity from {planned_run.complexity_score:.1f} to save costs")
            recommendations.append(f"   Complexity 2.0 would cost ~${planned_run.estimated_cost_usd * (2.0 / planned_run.complexity_score):.2f}")
        
        # Check iterations
        if planned_run.iterations > 3:
            recommendations.append(f"💡 Consider reducing iterations from {planned_run.iterations} to 3")
            recommendations.append(f"   3 iterations would cost ~${planned_run.estimated_cost_usd * (3 / planned_run.iterations):.2f}")
        
        # Daily usage warning
        today_usage = self.get_project_usage_today(planned_run.project or "default")
        if today_usage + planned_run.estimated_cost_usd > budget.daily_budget_usd * 1.5:
            recommendations.append(f"⚠️  High daily usage: today's total will be ${today_usage + planned_run.estimated_cost_usd:.2f}")
        
        return recommendations
    
    def record_run_usage(self, run_cost: StudioRunCost) -> None:
        """Record actual usage for a completed run."""
        
        usage_log = self.load_usage_log()
        
        # Add the run
        usage_log["runs"].append(asdict(run_cost))
        
        # Update aggregates
        self.update_usage_aggregates(usage_log)
        
        # Save updated log
        self.save_usage_log(usage_log)

    def analyze_budget_trends(self, days: int = 7) -> Dict[str, float]:
        """Return rolling usage averages and projections."""

        usage_log = self.load_usage_log()
        daily_totals = usage_log.get("daily_totals", {})
        recent_dates = sorted(daily_totals.keys())[-days:]
        recent_costs = [daily_totals[date]["cost"] for date in recent_dates]

        if not recent_costs:
            return {"days_analyzed": 0, "daily_average": 0.0, "monthly_projection": 0.0}

        daily_avg = sum(recent_costs) / len(recent_costs)
        monthly_projection = daily_avg * 30

        return {
            "days_analyzed": len(recent_costs),
            "daily_average": round(daily_avg, 2),
            "monthly_projection": round(monthly_projection, 2),
        }

    def check_budget_alerts(self, budget_status: Dict) -> List[str]:
        """Return proactive alerts based on budget thresholds and trends."""

        alerts: List[str] = []

        monthly = budget_status.get("monthly", {})
        monthly_budget = monthly.get("budget", 0)
        monthly_spent = monthly.get("spent", 0)
        if monthly_budget > 0:
            percent_used = (monthly_spent / monthly_budget) * 100
            if percent_used >= 100:
                alerts.append("❌ Monthly budget exceeded")
            elif percent_used >= 80:
                alerts.append(f"⚠️  {percent_used:.0f}% of monthly budget used")

        daily = budget_status.get("daily", {})
        daily_budget = daily.get("budget", 0)
        daily_spent = daily.get("spent", 0)
        if daily_budget > 0 and daily_spent > daily_budget * 1.5:
            alerts.append(
                f"⚠️  Today's usage is {daily_spent / daily_budget:.1f}× the daily budget"
            )

        trends = self.analyze_budget_trends()
        monthly_projection = trends.get("monthly_projection", 0)
        if monthly_budget > 0 and monthly_projection > monthly_budget:
            overage = monthly_projection - monthly_budget
            alerts.append(
                f"⚠️  Projected to exceed monthly budget by ${overage:.2f}"
            )

        return alerts
    
    def get_studio_budget_status(self) -> StudioBudgetStatus:
        """Get overall budget status across all projects."""
        
        projects = self.get_all_projects()
        total_monthly = sum(p.monthly_budget_usd for p in projects.values())
        
        usage_log = self.load_usage_log()
        if "daily_totals" not in usage_log:
            self.update_usage_aggregates(usage_log)
            self.save_usage_log(usage_log)
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate total spent this month
        month_runs = [r for r in usage_log["runs"] 
                     if datetime.fromisoformat(r["timestamp"]) >= current_month]
        total_spent = sum(r["estimated_cost_usd"] for r in month_runs)
        
        # Project breakdown
        project_breakdown = {}
        for project_name, budget in projects.items():
            project_runs = [r for r in month_runs if r["project"] == project_name]
            project_spent = sum(r["estimated_cost_usd"] for r in project_runs)
            
            project_breakdown[project_name] = {
                "budget": budget.monthly_budget_usd,
                "spent": project_spent,
                "remaining": budget.monthly_budget_usd - project_spent,
                "percent_used": (project_spent / budget.monthly_budget_usd * 100) if budget.monthly_budget_usd > 0 else 0
            }
        
        # Daily usage trend (last 7 days)
        daily_usage_trend = []
        for i in range(7):
            date = (datetime.now(timezone.utc) - timedelta(days=i)).date()
            day_runs = [r for r in usage_log["runs"] 
                       if datetime.fromisoformat(r["timestamp"]).date() == date]
            day_spent = sum(r["estimated_cost_usd"] for r in day_runs)
            daily_usage_trend.append({
                "date": date.isoformat(),
                "spent": day_spent,
                "runs": len(day_runs)
            })
        
        # Generate recommendations
        recommendations = []
        if total_spent > total_monthly * 0.8:
            recommendations.append("⚠️  You've used over 80% of your monthly Studio budget")
        
        if total_spent > total_monthly:
            recommendations.append("❌ You've exceeded your monthly Studio budget")
        
        # Find highest spending project
        if project_breakdown:
            highest_project = max(project_breakdown.items(), key=lambda x: x[1]["percent_used"])
            if highest_project[1]["percent_used"] > 50:
                recommendations.append(f"💡 {highest_project[0]} is using {highest_project[1]['percent_used']:.1f}% of its budget")
        
        trend_summary = self.analyze_budget_trends()

        return StudioBudgetStatus(
            total_monthly_budget=total_monthly,
            total_spent_this_month=total_spent,
            total_remaining=total_monthly - total_spent,
            project_breakdown=project_breakdown,
            daily_usage_trend=daily_usage_trend,
            recommendations=recommendations,
            trend_summary=trend_summary,
        )
    
    # Helper methods
    def get_project_budget(self, project_name: str) -> Optional[ProjectBudget]:
        """Get budget configuration for a project."""
        projects = self.get_all_projects()
        return projects.get(project_name)
    
    def get_all_projects(self) -> Dict[str, ProjectBudget]:
        """Get all project budgets."""
        if not self.projects_file.exists():
            return {}
        
        with open(self.projects_file, 'r') as f:
            data = json.load(f)
        
        return {name: ProjectBudget(**config) for name, config in data.items()}
    
    def save_project_budget(self, budget: ProjectBudget) -> None:
        """Save project budget configuration."""
        projects = self.get_all_projects()
        projects[budget.project_name] = budget
        
        with open(self.projects_file, 'w') as f:
            json.dump({name: asdict(budget) for name, budget in projects.items()}, f, indent=2)
    
    def load_usage_log(self) -> Dict:
        """Load usage log."""
        if not self.usage_file.exists():
            return {
                "runs": [],
                "daily_totals": {},
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        
        with open(self.usage_file, 'r') as f:
            return json.load(f)
    
    def save_usage_log(self, usage_log: Dict) -> None:
        """Save usage log."""
        usage_log.setdefault("daily_totals", {})
        usage_log["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(self.usage_file, 'w') as f:
            json.dump(usage_log, f, indent=2)
    
    def update_usage_aggregates(self, usage_log: Dict) -> None:
        """Rebuild rolling aggregates (daily totals)."""

        totals: Dict[str, Dict[str, float]] = {}
        for entry in usage_log.get("runs", []):
            try:
                date = datetime.fromisoformat(entry["timestamp"]).date().isoformat()
            except (KeyError, ValueError):
                continue
            bucket = totals.setdefault(date, {"cost": 0.0, "runs": 0})
            bucket["cost"] += float(entry.get("estimated_cost_usd", 0.0))
            bucket["runs"] += 1

        sorted_dates = sorted(totals.keys())
        if len(sorted_dates) > MAX_DAILY_TOTALS:
            sorted_dates = sorted_dates[-MAX_DAILY_TOTALS:]
        usage_log["daily_totals"] = {date: totals[date] for date in sorted_dates}
    
    def get_project_usage_this_month(self, project_name: str) -> Dict:
        """Get usage for a project in the current month."""
        usage_log = self.load_usage_log()
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        month_runs = [r for r in usage_log["runs"] 
                     if r["project"] == project_name and 
                     datetime.fromisoformat(r["timestamp"]) >= current_month]
        
        return {
            "spent": sum(r["estimated_cost_usd"] for r in month_runs),
            "runs": len(month_runs),
            "tokens": sum(r["estimated_tokens"] for r in month_runs)
        }
    
    def get_phase_usage_this_month(self, project_name: str, phase: str) -> float:
        """Get usage for a specific phase in the current month."""
        usage_log = self.load_usage_log()
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        month_runs = [r for r in usage_log["runs"] 
                     if r["project"] == project_name and 
                     r["phase"] == phase and
                     datetime.fromisoformat(r["timestamp"]) >= current_month]
        
        return sum(r["estimated_cost_usd"] for r in month_runs)
    
    def get_project_usage_today(self, project_name: str) -> float:
        """Get usage for a project today."""
        usage_log = self.load_usage_log()
        today = datetime.now(timezone.utc).date()
        
        today_runs = [r for r in usage_log["runs"] 
                     if r["project"] == project_name and 
                     datetime.fromisoformat(r["timestamp"]).date() == today]
        
        return sum(r["estimated_cost_usd"] for r in today_runs)

# Convenience functions
def initialize_studio_budget(project_name: str, monthly_budget: float) -> ProjectBudget:
    """Initialize Studio budget tracking for a project."""
    tracker = StudioBudgetTracker()
    return tracker.initialize_project_budget(project_name, monthly_budget)

def check_studio_budget(project_name: str, phase: str, iterations: int = 3, 
                       complexity: float = 1.0) -> Dict:
    """Check if a Studio run fits within budget."""
    tracker = StudioBudgetTracker()
    
    # Detect current project from directory
    current_project = Path.cwd().name
    
    # Estimate run cost
    planned_run = tracker.estimate_run_cost(phase, iterations, complexity=complexity)
    planned_run.project = current_project
    
    return tracker.check_project_budget(current_project, planned_run)

def get_studio_budget_status() -> StudioBudgetStatus:
    """Get overall Studio budget status."""
    tracker = StudioBudgetTracker()
    return tracker.get_studio_budget_status()


def estimate_cost_from_output_tokens(output_tokens: int) -> Dict[str, float]:
    """Utility to estimate cost from output token counts."""

    estimated_output_cost = (output_tokens / 1000) * OUTPUT_COST_PER_1K_TOKENS
    estimated_total_cost = estimated_output_cost * INPUT_OUTPUT_MULTIPLIER
    return {
        "output_cost": round(estimated_output_cost, 2),
        "total_cost": round(estimated_total_cost, 2),
    }


def validate_budget_estimate(run_dir: Path, estimated_cost: float, *, model: str = "gpt-4") -> Dict:
    """Validate an estimated run cost by counting markdown output tokens.

    Args:
        run_dir: Directory containing Studio run artifacts.
        estimated_cost: Original estimated cost for the run.
        model: Tokenizer model name for tiktoken (default: gpt-4).

    Returns:
        Dict containing output token counts, derived cost estimates, variance, and notes.
    """

    try:
        import tiktoken  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency issues handled by caller
        raise ImportError(
            "tiktoken is required for budget validation. Install the optional dependency to enable this feature."
        ) from exc

    encoding = tiktoken.encoding_for_model(model)
    output_tokens = 0

    for artifact in run_dir.glob("*.md"):
        if artifact.name == "instructions.md":
            continue
        try:
            content = artifact.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        output_tokens += len(encoding.encode(content))

    estimated_output_cost = (output_tokens / 1000) * OUTPUT_COST_PER_1K_TOKENS
    estimated_total_cost = estimated_output_cost * INPUT_OUTPUT_MULTIPLIER

    variance_percent = None
    if estimated_cost > 0:
        variance_percent = ((estimated_total_cost - estimated_cost) / estimated_cost) * 100

    return {
        "output_tokens": output_tokens,
        "estimated_output_cost": round(estimated_output_cost, 2),
        "estimated_total_cost": round(estimated_total_cost, 2),
        "original_estimate": round(estimated_cost, 2),
        "variance_percent": round(variance_percent, 1) if variance_percent is not None else None,
        "note": (
            "Output-token-based validation only; actual Cascade usage may differ due to input tokens and system overhead."
        ),
    }

if __name__ == "__main__":
    # Example usage
    status = get_studio_budget_status()
    print(f"Total Monthly Budget: ${status.total_monthly_budget:.2f}")
    print(f"Spent This Month: ${status.total_spent_this_month:.2f}")
    print(f"Remaining: ${status.total_remaining:.2f}")
    
    for rec in status.recommendations:
        print(rec)
