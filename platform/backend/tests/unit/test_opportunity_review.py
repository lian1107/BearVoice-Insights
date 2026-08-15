import hashlib
import uuid

from bearvoice.domain.enums import OpportunityStatus
from bearvoice.domain.models import IngestionBatch, Source, VoiceRecord
from bearvoice.domain.schemas import OpportunityDraft
from bearvoice.modules.opportunities.service import create_opportunity


async def seed_voice_records(db_session, count: int) -> list[VoiceRecord]:
    source = Source(
        id=uuid.uuid4(),
        source_type="test",
        name=f"test-{uuid.uuid4()}",
        channel="test",
        connection_status="verified",
        authorization_scope={},
    )
    db_session.add(source)
    await db_session.flush()
    batch = IngestionBatch(
        id=uuid.uuid4(),
        source_id=source.id,
        file_hash=hashlib.sha256(source.name.encode()).hexdigest(),
        raw_count=count,
        deduplicated_count=count,
        quarantined_count=0,
        status="imported",
    )
    db_session.add(batch)
    await db_session.flush()
    records = [
        VoiceRecord(
            id=uuid.uuid4(),
            source_id=source.id,
            ingestion_batch_id=batch.id,
            external_id=f"voice-{index}-{uuid.uuid4()}",
            product="养生壶",
            channel="test",
            normalized_text=f"玻璃壶身异常样本 {index}",
            content_hash=hashlib.sha256(str(index).encode()).hexdigest(),
            privacy_status="clean",
            attributes={},
        )
        for index in range(count)
    ]
    db_session.add_all(records)
    await db_session.flush()
    return records


async def test_safety_opportunity_bypasses_volume_ranking_but_still_requires_review(
    db_session,
):
    records = await seed_voice_records(db_session, 3)
    opportunity = await create_opportunity(
        db_session,
        OpportunityDraft(
            opportunity_type="improvement",
            title="玻璃壶身炸裂",
            safety_level="critical",
            evidence_record_ids=[str(record.id) for record in records],
        ),
    )

    assert opportunity.priority_override == "safety"
    assert opportunity.status == OpportunityStatus.PENDING_REVIEW.value
