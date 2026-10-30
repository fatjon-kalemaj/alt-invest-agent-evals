"""The gold labels must be derivable from the documents, or the eval measures label noise."""

import json
import re

import pytest

from cimeval.dataset import DATASET_DIR, FACT_FIELDS, load_cases
from cimeval.graders import normalize

CASES = load_cases()


def test_eight_cases_load():
    assert len(CASES) == 8


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_every_stated_fact_appears_in_document(case):
    for field in FACT_FIELDS:
        value = case.labels["facts"][field]
        if value is None:
            continue
        text = f"{value:g}"
        variants = {text, f"{value:.1f}"}
        assert any(re.search(rf"(?<![\d.]){re.escape(v)}(?![\d])", case.document) for v in variants), (field, value)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_planted_evidence_and_decoy_evidence_are_verbatim(case):
    doc = normalize(case.document)
    for item in case.labels["planted_flags"] + case.labels["decoys"]:
        assert normalize(item["evidence"]) in doc, item["id"]


def test_both_directions_covered():
    # At least one clean deal, so "flag everything" cannot score perfectly.
    assert any(not c.labels["planted_flags"] for c in CASES)
    assert sum(len(c.labels["decoys"]) for c in CASES) >= 8


def test_null_facts_exist_to_test_abstention():
    assert any(v is None for c in CASES for v in c.labels["facts"].values())


def test_calibration_set_references_real_targets():
    labels = {c.case_id: c.labels for c in CASES}
    for line in (DATASET_DIR.parent / "judge_calibration.jsonl").read_text().splitlines():
        item = json.loads(line)
        pool = labels[item["case_id"]]["planted_flags" if item["kind"] == "flag" else "decoys"]
        assert any(t["id"] == item["target_id"] for t in pool), item["id"]
