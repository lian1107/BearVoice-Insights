import uuid

from sqlalchemy import func, select

from bearvoice.config import Settings
from bearvoice.domain.models import (
    AnalysisRun,
    Cluster,
    IngestionBatch,
    Opportunity,
    SemanticVoiceCache,
    Signal,
    Source,
    VoiceRecord,
)
from bearvoice.modules.analysis.semantic_models import VoiceSemanticResult
from bearvoice.modules.analysis.semantic_engine import SemanticOutputError
from bearvoice.modules.analysis.semantic_persistence import run_semantic_analysis
from bearvoice.modules.analysis.china_model_adapter import ModelTransportError


class FakeSemanticEngine:
    def __init__(self, *, fail_on: str | None = None):
        self.fail_on = fail_on

    async def analyze(self, voice, *, run_id):
        if voice.voice_id == self.fail_on:
            raise RuntimeError("模拟模型拒绝")
        return VoiceSemanticResult.model_validate(
            {
                "schema_version": "1.0",
                "voice_id": voice.voice_id,
                "signals": [
                    {
                        "signal_type": "defect",
                        "lifecycle_stage": "use",
                        "object_name": "壶盖",
                        "issue": "壶盖漏水",
                        "latent_need": "安全密封",
                        "scenario": "倒水时",
                        "evidence_text": "壶盖漏水",
                        "confidence": 0.8,
                        "uncalibrated": True,
                        "risk_level": "high",
                        "root_cause_hypotheses": ["密封圈尺寸待验证"],
                        "missing_information": ["生产批次"],
                        "improvement_directions": ["评估密封结构优化"],
                        "validation_suggestions": ["按批次做水压对比测试"],
                    }
                ],
            }
        )


class RetryingSemanticEngine(FakeSemanticEngine):
    def __init__(self):
        super().__init__()
        self.attempts: dict[str, int] = {}

    async def analyze(self, voice, *, run_id):
        self.attempts[voice.voice_id] = self.attempts.get(voice.voice_id, 0) + 1
        if self.attempts[voice.voice_id] == 1:
            raise ModelTransportError("模拟临时限流")
        return await super().analyze(voice, run_id=run_id)


class CountingSemanticEngine(FakeSemanticEngine):
    def __init__(self, *, fail_on: str | None = None):
        super().__init__(fail_on=fail_on)
        self.calls: list[str] = []

    async def analyze(self, voice, *, run_id):
        self.calls.append(voice.voice_id)
        return await super().analyze(voice, run_id=run_id)


class InvalidOutputEngine(FakeSemanticEngine):
    def __init__(self, invalid_voice_id: str):
        super().__init__()
        self.invalid_voice_id = invalid_voice_id
        self.attempts = 0

    async def analyze(self, voice, *, run_id):
        if voice.voice_id == self.invalid_voice_id:
            self.attempts += 1
            raise SemanticOutputError("模拟严格 JSON 契约失败")
        return await super().analyze(voice, run_id=run_id)


async def _seed_batch(db_session, *, count: int = 2):
    source = Source(
        id=uuid.uuid4(),
        source_type="csv",
        name=f"语义测试-{uuid.uuid4()}",
        channel="test",
        connection_status="verified",
        authorization_scope={},
    )
    db_session.add(source)
    await db_session.flush()
    batch = IngestionBatch(
        id=uuid.uuid4(),
        source_id=source.id,
        file_hash=uuid.uuid4().hex * 2,
        raw_count=count,
        deduplicated_count=count,
        quarantined_count=0,
        status="succeeded",
        operator_id="tester",
    )
    db_session.add(batch)
    await db_session.flush()
    records = [
        VoiceRecord(
            id=uuid.uuid4(),
            source_id=source.id,
            ingestion_batch_id=batch.id,
            external_id=f"voice-{index}",
            product="养生壶",
            channel="test",
            normalized_text="壶盖漏水",
            content_hash=str(index).zfill(64),
            privacy_status="clean",
            attributes={},
        )
        for index in range(count)
    ]
    db_session.add_all(records)
    await db_session.flush()
    return batch, records


def _settings():
    return Settings(
        deepseek_api_key="test-secret",
        model_endpoint_allowlist=("https://api.deepseek.com",),
    )


async def test_semantic_batch_persists_multi_signal_candidates_separately(
    db_session,
):
    batch, _ = await _seed_batch(db_session)

    result = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=_settings(),
        engine=FakeSemanticEngine(),
    )

    run = await db_session.get(AnalysisRun, result.analysis_run_id)
    persisted_signals = list(
        await db_session.scalars(
            select(Signal).where(
                Signal.analysis_run_id == result.analysis_run_id
            )
        )
    )
    signal_count = len(persisted_signals)
    assert all(
        signal.lifecycle_stage == "use"
        and signal.issue == "壶盖漏水"
        and signal.latent_need == "安全密封"
        and signal.scenario == "倒水时"
        and signal.risk_level == "high"
        and signal.root_cause_hypotheses == ["密封圈尺寸待验证"]
        and signal.missing_information == ["生产批次"]
        and signal.improvement_directions == ["评估密封结构优化"]
        and signal.validation_suggestions == ["按批次做水压对比测试"]
        for signal in persisted_signals
    )
    counted_signals = await db_session.scalar(
        select(func.count()).select_from(Signal).where(
            Signal.analysis_run_id == result.analysis_run_id
        )
    )
    cluster = await db_session.scalar(select(Cluster))
    opportunity = await db_session.scalar(select(Opportunity))
    assert result.status == "pending_review", (run.error_code, run.error_message)
    assert result.signal_count == signal_count == counted_signals == 2
    assert run.model_version == "deepseek:deepseek-v4-pro"
    assert run.model_version != "local-rule-baseline-v1"
    assert "待验证根因假设" in cluster.description
    assert opportunity.status == "pending_review"
    assert "根因仅为待验证假设" in opportunity.problem

    repeated = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=_settings(),
        engine=FakeSemanticEngine(),
    )
    assert repeated.reused is True
    assert repeated.analysis_run_id == result.analysis_run_id
    assert await db_session.scalar(select(func.count()).select_from(AnalysisRun)) == 1


async def test_semantic_batch_failure_leaves_no_partial_signals(db_session):
    batch, records = await _seed_batch(db_session)

    result = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=_settings(),
        engine=FakeSemanticEngine(fail_on=str(records[1].id)),
    )

    run = await db_session.get(AnalysisRun, result.analysis_run_id)
    signal_count = await db_session.scalar(
        select(func.count()).select_from(Signal).where(
            Signal.analysis_run_id == result.analysis_run_id
        )
    )
    assert result.status == "failed"
    assert signal_count == 0
    assert run.stage_status["status"] == "failed"
    assert run.stage_status["notice"] == "整批语义结果已拒绝，未写入任何 Signal"


async def test_semantic_batch_retries_transient_calls_and_records_real_call_count(
    db_session,
):
    batch, records = await _seed_batch(db_session)
    engine = RetryingSemanticEngine()
    settings = _settings().model_copy(
        update={
            "semantic_batch_size": 2,
            "semantic_max_concurrency": 2,
            "semantic_retry_max_attempts": 3,
            "semantic_retry_initial_seconds": 0.1,
        }
    )

    result = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=settings,
        engine=engine,
    )

    run = await db_session.get(AnalysisRun, result.analysis_run_id)
    assert result.status == "pending_review"
    assert run.stage_status["model_calls"] == 4
    assert run.stage_status["batch_size"] == 2
    assert set(engine.attempts.values()) == {2}


async def test_semantic_batch_never_exceeds_reserved_model_call_limit(db_session):
    batch, _ = await _seed_batch(db_session)
    engine = CountingSemanticEngine()

    result = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=_settings(),
        engine=engine,
        model_call_limit=1,
    )

    assert result.status == "failed"
    assert result.error_code == "SemanticCallBudgetExceeded"
    assert len(engine.calls) == 1


async def test_failed_run_checkpoints_validated_voices_for_safe_resume(db_session):
    batch, records = await _seed_batch(db_session, count=3)
    ordered_records = sorted(records, key=lambda record: record.id)
    settings = _settings().model_copy(
        update={
            "semantic_batch_size": 1,
            "semantic_max_concurrency": 1,
            "semantic_retry_max_attempts": 1,
        }
    )
    failing = CountingSemanticEngine(fail_on=str(ordered_records[2].id))

    failed = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=settings,
        engine=failing,
    )
    assert failed.status == "failed"
    assert await db_session.scalar(
        select(func.count()).select_from(SemanticVoiceCache)
    ) == 2

    resumed_engine = CountingSemanticEngine()
    resumed = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=settings,
        engine=resumed_engine,
    )
    resumed_run = await db_session.get(AnalysisRun, resumed.analysis_run_id)
    assert resumed.status == "pending_review"
    assert resumed_run.stage_status["cache_hits"] == 2
    assert resumed_run.stage_status["model_calls"] == 1
    assert resumed_engine.calls == [str(ordered_records[2].id)]


async def test_exhausted_schema_failure_is_explicitly_unresolved(db_session):
    batch, records = await _seed_batch(db_session)
    settings = _settings().model_copy(
        update={
            "semantic_batch_size": 2,
            "semantic_retry_max_attempts": 2,
            "semantic_retry_initial_seconds": 0.1,
        }
    )
    engine = InvalidOutputEngine(str(records[1].id))

    result = await run_semantic_analysis(
        db_session,
        batch_id=batch.id,
        product="养生壶",
        provider="deepseek",
        actor_id="admin-1",
        settings=settings,
        engine=engine,
    )
    run = await db_session.get(AnalysisRun, result.analysis_run_id)
    assert result.status == "pending_review"
    assert result.signal_count == 1
    assert run.stage_status["unresolved_voice_count"] == 1
    assert run.stage_status["successful_voice_calls"] == 1
    assert engine.attempts == 2
