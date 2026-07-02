"""Pure aggregation and formatting for the cross-run stats dashboard.

Everything here is a pure function: data in, data (or a rendered string) out. No
filesystem, no argparse, no path resolution. The ``run_phase`` CLI handlers do
the reading and writing, then hand the collected records to these functions.
Keeping the number-crunching separate from the I/O makes it trivial to test and
keeps the aggregation logic out of the 3,000-line entrypoint.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def _summarize_metrics(entries: List[Dict]) -> Dict:
    """Aggregate metrics entries into a summary."""
    total_tokens = sum(e.get("total_tokens", 0) for e in entries)
    total_duration = sum(e.get("duration_ms", 0) for e in entries)
    total_tool_uses = sum(e.get("tool_uses", 0) for e in entries)

    by_scope: Dict[str, Dict] = {}
    by_role: Dict[str, Dict] = {}

    for e in entries:
        scope = e.get("scope", "flat")
        role = e.get("role", "unknown")

        for group, key in [(by_scope, scope), (by_role, role)]:
            if key not in group:
                group[key] = {"agents": 0, "total_tokens": 0, "duration_ms": 0}
            group[key]["agents"] += 1
            group[key]["total_tokens"] += e.get("total_tokens", 0)
            group[key]["duration_ms"] += e.get("duration_ms", 0)

    return {
        "agents": len(entries),
        "total_tokens": total_tokens,
        "total_duration_ms": total_duration,
        "total_tool_uses": total_tool_uses,
        "by_scope": by_scope,
        "by_role": by_role,
    }


def _parse_usage_log(text: str) -> Dict:
    """Summarize the prepare usage log (.studio/usage.log) into counts.

    Lines look like: ``ts | prepare | phase | mode | roles=... | scoped=true``.
    """
    by_phase: Dict[str, int] = {}
    by_mode: Dict[str, int] = {}
    scoped = {"true": 0, "false": 0}
    total = 0
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue
        _, _command, phase, mode, _roles, scoped_field = parts[:6]
        total += 1
        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_mode[mode] = by_mode.get(mode, 0) + 1
        val = scoped_field.split("=", 1)[1] if "=" in scoped_field else scoped_field
        if val in scoped:
            scoped[val] += 1
    return {"total": total, "by_phase": by_phase, "by_mode": by_mode, "scoped": scoped}


def aggregate_stats(runs: List[Dict]) -> Dict:
    """Aggregate cross-run signals into a stats summary.

    Pure over a list of enriched run dicts. Each run is a run.json dict that may
    additionally carry ``_rating`` (rating.json dict or None) and ``_decisions``
    (list of DecisionPoint). Missing fields are tolerated.
    """
    by_phase: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    verdicts = {"APPROVED": 0, "REJECTED": 0, "UNKNOWN": 0}

    scores: List[int] = []
    scores_by_phase: Dict[str, List[int]] = {}
    rated: List[Dict] = []

    total_tokens = 0
    token_runs = 0
    total_cost = 0.0
    cost_runs = 0
    total_hours = 0.0
    hours_runs = 0

    dec_priority = {"P0": 0, "P1": 0, "P2": 0}
    dec_total = 0
    dec_answered = 0

    for run in runs:
        phase = run.get("phase", "unknown")
        status = run.get("status", "UNKNOWN")
        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

        verdict = (run.get("verdict") or "").upper()
        if verdict in ("APPROVED", "REJECTED"):
            verdicts[verdict] += 1
        elif verdict:
            verdicts["UNKNOWN"] += 1

        tok = (run.get("metrics") or {}).get("total_tokens", 0)
        if tok:
            total_tokens += tok
            token_runs += 1

        cost = run.get("cost")
        if isinstance(cost, (int, float)):
            total_cost += cost
            cost_runs += 1
        hours = run.get("hours")
        if isinstance(hours, (int, float)):
            total_hours += hours
            hours_runs += 1

        rating = run.get("_rating")
        if rating and isinstance(rating.get("score"), (int, float)):
            sc = rating["score"]
            scores.append(sc)
            scores_by_phase.setdefault(phase, []).append(sc)
            rated.append({
                "run_id": run.get("run_id", run.get("run_dir", "?")),
                "phase": phase,
                "score": sc,
                "note": rating.get("note", ""),
            })

        for dp in run.get("_decisions", []):
            dec_total += 1
            pr = getattr(dp, "priority", "P2")
            if pr in dec_priority:
                dec_priority[pr] += 1
            if getattr(dp, "answer", None) is not None:
                dec_answered += 1

    verdict_total = verdicts["APPROVED"] + verdicts["REJECTED"]
    return {
        "total_runs": len(runs),
        "by_phase": by_phase,
        "by_status": by_status,
        "verdicts": verdicts,
        "approval_rate": (verdicts["APPROVED"] / verdict_total) if verdict_total else None,
        "ratings": {
            "count": len(scores),
            "avg": (sum(scores) / len(scores)) if scores else None,
            "by_phase_avg": {p: sum(v) / len(v) for p, v in scores_by_phase.items()},
            "lowest": sorted(rated, key=lambda r: r["score"])[:5],
        },
        "tokens": {
            "total": total_tokens,
            "runs": token_runs,
            "avg": (total_tokens / token_runs) if token_runs else None,
        },
        "cost": {"total": total_cost, "runs": cost_runs},
        "hours": {"total": total_hours, "runs": hours_runs},
        "decisions": {
            "total": dec_total,
            "by_priority": dec_priority,
            "answered": dec_answered,
            "answer_rate": (dec_answered / dec_total) if dec_total else None,
        },
    }


def format_stats(agg: Dict, usage: Optional[Dict] = None, clarity_note: Optional[str] = None) -> str:
    """Render an aggregate_stats() result as a terminal dashboard."""
    bar = "=" * 60
    lines: List[str] = [bar, "Studio Cross-Run Stats", bar]

    if agg["total_runs"] == 0:
        lines.append("No runs found yet. Run a phase first.")
        lines.append(bar)
        return "\n".join(lines)

    lines.append(f"Total runs: {agg['total_runs']}")
    lines.append("  By phase:  " + ", ".join(f"{k}={v}" for k, v in sorted(agg["by_phase"].items())))
    lines.append("  By status: " + ", ".join(f"{k}={v}" for k, v in sorted(agg["by_status"].items())))

    v = agg["verdicts"]
    lines.append("")
    lines.append("Verdicts (agent):")
    lines.append(f"  APPROVED={v['APPROVED']}  REJECTED={v['REJECTED']}  UNKNOWN={v['UNKNOWN']}")
    if agg["approval_rate"] is not None:
        lines.append(f"  Approval rate: {agg['approval_rate']*100:.0f}% (of decided runs)")

    r = agg["ratings"]
    lines.append("")
    lines.append("Quality ratings (human):")
    if r["count"] == 0:
        lines.append("  No runs rated yet. Use: rate --run-dir <path> --score 1-5")
    else:
        lines.append(f"  Rated {r['count']}/{agg['total_runs']} runs — avg {r['avg']:.1f}/5")
        if r["by_phase_avg"]:
            lines.append("  By phase: " + ", ".join(f"{p}={s:.1f}" for p, s in sorted(r["by_phase_avg"].items())))
        if r["lowest"]:
            lines.append("  Lowest-rated (improvement targets):")
            for item in r["lowest"]:
                note = f" — {item['note']}" if item["note"] else ""
                lines.append(f"    {item['score']}/5  {item['run_id']}{note}")

    t = agg["tokens"]
    lines.append("")
    lines.append("Efficiency:")
    if t["runs"]:
        lines.append(f"  Tokens: {t['total']:,} across {t['runs']} runs (avg {t['avg']:,.0f}/run)")
    else:
        lines.append("  No token metrics recorded.")
    if agg["cost"]["runs"]:
        lines.append(f"  Cost: ${agg['cost']['total']:.2f} across {agg['cost']['runs']} runs")
    if agg["hours"]["runs"]:
        lines.append(f"  Hours: {agg['hours']['total']:.1f} across {agg['hours']['runs']} runs")

    d = agg["decisions"]
    lines.append("")
    lines.append("Decision points:")
    if d["total"]:
        bp = d["by_priority"]
        lines.append(f"  {d['total']} total — P0={bp['P0']} P1={bp['P1']} P2={bp['P2']}")
        if d["answer_rate"] is not None:
            lines.append(f"  Answered: {d['answered']}/{d['total']} ({d['answer_rate']*100:.0f}%)")
    else:
        lines.append("  None recorded.")

    if usage and usage["total"]:
        lines.append("")
        lines.append("Usage (prepare log):")
        lines.append(f"  {usage['total']} prepares — " + ", ".join(f"{k}={v}" for k, v in sorted(usage["by_phase"].items())))
        lines.append("  Modes: " + ", ".join(f"{k}={v}" for k, v in sorted(usage["by_mode"].items())))
        lines.append(f"  Scoped: {usage['scoped'].get('true', 0)} / Flat: {usage['scoped'].get('false', 0)}")

    if clarity_note:
        lines.append("")
        lines.append(f"Clarity: {clarity_note}")

    lines.append(bar)
    return "\n".join(lines)
