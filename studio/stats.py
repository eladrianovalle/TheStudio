"""Pure aggregation and formatting for the cross-run stats dashboard.

Everything here is a pure function: data in, data (or a rendered string) out. No
filesystem, no argparse, no path resolution. The ``run_phase`` CLI handlers do
the reading and writing, then hand the collected records to these functions.
Keeping the number-crunching separate from the I/O makes it trivial to test and
keeps the aggregation logic out of the 3,000-line entrypoint.
"""
from __future__ import annotations

from statistics import median
from typing import Dict, List, Optional

# Outcome vocabularies — kept small on purpose. "Did it ship" and a coarse
# impact bucket are the cheapest things to record that still let us count.
VALID_SHIPPED = ("yes", "no", "partial")
VALID_IMPACT = ("none", "minor", "major")


def summarize_outcomes(records: List[Dict]) -> Dict:
    """Roll up outcome records into counts and a few recent qualitative notes.

    An outcome record is a flat dict that may carry ``repo``, ``run_id``,
    ``shipped`` (one of VALID_SHIPPED), ``impact`` (one of VALID_IMPACT), and
    ``changed`` (freetext: what this run actually changed). Records come from two
    places: this repo's rated runs and the cross-repo ledger. Any field may be
    missing — a record with none of shipped/impact/changed still counts toward
    its repo's tally but not the rates.

    Pure: data in, summary dict out.
    """
    shipped = {k: 0 for k in VALID_SHIPPED}
    impact = {k: 0 for k in VALID_IMPACT}
    by_repo: Dict[str, int] = {}
    recent_changed: List[Dict] = []
    with_outcome = 0

    for rec in records:
        repo = rec.get("repo") or "?"
        by_repo[repo] = by_repo.get(repo, 0) + 1

        s = rec.get("shipped")
        i = rec.get("impact")
        c = (rec.get("changed") or "").strip()

        if s in shipped:
            shipped[s] += 1
        if i in impact:
            impact[i] += 1
        if (s in shipped) or (i in impact) or c:
            with_outcome += 1
        if c:
            recent_changed.append({
                "repo": repo,
                "run_id": rec.get("run_id", "?"),
                "changed": c,
            })

    ship_total = sum(shipped.values())
    return {
        "records": len(records),
        "with_outcome": with_outcome,
        "repos": len(by_repo),
        "by_repo": by_repo,
        "shipped": shipped,
        "ship_rate": (shipped["yes"] / ship_total) if ship_total else None,
        "impact": impact,
        "recent_changed": recent_changed[-8:],
    }


def _is_number(value) -> bool:
    """True for a real int/float. Excludes bool: it is an int subclass, but a
    flag is not a count, and treating it as one hides bad data instead of
    dropping it.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric(value) -> float:
    """Return the value if it is a real number, else 0.

    Session records come from disk and may carry nulls or missing fields, so
    every count is read through this guard before it enters a sum.
    """
    return value if _is_number(value) else 0


def _session_health_signals(records: List[Dict]) -> Dict:
    """Compute the five session-health signals over a list of session records.

    Split out from :func:`summarize_session_health` so the same math can run over
    the full history and over each half when we show a recent-vs-earlier trend.
    Each record is a ``session.json`` dict (see docs/SESSION_ANALYTICS_PLAN.md).
    Missing or partial fields are tolerated; an empty list yields all Nones.
    """
    count = len(records)

    # Assumed-P0 rate: blocking questions the session guessed on, over all the
    # blocking questions it surfaced. None when no P0 was ever surfaced.
    p0_surfaced = 0
    p0_assumed = 0
    for record in records:
        decisions = record.get("decisions") or {}
        surfaced = decisions.get("surfaced") or {}
        p0_surfaced += _numeric(surfaced.get("P0"))
        p0_assumed += _numeric(decisions.get("p0_assumed"))
    assumed_p0_rate = (p0_assumed / p0_surfaced) if p0_surfaced else None

    # Convergence: median iterations-to-verdict, and the fraction of sessions
    # that saw at least one rejection along the way.
    iteration_counts: List[float] = []
    sessions_with_rejection = 0
    for record in records:
        convergence = record.get("convergence") or {}
        iterations = convergence.get("iterations")
        if _is_number(iterations):
            iteration_counts.append(iterations)
        if _numeric(convergence.get("rejections")) > 0:
            sessions_with_rejection += 1
    median_iterations = median(iteration_counts) if iteration_counts else None
    rejection_rate = (sessions_with_rejection / count) if count else None

    # Clarity gain: mean of (after - before), only over records that have both.
    clarity_gains: List[float] = []
    for record in records:
        clarity = record.get("clarity") or {}
        before = clarity.get("mean_before")
        after = clarity.get("mean_after")
        if _is_number(before) and _is_number(after):
            clarity_gains.append(after - before)
    clarity_gain = (sum(clarity_gains) / len(clarity_gains)) if clarity_gains else None

    # Tokens per settled decision: total spend over decisions actually answered
    # (by the user or by an assumption). None when nothing settled.
    total_tokens = 0
    settled_decisions = 0
    for record in records:
        cost = record.get("cost") or {}
        total_tokens += _numeric(cost.get("total_tokens"))
        decisions = record.get("decisions") or {}
        settled_decisions += (
            _numeric(decisions.get("answered_by_user"))
            + _numeric(decisions.get("answered_by_assumption"))
        )
    tokens_per_settled_decision = (
        (total_tokens / settled_decisions) if settled_decisions else None
    )

    # Editor liveness: fraction of sessions whose final doc shrank vs the first
    # draft (shrink_ratio > 0). 0% is the failure mode: a dead cut mandate.
    sessions_that_shrank = 0
    for record in records:
        editor = record.get("editor") or {}
        shrink_ratio = editor.get("shrink_ratio")
        if _is_number(shrink_ratio) and shrink_ratio > 0:
            sessions_that_shrank += 1
    editor_liveness = (sessions_that_shrank / count) if count else None

    return {
        "records": count,
        "assumed_p0_rate": assumed_p0_rate,
        "convergence": {
            "median_iterations": median_iterations,
            "rejection_rate": rejection_rate,
        },
        "clarity_gain": clarity_gain,
        "tokens_per_settled_decision": tokens_per_settled_decision,
        "editor_liveness": editor_liveness,
    }


def summarize_session_health(session_records: List[Dict]) -> Dict:
    """Roll up ``session.json`` records into the five health signals over time.

    Each input is a ``session.json`` dict written automatically at finalize (see
    docs/SESSION_ANALYTICS_PLAN.md). These measure a run's *health* — did the
    debate converge, settle its blocking questions, and reduce uncertainty, at
    what cost — not the quality of a plan that hasn't been built yet.

    Returns the all-time figures plus, once there are enough records (>= 6), a
    ``trend`` block that splits the list in half (caller passes them oldest
    first) so a reader can see whether the two most telling signals — assumed-P0
    rate and median iterations — are moving in the right direction. With fewer
    records ``trend`` is None. Never raises: missing fields and an empty list
    yield Nones and zeros.

    Pure: data in, summary dict out.
    """
    records = [r for r in session_records if isinstance(r, dict)]
    summary = _session_health_signals(records)

    # A recent-vs-earlier split only says something once each half has a few
    # sessions in it; below that it is noise, so we withhold it.
    if len(records) >= 6:
        midpoint = len(records) // 2
        summary["trend"] = {
            "earlier": _session_health_signals(records[:midpoint]),
            "recent": _session_health_signals(records[midpoint:]),
        }
    else:
        summary["trend"] = None

    return summary


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


def _format_outcomes(outcomes: Dict) -> List[str]:
    """Render the outcomes block (did it ship / what changed) for the dashboard."""
    lines = ["", "Outcomes (did it ship / what changed):"]
    if outcomes["records"] == 0:
        lines.append(
            "  No outcomes recorded yet. Add to a rating: "
            "rate --run-dir <path> --score N --shipped yes --impact major --changed \"...\""
        )
        return lines

    repos = ", ".join(f"{k}={v}" for k, v in sorted(outcomes["by_repo"].items()))
    lines.append(f"  {outcomes['records']} rated runs across {outcomes['repos']} repo(s): {repos}")

    sh = outcomes["shipped"]
    ship_line = f"  Shipped: yes={sh['yes']} no={sh['no']} partial={sh['partial']}"
    if outcomes["ship_rate"] is not None:
        ship_line += f" (ship rate {outcomes['ship_rate']*100:.0f}%)"
    lines.append(ship_line)

    im = outcomes["impact"]
    if any(im.values()):
        lines.append(f"  Impact:  none={im['none']} minor={im['minor']} major={im['major']}")

    if outcomes["recent_changed"]:
        lines.append("  Recent changes:")
        for item in reversed(outcomes["recent_changed"]):
            changed = item["changed"]
            if len(changed) > 80:
                changed = changed[:77] + "..."
            lines.append(f"    [{item['repo']}] {item['run_id']} — {changed}")
    return lines


def _fmt_signal(value: Optional[float], *, pct: bool) -> str:
    """Format one session-health number, or "n/a" when it could not be computed."""
    if value is None:
        return "n/a"
    if pct:
        return f"{value*100:.0f}%"
    return f"{value:g}"


def _format_session_health(health: Dict) -> List[str]:
    """Render the session-health block: five signals auto-measured at finalize.

    Each line labels what the number means in a few words, because these are for
    a human reading the dashboard, not targets for an agent to chase.
    """
    lines = ["", "Session health (auto-measured at finalize):"]
    lines.append(f"  {health['records']} finalized session(s) on record")

    assumed = health["assumed_p0_rate"]
    if assumed is None:
        lines.append("  Assumed-P0 rate: n/a (no blocking questions surfaced)")
    else:
        lines.append(
            f"  Assumed-P0 rate: {assumed*100:.0f}% "
            "(blocking questions guessed instead of asked; want ~0%)"
        )

    convergence = health["convergence"]
    median_iterations = _fmt_signal(convergence["median_iterations"], pct=False)
    rejection_rate = _fmt_signal(convergence["rejection_rate"], pct=True)
    lines.append(
        f"  Convergence: median {median_iterations} iterations, "
        f"{rejection_rate} of sessions hit a rejection (both extremes are smells)"
    )

    gain = health["clarity_gain"]
    if gain is None:
        lines.append("  Clarity gain: n/a (no before/after snapshots)")
    else:
        lines.append(f"  Clarity gain: {gain:+.2f} mean per session (uncertainty reduced; higher is better)")

    tokens = health["tokens_per_settled_decision"]
    if tokens is None:
        lines.append("  Tokens/settled decision: n/a (nothing settled)")
    else:
        lines.append(f"  Tokens/settled decision: {tokens:,.0f} (spend per question answered)")

    liveness = health["editor_liveness"]
    if liveness is None:
        lines.append("  Editor liveness: n/a")
    else:
        lines.append(
            f"  Editor liveness: {liveness*100:.0f}% "
            "of sessions shrank the doc (0% means a dead cut mandate)"
        )

    trend = health.get("trend")
    if trend:
        earlier = trend["earlier"]
        recent = trend["recent"]
        lines.append(f"  Trend (recent {recent['records']} vs earlier {earlier['records']}):")
        lines.append(
            "    Assumed-P0 rate: "
            f"{_fmt_signal(earlier['assumed_p0_rate'], pct=True)} -> "
            f"{_fmt_signal(recent['assumed_p0_rate'], pct=True)}"
        )
        lines.append(
            "    Median iterations: "
            f"{_fmt_signal(earlier['convergence']['median_iterations'], pct=False)} -> "
            f"{_fmt_signal(recent['convergence']['median_iterations'], pct=False)}"
        )
    return lines


def format_stats(
    agg: Dict,
    usage: Optional[Dict] = None,
    clarity_note: Optional[str] = None,
    outcomes: Optional[Dict] = None,
    session_health: Optional[Dict] = None,
) -> str:
    """Render an aggregate_stats() result as a terminal dashboard."""
    bar = "=" * 60
    lines: List[str] = [bar, "Studio Cross-Run Stats", bar]

    if agg["total_runs"] == 0:
        lines.append("No local runs found yet. Run a phase first.")
        # Cross-repo outcomes (imported into the ledger) can still be worth showing
        # even when this repo has no runs of its own — that's the tool-repo case.
        if outcomes is not None and outcomes["records"] > 0:
            lines.extend(_format_outcomes(outcomes))
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

    if outcomes is not None:
        lines.extend(_format_outcomes(outcomes))

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

    if session_health and session_health.get("records"):
        lines.extend(_format_session_health(session_health))

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
