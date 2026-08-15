from bearvoice.modules.evaluation.service import build_stratified_sample
from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)


async def test_sample_is_deterministic_and_covers_signals_clusters_and_hard_cases(
    db_session,
    repo_root,
):
    run_id = await import_legacy_snapshot(
        db_session,
        load_legacy_snapshot(repo_root),
    )

    first = await build_stratified_sample(
        db_session,
        run_id,
        size=100,
        seed=20260815,
    )
    second = await build_stratified_sample(
        db_session,
        run_id,
        size=100,
        seed=20260815,
    )

    assert [item.voice_record_id for item in first] == [
        item.voice_record_id for item in second
    ]
    assert len(first) == 100
    assert {item.primary_signal for item in first} == {
        "缺陷",
        "认知",
        "预期",
        "咨询",
    }
    assert len({item.cluster_id for item in first}) == 10
    assert any("multi_turn" in item.difficulty_tags for item in first)
    assert any("safety" in item.difficulty_tags for item in first)
    assert {item.review_status for item in first} == {"pending_human_review"}
    assert all(not item.expected_signals for item in first)
