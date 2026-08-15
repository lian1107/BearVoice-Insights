from sqlalchemy import func, select

from bearvoice.domain.models import VoiceRecord
from bearvoice.modules.ingest.adapter import CsvVoiceAdapter


async def test_csv_adapter_is_idempotent_and_never_persists_raw_address(
    db_session,
    kettle_csv,
):
    adapter = CsvVoiceAdapter(
        source_name="天猫咨询",
        product_column="商品标题",
    )

    first = await adapter.import_file(db_session, kettle_csv)
    second = await adapter.import_file(db_session, kettle_csv)
    count = await db_session.scalar(select(func.count()).select_from(VoiceRecord))
    texts = list(
        await db_session.scalars(select(VoiceRecord.normalized_text))
    )

    assert first.batch_id == second.batch_id
    assert first.raw_count == 1500
    assert first.deduplicated_count == 1109
    assert count == 1109
    assert all("省榆县街市场门口" not in text for text in texts)
    assert any("[地址已脱敏]" in text for text in texts)
