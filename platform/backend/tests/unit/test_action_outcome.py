import uuid

import pytest
from sqlalchemy import func, select

from bearvoice.domain.enums import OpportunityStatus
from bearvoice.domain.models import AuditEvent, Opportunity, OutcomeMeasurement
from bearvoice.modules.opportunities.service import (
    InvalidTransition,
    OutcomeDraft,
    complete_action_item,
    create_action_item,
)


async def test_completed_action_requires_outcome_measurement(db_session):
    opportunity = Opportunity(
        id=uuid.uuid4(),
        opportunity_type="improvement",
        title="改善壶盖清洁",
        problem="壶盖不可拆洗",
        status=OpportunityStatus.ACCEPTED.value,
    )
    db_session.add(opportunity)
    await db_session.flush()
    action = await create_action_item(
        db_session,
        opportunity.id,
        owner_id="pm-1",
        objective="完成可拆洗壶盖验证",
        decision_rationale="已通过机会审核",
    )

    with pytest.raises(InvalidTransition, match="完成行动前必须记录结果和限制"):
        await complete_action_item(
            db_session,
            action.id,
            outcome=None,
            actor_id="pm-1",
        )

    completed = await complete_action_item(
        db_session,
        action.id,
        outcome=OutcomeDraft(
            result="样机清洁耗时下降",
            limitations="仅完成 20 台内部样机测试",
        ),
        actor_id="pm-1",
    )
    measurements = int(
        await db_session.scalar(
            select(func.count()).select_from(OutcomeMeasurement)
        )
        or 0
    )
    audits = int(
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "action.complete")
        )
        or 0
    )

    assert completed.status == "completed"
    assert measurements == 1
    assert audits == 1
