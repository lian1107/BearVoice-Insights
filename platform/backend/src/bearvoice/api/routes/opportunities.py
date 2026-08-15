import uuid
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission, ReviewDecisionType
from bearvoice.domain.models import AuditEvent, Opportunity, OpportunityEvidence
from bearvoice.modules.opportunities.service import (
    InvalidTransition,
    ReviewOpportunityCommand,
    create_action_item,
    review_opportunity,
)
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    require_permission,
)


router = APIRouter(tags=["opportunities"])


class OpportunityReviewBody(BaseModel):
    decision: ReviewDecisionType
    reason: str
    owner: str | None = None
    due_date: date | None = None
    external_reference: str | None = None


def _summary(item: Opportunity, evidence_count: int) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "status": item.status,
        "opportunity_type": item.opportunity_type,
        "safety_level": item.safety_level,
        "priority_override": item.priority_override,
        "severity": item.severity,
        "impact_scope": item.impact_scope,
        "evidence_count": evidence_count,
    }


async def _get_scoped_opportunity(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
    principal: Principal,
) -> Opportunity:
    item = await session.get(Opportunity, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="机会不存在或无权访问")
    assert_product_scope(item.product or "", principal)
    return item


async def _audit_timeline(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
) -> list[dict[str, object]]:
    entries = list(
        await session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.subject_type == "opportunity",
                AuditEvent.subject_id == opportunity_id,
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    return [
        {
            "id": entry.id,
            "action": entry.action,
            "actor_id": entry.actor_id,
            "reason": entry.reason or "",
            "created_at": entry.created_at,
        }
        for entry in entries
    ]


@router.get("/opportunities")
async def opportunities(
    product: str,
    principal: Principal = Depends(require_permission(Permission.READ_VOICE)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    assert_product_scope(product, principal)
    rows = (
        await session.execute(
            select(
                Opportunity,
                func.count(distinct(OpportunityEvidence.voice_record_id)),
            )
            .outerjoin(
                OpportunityEvidence,
                OpportunityEvidence.opportunity_id == Opportunity.id,
            )
            .where(Opportunity.product == product)
            .group_by(Opportunity.id)
            .order_by(Opportunity.created_at)
        )
    ).all()
    return [_summary(item, int(evidence_count)) for item, evidence_count in rows]


@router.get("/opportunities/{opportunity_id}")
async def opportunity_detail(
    opportunity_id: uuid.UUID,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_OPPORTUNITY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    item = await _get_scoped_opportunity(session, opportunity_id, principal)
    evidence_ids = list(
        await session.scalars(
            select(OpportunityEvidence.signal_id)
            .where(
                OpportunityEvidence.opportunity_id == item.id,
                OpportunityEvidence.signal_id.is_not(None),
            )
            .order_by(OpportunityEvidence.created_at, OpportunityEvidence.id)
        )
    )
    body = _summary(item, len(evidence_ids))
    body.update(
        {
            "problem": item.problem,
            "evidence_ids": evidence_ids,
            "audit_timeline": await _audit_timeline(session, item.id),
        }
    )
    return body


@router.post("/opportunities/{opportunity_id}/reviews")
async def submit_opportunity_review(
    opportunity_id: uuid.UUID,
    body: OpportunityReviewBody,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_OPPORTUNITY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    item = await _get_scoped_opportunity(session, opportunity_id, principal)
    if (body.due_date or body.external_reference) and not (body.owner or "").strip():
        raise HTTPException(
            status_code=422,
            detail="填写计划日期或外部任务编号时必须指定负责人",
        )
    try:
        reviewed = await review_opportunity(
            session,
            ReviewOpportunityCommand(
                opportunity_id=item.id,
                decision=body.decision,
                actor_id=principal.subject,
                reason=body.reason,
            ),
        )
        if body.decision == ReviewDecisionType.APPROVE and body.owner:
            action = await create_action_item(
                session,
                reviewed.id,
                owner_id=body.owner,
                objective=reviewed.title,
                decision_rationale=body.reason,
            )
            action.due_at = (
                datetime.combine(body.due_date, time.min, tzinfo=UTC)
                if body.due_date
                else None
            )
            action.external_system_ref = body.external_reference
        await session.flush()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidTransition, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    timeline = await _audit_timeline(session, reviewed.id)
    return {"status": reviewed.status, "audit": timeline[-1]}
