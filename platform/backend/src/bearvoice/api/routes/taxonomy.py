from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import Cluster, TaxonomyVersion
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    require_permission,
)


router = APIRouter(tags=["taxonomy"])


@router.get("/taxonomies")
async def taxonomies(
    product: str,
    principal: Principal = Depends(require_permission(Permission.READ_VOICE)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    assert_product_scope(product, principal)
    rows = (
        await session.execute(
            select(
                TaxonomyVersion.id,
                TaxonomyVersion.status,
                TaxonomyVersion.origin,
                TaxonomyVersion.parent_version_id,
                func.count(Cluster.id),
            )
            .outerjoin(Cluster, Cluster.taxonomy_version_id == TaxonomyVersion.id)
            .where(TaxonomyVersion.product_scope == product)
            .group_by(TaxonomyVersion.id)
            .order_by(TaxonomyVersion.created_at.desc())
        )
    ).all()
    return [
        {
            "id": taxonomy_id,
            "status": status,
            "origin": origin,
            "parent_version_id": parent_id,
            "cluster_count": int(cluster_count),
        }
        for taxonomy_id, status, origin, parent_id, cluster_count in rows
    ]
