"""Deterministic graders. No model calls, so these run in CI on every commit."""

import re

from cimscreen.schema import Screen

from .dataset import FACT_FIELDS, Case

PCT_FIELDS = {"revenue_growth_pct", "top_customer_pct"}


def normalize(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "—": "-", "–": "-"}))
    text = text.replace("*", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \"'.,;:")


def _close(a: float, b: float) -> bool:
    # Figures are reported to one decimal; rounding noise only, not "close enough".
    return abs(a - b) <= max(0.051, 0.001 * abs(b))


def fact_correct(field: str, expected, got: float | None) -> bool:
    # A label can accept several figures when the document itself gives more than
    # one defensible answer (reported vs adjusted EBITDA, pro forma vs standalone).
    if isinstance(expected, dict):
        return any(fact_correct(field, e, got) for e in expected["any_of"])
    if expected is None:
        return got is None
    if got is None:
        return False
    if _close(got, expected):
        return True
    # 0.38 for 38% is the same answer in a different unit, not a wrong one.
    return field in PCT_FIELDS and _close(got * 100, expected)


def grade_facts(case: Case, screen: Screen) -> dict:
    expected = case.labels["facts"]
    got = screen.financials.model_dump()
    per_field = {f: fact_correct(f, expected[f], got[f]) for f in FACT_FIELDS}
    null_fields = [f for f in FACT_FIELDS if expected[f] is None]  # any_of labels never include null
    return {
        "fact_accuracy": sum(per_field.values()) / len(FACT_FIELDS),
        # Did it decline to invent a number the document never states?
        "abstention": (sum(per_field[f] for f in null_fields) / len(null_fields)) if null_fields else None,
        "fact_detail": per_field,
    }


def quote_in_document(quote: str, document: str) -> bool:
    doc = normalize(document)
    fragments = [normalize(f) for f in re.split(r"\.\.\.|…|\[\.\.\.\]", quote)]
    fragments = [f for f in fragments if f]
    if not fragments or sum(len(f) for f in fragments) < 12:
        return False
    pos = 0
    for frag in fragments:
        idx = doc.find(frag, pos)
        if idx < 0:
            return False
        pos = idx + len(frag)
    return True


def grade_grounding(case: Case, screen: Screen) -> dict:
    flags = screen.red_flags
    if not flags:
        return {"grounding": None, "ungrounded_quotes": []}
    bad = [f.evidence_quote for f in flags if not quote_in_document(f.evidence_quote, case.document)]
    return {"grounding": 1 - len(bad) / len(flags), "ungrounded_quotes": bad}


def grade_recommendation(case: Case, screen: Screen) -> dict:
    return {"recommendation_ok": float(screen.recommendation.value in case.labels["acceptable_recommendations"])}


def grade_code(case: Case, screen: Screen) -> dict:
    out = {}
    out.update(grade_facts(case, screen))
    out.update(grade_grounding(case, screen))
    out.update(grade_recommendation(case, screen))
    out["n_red_flags"] = len(screen.red_flags)
    out["n_dd_questions"] = len(screen.dd_questions)
    return out
