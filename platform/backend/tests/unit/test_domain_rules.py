import pytest

from bearvoice.domain.enums import OpportunityStatus
from bearvoice.domain.schemas import OpportunityDraft


def test_new_product_draft_requires_five_independent_evidence_items():
    with pytest.raises(ValueError, match="新品型机会至少需要 5 条独立证据"):
        OpportunityDraft(
            opportunity_type="new_product",
            title="一人份免看管早餐壶",
            evidence_record_ids=["a", "b", "c", "d"],
        )


def test_opportunity_cannot_skip_human_review():
    assert (
        OpportunityStatus.DRAFT.can_transition_to(OpportunityStatus.ACCEPTED)
        is False
    )
