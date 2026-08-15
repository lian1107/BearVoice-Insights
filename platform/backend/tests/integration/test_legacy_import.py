from sqlalchemy import func, select

from bearvoice.domain.models import AnalysisRun, Cluster, Opportunity, Signal, VoiceRecord
from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)


async def count_rows(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_imports_verified_kettle_baseline_once(db_session, repo_root):
    snapshot = load_legacy_snapshot(repo_root)
    run_id = await import_legacy_snapshot(db_session, snapshot)
    repeated_run_id = await import_legacy_snapshot(db_session, snapshot)

    assert repeated_run_id == run_id
    assert snapshot.extract_cache_count == 10
    assert snapshot.actionable_signal_count == 254
    assert await count_rows(db_session, VoiceRecord) == 370
    assert await count_rows(db_session, Signal) == 370
    assert await count_rows(db_session, Cluster) == 10
    assert await count_rows(db_session, Opportunity) == 9
    assert await count_rows(db_session, AnalysisRun) == 1
