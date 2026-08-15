from sqlalchemy import select

from bearvoice.domain.models import Signal, VoiceRecord
from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)


async def test_evidence_response_contains_sanitized_quote_and_provenance(
    api_client,
    reviewer_token,
    db_session,
    repo_root,
):
    await import_legacy_snapshot(db_session, load_legacy_snapshot(repo_root))
    evidence_id = await db_session.scalar(
        select(Signal.id)
        .join(VoiceRecord, VoiceRecord.id == Signal.voice_record_id)
        .where(VoiceRecord.privacy_status == "masked")
        .limit(1)
    )

    response = await api_client.get(
        f"/api/evidence/{evidence_id}",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "[地址已脱敏]" in body["quote"]
    assert body["voice_record_id"]
    assert body["source"] == "天猫咨询"
    assert body["analysis_run_id"]
    assert body["privacy_status"] == "masked"
    assert "raw_object_ref" not in body
    assert "internal_path" not in body
