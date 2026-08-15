from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.modules.reporting.decision_insights import (
    DecisionInsightResponse,
    get_decision_insights,
)
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    require_permission,
)


router = APIRouter(tags=["insights"])


@router.get("/insights/decision", response_model=DecisionInsightResponse)
async def decision_insights(
    product: str = Query(min_length=1, max_length=120),
    principal: Principal = Depends(require_permission(Permission.RUN_ANALYSIS)),
    session: AsyncSession = Depends(get_db_session),
) -> DecisionInsightResponse:
    normalized_product = product.strip()
    if not normalized_product:
        raise HTTPException(status_code=422, detail="产品线不能为空")
    assert_product_scope(normalized_product, principal)
    try:
        return await get_decision_insights(session, product=normalized_product)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
