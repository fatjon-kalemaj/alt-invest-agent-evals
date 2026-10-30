"""Output contract for a first-pass CIM screen.

Every numeric field is nullable on purpose: when the document does not state a
figure, the correct answer is null, not a plausible guess. The eval scores that
abstention separately from accuracy.
"""

from enum import Enum

from pydantic import BaseModel, Field


class FlagCategory(str, Enum):
    customer_concentration = "customer_concentration"
    supplier_concentration = "supplier_concentration"
    quality_of_earnings = "quality_of_earnings"
    revenue_quality = "revenue_quality"
    churn_retention = "churn_retention"
    legal_regulatory = "legal_regulatory"
    key_person = "key_person"
    working_capital = "working_capital"
    other = "other"


class Recommendation(str, Enum):
    pursue = "pursue"
    needs_more_info = "needs_more_info"
    pass_ = "pass"


class Financials(BaseModel):
    revenue_ltm_musd: float | None = Field(
        description="Last-twelve-months revenue in USD millions, exactly as reported. Null if not stated."
    )
    ebitda_ltm_musd: float | None = Field(
        description="LTM EBITDA in USD millions as the document labels it (adjusted if that is the only figure). "
        "Null if no dollar figure is stated; do not derive it from a margin range."
    )
    revenue_growth_pct: float | None = Field(
        description="Most recent year-over-year total revenue growth in percent. Null if not stated."
    )
    top_customer_pct: float | None = Field(
        description="Share of revenue from the single largest customer or payer, in percent. "
        "If the document gives that customer's revenue in dollars, compute the share. Null if it cannot be determined."
    )


class RedFlag(BaseModel):
    category: FlagCategory
    description: str = Field(description="One or two sentences: what the risk is and why it matters to a buyer.")
    evidence_quote: str = Field(
        description="A verbatim quote from the document that supports this flag. Copy it exactly; do not paraphrase."
    )


class Screen(BaseModel):
    company_name: str
    sector: str
    financials: Financials
    red_flags: list[RedFlag] = Field(
        description="Material diligence risks only. Do not list items the document already resolves."
    )
    dd_questions: list[str] = Field(
        description="Specific questions for management, each tied to something in this document."
    )
    recommendation: Recommendation
    rationale: str = Field(description="Two to four sentences supporting the recommendation.")
