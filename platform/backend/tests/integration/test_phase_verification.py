import uuid

import pytest

from bearvoice.domain.models import AnalysisRun
from bearvoice.modules.analysis.activities import (
    PhaseVerificationError,
    verify_and_record_analysis_phase,
)
from bearvoice.modules.analysis.workflow import PhaseActivityInput


def phase_input(run: AnalysisRun, phase: str) -> PhaseActivityInput:
    return PhaseActivityInput(
        run_id=str(run.id),
        phase=phase,
        input_hash=run.dataset_hash,
        idempotency_key=f"{run.id}:{phase}:{run.dataset_hash}",
        cache_only=True,
    )


async def test_phase_verification_is_idempotent(db_session):
    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_hash="a" * 64,
        code_version="test",
        parameters={},
        stage_status={},
    )
    db_session.add(run)
    await db_session.flush()

    first = await verify_and_record_analysis_phase(
        db_session,
        phase_input(run, "validate"),
        attempt=1,
    )
    replay = await verify_and_record_analysis_phase(
        db_session,
        phase_input(run, "validate"),
        attempt=2,
    )

    assert first["status"] == "completed"
    assert replay["replayed"] is True
    assert replay["attempt"] == 1


async def test_phase_verification_fails_closed_without_real_outputs(db_session):
    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_hash="b" * 64,
        code_version="test",
        parameters={},
        stage_status={},
    )
    db_session.add(run)
    await db_session.flush()
    await verify_and_record_analysis_phase(
        db_session,
        phase_input(run, "validate"),
        attempt=1,
    )

    with pytest.raises(PhaseVerificationError, match="真实抽取结果"):
        await verify_and_record_analysis_phase(
            db_session,
            phase_input(run, "privacy_gate"),
            attempt=1,
        )


async def test_phase_verification_rejects_input_hash_drift(db_session):
    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_hash="c" * 64,
        code_version="test",
        parameters={},
        stage_status={},
    )
    db_session.add(run)
    await db_session.flush()
    command = phase_input(run, "validate")
    command = PhaseActivityInput(
        **{**command.__dict__, "input_hash": "d" * 64}
    )

    with pytest.raises(PhaseVerificationError, match="输入哈希"):
        await verify_and_record_analysis_phase(
            db_session,
            command,
            attempt=1,
        )
