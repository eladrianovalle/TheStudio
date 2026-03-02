"""Tests for studio_budget_tracker core behaviors."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import studio_budget_tracker as sbt  # type: ignore


@pytest.fixture()
def tracker(tmp_path: Path) -> sbt.StudioBudgetTracker:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    studio_dir = repo_root / ".studio"
    studio_dir.mkdir()

    tracker = sbt.StudioBudgetTracker()
    tracker.studio_root = repo_root
    tracker.budget_file = studio_dir / "budget_config.json"
    tracker.usage_file = studio_dir / "usage_log.json"
    tracker.projects_file = studio_dir / "projects.json"
    tracker.save_usage_log(
        {
            "runs": [],
            "daily_totals": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    )

    return tracker


def test_initialize_project_budget_validation(tracker: sbt.StudioBudgetTracker) -> None:
    with pytest.raises(ValueError):
        tracker.initialize_project_budget("", 10.0)
    with pytest.raises(ValueError):
        tracker.initialize_project_budget("Project", 0)


def test_estimate_run_cost_validation(tracker: sbt.StudioBudgetTracker) -> None:
    with pytest.raises(ValueError):
        tracker.estimate_run_cost("unknown")
    with pytest.raises(ValueError):
        tracker.estimate_run_cost("tech", iterations=0)
    with pytest.raises(ValueError):
        tracker.estimate_run_cost("tech", complexity=0)
    with pytest.raises(ValueError):
        tracker.estimate_run_cost("tech", scopes=[])


def test_phase_cost_ordering(tracker: sbt.StudioBudgetTracker) -> None:
    market = tracker.estimate_run_cost("market")
    design = tracker.estimate_run_cost("design")
    tech = tracker.estimate_run_cost("tech")
    studio = tracker.estimate_run_cost("studio")

    assert market.estimated_cost_usd < design.estimated_cost_usd < tech.estimated_cost_usd < studio.estimated_cost_usd


def test_budget_status_and_trends(tracker: sbt.StudioBudgetTracker) -> None:
    tracker.initialize_project_budget("TestProject", 60.0)
    run_cost = sbt.StudioRunCost(
        run_id="run1",
        phase="studio",
        project="TestProject",
        timestamp=datetime.now(timezone.utc).isoformat(),
        estimated_tokens=20000,
        estimated_cost_usd=10.0,
        iterations=3,
        scopes=["high_level", "implementation"],
        complexity_score=1.5,
    )
    tracker.record_run_usage(run_cost)

    status = tracker.get_studio_budget_status()

    assert status.total_monthly_budget == pytest.approx(60.0)
    assert status.project_breakdown["TestProject"]["spent"] == pytest.approx(10.0)
    assert status.trend_summary is not None
    assert status.trend_summary["days_analyzed"] >= 1


def test_budget_alerts_trigger_when_thresholds_exceeded(tracker: sbt.StudioBudgetTracker) -> None:
    tracker.initialize_project_budget("AlertProject", 15.0)

    tracker.record_run_usage(
        sbt.StudioRunCost(
            run_id="baseline",
            phase="studio",
            project="AlertProject",
            timestamp=datetime.now(timezone.utc).isoformat(),
            estimated_tokens=20000,
            estimated_cost_usd=12.0,
            iterations=3,
            scopes=["high_level"],
            complexity_score=1.0,
        )
    )

    planned = tracker.estimate_run_cost("studio", iterations=3)
    planned.project = "AlertProject"
    budget_status = tracker.check_project_budget("AlertProject", planned)
    alerts = tracker.check_budget_alerts(budget_status)

    assert any(alert.startswith("⚠️") or alert.startswith("❌") for alert in alerts)
