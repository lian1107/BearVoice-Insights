from sqlalchemy import select

from bearvoice.domain.models import ActionItem, Cluster, Opportunity, TaxonomyVersion
from bearvoice.modules.evaluation.service import build_stratified_sample
from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)
from bearvoice.security.auth import issue_dev_token


async def test_reviewer_can_inspect_evidence_and_persist_audited_decision(
    api_client,
    reviewer_token,
    db_session,
    repo_root,
):
    await import_legacy_snapshot(db_session, load_legacy_snapshot(repo_root))
    opportunity = await db_session.scalar(
        select(Opportunity)
        .where(Opportunity.priority_override == "safety")
        .limit(1)
    )
    headers = {"Authorization": f"Bearer {reviewer_token}"}

    detail_response = await api_client.get(
        f"/api/opportunities/{opportunity.id}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "pending_review"
    assert detail["evidence_count"] >= 3
    assert detail["evidence_ids"]

    evidence_response = await api_client.get(
        f"/api/evidence/{detail['evidence_ids'][0]}",
        params={"opportunity_id": opportunity.id},
        headers=headers,
    )
    assert evidence_response.status_code == 200
    assert evidence_response.json()["direction"] == "support"

    review_response = await api_client.post(
        f"/api/opportunities/{opportunity.id}/reviews",
        headers=headers,
        json={
            "decision": "approve",
            "reason": "涉及人身安全，转品控复核",
            "owner": "quality-owner",
            "due_date": "2026-08-30",
            "external_reference": "QA-2026-001",
        },
    )
    assert review_response.status_code == 200
    review = review_response.json()
    assert review["status"] == "accepted"
    assert review["audit"]["actor_id"] == "reviewer-1"
    assert review["audit"]["reason"] == "涉及人身安全，转品控复核"

    action = await db_session.scalar(
        select(ActionItem).where(ActionItem.opportunity_id == opportunity.id)
    )
    assert action is not None
    assert action.owner_id == "quality-owner"
    assert action.external_system_ref == "QA-2026-001"


async def test_model_reviewer_keeps_suggestion_separate_from_human_label(
    api_client,
    api_settings,
    db_session,
    repo_root,
):
    run_id = await import_legacy_snapshot(
        db_session,
        load_legacy_snapshot(repo_root),
    )
    await build_stratified_sample(db_session, run_id, size=100)
    token = issue_dev_token(
        api_settings,
        subject="model-reviewer-1",
        roles=("model_reviewer",),
        product_lines=("养生壶",),
    )
    headers = {"Authorization": f"Bearer {token}"}

    queue_response = await api_client.get(
        "/api/evaluations/golden-examples",
        headers=headers,
    )
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert len(queue) == 100
    assert queue[0]["review_status"] == "pending_human_review"
    assert "不是黄金答案" in queue[0]["model_suggestion"]
    assert queue[0]["reviewer_one"] is None

    review_response = await api_client.post(
        f"/api/evaluations/golden-examples/{queue[0]['id']}/reviews",
        headers=headers,
        json={
            "signal": "缺陷",
            "object_name": "玻璃壶体",
            "evidence_text": queue[0]["redacted_input"],
        },
    )
    assert review_response.status_code == 200
    reviewed = review_response.json()
    assert reviewed["review_status"] == "pending_second_review"
    assert reviewed["reviewer_one"] == "缺陷 / 玻璃壶体"
    assert reviewed["reviewer_two"] is None


async def test_taxonomy_revision_creates_child_version_without_overwrite(
    api_client,
    reviewer_token,
    db_session,
    repo_root,
):
    await import_legacy_snapshot(db_session, load_legacy_snapshot(repo_root))
    taxonomy = await db_session.scalar(select(TaxonomyVersion).limit(1))
    cluster = await db_session.scalar(
        select(Cluster)
        .where(Cluster.taxonomy_version_id == taxonomy.id)
        .limit(1)
    )
    original_name = cluster.current_name

    response = await api_client.post(
        f"/api/taxonomies/{taxonomy.id}/revisions",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={
            "operation": "rename",
            "cluster_ids": [str(cluster.id)],
            "new_name": f"{original_name}（人工复核）",
            "reason": "消除聚类名称歧义",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] != str(taxonomy.id)
    assert body["parent_version_id"] == str(taxonomy.id)
    assert body["status"] == "draft"
    await db_session.refresh(cluster)
    assert cluster.current_name == original_name
    revised_name = await db_session.scalar(
        select(Cluster.current_name).where(
            Cluster.taxonomy_version_id == body["id"],
            Cluster.current_name == f"{original_name}（人工复核）",
        )
    )
    assert revised_name == f"{original_name}（人工复核）"
