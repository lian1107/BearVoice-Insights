from sqlalchemy import func, select

from bearvoice.domain.enums import OpportunityStatus, ReviewDecisionType
from bearvoice.domain.models import AuditEvent, ReviewDecision
from bearvoice.domain.schemas import OpportunityDraft
from bearvoice.modules.opportunities.service import (
    ReviewOpportunityCommand,
    create_opportunity,
    review_opportunity,
)
from tests.unit.test_opportunity_review import seed_voice_records


async def test_accepting_opportunity_requires_reason_and_creates_audit(
    db_session,
):
    records = await seed_voice_records(db_session, 3)
    opportunity = await create_opportunity(
        db_session,
        OpportunityDraft(
            opportunity_type="improvement",
            title="玻璃壶身炸裂",
            safety_level="critical",
            evidence_record_ids=[str(record.id) for record in records],
        ),
    )

    reviewed = await review_opportunity(
        db_session,
        ReviewOpportunityCommand(
            opportunity_id=opportunity.id,
            decision=ReviewDecisionType.APPROVE,
            actor_id="reviewer-1",
            reason="三条独立炸裂证据，进入专项验证",
        ),
    )

    decisions = int(
        await db_session.scalar(select(func.count()).select_from(ReviewDecision))
        or 0
    )
    audits = int(
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "opportunity.review")
        )
        or 0
    )
    assert reviewed.status == OpportunityStatus.ACCEPTED.value
    assert decisions == 1
    assert audits == 1
