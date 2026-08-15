import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from bearvoice.db import Base
from bearvoice.domain.enums import OpportunityStatus


class IdTimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Source(IdTimestampMixin, Base):
    __tablename__ = "sources"

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    connection_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="configured"
    )
    authorization_scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class IngestionBatch(IdTimestampMixin, Base):
    __tablename__ = "ingestion_batches"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deduplicated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    operator_id: Mapped[str | None] = mapped_column(String(200))


class VoiceRecord(IdTimestampMixin, Base):
    __tablename__ = "voice_records"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "external_id", name="uq_voice_source_external"
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ingestion_batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    product: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_object_ref: Mapped[str | None] = mapped_column(String(1024))
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    privacy_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class ConversationTurn(IdTimestampMixin, Base):
    __tablename__ = "conversation_turns"
    __table_args__ = (
        UniqueConstraint(
            "voice_record_id", "turn_index", name="uq_voice_turn_index"
        ),
    )

    voice_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voice_records.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_role: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class PrivacyFinding(IdTimestampMixin, Base):
    __tablename__ = "privacy_findings"

    voice_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voice_records.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    recognizer: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )


class AnalysisRun(IdTimestampMixin, Base):
    __tablename__ = "analysis_runs"

    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(200))
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    stage_status: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    cost_amount: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class Signal(IdTimestampMixin, Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "voice_record_id",
            "signal_index",
            name="uq_run_voice_signal",
        ),
    )

    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    voice_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voice_records.id", ondelete="CASCADE"), nullable=False
    )
    signal_index: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    object_name: Mapped[str | None] = mapped_column(String(200))
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    calibration_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uncalibrated"
    )
    is_outlier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Embedding(IdTimestampMixin, Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint(
            "signal_id", "model_version", name="uq_embedding_signal_model"
        ),
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(200), nullable=False)
    vector: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)


class TaxonomyVersion(IdTimestampMixin, Base):
    __tablename__ = "taxonomy_versions"

    product_scope: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("taxonomy_versions.id", ondelete="SET NULL")
    )
    origin: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    published_by: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Cluster(IdTimestampMixin, Base):
    __tablename__ = "clusters"

    taxonomy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taxonomy_versions.id", ondelete="CASCADE"), nullable=False
    )
    original_name: Mapped[str] = mapped_column(String(200), nullable=False)
    current_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    primary_signal_type: Mapped[str | None] = mapped_column(String(50))
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    representative_record_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    is_outlier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class ClusterMembership(IdTimestampMixin, Base):
    __tablename__ = "cluster_memberships"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version_id",
            "signal_id",
            name="uq_taxonomy_signal_membership",
        ),
    )

    taxonomy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taxonomy_versions.id", ondelete="CASCADE"), nullable=False
    )
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clusters.id", ondelete="SET NULL")
    )
    signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    assignment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="assigned"
    )


class TaxonomyRevision(IdTimestampMixin, Base):
    __tablename__ = "taxonomy_revisions"

    taxonomy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taxonomy_versions.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)


class Opportunity(IdTimestampMixin, Base):
    __tablename__ = "opportunities"

    opportunity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    scenario: Mapped[str | None] = mapped_column(Text)
    audience: Mapped[str | None] = mapped_column(Text)
    product: Mapped[str | None] = mapped_column(String(120), index=True)
    sku: Mapped[str | None] = mapped_column(String(120))
    component: Mapped[str | None] = mapped_column(String(120))
    impact_scope: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(32))
    safety_level: Mapped[str | None] = mapped_column(String(32), index=True)
    differentiation: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    priority_override: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OpportunityStatus.DRAFT.value
    )
    owner_id: Mapped[str | None] = mapped_column(String(200))


class OpportunityEvidence(IdTimestampMixin, Base):
    __tablename__ = "opportunity_evidence"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "voice_record_id",
            "evidence_direction",
            name="uq_opportunity_voice_direction",
        ),
        CheckConstraint(
            "evidence_direction IN ('support', 'oppose')",
            name="evidence_direction",
        ),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    voice_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voice_records.id", ondelete="RESTRICT"), nullable=False
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL")
    )
    evidence_direction: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(200))


class ReviewDecision(IdTimestampMixin, Base):
    __tablename__ = "review_decisions"

    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class CompetitorEvidence(IdTimestampMixin, Base):
    __tablename__ = "competitor_evidence"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    competitor: Mapped[str] = mapped_column(String(200), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_dimension: Mapped[str] = mapped_column(String(200), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )


class ActionItem(IdTimestampMixin, Base):
    __tablename__ = "action_items"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(200), nullable=False)
    collaborating_departments: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    external_system_ref: Mapped[str | None] = mapped_column(String(1024))
    decision_rationale: Mapped[str] = mapped_column(Text, nullable=False)


class OutcomeMeasurement(IdTimestampMixin, Base):
    __tablename__ = "outcome_measurements"

    action_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(200), nullable=False)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float | None] = mapped_column(Float)
    actual_value: Mapped[float | None] = mapped_column(Float)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conclusion: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)


class GoldenExample(IdTimestampMixin, Base):
    __tablename__ = "golden_examples"

    voice_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voice_records.id", ondelete="RESTRICT"), nullable=False
    )
    redacted_input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_signals: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    expected_objects: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    evidence_ranges: Mapped[list[dict[str, int]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    difficulty_tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_label"
    )
    reviewer_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    dispute_status: Mapped[str | None] = mapped_column(String(32))


class EvaluationRun(IdTimestampMixin, Base):
    __tablename__ = "evaluation_runs"

    model_version: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    slice_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")


class ModelRelease(IdTimestampMixin, Base):
    __tablename__ = "model_releases"

    model_version: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_releases.id", ondelete="SET NULL")
    )


class AuditEvent(IdTimestampMixin, Base):
    __tablename__ = "audit_events"

    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_id: Mapped[str | None] = mapped_column(String(100), index=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
