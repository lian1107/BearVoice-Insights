from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import EvaluationRun, GoldenExample, ModelRelease
from bearvoice.security.auth import Principal, require_permission


router = APIRouter(tags=["evaluation"])


@router.get("/evaluations/summary")
async def evaluation_summary(
    _principal: Principal = Depends(
        require_permission(Permission.MANAGE_EVALUATION)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    golden_rows = (
        await session.execute(
            select(GoldenExample.review_status, func.count(GoldenExample.id))
            .group_by(GoldenExample.review_status)
        )
    ).all()
    active_release = await session.scalar(
        select(ModelRelease.model_version).where(ModelRelease.status == "active")
    )
    evaluation_count = int(
        await session.scalar(select(func.count()).select_from(EvaluationRun)) or 0
    )
    return {
        "golden_examples": {status: int(count) for status, count in golden_rows},
        "evaluation_count": evaluation_count,
        "active_model_version": active_release,
    }
