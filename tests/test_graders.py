import pytest

from cimeval.baselines import null_screen, oracle_screen
from cimeval.dataset import DATASETS, load_cases
from cimeval.graders import fact_correct, grade_code, quote_in_document
from cimscreen.schema import FlagCategory, RedFlag

CASES = load_cases(DATASETS["core"]) + load_cases(DATASETS["hard"])


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_oracle_scores_perfectly_on_code_graders(case):
    g = grade_code(case, oracle_screen(case))
    assert g["fact_accuracy"] == 1.0
    assert g["recommendation_ok"] == 1.0
    assert g["abstention"] in (None, 1.0)
    assert g["grounding"] in (None, 1.0)


def test_any_of_label_accepts_each_listed_figure():
    expected = {"any_of": [14.2, 19.1]}
    assert fact_correct("ebitda_ltm_musd", expected, 14.2)
    assert fact_correct("ebitda_ltm_musd", expected, 19.1)
    assert not fact_correct("ebitda_ltm_musd", expected, 16.0)
    assert not fact_correct("ebitda_ltm_musd", expected, None)


def test_null_baseline_fails_facts():
    accs = [grade_code(c, null_screen(c))["fact_accuracy"] for c in CASES]
    # Null only gets credit for the fields that really are unstated.
    assert max(accs) <= 0.5


def test_fabricated_quote_is_ungrounded():
    case = CASES[0]
    s = oracle_screen(case)
    s.red_flags.append(RedFlag(category=FlagCategory.other, description="x",
                               evidence_quote="The company has received a takeover offer from a competitor."))
    g = grade_code(case, s)
    assert g["grounding"] == pytest.approx(2 / 3)
    assert g["ungrounded_quotes"]


def test_quote_matching_tolerates_formatting_not_content():
    doc = "Its largest customer, a Mid-Atlantic grocery chain, accounted for 38% of LTM revenue."
    assert quote_in_document("“accounted for 38% of LTM revenue.”", doc)
    assert quote_in_document("Its largest customer ... accounted for 38% of LTM revenue", doc)
    assert not quote_in_document("accounted for 48% of LTM revenue", doc)
    assert not quote_in_document("38%", doc)  # too short to count as evidence
    assert not quote_in_document("accounted for 38% ... Its largest customer", doc)  # order matters


@pytest.mark.parametrize(
    "field,expected,got,ok",
    [
        ("revenue_ltm_musd", 84.2, 84.2, True),
        ("revenue_ltm_musd", 84.2, 84.0, False),
        ("revenue_ltm_musd", 118.0, 118, True),
        ("ebitda_ltm_musd", None, None, True),
        ("ebitda_ltm_musd", None, 12.1, False),  # invented a number the CIM never states
        ("ebitda_ltm_musd", 8.3, None, False),
        ("top_customer_pct", 38, 0.38, True),  # same answer, fraction form
        ("revenue_ltm_musd", 0.842, 84.2, False),  # unit leniency only applies to percentages
    ],
)
def test_fact_tolerance(field, expected, got, ok):
    assert fact_correct(field, expected, got) is ok
