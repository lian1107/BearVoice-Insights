import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import Cluster, TaxonomyVersion
from bearvoice.modules.review.service import (
    MergeClustersCommand,
    ReviseTaxonomyCommand,
    SplitGroup,
    apply_taxonomy_edit,
    apply_taxonomy_revision,
)
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    require_permission,
)


router = APIRouter(tags=["taxonomy"])


class SplitGroupBody(BaseModel):
    name: str
    signal_ids: list[uuid.UUID]


class TaxonomyRevisionBody(BaseModel):
    operation: Literal["rename", "merge", "split", "remove", "restore"]
    cluster_ids: list[uuid.UUID]
    new_name: str = ""
    reason: str
    split_groups: list[SplitGroupBody] = Field(default_factory=list)


def _summary(item: TaxonomyVersion, cluster_count: int) -> dict[str, object]:
    return {
        "id": item.id,
        "status": item.status,
        "origin": item.origin,
        "parent_version_id": item.parent_version_id,
        "cluster_count": cluster_count,
    }


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
                TaxonomyVersion,
                func.count(Cluster.id).filter(Cluster.status != "removed"),
            )
            .outerjoin(Cluster, Cluster.taxonomy_version_id == TaxonomyVersion.id)
            .where(TaxonomyVersion.product_scope == product)
            .group_by(TaxonomyVersion.id)
            .order_by(TaxonomyVersion.created_at.desc())
        )
    ).all()
    return [_summary(item, int(cluster_count)) for item, cluster_count in rows]


@router.post("/taxonomies/{taxonomy_id}/revisions")
async def create_taxonomy_revision(
    taxonomy_id: uuid.UUID,
    body: TaxonomyRevisionBody,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_TAXONOMY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    source = await session.get(TaxonomyVersion, taxonomy_id)
    if source is None:
        raise HTTPException(status_code=404, detail="分类法版本不存在")
    assert_product_scope(source.product_scope, principal)
    try:
        if body.operation == "merge":
            revised = await apply_taxonomy_revision(
                session,
                MergeClustersCommand(
                    taxonomy_id=source.id,
                    cluster_ids=tuple(body.cluster_ids),
                    new_name=body.new_name,
                    actor_id=principal.subject,
                    reason=body.reason,
                ),
            )
        else:
            revised = await apply_taxonomy_edit(
                session,
                ReviseTaxonomyCommand(
                    taxonomy_id=source.id,
                    operation=body.operation,
                    cluster_ids=tuple(body.cluster_ids),
                    new_name=body.new_name,
                    actor_id=principal.subject,
                    reason=body.reason,
                    split_groups=tuple(
                        SplitGroup(
                            name=group.name,
                            signal_ids=tuple(group.signal_ids),
                        )
                        for group in body.split_groups
                    ),
                ),
            )
        await session.flush()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    cluster_count = int(
        await session.scalar(
            select(func.count(Cluster.id)).where(
                Cluster.taxonomy_version_id == revised.id,
                Cluster.status != "removed",
            )
        )
        or 0
    )
    return _summary(revised, cluster_count)
