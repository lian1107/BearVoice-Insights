from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class OpportunityDraft(BaseModel):
    opportunity_type: Literal["improvement", "new_product"]
    title: str = Field(min_length=1, max_length=200)
    evidence_record_ids: list[str]

    @model_validator(mode="after")
    def validate_evidence_threshold(self) -> Self:
        independent_count = len(set(self.evidence_record_ids))
        if self.opportunity_type == "new_product" and independent_count < 5:
            raise ValueError("新品型机会至少需要 5 条独立证据")
        if self.opportunity_type == "improvement" and independent_count < 3:
            raise ValueError("改进型机会至少需要 3 条独立证据")
        return self
