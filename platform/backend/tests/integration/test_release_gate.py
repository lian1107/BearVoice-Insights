import uuid

from sqlalchemy import func, select

from bearvoice.domain.models import AuditEvent, EvaluationRun, ModelRelease
from bearvoice.modules.evaluation.service import (
    decide_release,
    rollback_release,
)


def evaluation(metrics: dict[str, int], version: str) -> EvaluationRun:
    return EvaluationRun(
        id=uuid.uuid4(),
        model_version=version,
        prompt_version="prompt-v1",
        dataset_hash="a" * 64,
        metrics=metrics,
        slice_metrics={},
        status="evaluated",
    )


async def test_model_release_is_blocked_when_safety_regresses(db_session):
    run = evaluation(
        {
            "unresolved_evidence": 0,
            "privacy_leaks": 0,
            "duplicate_primary_memberships": 0,
            "safety_false_negatives": 1,
        },
        "model-v2",
    )
    db_session.add(run)
    await db_session.flush()

    release = await decide_release(
        db_session,
        run.id,
        actor_id="model-reviewer",
    )

    assert release.status == "blocked"
    assert release.reason_code == "safety_regression"
    assert release.gate_results["safety_regression"] == "blocked"


async def test_rollback_reactivates_previous_passed_release_and_is_audited(
    db_session,
):
    previous_evaluation = evaluation(
        {
            "unresolved_evidence": 0,
            "privacy_leaks": 0,
            "duplicate_primary_memberships": 0,
            "safety_false_negatives": 0,
        },
        "model-v1",
    )
    current_evaluation = evaluation(previous_evaluation.metrics, "model-v2")
    db_session.add_all([previous_evaluation, current_evaluation])
    await db_session.flush()
    previous = await decide_release(
        db_session,
        previous_evaluation.id,
        actor_id="reviewer-a",
    )
    current = await decide_release(
        db_session,
        current_evaluation.id,
        actor_id="reviewer-b",
    )
    assert previous.status == "superseded"
    assert current.status == "active"

    rolled_back = await rollback_release(
        db_session,
        target_release_id=previous.id,
        actor_id="model-reviewer",
        reason="线上安全样本退化",
    )
    audit_count = int(
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "model_release.rolled_back")
        )
        or 0
    )

    assert rolled_back.status == "active"
    assert current.status == "rolled_back"
    assert audit_count == 1
    assert int(
        await db_session.scalar(
            select(func.count())
            .select_from(ModelRelease)
            .where(ModelRelease.status == "active")
        )
        or 0
    ) == 1
