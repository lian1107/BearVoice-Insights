import uuid

from bearvoice.domain.models import AnalysisRun
from bearvoice.modules.analysis.activities import (
    RunFailure,
    load_analysis_run,
    record_run_failure,
)


async def test_failed_run_records_redacted_machine_readable_diagnostics(
    db_session,
):
    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_hash="a" * 64,
        code_version="test",
        model_version=None,
        parameters={},
        stage_status={},
    )
    db_session.add(run)
    await db_session.flush()

    secret = "sk-" + "test-secret-value"
    await record_run_failure(
        db_session,
        RunFailure(
            run_id=run.id,
            phase="cluster",
            error_code="invalid_output",
            provider="cache-only",
            model=None,
            attempts=1,
            completed_phases=(
                "validate",
                "privacy_gate",
                "extract",
                "embed",
            ),
            message=f"聚类结构错误，token={secret}",
        ),
    )
    history = await load_analysis_run(db_session, run.id)

    assert history.phase == "cluster"
    assert history.error_code == "invalid_output"
    assert history.completed_phases == (
        "validate",
        "privacy_gate",
        "extract",
        "embed",
    )
    assert secret not in history.redacted_message
    assert "[REDACTED]" in history.redacted_message
