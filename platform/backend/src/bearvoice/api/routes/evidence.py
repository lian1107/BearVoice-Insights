import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.modules.reporting.queries import (
    EvidenceProjection,
    get_evidence_projection,
)
from bearvoice.security.auth import Principal, require_permission


router = APIRouter(tags=["evidence"])


@router.get("/evidence/{evidence_id}", response_model=EvidenceProjection)
async def evidence(
    evidence_id: uuid.UUID,
    opportunity_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_permission(Permission.READ_VOICE)),
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceProjection:
    allowed_products = (
        None
        if Permission.READ_ALL_PRODUCT_LINES in principal.permissions
        else principal.product_lines
    )
    projection = await get_evidence_projection(
        session,
        evidence_id=evidence_id,
        allowed_products=allowed_products,
        opportunity_id=opportunity_id,
    )
    if projection is None:
        raise HTTPException(status_code=404, detail="证据不存在或无权访问")
    return projection
