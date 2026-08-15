import uuid

from sqlalchemy import select

from bearvoice.domain.models import Cluster, TaxonomyVersion
from bearvoice.modules.review.service import (
    MergeClustersCommand,
    apply_taxonomy_revision,
)


async def test_merge_creates_new_taxonomy_version_without_mutating_source(
    db_session,
):
    source = TaxonomyVersion(
        id=uuid.uuid4(),
        product_scope="养生壶",
        origin="test",
        status="draft",
    )
    db_session.add(source)
    await db_session.flush()
    original_clusters = [
        Cluster(
            id=uuid.uuid4(),
            taxonomy_version_id=source.id,
            original_name=name,
            current_name=name,
            keywords=[],
            representative_record_ids=[],
            is_outlier=False,
            status="active",
        )
        for name in ("原类一", "原类二", "保留类")
    ]
    db_session.add_all(original_clusters)
    await db_session.flush()

    revised = await apply_taxonomy_revision(
        db_session,
        MergeClustersCommand(
            taxonomy_id=source.id,
            cluster_ids=(original_clusters[0].id, original_clusters[1].id),
            new_name="加热与测温异常",
            actor_id="reviewer-1",
            reason="同一加热控制根因",
        ),
    )
    source_names = list(
        await db_session.scalars(
            select(Cluster.current_name)
            .where(Cluster.taxonomy_version_id == source.id)
            .order_by(Cluster.current_name)
        )
    )
    revised_names = set(
        await db_session.scalars(
            select(Cluster.current_name).where(
                Cluster.taxonomy_version_id == revised.id
            )
        )
    )

    assert revised.parent_version_id == source.id
    assert source_names == ["保留类", "原类一", "原类二"]
    assert revised_names == {"保留类", "加热与测温异常"}
