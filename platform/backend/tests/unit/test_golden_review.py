from sqlalchemy import func, select

from bearvoice.domain.models import GoldenReview
from bearvoice.modules.evaluation.service import (
    GoldenLabel,
    adjudicate_golden_example,
    build_stratified_sample,
    submit_golden_review,
)
from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)


async def test_two_independent_matching_reviews_approve_golden_label(
    db_session,
    repo_root,
):
    run_id = await import_legacy_snapshot(
        db_session,
        load_legacy_snapshot(repo_root),
    )
    example = (
        await build_stratified_sample(db_session, run_id, size=100)
    )[0]
    label = GoldenLabel(
        expected_signals=({"type": "咨询"},),
        expected_objects=("壶盖",),
        evidence_ranges=({"start": 0, "end": 2},),
    )

    first = await submit_golden_review(
        db_session,
        example.id,
        reviewer_id="reviewer-a",
        label=label,
    )
    assert first.review_status == "pending_second_review"
    assert first.expected_signals == []

    approved = await submit_golden_review(
        db_session,
        example.id,
        reviewer_id="reviewer-b",
        label=label,
    )
    assert approved.review_status == "approved"
    assert approved.expected_signals == [{"type": "咨询"}]
    assert approved.reviewer_ids == ["reviewer-a", "reviewer-b"]


async def test_disagreement_requires_third_person_adjudication(db_session, repo_root):
    run_id = await import_legacy_snapshot(
        db_session,
        load_legacy_snapshot(repo_root),
    )
    example = (
        await build_stratified_sample(db_session, run_id, size=100)
    )[1]
    label_a = GoldenLabel(
        expected_signals=({"type": "缺陷"},),
        expected_objects=("玻璃壶体",),
        evidence_ranges=({"start": 0, "end": 4},),
    )
    label_b = GoldenLabel(
        expected_signals=({"type": "预期"},),
        expected_objects=("容量",),
        evidence_ranges=({"start": 0, "end": 4},),
    )

    await submit_golden_review(
        db_session,
        example.id,
        reviewer_id="reviewer-a",
        label=label_a,
    )
    disputed = await submit_golden_review(
        db_session,
        example.id,
        reviewer_id="reviewer-b",
        label=label_b,
    )
    assert disputed.review_status == "disputed"
    assert disputed.expected_signals == []

    approved = await adjudicate_golden_example(
        db_session,
        example.id,
        adjudicator_id="reviewer-c",
        label=label_a,
        reason="直接证据支持缺陷标签",
    )
    review_count = int(
        await db_session.scalar(select(func.count()).select_from(GoldenReview))
        or 0
    )
    assert approved.review_status == "approved"
    assert approved.dispute_status == "resolved"
    assert approved.reviewer_ids == ["reviewer-a", "reviewer-b", "reviewer-c"]
    assert review_count == 3
