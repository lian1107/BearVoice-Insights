import hashlib
import json
import random
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.models import (
    AnalysisRun,
    AuditEvent,
    Cluster,
    ClusterMembership,
    GoldenExample,
    GoldenReview,
    EvaluationRun,
    ModelRelease,
    Signal,
    TaxonomyVersion,
    VoiceRecord,
)


SAFETY_PATTERN = re.compile(r"炸|爆|烫伤|漏电|起火|安全")


@dataclass(frozen=True)
class SampleCandidate:
    voice_record_id: uuid.UUID
    redacted_input: str
    primary_signal: str
    cluster_id: uuid.UUID
    difficulty_tags: tuple[str, ...]


@dataclass(frozen=True)
class GoldenLabel:
    expected_signals: tuple[dict[str, object], ...]
    expected_objects: tuple[str, ...]
    evidence_ranges: tuple[dict[str, int], ...]

    def snapshot(self) -> dict[str, object]:
        return {
            "expected_signals": list(self.expected_signals),
            "expected_objects": list(self.expected_objects),
            "evidence_ranges": list(self.evidence_ranges),
        }


@dataclass(frozen=True)
class GateMetrics:
    unresolved_evidence: int = 0
    privacy_leaks: int = 0
    duplicate_primary_memberships: int = 0
    safety_false_negatives: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "unresolved_evidence": self.unresolved_evidence,
            "privacy_leaks": self.privacy_leaks,
            "duplicate_primary_memberships": self.duplicate_primary_memberships,
            "safety_false_negatives": self.safety_false_negatives,
        }


BLOCKING_GATES = (
    ("unresolved_evidence", "unresolved_evidence"),
    ("privacy_leak", "privacy_leaks"),
    ("duplicate_membership", "duplicate_primary_memberships"),
    ("safety_regression", "safety_false_negatives"),
)


def _difficulty_tags(record: VoiceRecord, signal: Signal) -> tuple[str, ...]:
    tags: list[str] = []
    if SAFETY_PATTERN.search(record.normalized_text):
        tags.append("safety")
    if record.normalized_text.count("/") >= 2:
        tags.append("multi_turn")
    if signal.is_outlier or (
        signal.confidence is not None and signal.confidence < 0.6
    ):
        tags.append("boundary")
    if signal.signal_type == "咨询":
        tags.append("pure_inquiry")
    return tuple(tags)


def choose_stratified_rows(
    rows: list[SampleCandidate],
    *,
    size: int,
    seed: int,
) -> list[SampleCandidate]:
    if size <= 0:
        raise ValueError("样本数必须大于 0")
    if len(rows) < size:
        raise ValueError(f"可用原声仅 {len(rows)} 条，不足以抽取 {size} 条")

    ordered = sorted(rows, key=lambda row: str(row.voice_record_id))
    random.Random(seed).shuffle(ordered)
    selected: list[SampleCandidate] = []
    selected_ids: set[uuid.UUID] = set()

    def take_first(predicate) -> None:
        for row in ordered:
            if row.voice_record_id not in selected_ids and predicate(row):
                selected.append(row)
                selected_ids.add(row.voice_record_id)
                return

    take_first(lambda row: "safety" in row.difficulty_tags)
    take_first(lambda row: "multi_turn" in row.difficulty_tags)
    for signal_type in sorted({row.primary_signal for row in ordered}):
        take_first(lambda row, value=signal_type: row.primary_signal == value)
    for cluster_id in sorted({row.cluster_id for row in ordered}, key=str):
        take_first(lambda row, value=cluster_id: row.cluster_id == value)

    for row in ordered:
        if len(selected) >= size:
            break
        if row.voice_record_id not in selected_ids:
            selected.append(row)
            selected_ids.add(row.voice_record_id)
    return selected


async def build_stratified_sample(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    size: int = 100,
    seed: int = 20260815,
) -> list[GoldenExample]:
    run = await session.get(AnalysisRun, run_id)
    if run is None:
        raise LookupError(f"分析运行不存在：{run_id}")

    existing = list(
        await session.scalars(
            select(GoldenExample)
            .where(
                GoldenExample.analysis_run_id == run_id,
                GoldenExample.sampling_seed == seed,
            )
            .order_by(GoldenExample.sample_order)
        )
    )
    if existing:
        if len(existing) != size:
            raise ValueError(
                f"种子 {seed} 已生成 {len(existing)} 条样本，不能改为 {size} 条"
            )
        return existing

    rows = (
        await session.execute(
            select(VoiceRecord, Signal, Cluster, TaxonomyVersion)
            .join(Signal, Signal.voice_record_id == VoiceRecord.id)
            .join(ClusterMembership, ClusterMembership.signal_id == Signal.id)
            .join(Cluster, Cluster.id == ClusterMembership.cluster_id)
            .join(
                TaxonomyVersion,
                TaxonomyVersion.id == ClusterMembership.taxonomy_version_id,
            )
            .where(Signal.analysis_run_id == run_id)
            .order_by(
                VoiceRecord.id,
                TaxonomyVersion.created_at.desc(),
                TaxonomyVersion.id.desc(),
            )
        )
    ).all()
    latest_by_voice: dict[uuid.UUID, SampleCandidate] = {}
    for record, signal, cluster, _taxonomy in rows:
        latest_by_voice.setdefault(
            record.id,
            SampleCandidate(
                voice_record_id=record.id,
                redacted_input=record.normalized_text,
                primary_signal=signal.signal_type,
                cluster_id=cluster.id,
                difficulty_tags=_difficulty_tags(record, signal),
            ),
        )

    selected = choose_stratified_rows(
        list(latest_by_voice.values()),
        size=size,
        seed=seed,
    )
    examples = [
        GoldenExample(
            id=uuid.uuid4(),
            analysis_run_id=run_id,
            voice_record_id=row.voice_record_id,
            redacted_input=row.redacted_input,
            primary_signal=row.primary_signal,
            cluster_id=row.cluster_id,
            sampling_seed=seed,
            sample_order=sample_order,
            expected_signals=[],
            expected_objects=[],
            evidence_ranges=[],
            difficulty_tags=list(row.difficulty_tags),
            review_status="pending_human_review",
            reviewer_ids=[],
        )
        for sample_order, row in enumerate(selected)
    ]
    session.add_all(examples)
    await session.flush()
    return examples


def _validate_label(example: GoldenExample, label: GoldenLabel) -> None:
    if not label.expected_signals:
        raise ValueError("黄金样本必须标注至少一类信号")
    text_length = len(example.redacted_input)
    for evidence_range in label.evidence_ranges:
        start = evidence_range.get("start")
        end = evidence_range.get("end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > text_length
        ):
            raise ValueError("证据范围无法解析回脱敏原声")


def _apply_label(example: GoldenExample, snapshot: dict[str, object]) -> None:
    example.expected_signals = list(snapshot["expected_signals"])
    example.expected_objects = list(snapshot["expected_objects"])
    example.evidence_ranges = list(snapshot["evidence_ranges"])


async def submit_golden_review(
    session: AsyncSession,
    example_id: uuid.UUID,
    *,
    reviewer_id: str,
    label: GoldenLabel,
) -> GoldenExample:
    if not reviewer_id.strip():
        raise ValueError("审核人不能为空")
    example = await session.scalar(
        select(GoldenExample)
        .where(GoldenExample.id == example_id)
        .with_for_update()
    )
    if example is None:
        raise LookupError(f"黄金样本不存在：{example_id}")
    if example.review_status not in {
        "pending_human_review",
        "pending_second_review",
    }:
        raise ValueError("该样本不接受新的独立审核")
    _validate_label(example, label)

    reviews = list(
        await session.scalars(
            select(GoldenReview)
            .where(
                GoldenReview.golden_example_id == example.id,
                GoldenReview.review_role == "independent",
            )
            .order_by(GoldenReview.created_at, GoldenReview.id)
        )
    )
    if reviewer_id in {review.reviewer_id for review in reviews}:
        raise ValueError("同一审核人不能重复提交")
    if len(reviews) >= 2:
        raise ValueError("两份独立审核已齐备")

    snapshot = label.snapshot()
    session.add(
        GoldenReview(
            id=uuid.uuid4(),
            golden_example_id=example.id,
            reviewer_id=reviewer_id,
            review_role="independent",
            label_snapshot=snapshot,
        )
    )
    example.reviewer_ids = [*example.reviewer_ids, reviewer_id]
    if not reviews:
        example.review_status = "pending_second_review"
    elif reviews[0].label_snapshot == snapshot:
        _apply_label(example, snapshot)
        example.review_status = "approved"
        example.dispute_status = None
        session.add(
            AuditEvent(
                id=uuid.uuid4(),
                actor_id=reviewer_id,
                action="golden_example.approved",
                subject_type="golden_example",
                subject_id=example.id,
                after_state={"review_status": "approved"},
                reason="两名审核者标注一致",
            )
        )
    else:
        example.review_status = "disputed"
        example.dispute_status = "pending_adjudication"
        session.add(
            AuditEvent(
                id=uuid.uuid4(),
                actor_id=reviewer_id,
                action="golden_example.disputed",
                subject_type="golden_example",
                subject_id=example.id,
                after_state={"review_status": "disputed"},
                reason="两名审核者标注不一致",
            )
        )
    await session.flush()
    return example


async def adjudicate_golden_example(
    session: AsyncSession,
    example_id: uuid.UUID,
    *,
    adjudicator_id: str,
    label: GoldenLabel,
    reason: str,
) -> GoldenExample:
    if not reason.strip():
        raise ValueError("仲裁必须填写理由")
    example = await session.scalar(
        select(GoldenExample)
        .where(GoldenExample.id == example_id)
        .with_for_update()
    )
    if example is None:
        raise LookupError(f"黄金样本不存在：{example_id}")
    if example.review_status != "disputed":
        raise ValueError("只有争议样本可以仲裁")
    if adjudicator_id in example.reviewer_ids:
        raise ValueError("仲裁人必须独立于前两名审核者")
    _validate_label(example, label)
    snapshot = label.snapshot()
    session.add(
        GoldenReview(
            id=uuid.uuid4(),
            golden_example_id=example.id,
            reviewer_id=adjudicator_id,
            review_role="adjudicator",
            label_snapshot=snapshot,
        )
    )
    _apply_label(example, snapshot)
    example.reviewer_ids = [*example.reviewer_ids, adjudicator_id]
    example.review_status = "approved"
    example.dispute_status = "resolved"
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=adjudicator_id,
            action="golden_example.adjudicated",
            subject_type="golden_example",
            subject_id=example.id,
            after_state={"review_status": "approved"},
            reason=reason.strip(),
        )
    )
    await session.flush()
    return example


async def evaluate_release(
    session: AsyncSession,
    *,
    candidate: str,
    golden_set: list[GoldenExample],
    metrics: GateMetrics,
    prompt_version: str = "prompt-v1",
) -> EvaluationRun:
    if not golden_set or any(
        example.review_status != "approved" for example in golden_set
    ):
        raise ValueError("只能使用已经双人审核或仲裁的黄金样本")
    example_ids = sorted(str(example.id) for example in golden_set)
    dataset_hash = hashlib.sha256(
        json.dumps(example_ids, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    evaluation = EvaluationRun(
        id=uuid.uuid4(),
        model_version=candidate,
        prompt_version=prompt_version,
        dataset_hash=dataset_hash,
        metrics=metrics.as_dict(),
        slice_metrics={},
        status="evaluated",
    )
    session.add(evaluation)
    await session.flush()
    return evaluation


def _gate_results(metrics: dict[str, object]) -> tuple[dict[str, str], str | None]:
    results: dict[str, str] = {}
    first_failure: str | None = None
    for reason_code, metric_name in BLOCKING_GATES:
        blocked = int(metrics.get(metric_name, 0) or 0) > 0
        results[reason_code] = "blocked" if blocked else "passed"
        if blocked and first_failure is None:
            first_failure = reason_code
    return results, first_failure


async def decide_release(
    session: AsyncSession,
    evaluation_id: uuid.UUID,
    *,
    actor_id: str,
) -> ModelRelease:
    evaluation = await session.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.id == evaluation_id)
        .with_for_update()
    )
    if evaluation is None:
        raise LookupError(f"评测运行不存在：{evaluation_id}")
    existing = await session.scalar(
        select(ModelRelease).where(
            ModelRelease.evaluation_run_id == evaluation_id
        )
    )
    if existing is not None:
        raise ValueError("该评测运行已经做出发布决定")
    gate_results, failure = _gate_results(evaluation.metrics)
    status = "blocked" if failure else "active"
    if status == "active":
        active_releases = list(
            await session.scalars(
                select(ModelRelease)
                .where(ModelRelease.status == "active")
                .with_for_update()
            )
        )
        for active_release in active_releases:
            active_release.status = "superseded"

    release = ModelRelease(
        id=uuid.uuid4(),
        model_version=evaluation.model_version,
        prompt_version=evaluation.prompt_version,
        evaluation_run_id=evaluation.id,
        status=status,
        reason_code=failure,
        gate_results=gate_results,
        approved_by=actor_id if status == "active" else None,
        released_at=datetime.now(UTC) if status == "active" else None,
    )
    evaluation.status = "blocked" if failure else "released"
    session.add(release)
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=(
                "model_release.blocked"
                if failure
                else "model_release.activated"
            ),
            subject_type="model_release",
            subject_id=release.id,
            after_state={"status": status, "reason_code": failure},
            reason=failure or "所有确定性发布门禁通过",
        )
    )
    await session.flush()
    return release


async def rollback_release(
    session: AsyncSession,
    *,
    target_release_id: uuid.UUID,
    actor_id: str,
    reason: str,
) -> ModelRelease:
    if not reason.strip():
        raise ValueError("回滚必须填写理由")
    target = await session.scalar(
        select(ModelRelease)
        .where(ModelRelease.id == target_release_id)
        .with_for_update()
    )
    if target is None:
        raise LookupError(f"目标发布不存在：{target_release_id}")
    if target.status not in {"superseded", "rolled_back"} or any(
        value != "passed" for value in target.gate_results.values()
    ):
        raise ValueError("只能回到曾通过全部门禁的历史版本")
    current = await session.scalar(
        select(ModelRelease)
        .where(ModelRelease.status == "active")
        .with_for_update()
    )
    if current is None:
        raise ValueError("当前没有可回滚的活跃版本")

    current.status = "rolled_back"
    target.status = "active"
    target.approved_by = actor_id
    target.released_at = datetime.now(UTC)
    target.rollback_of_id = current.id
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action="model_release.rolled_back",
            subject_type="model_release",
            subject_id=target.id,
            before_state={"active_release_id": str(current.id)},
            after_state={"active_release_id": str(target.id)},
            reason=reason.strip(),
        )
    )
    await session.flush()
    return target
