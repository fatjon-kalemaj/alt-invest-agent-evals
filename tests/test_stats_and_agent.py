from types import SimpleNamespace

import pytest

from cimeval.stats import paired_diff, summarize
from cimscreen import agent
from cimscreen.schema import Screen


def test_reps_are_averaged_within_case_before_aggregating():
    rows = [
        {"case_id": "a", "metrics": {"flag_recall": 1.0}},
        {"case_id": "a", "metrics": {"flag_recall": 1.0}},
        {"case_id": "a", "metrics": {"flag_recall": 1.0}},
        {"case_id": "b", "metrics": {"flag_recall": 0.0}},
        {"case_id": "c", "metrics": None},  # truncated / refused: not averaged in
    ]
    s = summarize(rows)
    assert s["flag_recall"]["mean"] == 0.5
    assert s["flag_recall"]["n_cases"] == 2


def test_paired_diff_uses_common_cases():
    base = {"m": {"per_case": {"a": 0.5, "b": 0.5}}}
    new = {"m": {"per_case": {"a": 1.0, "b": 0.5, "c": 0.0}}}
    assert paired_diff(base, new, "m")["mean_diff"] == 0.25


class FakeClient:
    def __init__(self, response):
        self.messages = SimpleNamespace(create=lambda **kw: response)


def _response(stop_reason, text="", model=agent.DEFAULT_MODEL, stop_details=None):
    usage = SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(model=model, stop_reason=stop_reason, stop_details=stop_details, usage=usage,
                           content=[SimpleNamespace(type="text", text=text)], _request_id="req_test")


VALID = Screen(company_name="X", sector="Y",
               financials={"revenue_ltm_musd": 1, "ebitda_ltm_musd": None, "revenue_growth_pct": None, "top_customer_pct": None},
               red_flags=[], dd_questions=[], recommendation="pursue", rationale="r").model_dump_json()


@pytest.mark.parametrize(
    "stop_reason,text,status",
    [("end_turn", VALID, "ok"), ("max_tokens", VALID[:40], "truncated"), ("end_turn", "{}", "invalid_output")],
)
def test_agent_distinguishes_outcomes(stop_reason, text, status):
    r = agent.screen("doc", client=FakeClient(_response(stop_reason, text)))
    assert r.status == status


def test_refusal_is_its_own_status():
    r = agent.screen("doc", client=FakeClient(_response("refusal", stop_details=SimpleNamespace(category="cyber"))))
    assert r.status == "refusal" and r.refusal_category == "cyber"


def test_wrong_served_model_fails_loudly():
    with pytest.raises(agent.ServedModelMismatch):
        agent.screen("doc", client=FakeClient(_response("end_turn", VALID, model="claude-haiku-5-5")))
