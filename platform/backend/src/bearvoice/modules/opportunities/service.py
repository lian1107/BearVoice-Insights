import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.enums import OpportunityStatus, ReviewDecisionType
from bearvoice.domain.models import (
    ActionItem,
    AuditEvent,
    Opportunity,
    OpportunityEvidence,
    OutcomeMeasurement,
    ReviewDecision,
    VoiceRecord,
)
from bearvoice.domain.schemas import OpportunityDraft


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True)
class OutcomeDraft:
    result: str
    limitations: str
    metric_name: str = "qualitative_outcome"
    baseline_value: float | None = None
    target_value: float | None = None
    actual_value: float | None = None


@dataclass(frozen=True)
class ReviewOpportunityCommand:
    opportunity_id: uuid.UUID
    decision: ReviewDecisionType
    actor_id: str
    reason: str


@dataclass(frozen=True)
class TransitionOpportunityCommand:
    opportunity_id: uuid.UUID
    target_status: OpportunityStatus
    actor_id: str
    reason: str


async def create_opportunity(
    session: AsyncSession,
    draft: OpportunityDraft,
) -> Opportunity:
    evidence_ids = tuple(dict.fromkeys(uuid.UUID(item) for item in draft.evidence_record_ids))
    existing_ids = set(
        await session.scalars(
            select(VoiceRecord.id).where(VoiceRecord.id.in_(evidence_ids))
        )
    )
    if existing_ids != set(evidence_ids):
        raise ValueError("机会证据包含不存在的原声")

    opportunity = Opportunity(
        id=uuid.uuid4(),
        opportunity_type=draft.opportunity_type,
        title=draft.title,
        problem=draft.title,
        safety_level=draft.safety_level,
        priority_override=(
            "safety"
            if draft.safety_level in {"high", "critical"}
            else None
        ),
        status=OpportunityStatus.PENDING_REVIEW.value,
    )
    session.add(opportunity)
    await session.flush()
    session.add_all(
        OpportunityEvidence(
            id=uuid.uuid4(),
            opportunity_id=opportunity.id,
            voice_record_id=record_id,
            evidence_direction="support",
            reviewed=False,
        )
        for record_id in evidence_ids
    )
    await session.flush()
    return opportunity


async def review_opportunity(
    session: AsyncSession,
    command: ReviewOpportunityCommand,
) -> Opportunity:
    if not command.reason.strip():
        raise ValueError("机会审核必须填写理由")
    opportunity = await session.scalar(
        select(Opportunity)
        .where(Opportunity.id == command.opportunity_id)
        .with_for_update()
    )
    if opportunity is None:
        raise LookupError(f"机会不存在：{command.opportunity_id}")
    if opportunity.status != OpportunityStatus.PENDING_REVIEW.value:
        raise InvalidTransition("只有待审核机会可以执行审核决定")

    evidence_count = int(
        await session.scalar(
            select(func.count(func.distinct(OpportunityEvidence.voice_record_id)))
            .select_from(OpportunityEvidence)
            .where(
                OpportunityEvidence.opportunity_id == opportunity.id,
                OpportunityEvidence.evidence_direction == "support",
            )
        )
        or 0
    )
    threshold = 5 if opportunity.opportunity_type == "new_product" else 3
    if command.decision == ReviewDecisionType.APPROVE and evidence_count < threshold:
        raise InvalidTransition(f"机会至少需要 {threshold} 条独立证据")

    before_status = opportunity.status
    if command.decision == ReviewDecisionType.APPROVE:
        opportunity.status = OpportunityStatus.ACCEPTED.value
        evidence = list(
            await session.scalars(
                select(OpportunityEvidence).where(
                    OpportunityEvidence.opportunity_id == opportunity.id
                )
            )
        )
        for item in evidence:
            item.reviewed = True
            item.reviewer_id = command.actor_id
    elif command.decision == ReviewDecisionType.REJECT:
        opportunity.status = OpportunityStatus.REJECTED.value
    else:
        opportunity.status = OpportunityStatus.DRAFT.value

    session.add(
        ReviewDecision(
            id=uuid.uuid4(),
            subject_type="opportunity",
            subject_id=opportunity.id,
            decision_type=command.decision.value,
            reviewer_id=command.actor_id,
            rationale=command.reason,
            evidence_snapshot={
                "independent_supporting_voice_records": evidence_count,
                "required": threshold,
            },
        )
    )
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=command.actor_id,
            action="opportunity.review",
            subject_type="opportunity",
            subject_id=opportunity.id,
            before_state={"status": before_status},
            after_state={"status": opportunity.status},
            reason=command.reason,
        )
    )
    await session.flush()
    return opportunity


async def transition_opportunity(
    session: AsyncSession,
    command: TransitionOpportunityCommand,
) -> Opportunity:
    if not command.reason.strip():
        raise ValueError("状态变化必须填写理由")
    opportunity = await session.scalar(
        select(Opportunity)
        .where(Opportunity.id == command.opportunity_id)
        .with_for_update()
    )
    if opportunity is None:
        raise LookupError(f"机会不存在：{command.opportunity_id}")
    current = OpportunityStatus(opportunity.status)
    if not current.can_transition_to(command.target_status):
        raise InvalidTransition(
            f"不允许从 {current.value} 跳转到 {command.target_status.value}"
        )
    opportunity.status = command.target_status.value
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=command.actor_id,
            action="opportunity.transition",
            subject_type="opportunity",
            subject_id=opportunity.id,
            before_state={"status": current.value},
            after_state={"status": command.target_status.value},
            reason=command.reason,
        )
    )
    await session.flush()
    return opportunity


async def create_action_item(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
    *,
    owner_id: str,
    objective: str,
    decision_rationale: str,
) -> ActionItem:
    if not owner_id.strip() or not objective.strip() or not decision_rationale.strip():
        raise ValueError("行动必须包含负责人、目标和决策依据")
    opportunity = await session.scalar(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id)
        .with_for_update()
    )
    if opportunity is None:
        raise LookupError(f"机会不存在：{opportunity_id}")
    if opportunity.status not in {
        OpportunityStatus.ACCEPTED.value,
        OpportunityStatus.VALIDATING.value,
        OpportunityStatus.PLANNED.value,
        OpportunityStatus.IN_PROGRESS.value,
    }:
        raise InvalidTransition("只有已接受的机会可以创建行动")

    action = ActionItem(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        owner_id=owner_id.strip(),
        objective=objective.strip(),
        status="planned",
        decision_rationale=decision_rationale.strip(),
    )
    session.add(action)
    await session.flush()
    return action


async def complete_action_item(
    session: AsyncSession,
    action_id: uuid.UUID,
    *,
    outcome: OutcomeDraft | None,
    actor_id: str,
) -> ActionItem:
    if (
        outcome is None
        or not outcome.result.strip()
        or not outcome.limitations.strip()
    ):
        raise InvalidTransition("完成行动前必须记录结果和限制")
    if not actor_id.strip():
        raise ValueError("完成行动必须记录操作人")

    action = await session.scalar(
        select(ActionItem).where(ActionItem.id == action_id).with_for_update()
    )
    if action is None:
        raise LookupError(f"行动不存在：{action_id}")
    if action.status == "completed":
        raise InvalidTransition("行动已完成，不能重复结项")

    before_status = action.status
    action.status = "completed"
    measurement = OutcomeMeasurement(
        id=uuid.uuid4(),
        action_item_id=action.id,
        metric_name=outcome.metric_name.strip() or "qualitative_outcome",
        baseline_value=outcome.baseline_value,
        target_value=outcome.target_value,
        actual_value=outcome.actual_value,
        conclusion=outcome.result.strip(),
        limitations=outcome.limitations.strip(),
    )
    session.add(measurement)
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id.strip(),
            action="action.complete",
            subject_type="action_item",
            subject_id=action.id,
            before_state={"status": before_status},
            after_state={
                "status": action.status,
                "outcome_measurement_id": str(measurement.id),
            },
            reason=outcome.result.strip(),
        )
    )
    await session.flush()
    return action
