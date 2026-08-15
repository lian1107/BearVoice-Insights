from sqlalchemy import select

from bearvoice.domain.enums import ReviewDecisionType
from bearvoice.domain.models import AuditEvent, Opportunity
from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)
from bearvoice.modules.opportunities.service import (
    OutcomeDraft,
    ReviewOpportunityCommand,
    complete_action_item,
    create_action_item,
    review_opportunity,
)
from bearvoice.modules.reporting.queries import get_dashboard_snapshot


async def test_kettle_vertical_slice_without_model_calls(db_session, repo_root):
    legacy = load_legacy_snapshot(repo_root)
    run_id = await import_legacy_snapshot(db_session, legacy)
    assert legacy.extract_cache_count == 10
    assert run_id
    model_calls = 0

    dashboard = await get_dashboard_snapshot(
        db_session,
        product="养生壶",
    )
    assert (dashboard.total_voices, dashboard.actionable_voices) == (370, 254)

    opportunity = await db_session.scalar(
        select(Opportunity).where(Opportunity.priority_override == "safety")
    )
    reviewed = await review_opportunity(
        db_session,
        ReviewOpportunityCommand(
            opportunity_id=opportunity.id,
            decision=ReviewDecisionType.APPROVE,
            actor_id="quality-reviewer-1",
            reason="涉及安全风险，转品控复核",
        ),
    )

    assert reviewed.status == "accepted"
    audit = await db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.subject_type == "opportunity",
            AuditEvent.subject_id == reviewed.id,
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit.action == "opportunity.review"
    assert audit.actor_id == "quality-reviewer-1"

    action = await create_action_item(
        db_session,
        reviewed.id,
        owner_id="quality-owner-1",
        objective="复核玻璃壶体批次并完成冷热冲击测试",
        decision_rationale="安全风险优先",
    )
    completed = await complete_action_item(
        db_session,
        action.id,
        actor_id="quality-owner-1",
        outcome=OutcomeDraft(
            result="完成批次复核并隔离异常批次",
            limitations="仍需更长周期售后数据验证",
        ),
    )
    assert completed.status == "completed"
    assert model_calls == 0
