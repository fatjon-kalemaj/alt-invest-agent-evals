"""Aggregation with honest error bars.

Reps of the same case are not independent samples, so we average reps within a
case first and bootstrap over cases. With 8 cases the intervals are wide; that
is the point of showing them.
"""

import random
from collections import defaultdict
from statistics import mean

METRICS = (
    "flag_recall",
    "recall_arithmetic",
    "recall_footnote",
    "recall_cross_reference",
    "followup_coverage",
    "decoy_false_alarm",
    "grounding",
    "fact_accuracy",
    "abstention",
    "recommendation_ok",
)
# Lower is better for these.
LOWER_IS_BETTER = {"decoy_false_alarm"}


def per_case_means(rows: list[dict], metric: str) -> dict[str, float]:
    by_case = defaultdict(list)
    for r in rows:
        v = (r.get("metrics") or {}).get(metric)
        if v is not None:
            by_case[r["case_id"]].append(v)
    return {c: mean(vs) for c, vs in by_case.items()}


def bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    if len(values) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(values, k=len(values))) for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def summarize(rows: list[dict]) -> dict:
    out = {}
    for m in METRICS:
        cm = per_case_means(rows, m)
        vals = list(cm.values())
        if not vals:
            continue
        lo, hi = bootstrap_ci(vals)
        out[m] = {"mean": mean(vals), "ci95": [lo, hi], "n_cases": len(vals), "per_case": cm}
    return out


def paired_diff(base: dict, new: dict, metric: str) -> dict | None:
    b, n = base.get(metric, {}).get("per_case", {}), new.get(metric, {}).get("per_case", {})
    common = sorted(set(b) & set(n))
    if not common:
        return None
    diffs = [n[c] - b[c] for c in common]
    lo, hi = bootstrap_ci(diffs)
    return {"mean_diff": mean(diffs), "ci95": [lo, hi], "n_cases": len(common)}
