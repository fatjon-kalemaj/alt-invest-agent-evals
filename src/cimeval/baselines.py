"""Known-good and known-bad agents for checking the harness itself.

oracle: builds the screen from the gold labels. Should score at or near the top
on every metric; if it does not, the grader is broken.
null: returns an empty screen. Should score near zero on recall; if it does
not, the grader is too lenient.
"""

from cimscreen.schema import Financials, FlagCategory, Recommendation, RedFlag, Screen

from .dataset import Case


def oracle_screen(case: Case) -> Screen:
    labels = case.labels
    flags = [
        RedFlag(category=FlagCategory(f["category"]), description=f["issue"], evidence_quote=f["evidence"])
        for f in labels["planted_flags"]
    ]
    questions = [f"Regarding: {f['issue']} What is management's explanation and plan?" for f in labels["planted_flags"]]
    return Screen(
        company_name=labels["company_name"],
        sector="(oracle)",
        financials=Financials(**{k: v["any_of"][0] if isinstance(v, dict) else v for k, v in labels["facts"].items()}),
        red_flags=flags,
        dd_questions=questions,
        recommendation=Recommendation(labels["acceptable_recommendations"][0]),
        rationale="Oracle screen built from gold labels.",
    )


def null_screen(case: Case) -> Screen:
    return Screen(
        company_name="",
        sector="",
        financials=Financials(revenue_ltm_musd=None, ebitda_ltm_musd=None, revenue_growth_pct=None, top_customer_pct=None),
        red_flags=[],
        dd_questions=[],
        recommendation=Recommendation.pursue,
        rationale="",
    )
