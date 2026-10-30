"""The gold labels must be derivable from the documents, or the eval measures label noise."""

import json
import re

import pytest

from cimeval.dataset import DATASET_DIR, DATASETS, FACT_FIELDS, load_cases
from cimeval.graders import normalize

CORE = load_cases(DATASETS["core"])
HARD = load_cases(DATASETS["hard"])
CASES = CORE + HARD


def test_dataset_sizes():
    assert len(CORE) == 8
    assert len(HARD) == 6


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_every_stated_fact_appears_in_document(case):
    derived = set(case.labels.get("derived_facts", []))
    for field in FACT_FIELDS:
        value = case.labels["facts"][field]
        if value is None or field in derived:
            continue
        options = value["any_of"] if isinstance(value, dict) else [value]
        # For any_of labels, at least one accepted figure must be printed in the document.
        assert any(
            re.search(rf"(?<![\d.]){re.escape(v)}(?![\d])", case.document)
            for o in options for v in {f"{o:g}", f"{o:.1f}"}
        ), (field, value)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_planted_evidence_and_decoy_evidence_are_verbatim(case):
    doc = normalize(case.document)
    for item in case.labels["planted_flags"] + case.labels["decoys"]:
        assert normalize(item["evidence"]) in doc, item["id"]


@pytest.mark.parametrize("cases", [CORE, HARD], ids=["core", "hard"])
def test_both_directions_covered(cases):
    # Decoys in every set, so "flag everything" cannot score perfectly.
    assert sum(len(c.labels["decoys"]) for c in cases) >= 8


def test_core_has_a_clean_deal():
    assert any(not c.labels["planted_flags"] for c in CORE)


def test_hard_flags_are_tagged_by_difficulty():
    kinds = {f["difficulty"] for c in HARD for f in c.labels["planted_flags"]}
    assert kinds == {"arithmetic", "footnote", "cross_reference"}


def test_null_facts_exist_to_test_abstention():
    assert any(v is None for c in CASES for v in c.labels["facts"].values())


def test_calibration_set_references_real_targets():
    labels = {c.case_id: c.labels for c in CORE}
    for line in (DATASET_DIR.parent / "judge_calibration.jsonl").read_text().splitlines():
        item = json.loads(line)
        pool = labels[item["case_id"]]["planted_flags" if item["kind"] == "flag" else "decoys"]
        assert any(t["id"] == item["target_id"] for t in pool), item["id"]
