from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import Opportunity, OpportunityEvidence
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    require_permission,
)


router = APIRouter(tags=["opportunities"])


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
    return [
        {
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "opportunity_type": item.opportunity_type,
            "safety_level": item.safety_level,
            "priority_override": item.priority_override,
            "evidence_count": int(evidence_count),
        }
        for item, evidence_count in rows
    ]
