from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.modules.reporting.queries import (
    DashboardSnapshot,
    get_dashboard_snapshot,
)
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    require_permission,
)


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardSnapshot)
async def dashboard(
    product: str,
    principal: Principal = Depends(require_permission(Permission.READ_VOICE)),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardSnapshot:
    assert_product_scope(product, principal)
    return await get_dashboard_snapshot(
        session,
        product=product,
    )
