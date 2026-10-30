"""Load the synthetic CIM cases and their gold labels."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parents[2] / "evals" / "dataset"
FACT_FIELDS = ("revenue_ltm_musd", "ebitda_ltm_musd", "revenue_growth_pct", "top_customer_pct")


@dataclass(frozen=True)
class Case:
    case_id: str
    document: str
    labels: dict


def load_cases(dataset_dir: Path = DATASET_DIR, only: list[str] | None = None) -> list[Case]:
    cases = []
    for label_path in sorted((dataset_dir / "labels").glob("*.json")):
        labels = json.loads(label_path.read_text())
        case_id = labels["case_id"]
        if only and case_id not in only:
            continue
        document = (dataset_dir / "cims" / f"{case_id}.md").read_text()
        cases.append(Case(case_id, document, labels))
    return cases


def dataset_hash(dataset_dir: Path = DATASET_DIR) -> str:
    h = hashlib.sha256()
    for p in sorted(dataset_dir.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(dataset_dir).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]
