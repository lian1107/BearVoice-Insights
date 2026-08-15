import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.models import (
    AuditEvent,
    Cluster,
    ClusterMembership,
    TaxonomyRevision,
    TaxonomyVersion,
)


@dataclass(frozen=True)
class MergeClustersCommand:
    taxonomy_id: uuid.UUID
    cluster_ids: tuple[uuid.UUID, ...]
    new_name: str
    actor_id: str
    reason: str


@dataclass(frozen=True)
class SplitGroup:
    name: str
    signal_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class ReviseTaxonomyCommand:
    taxonomy_id: uuid.UUID
    operation: str
    cluster_ids: tuple[uuid.UUID, ...]
    new_name: str
    actor_id: str
    reason: str
    split_groups: tuple[SplitGroup, ...] = ()


async def apply_taxonomy_revision(
    session: AsyncSession,
    command: MergeClustersCommand,
) -> TaxonomyVersion:
    if len(set(command.cluster_ids)) < 2:
        raise ValueError("合并至少需要两个不同聚类")
    if not command.new_name.strip() or not command.reason.strip():
        raise ValueError("聚类新名称和修订理由不能为空")

    source = await session.scalar(
        select(TaxonomyVersion)
        .where(TaxonomyVersion.id == command.taxonomy_id)
        .with_for_update()
    )
    if source is None:
        raise LookupError(f"分类法版本不存在：{command.taxonomy_id}")
    source_clusters = list(
        await session.scalars(
            select(Cluster).where(Cluster.taxonomy_version_id == source.id)
        )
    )
    cluster_by_id = {cluster.id: cluster for cluster in source_clusters}
    missing = set(command.cluster_ids) - set(cluster_by_id)
    if missing:
        raise ValueError("待合并聚类不属于源分类法")

    revised = TaxonomyVersion(
        id=uuid.uuid4(),
        product_scope=source.product_scope,
        parent_version_id=source.id,
        origin="human_revision",
        status="draft",
    )
    session.add(revised)
    await session.flush()

    selected = [cluster_by_id[item] for item in command.cluster_ids]
    copied_cluster_ids: dict[uuid.UUID, uuid.UUID] = {}
    copied_clusters: list[Cluster] = []
    for cluster in source_clusters:
        if cluster.id in command.cluster_ids:
            continue
        copied = _copy_cluster(cluster, revised.id)
        copied_cluster_ids[cluster.id] = copied.id
        copied_clusters.append(copied)

    merged = Cluster(
        id=uuid.uuid4(),
        taxonomy_version_id=revised.id,
        original_name=command.new_name,
        current_name=command.new_name,
        description=command.reason,
        primary_signal_type=selected[0].primary_signal_type,
        keywords=sorted(
            {keyword for cluster in selected for keyword in cluster.keywords}
        ),
        representative_record_ids=list(
            dict.fromkeys(
                record_id
                for cluster in selected
                for record_id in cluster.representative_record_ids
            )
        )[:10],
        is_outlier=all(cluster.is_outlier for cluster in selected),
        status="active",
    )
    session.add_all([*copied_clusters, merged])
    await session.flush()

    source_memberships = list(
        await session.scalars(
            select(ClusterMembership).where(
                ClusterMembership.taxonomy_version_id == source.id
            )
        )
    )
    new_memberships: list[ClusterMembership] = []
    for membership in source_memberships:
        if membership.cluster_id in command.cluster_ids:
            target_cluster_id = merged.id
        elif membership.cluster_id is None:
            target_cluster_id = None
        else:
            target_cluster_id = copied_cluster_ids[membership.cluster_id]
        new_memberships.append(
            ClusterMembership(
                id=uuid.uuid4(),
                taxonomy_version_id=revised.id,
                cluster_id=target_cluster_id,
                signal_id=membership.signal_id,
                assignment_status=membership.assignment_status,
            )
        )
    session.add_all(new_memberships)
    session.add(
        TaxonomyRevision(
            id=uuid.uuid4(),
            taxonomy_version_id=revised.id,
            operation="merge",
            payload={
                "source_taxonomy_id": str(source.id),
                "cluster_ids": [str(item) for item in command.cluster_ids],
                "new_cluster_id": str(merged.id),
                "new_name": command.new_name,
            },
            reason=command.reason,
            actor_id=command.actor_id,
        )
    )
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=command.actor_id,
            action="taxonomy.merge_clusters",
            subject_type="taxonomy_version",
            subject_id=revised.id,
            before_state={"taxonomy_version_id": str(source.id)},
            after_state={"taxonomy_version_id": str(revised.id)},
            reason=command.reason,
        )
    )
    await session.flush()
    return revised


async def apply_taxonomy_edit(
    session: AsyncSession,
    command: ReviseTaxonomyCommand,
) -> TaxonomyVersion:
    if command.operation not in {"rename", "remove", "restore", "split"}:
        raise ValueError(f"不支持的分类法操作：{command.operation}")
    if not command.reason.strip() or not command.cluster_ids:
        raise ValueError("分类法修订必须选择聚类并填写理由")

    source = await session.scalar(
        select(TaxonomyVersion)
        .where(TaxonomyVersion.id == command.taxonomy_id)
        .with_for_update()
    )
    if source is None:
        raise LookupError(f"分类法版本不存在：{command.taxonomy_id}")
    source_clusters = list(
        await session.scalars(
            select(Cluster).where(Cluster.taxonomy_version_id == source.id)
        )
    )
    cluster_by_id = {cluster.id: cluster for cluster in source_clusters}
    selected_ids = set(command.cluster_ids)
    if selected_ids - set(cluster_by_id):
        raise ValueError("待修订聚类不属于源分类法")
    if command.operation in {"rename", "split"} and len(selected_ids) != 1:
        raise ValueError("改名或拆分一次只能选择一个聚类")
    if command.operation == "rename" and not command.new_name.strip():
        raise ValueError("聚类新名称不能为空")

    source_memberships = list(
        await session.scalars(
            select(ClusterMembership).where(
                ClusterMembership.taxonomy_version_id == source.id
            )
        )
    )
    revised = TaxonomyVersion(
        id=uuid.uuid4(),
        product_scope=source.product_scope,
        parent_version_id=source.id,
        origin="human_revision",
        status="draft",
    )
    session.add(revised)
    await session.flush()

    copied_cluster_ids: dict[uuid.UUID, uuid.UUID] = {}
    split_signal_targets: dict[uuid.UUID, uuid.UUID] = {}
    new_clusters: list[Cluster] = []
    if command.operation == "split":
        source_cluster = cluster_by_id[next(iter(selected_ids))]
        source_signal_ids = {
            membership.signal_id
            for membership in source_memberships
            if membership.cluster_id == source_cluster.id
        }
        if len(command.split_groups) < 2:
            raise ValueError("拆分至少需要两个成员分组")
        group_signal_ids = [
            signal_id
            for group in command.split_groups
            for signal_id in group.signal_ids
        ]
        if len(group_signal_ids) != len(set(group_signal_ids)):
            raise ValueError("拆分成员不能出现在多个分组")
        if set(group_signal_ids) != source_signal_ids:
            raise ValueError("拆分分组必须完整覆盖原聚类成员")
        for group in command.split_groups:
            if not group.name.strip() or not group.signal_ids:
                raise ValueError("拆分分组必须包含名称和成员")
            cluster = Cluster(
                id=uuid.uuid4(),
                taxonomy_version_id=revised.id,
                original_name=group.name.strip(),
                current_name=group.name.strip(),
                description=command.reason,
                primary_signal_type=source_cluster.primary_signal_type,
                keywords=list(source_cluster.keywords),
                representative_record_ids=list(source_cluster.representative_record_ids),
                is_outlier=source_cluster.is_outlier,
                status="active",
            )
            new_clusters.append(cluster)
            for signal_id in group.signal_ids:
                split_signal_targets[signal_id] = cluster.id

    for cluster in source_clusters:
        if command.operation == "split" and cluster.id in selected_ids:
            continue
        copied = _copy_cluster(cluster, revised.id)
        if cluster.id in selected_ids:
            if command.operation == "rename":
                copied.current_name = command.new_name.strip()
            elif command.operation == "remove":
                copied.status = "removed"
            elif command.operation == "restore":
                if cluster.status != "removed":
                    raise ValueError("只有已移出的聚类可以恢复")
                copied.status = "active"
        copied_cluster_ids[cluster.id] = copied.id
        new_clusters.append(copied)
    session.add_all(new_clusters)
    await session.flush()

    new_memberships: list[ClusterMembership] = []
    for membership in source_memberships:
        target_cluster_id = (
            split_signal_targets[membership.signal_id]
            if command.operation == "split" and membership.cluster_id in selected_ids
            else (
                copied_cluster_ids[membership.cluster_id]
                if membership.cluster_id is not None
                else None
            )
        )
        new_memberships.append(
            ClusterMembership(
                id=uuid.uuid4(),
                taxonomy_version_id=revised.id,
                cluster_id=target_cluster_id,
                signal_id=membership.signal_id,
                assignment_status=membership.assignment_status,
            )
        )
    session.add_all(new_memberships)
    session.add(
        TaxonomyRevision(
            id=uuid.uuid4(),
            taxonomy_version_id=revised.id,
            operation=command.operation,
            payload={
                "source_taxonomy_id": str(source.id),
                "cluster_ids": [str(item) for item in command.cluster_ids],
                "new_name": command.new_name,
                "split_groups": [
                    {
                        "name": group.name,
                        "signal_ids": [str(item) for item in group.signal_ids],
                    }
                    for group in command.split_groups
                ],
            },
            reason=command.reason,
            actor_id=command.actor_id,
        )
    )
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=command.actor_id,
            action=f"taxonomy.{command.operation}",
            subject_type="taxonomy_version",
            subject_id=revised.id,
            before_state={"taxonomy_version_id": str(source.id)},
            after_state={"taxonomy_version_id": str(revised.id)},
            reason=command.reason,
        )
    )
    await session.flush()
    return revised


def _copy_cluster(cluster: Cluster, taxonomy_version_id: uuid.UUID) -> Cluster:
    return Cluster(
        id=uuid.uuid4(),
        taxonomy_version_id=taxonomy_version_id,
        original_name=cluster.original_name,
        current_name=cluster.current_name,
        description=cluster.description,
        primary_signal_type=cluster.primary_signal_type,
        keywords=list(cluster.keywords),
        representative_record_ids=list(cluster.representative_record_ids),
        is_outlier=cluster.is_outlier,
        status=cluster.status,
    )
