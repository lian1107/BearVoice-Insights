import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import (
    EvaluationRun,
    GoldenExample,
    GoldenReview,
    ModelRelease,
)
from bearvoice.modules.evaluation.service import GoldenLabel, submit_golden_review
from bearvoice.security.auth import Principal, require_permission


router = APIRouter(tags=["evaluation"])


class GoldenReviewBody(BaseModel):
    signal: str
    object_name: str = ""
    evidence_text: str


def _label_text(snapshot: dict[str, object]) -> str:
    signals = snapshot.get("expected_signals", [])
    objects = snapshot.get("expected_objects", [])
    signal_names = [
        str(item.get("signal_type") or item.get("type") or "")
        for item in signals
        if isinstance(item, dict)
    ]
    parts = [value for value in ["、".join(signal_names), "、".join(map(str, objects))] if value]
    return " / ".join(parts) or "未填写"


async def _serialize_example(
    session: AsyncSession,
    example: GoldenExample,
) -> dict[str, object]:
    reviews = list(
        await session.scalars(
            select(GoldenReview)
            .where(GoldenReview.golden_example_id == example.id)
            .order_by(GoldenReview.created_at, GoldenReview.id)
        )
    )
    independent = [item for item in reviews if item.review_role == "independent"]
    adjudication = next(
        (item for item in reversed(reviews) if item.review_role == "adjudication"),
        None,
    )
    return {
        "id": example.id,
        "redacted_input": example.redacted_input,
        "model_suggestion": (
            f"分层标签：{example.primary_signal}（仅用于抽样，不是黄金答案）"
        ),
        "reviewer_one": (
            _label_text(independent[0].label_snapshot) if independent else None
        ),
        "reviewer_two": (
            _label_text(independent[1].label_snapshot)
            if len(independent) > 1
            else None
        ),
        "adjudication": (
            _label_text(adjudication.label_snapshot) if adjudication else None
        ),
        "review_status": example.review_status,
        "difficulty_tags": list(example.difficulty_tags),
    }


@router.get("/evaluations/summary")
async def evaluation_summary(
    _principal: Principal = Depends(
        require_permission(Permission.MANAGE_EVALUATION)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    golden_rows = (
        await session.execute(
            select(GoldenExample.review_status, func.count(GoldenExample.id))
            .group_by(GoldenExample.review_status)
        )
    ).all()
    active_release = await session.scalar(
        select(ModelRelease.model_version).where(ModelRelease.status == "active")
    )
    evaluation_count = int(
        await session.scalar(select(func.count()).select_from(EvaluationRun)) or 0
    )
    return {
        "golden_examples": {status: int(count) for status, count in golden_rows},
        "evaluation_count": evaluation_count,
        "active_model_version": active_release,
    }


@router.get("/evaluations/golden-examples")
async def golden_review_queue(
    _principal: Principal = Depends(
        require_permission(Permission.MANAGE_EVALUATION)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    examples = list(
        await session.scalars(
            select(GoldenExample)
            .order_by(GoldenExample.sample_order, GoldenExample.id)
            .limit(100)
        )
    )
    return [await _serialize_example(session, item) for item in examples]


@router.post("/evaluations/golden-examples/{example_id}/reviews")
async def review_golden_example(
    example_id: uuid.UUID,
    body: GoldenReviewBody,
    principal: Principal = Depends(
        require_permission(Permission.MANAGE_EVALUATION)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    example = await session.get(GoldenExample, example_id)
    if example is None:
        raise HTTPException(status_code=404, detail="黄金样本不存在")
    start = example.redacted_input.find(body.evidence_text)
    if start < 0:
        raise HTTPException(status_code=422, detail="证据片段无法定位到脱敏原声")
    try:
        reviewed = await submit_golden_review(
            session,
            example.id,
            reviewer_id=principal.subject,
            label=GoldenLabel(
                expected_signals=({"signal_type": body.signal.strip()},),
                expected_objects=(body.object_name.strip(),)
                if body.object_name.strip()
                else (),
                evidence_ranges=(
                    {"start": start, "end": start + len(body.evidence_text)},
                ),
            ),
        )
        await session.flush()
    except (LookupError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return await _serialize_example(session, reviewed)
