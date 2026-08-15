import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import IngestionBatch, Source
from bearvoice.modules.analysis.baseline import run_local_baseline
from bearvoice.modules.ingest.adapter import CsvVoiceAdapter
from bearvoice.security.auth import (
    Principal,
    assert_permission,
    assert_product_scope,
    require_permission,
)
from bearvoice.storage import create_object_store


router = APIRouter(tags=["sources"])
SAFE_FILENAME = re.compile(r"[^0-9A-Za-z._-]+")


@router.get("/sources")
async def sources(
    _principal: Principal = Depends(require_permission(Permission.MANAGE_SOURCES)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(
                Source.id,
                Source.name,
                Source.channel,
                Source.connection_status,
                func.coalesce(func.sum(IngestionBatch.raw_count), 0),
                func.coalesce(func.sum(IngestionBatch.deduplicated_count), 0),
                func.coalesce(func.sum(IngestionBatch.quarantined_count), 0),
            )
            .outerjoin(IngestionBatch, IngestionBatch.source_id == Source.id)
            .group_by(Source.id)
            .order_by(Source.name)
        )
    ).all()
    return [
        {
            "id": source_id,
            "name": name,
            "channel": channel,
            "connection_status": status,
            "raw_count": int(raw_count),
            "deduplicated_count": int(deduplicated_count),
            "quarantined_count": int(quarantined_count),
        }
        for (
            source_id,
            name,
            channel,
            status,
            raw_count,
            deduplicated_count,
            quarantined_count,
        ) in rows
    ]


@router.post("/sources/upload", status_code=201)
async def upload_and_analyze_source(
    request: Request,
    file: UploadFile = File(...),
    source_name: str = Form(..., min_length=2, max_length=200),
    channel: str = Form(..., min_length=1, max_length=80),
    product: str = Form(..., min_length=1, max_length=120),
    product_column: str = Form(default="商品标题", min_length=1, max_length=120),
    principal: Principal = Depends(require_permission(Permission.MANAGE_SOURCES)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Import a UTF-8 CSV and create an offline, reviewable analysis baseline."""

    assert_permission(principal, Permission.RUN_ANALYSIS)
    cleaned_source_name = source_name.strip()
    cleaned_channel = channel.strip()
    cleaned_product = product.strip()
    cleaned_product_column = product_column.strip()
    if not all(
        (cleaned_source_name, cleaned_channel, cleaned_product, cleaned_product_column)
    ):
        raise HTTPException(status_code=422, detail="来源、渠道、产品线和产品列不能为空")
    assert_product_scope(cleaned_product, principal)
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="当前仅支持 UTF-8 CSV 文件")
    settings = request.app.state.settings
    payload = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not payload:
        raise HTTPException(status_code=422, detail="上传文件为空")
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {settings.max_upload_bytes // 1_048_576} MB 上限",
        )

    digest = hashlib.sha256(payload).hexdigest()
    safe_name = SAFE_FILENAME.sub("-", filename).strip("-.") or "voices.csv"
    object_ref = (
        f"uploads/{datetime.now(UTC):%Y/%m/%d}/{digest[:16]}-{safe_name}"
    )
    adapter = CsvVoiceAdapter(
        source_name=cleaned_source_name,
        product_column=cleaned_product_column,
        channel=cleaned_channel,
        product_name=cleaned_product,
    )
    try:
        imported = await adapter.import_bytes(
            session,
            payload,
            object_ref=object_ref,
        )
        batch = await session.get(IngestionBatch, imported.batch_id)
        if batch is not None:
            batch.operator_id = principal.subject
        analysis = await run_local_baseline(
            session,
            batch_id=imported.batch_id,
            product=cleaned_product,
            actor_id=principal.subject,
        )
        create_object_store(settings).put(object_ref, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(status_code=503, detail="原始文件安全存储失败") from error

    return {
        "batch_id": imported.batch_id,
        "analysis_run_id": analysis.analysis_run_id,
        "raw_count": imported.raw_count,
        "deduplicated_count": imported.deduplicated_count,
        "quarantined_count": imported.quarantined_count,
        "signal_count": analysis.signal_count,
        "cluster_count": analysis.cluster_count,
        "opportunity_count": analysis.opportunity_count,
        "status": analysis.status,
        "reused": analysis.reused,
        "analysis_mode": "offline_keyword_rules",
        "model_calls": 0,
        "notice": "本地规则基线已生成，主题与机会发布前必须人工复核",
    }
