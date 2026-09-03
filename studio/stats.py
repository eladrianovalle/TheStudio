"""Pure aggregation and formatting for the cross-run stats dashboard.

Everything here is a pure function: data in, data (or a rendered string) out. No
filesystem, no argparse, no path resolution. The ``run_phase`` CLI handlers do
the reading and writing, then hand the collected records to these functions.
Keeping the number-crunching separate from the I/O makes it trivial to test and
keeps the aggregation logic out of the CLI entrypoint.
"""
from __future__ import annotations

import re
from statistics import median
from typing import Dict, List, Optional

# How much a shipped feature changed downstream, in three coarse buckets. Kept
# small on purpose: a bucket someone will actually pick beats a scale nobody fills.
VALID_IMPACT = ("none", "minor", "major")


def parse_frontmatter(text: str) -> Dict[str, str]:
    """The ``key: value`` lines of a markdown document's leading ``---`` block.

    Only the *leading* block counts, so a document discussing a field in its prose —
    a spec explaining what ``status: shipped`` means, say — cannot accidentally declare
    one. Anything in that block that isn't ``key: value`` is skipped, and values come
    back stripped.

    This is the one reader of spec frontmatter. ``tests/test_spec_verification.py``
    calls it, and so does ``run_phase._shipped_spec_records``, which feeds the stats
    dashboard — so the gate that demands these lines and the dashboard that prints them
    can never disagree about what a spec says. It takes a string rather than a path to keep this module free of
    I/O — opening the file stays with the caller.
    """
    block = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    if not block:
        return {}
    fields: Dict[str, str] = {}
    for line in block.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip():
            fields[key.strip()] = value.strip()
    return fields


def summarize_shipped_specs(records: List[Dict]) -> Dict:
    """Roll up shipped specs into an impact tally and the recent change lines.

    Each record is ``{"slug", "impact", "changed"}``, read from one spec's
    frontmatter by ``run_phase._shipped_spec_records``. An unrecognized or blank
    impact is counted by nothing — the spec-verification gate rejects those at the
    moment a spec claims it shipped, so anything odd reaching here is old data,
    not a case to invent a bucket for.

    Pure: data in, summary dict out.
    """
    impact = {k: 0 for k in VALID_IMPACT}
    recent_changed: List[Dict] = []

    for record in records:
        bucket = record.get("impact")
        if bucket in impact:
            impact[bucket] += 1
        changed = (record.get("changed") or "").strip()
        if changed:
            recent_changed.append({
                "slug": record.get("slug", "?"),
                "changed": changed,
            })

    return {
        "records": len(records),
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
    """Compute the three session-health signals over a list of session records.

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

    return {
        "records": count,
        "assumed_p0_rate": assumed_p0_rate,
        "convergence": {
            "median_iterations": median_iterations,
            "rejection_rate": rejection_rate,
        },
        "clarity_gain": clarity_gain,
    }


def summarize_session_health(session_records: List[Dict]) -> Dict:
    """Roll up ``session.json`` records into the three health signals over time.

    Each input is a ``session.json`` dict written automatically at finalize (see
    docs/SESSION_ANALYTICS_PLAN.md). These measure a run's *health*: did the
    debate converge, settle its blocking questions, and reduce uncertainty. They
    do not measure the quality of a plan not yet built.

    Records written before the volunteer-fed measurements were retired still
    carry ``cost`` and ``editor`` blocks. Nothing here reads them, so old and new
    records roll up side by side with no migration.

    Returns the all-time figures plus, once there are enough records (>= 6), a
    ``trend`` block that splits the list in half (caller passes them oldest
    first) so a reader can see whether the two most telling signals (assumed-P0
    rate and median iterations) are moving in the right direction. With fewer
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
    additionally carry ``_decisions`` (list of DecisionPoint). Missing fields are
    tolerated.
    """
    by_phase: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    verdicts = {"APPROVED": 0, "REJECTED": 0, "UNKNOWN": 0}

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
        "decisions": {
            "total": dec_total,
            "by_priority": dec_priority,
            "answered": dec_answered,
            "answer_rate": (dec_answered / dec_total) if dec_total else None,
        },
    }


def _format_shipped_specs(shipped_specs: Dict) -> List[str]:
    """Render the shipped-features block: what actually landed, and what it changed.

    Read honestly, this block is a Studio-source-repo feature: a consuming repo
    sees the empty state until someone there flips a spec to ``status: shipped``.
    """
    lines = ["", "Shipped features (from specs/):"]
    if shipped_specs["records"] == 0:
        lines.append(
            "  No shipped features recorded yet — a spec gains a line here when "
            "its frontmatter says status: shipped."
        )
        return lines

    lines.append(f"  {shipped_specs['records']} spec(s) at status: shipped")

    impact = shipped_specs["impact"]
    lines.append(
        f"  Impact:  none={impact['none']} minor={impact['minor']} major={impact['major']}"
    )

    if shipped_specs["recent_changed"]:
        lines.append("  Recent changes:")
        for item in reversed(shipped_specs["recent_changed"]):
            changed = item["changed"]
            if len(changed) > 80:
                changed = changed[:77] + "..."
            lines.append(f"    [{item['slug']}] {changed}")
    return lines


def _fmt_signal(value: Optional[float], *, pct: bool) -> str:
    """Format one session-health number, or "n/a" when it could not be computed."""
    if value is None:
        return "n/a"
    if pct:
        return f"{value*100:.0f}%"
    return f"{value:g}"


def _format_session_health(health: Dict) -> List[str]:
    """Render the session-health block: three signals auto-measured at finalize.

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
    shipped_specs: Optional[Dict] = None,
    session_health: Optional[Dict] = None,
) -> str:
    """Render an aggregate_stats() result as a terminal dashboard."""
    bar = "=" * 60
    lines: List[str] = [bar, "Studio Cross-Run Stats", bar]

    if agg["total_runs"] == 0:
        lines.append("No local runs found yet. Run a phase first.")
        # A repo can have shipped features before it has finalized runs — the state
        # right after /spec lands somewhere new — so the block renders here too,
        # empty state included: "nothing shipped yet" answers the same question, and
        # a reader who sees the line once knows where a feature would appear.
        if shipped_specs is not None:
            lines.extend(_format_shipped_specs(shipped_specs))
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

    if shipped_specs is not None:
        lines.extend(_format_shipped_specs(shipped_specs))

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
