"""Render a run's summary as Markdown for the README, PRs and the CI job summary."""

from statistics import median

from .stats import METRICS

LABELS = {
    "flag_recall": "Red-flag recall",
    "followup_coverage": "Follow-up question coverage",
    "decoy_false_alarm": "Decoy false-alarm rate (lower is better)",
    "grounding": "Evidence quotes found verbatim",
    "fact_accuracy": "Financial fact accuracy",
    "abstention": "Abstains on unstated figures",
    "recommendation_ok": "Recommendation in acceptable set",
}


def _pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.0f}%"


def render(config: dict, summary: dict) -> str:
    q, ops = summary["quality"], summary["ops"]
    title = (f"### prompt `{config['prompt_version']}` · `{config['model']}` · effort `{config['effort']}`"
             if config["agent"] == "claude" else f"### {config['agent']} baseline (harness check)")
    lines = [
        title,
        "",
        f"{ops['n_cases']} cases × {config['reps']} reps · judge `{config['judge_model']}` · dataset `{config['dataset_hash']}`",
        "",
        "| Metric | Mean | 95% CI (cases) |",
        "|---|---|---|",
    ]
    for m in METRICS:
        if m in q:
            lo, hi = q[m]["ci95"]
            lines.append(f"| {LABELS[m]} | {_pct(q[m]['mean'])} | {_pct(lo)} – {_pct(hi)} |")
    lines += [
        "",
        "| Ops | Value |",
        "|---|---|",
        f"| Status | {', '.join(f'{k}: {v}' for k, v in sorted(ops['status_counts'].items()))} |",
        f"| Harness errors (not scored) | {ops['harness_errors']} |",
        f"| Agent cost / screen | {ops['agent_cost_per_screen']} |",
        f"| Judge cost / screen | {ops['judge_cost_per_screen']} |",
        f"| Latency p50 / max | {ops['latency_p50_s']}s / {ops['latency_max_s']}s |",
        "",
    ]
    return "\n".join(lines)


def ops_summary(rows: list[dict], errors: list[dict]) -> dict:
    from collections import Counter

    status = Counter(r["status"] for r in rows)
    lat = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    agent_cost = [r["agent_cost_usd"] for r in rows if r.get("agent_cost_usd") is not None]
    judge_cost = [r["judge_cost_usd"] for r in rows if r.get("judge_cost_usd") is not None]
    fmt = lambda xs: f"${sum(xs) / len(xs):.4f}" if xs else "n/a"  # noqa: E731
    return {
        "n_cases": len({r["case_id"] for r in rows}),
        "status_counts": dict(status),
        "harness_errors": len(errors),
        "agent_cost_per_screen": fmt(agent_cost),
        "judge_cost_per_screen": fmt(judge_cost),
        "agent_cost_total_usd": round(sum(agent_cost), 4),
        "judge_cost_total_usd": round(sum(judge_cost), 4),
        "latency_p50_s": round(median(lat), 1) if lat else "n/a",
        "latency_max_s": round(max(lat), 1) if lat else "n/a",
    }
