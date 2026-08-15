from decimal import Decimal

import pytest
from sqlalchemy import func, select

from bearvoice.domain.models import ModelAnalysisJob, ModelBudgetCounter
from bearvoice.modules.analysis.semantic_jobs import (
    ModelBudgetExceeded,
    create_model_analysis_job,
)
from tests.integration.test_semantic_persistence import _seed_batch


def _job_settings():
    from bearvoice.config import Settings

    return Settings(
        deepseek_api_key="test-secret",
        model_endpoint_allowlist=("https://api.deepseek.com",),
        model_job_max_calls=10,
        model_daily_max_calls=10,
        model_job_budget_rmb=1,
        model_daily_budget_rmb=1,
        model_reserved_cost_per_call_rmb=0.1,
    )


async def test_model_job_reserves_budget_atomically_and_is_idempotent(db_session):
    batch, _ = await _seed_batch(db_session)

    job, reused = await create_model_analysis_job(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=_job_settings(),
    )
    repeated, repeated_reused = await create_model_analysis_job(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=_job_settings(),
    )

    counter = await db_session.scalar(select(ModelBudgetCounter))
    assert reused is False
    assert repeated_reused is True
    assert repeated.id == job.id
    assert job.status == "queued"
    assert job.requested_items == 2
    assert job.reserved_cost_amount == Decimal("0.6000")
    assert counter.reserved_calls == 6
    assert counter.reserved_cost_amount == Decimal("0.6000")
    assert await db_session.scalar(select(func.count()).select_from(ModelAnalysisJob)) == 1


async def test_model_job_rejects_before_queue_when_hard_budget_is_exceeded(
    db_session,
):
    batch, _ = await _seed_batch(db_session)
    settings = _job_settings().model_copy(update={"model_job_max_calls": 1})

    with pytest.raises(ModelBudgetExceeded, match="单任务上限"):
        await create_model_analysis_job(
            db_session,
            batch_id=batch.id,
            product="养生壶",
            provider="deepseek",
            actor_id="admin-1",
            settings=settings,
        )

    assert await db_session.scalar(select(func.count()).select_from(ModelAnalysisJob)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ModelBudgetCounter)) == 0
