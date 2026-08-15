from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import IngestionBatch, Source
from bearvoice.security.auth import Principal, require_permission


router = APIRouter(tags=["sources"])


@router.get("/sources")
async def sources(
    _principal: Principal = Depends(require_permission(Permission.MANAGE_SOURCES)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(
                Source.id,
                Source.name,
                Source.channel,
                Source.connection_status,
                func.coalesce(func.sum(IngestionBatch.raw_count), 0),
                func.coalesce(func.sum(IngestionBatch.deduplicated_count), 0),
                func.coalesce(func.sum(IngestionBatch.quarantined_count), 0),
            )
            .outerjoin(IngestionBatch, IngestionBatch.source_id == Source.id)
            .group_by(Source.id)
            .order_by(Source.name)
        )
    ).all()
    return [
        {
            "id": source_id,
            "name": name,
            "channel": channel,
            "connection_status": status,
            "raw_count": int(raw_count),
            "deduplicated_count": int(deduplicated_count),
            "quarantined_count": int(quarantined_count),
        }
        for (
            source_id,
            name,
            channel,
            status,
            raw_count,
            deduplicated_count,
            quarantined_count,
        ) in rows
    ]
