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

    refreshed = await api_client.get(
        f"/api/opportunities/{opportunity.id}",
        headers=headers,
    )
    execution = refreshed.json()["actions"][0]
    assert execution["owner"] == "quality-owner"
    assert execution["objective"] == opportunity.title
    assert execution["due_at"].startswith("2026-08-30")
    assert execution["status"] == "planned"
    assert execution["external_reference"] == "QA-2026-001"
    assert execution["audit_timeline"][0]["action"] == "action.create"


async def test_action_status_and_human_outcome_are_audited(
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
    review = await api_client.post(
        f"/api/opportunities/{opportunity.id}/reviews",
        headers=headers,
        json={
            "decision": "approve",
            "reason": "证据达到门槛，进入质量验证",
            "owner": "quality-owner",
            "collaborating_departments": ["研发", "客服"],
            "objective": "验证新壶体方案是否降低破裂反馈",
            "due_date": "2026-09-15",
            "external_reference": "QA-2026-002",
        },
    )
    assert review.status_code == 200
    action = review.json()["actions"][0]
    action_id = action["id"]
    assert action["collaborating_departments"] == ["研发", "客服"]

    premature = await api_client.post(
        f"/api/opportunities/{opportunity.id}/actions/{action_id}/transitions",
        headers=headers,
        json={"target_status": "completed", "reason": "直接结项"},
    )
    assert premature.status_code == 422
    assert "至少记录一个结果指标" in premature.json()["detail"]

    started = await api_client.post(
        f"/api/opportunities/{opportunity.id}/actions/{action_id}/transitions",
        headers=headers,
        json={"target_status": "in_progress", "reason": "样机测试已启动"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"

    illegal = await api_client.post(
        f"/api/opportunities/{opportunity.id}/actions/{action_id}/transitions",
        headers=headers,
        json={"target_status": "planned", "reason": "回退"},
    )
    assert illegal.status_code == 422
    assert "不允许" in illegal.json()["detail"]

    missing_definition = await api_client.post(
        f"/api/opportunities/{opportunity.id}/actions/{action_id}/outcomes",
        headers=headers,
        json={
            "metric_name": "每千订单破裂反馈数",
            "unit": "条/千订单",
            "baseline_value": 4.2,
            "target_value": 2.0,
            "actual_value": 2.8,
            "observation_window": "2026-09-01 至 2026-09-14",
            "conclusion": "观察窗口内指标下降",
            "limitations": "订单结构同期发生变化",
        },
    )
    assert missing_definition.status_code == 422

    outcome = await api_client.post(
        f"/api/opportunities/{opportunity.id}/actions/{action_id}/outcomes",
        headers=headers,
        json={
            "metric_name": "每千订单破裂反馈数",
            "metric_definition": "窗口内破裂相关有效反馈数 / 支付订单数 * 1000",
            "unit": "条/千订单",
            "baseline_value": 4.2,
            "target_value": 2.0,
            "actual_value": 2.8,
            "observation_window": "2026-09-01 至 2026-09-14",
            "conclusion": "观察窗口内指标下降，继续扩大样本",
            "limitations": "订单结构同期发生变化，不能证明由改版造成",
        },
    )
    assert outcome.status_code == 200
    assert outcome.json()["recorded_by"] == "reviewer-1"
    assert "不能证明因果" in outcome.json()["causality_notice"]

    completed = await api_client.post(
        f"/api/opportunities/{opportunity.id}/actions/{action_id}/transitions",
        headers=headers,
        json={"target_status": "completed", "reason": "阶段性验证完成"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["outcomes"][0]["metric_definition"].startswith(
        "窗口内破裂"
    )
    assert completed.json()["audit_timeline"][-1]["action"] == "action.transition"


async def test_action_write_requires_owner_and_product_scope(
    api_client,
    api_settings,
    reviewer_token,
    db_session,
    repo_root,
):
    await import_legacy_snapshot(db_session, load_legacy_snapshot(repo_root))
    opportunity = await db_session.scalar(select(Opportunity).limit(1))
    headers = {"Authorization": f"Bearer {reviewer_token}"}

    missing_owner = await api_client.post(
        f"/api/opportunities/{opportunity.id}/reviews",
        headers=headers,
        json={
            "decision": "approve",
            "reason": "进入验证",
            "objective": "验证产品改进",
        },
    )
    assert missing_owner.status_code == 422
    assert "必须指定负责人" in missing_owner.json()["detail"]

    outsider = issue_dev_token(
        api_settings,
        subject="other-product-reviewer",
        roles=("quality_reviewer",),
        product_lines=("其他产品",),
    )
    forbidden = await api_client.post(
        f"/api/opportunities/{opportunity.id}/actions",
        headers={"Authorization": f"Bearer {outsider}"},
        json={
            "owner": "pm-1",
            "objective": "不应创建",
            "decision_rationale": "越权测试",
        },
    )
    assert forbidden.status_code == 403


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
