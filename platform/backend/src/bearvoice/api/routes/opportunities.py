import uuid
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import ActionItemStatus, Permission, ReviewDecisionType
from bearvoice.domain.models import (
    ActionItem,
    AuditEvent,
    Opportunity,
    OpportunityEvidence,
    OutcomeMeasurement,
)
from bearvoice.modules.opportunities.service import (
    InvalidTransition,
    OutcomeDraft,
    ReviewOpportunityCommand,
    create_action_item,
    create_outcome_measurement,
    review_opportunity,
    transition_action_item,
)
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    require_permission,
)


router = APIRouter(tags=["opportunities"])


class OpportunityReviewBody(BaseModel):
    decision: ReviewDecisionType
    reason: str
    owner: str | None = None
    collaborating_departments: list[str] = Field(default_factory=list)
    objective: str | None = None
    due_date: date | None = None
    external_reference: str | None = None


class ActionCreateBody(BaseModel):
    owner: str
    collaborating_departments: list[str] = Field(default_factory=list)
    objective: str
    due_date: date | None = None
    external_reference: str | None = None
    decision_rationale: str


class ActionTransitionBody(BaseModel):
    target_status: ActionItemStatus
    reason: str


class OutcomeCreateBody(BaseModel):
    metric_name: str
    metric_definition: str
    unit: str
    baseline_value: float | None = None
    target_value: float | None = None
    actual_value: float | None = None
    observation_window: str
    conclusion: str
    limitations: str


def _outcome_summary(item: OutcomeMeasurement) -> dict[str, object]:
    return {
        "id": item.id,
        "metric_name": item.metric_name,
        "metric_definition": item.metric_definition,
        "unit": item.unit,
        "baseline_value": item.baseline_value,
        "target_value": item.target_value,
        "actual_value": item.actual_value,
        "observation_window": item.observation_window,
        "measured_at": item.measured_at,
        "conclusion": item.conclusion,
        "limitations": item.limitations,
        "recorded_by": item.recorded_by,
        "causality_notice": "该结果由人工录入，只记录同期变化，不能证明因果。",
    }


def _action_summary(
    item: ActionItem,
    outcomes: list[OutcomeMeasurement] | None = None,
) -> dict[str, object]:
    return {
        "id": item.id,
        "owner": item.owner_id,
        "collaborating_departments": item.collaborating_departments,
        "objective": item.objective,
        "due_at": item.due_at,
        "status": item.status,
        "external_reference": item.external_system_ref,
        "decision_rationale": item.decision_rationale,
        "outcomes": [_outcome_summary(outcome) for outcome in (outcomes or [])],
    }


def _summary(
    item: Opportunity,
    evidence_count: int,
    actions: list[ActionItem] | None = None,
) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "status": item.status,
        "opportunity_type": item.opportunity_type,
        "safety_level": item.safety_level,
        "priority_override": item.priority_override,
        "severity": item.severity,
        "impact_scope": item.impact_scope,
        "evidence_count": evidence_count,
        "actions": [_action_summary(action) for action in (actions or [])],
    }


async def _get_scoped_opportunity(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
    principal: Principal,
) -> Opportunity:
    item = await session.get(Opportunity, opportunity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="机会不存在或无权访问")
    assert_product_scope(item.product or "", principal)
    return item


async def _audit_timeline(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
) -> list[dict[str, object]]:
    entries = list(
        await session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.subject_type == "opportunity",
                AuditEvent.subject_id == opportunity_id,
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    return [
        {
            "id": entry.id,
            "action": entry.action,
            "actor_id": entry.actor_id,
            "reason": entry.reason or "",
            "created_at": entry.created_at,
        }
        for entry in entries
    ]


async def _get_scoped_action(
    session: AsyncSession,
    opportunity: Opportunity,
    action_id: uuid.UUID,
) -> ActionItem:
    action = await session.get(ActionItem, action_id)
    if action is None or action.opportunity_id != opportunity.id:
        raise HTTPException(status_code=404, detail="行动不存在或无权访问")
    return action


async def _load_actions(
    session: AsyncSession,
    opportunity_ids: list[uuid.UUID],
    *,
    include_outcomes: bool = False,
) -> dict[uuid.UUID, list[dict[str, object]]]:
    if not opportunity_ids:
        return {}
    actions = list(
        await session.scalars(
            select(ActionItem)
            .where(ActionItem.opportunity_id.in_(opportunity_ids))
            .order_by(ActionItem.created_at, ActionItem.id)
        )
    )
    outcomes_by_action: dict[uuid.UUID, list[OutcomeMeasurement]] = {}
    if include_outcomes and actions:
        outcomes = list(
            await session.scalars(
                select(OutcomeMeasurement)
                .where(
                    OutcomeMeasurement.action_item_id.in_([item.id for item in actions])
                )
                .order_by(OutcomeMeasurement.created_at, OutcomeMeasurement.id)
            )
        )
        for outcome in outcomes:
            outcomes_by_action.setdefault(outcome.action_item_id, []).append(outcome)
    grouped: dict[uuid.UUID, list[dict[str, object]]] = {}
    for action in actions:
        summary = _action_summary(action, outcomes_by_action.get(action.id, []))
        if include_outcomes:
            summary["audit_timeline"] = await _action_audit_timeline(
                session, action.id
            )
        grouped.setdefault(action.opportunity_id, []).append(summary)
    return grouped


async def _action_audit_timeline(
    session: AsyncSession,
    action_id: uuid.UUID,
) -> list[dict[str, object]]:
    entries = list(
        await session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.subject_type == "action_item",
                AuditEvent.subject_id == action_id,
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    return [
        {
            "id": entry.id,
            "action": entry.action,
            "actor_id": entry.actor_id,
            "reason": entry.reason or "",
            "created_at": entry.created_at,
        }
        for entry in entries
    ]


@router.get("/opportunities")
async def opportunities(
    product: str,
    principal: Principal = Depends(require_permission(Permission.READ_VOICE)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    assert_product_scope(product, principal)
    rows = (
        await session.execute(
            select(
                Opportunity,
                func.count(distinct(OpportunityEvidence.voice_record_id)),
            )
            .outerjoin(
                OpportunityEvidence,
                OpportunityEvidence.opportunity_id == Opportunity.id,
            )
            .where(Opportunity.product == product)
            .group_by(Opportunity.id)
            .order_by(Opportunity.created_at)
        )
    ).all()
    actions = await _load_actions(session, [item.id for item, _ in rows])
    return [
        {
            **_summary(item, int(evidence_count)),
            "actions": actions.get(item.id, []),
        }
        for item, evidence_count in rows
    ]


@router.get("/opportunities/{opportunity_id}")
async def opportunity_detail(
    opportunity_id: uuid.UUID,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_OPPORTUNITY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    item = await _get_scoped_opportunity(session, opportunity_id, principal)
    evidence_ids = list(
        await session.scalars(
            select(OpportunityEvidence.signal_id)
            .where(
                OpportunityEvidence.opportunity_id == item.id,
                OpportunityEvidence.signal_id.is_not(None),
            )
            .order_by(OpportunityEvidence.created_at, OpportunityEvidence.id)
        )
    )
    body = _summary(item, len(evidence_ids))
    actions = await _load_actions(session, [item.id], include_outcomes=True)
    body.update(
        {
            "problem": item.problem,
            "evidence_ids": evidence_ids,
            "audit_timeline": await _audit_timeline(session, item.id),
            "actions": actions.get(item.id, []),
        }
    )
    return body


@router.post("/opportunities/{opportunity_id}/reviews")
async def submit_opportunity_review(
    opportunity_id: uuid.UUID,
    body: OpportunityReviewBody,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_OPPORTUNITY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    item = await _get_scoped_opportunity(session, opportunity_id, principal)
    if (
        body.due_date
        or body.external_reference
        or body.objective
        or body.collaborating_departments
    ) and not (body.owner or "").strip():
        raise HTTPException(
            status_code=422,
            detail="填写行动目标、协作部门、计划日期或外部编号时必须指定负责人",
        )
    try:
        reviewed = await review_opportunity(
            session,
            ReviewOpportunityCommand(
                opportunity_id=item.id,
                decision=body.decision,
                actor_id=principal.subject,
                reason=body.reason,
            ),
        )
        if body.decision == ReviewDecisionType.APPROVE and body.owner:
            await create_action_item(
                session,
                reviewed.id,
                owner_id=body.owner,
                objective=(body.objective or reviewed.title),
                decision_rationale=body.reason,
                actor_id=principal.subject,
                collaborating_departments=tuple(body.collaborating_departments),
                due_at=(
                    datetime.combine(body.due_date, time.min, tzinfo=UTC)
                    if body.due_date
                    else None
                ),
                external_system_ref=body.external_reference,
            )
        await session.flush()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidTransition, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    timeline = await _audit_timeline(session, reviewed.id)
    actions = await _load_actions(session, [reviewed.id], include_outcomes=True)
    return {
        "status": reviewed.status,
        "audit": timeline[-1],
        "actions": actions.get(reviewed.id, []),
    }


@router.post("/opportunities/{opportunity_id}/actions")
async def add_action(
    opportunity_id: uuid.UUID,
    body: ActionCreateBody,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_OPPORTUNITY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    opportunity = await _get_scoped_opportunity(session, opportunity_id, principal)
    try:
        action = await create_action_item(
            session,
            opportunity.id,
            owner_id=body.owner,
            collaborating_departments=tuple(body.collaborating_departments),
            objective=body.objective,
            due_at=(
                datetime.combine(body.due_date, time.min, tzinfo=UTC)
                if body.due_date
                else None
            ),
            external_system_ref=body.external_reference,
            decision_rationale=body.decision_rationale,
            actor_id=principal.subject,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidTransition, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        **_action_summary(action),
        "audit_timeline": await _action_audit_timeline(session, action.id),
    }


@router.post("/opportunities/{opportunity_id}/actions/{action_id}/transitions")
async def transition_action(
    opportunity_id: uuid.UUID,
    action_id: uuid.UUID,
    body: ActionTransitionBody,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_OPPORTUNITY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    opportunity = await _get_scoped_opportunity(session, opportunity_id, principal)
    await _get_scoped_action(session, opportunity, action_id)
    try:
        action = await transition_action_item(
            session,
            action_id,
            target_status=body.target_status,
            actor_id=principal.subject,
            reason=body.reason,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidTransition, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    outcomes = list(
        await session.scalars(
            select(OutcomeMeasurement).where(
                OutcomeMeasurement.action_item_id == action.id
            )
        )
    )
    return {
        **_action_summary(action, outcomes),
        "audit_timeline": await _action_audit_timeline(session, action.id),
    }


@router.post("/opportunities/{opportunity_id}/actions/{action_id}/outcomes")
async def add_outcome(
    opportunity_id: uuid.UUID,
    action_id: uuid.UUID,
    body: OutcomeCreateBody,
    principal: Principal = Depends(
        require_permission(Permission.REVIEW_OPPORTUNITY)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    opportunity = await _get_scoped_opportunity(session, opportunity_id, principal)
    await _get_scoped_action(session, opportunity, action_id)
    try:
        outcome = await create_outcome_measurement(
            session,
            action_id,
            outcome=OutcomeDraft(
                result=body.conclusion,
                limitations=body.limitations,
                metric_name=body.metric_name,
                metric_definition=body.metric_definition,
                unit=body.unit,
                baseline_value=body.baseline_value,
                target_value=body.target_value,
                actual_value=body.actual_value,
                observation_window=body.observation_window,
            ),
            actor_id=principal.subject,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidTransition, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _outcome_summary(outcome)
