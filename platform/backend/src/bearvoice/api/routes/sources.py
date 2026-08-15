import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.db import get_db_session
from bearvoice.domain.enums import Permission
from bearvoice.domain.models import IngestionBatch, ModelAnalysisJob, Source
from bearvoice.modules.analysis.baseline import run_local_baseline
from bearvoice.modules.analysis.china_model_adapter import SUPPORTED_PROVIDERS
from bearvoice.modules.analysis.china_models import provider_options
from bearvoice.modules.analysis.semantic_jobs import (
    ModelBudgetExceeded,
    create_model_analysis_job,
    serialize_model_job,
)
from bearvoice.modules.ingest.adapter import CsvVoiceAdapter, preview_csv_bytes
from bearvoice.security.auth import (
    Principal,
    assert_permission,
    assert_product_scope,
    require_permission,
)
from bearvoice.storage import create_object_store


router = APIRouter(tags=["sources"])
SAFE_FILENAME = re.compile(r"[^0-9A-Za-z._-]+")


async def _read_csv_upload(request: Request, file: UploadFile) -> tuple[bytes, str]:
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
    return payload, filename


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


@router.get("/analysis/providers")
async def analysis_providers(
    request: Request,
    _principal: Principal = Depends(require_permission(Permission.RUN_ANALYSIS)),
) -> list[dict[str, object]]:
    """Return selection-safe provider state without keys or endpoint addresses."""

    configured = [
        {
            "provider": option.provider,
            "configured": option.configured,
            "approved": option.approved,
            "model": option.model,
        }
        for option in provider_options(request.app.state.settings)
    ]
    return [
        {
            "provider": "local",
            "configured": True,
            "approved": True,
            "model": "local-rule-baseline-v1",
        },
        *configured,
    ]


@router.get("/analysis/jobs/{job_id}")
async def analysis_job_status(
    job_id: uuid.UUID,
    principal: Principal = Depends(require_permission(Permission.RUN_ANALYSIS)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    job = await session.get(ModelAnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    assert_product_scope(job.product, principal)
    return serialize_model_job(job)


@router.post("/sources/preview")
async def preview_source_csv(
    request: Request,
    file: UploadFile = File(...),
    _principal: Principal = Depends(require_permission(Permission.MANAGE_SOURCES)),
) -> dict[str, object]:
    """Profile a CSV in memory without persisting its bytes or business records."""
    payload, _filename = await _read_csv_upload(request, file)
    try:
        return preview_csv_bytes(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/sources/upload", status_code=201)
async def upload_and_analyze_source(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    source_name: str = Form(..., min_length=2, max_length=200),
    channel: str = Form(..., min_length=1, max_length=80),
    product: str = Form(..., min_length=1, max_length=120),
    product_column: str = Form(default="商品标题", min_length=1, max_length=120),
    column_mapping: str | None = Form(default=None),
    analysis_provider: str = Form(default="local", min_length=1, max_length=50),
    principal: Principal = Depends(require_permission(Permission.MANAGE_SOURCES)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Import a UTF-8 CSV and create an offline, reviewable analysis baseline."""

    assert_permission(principal, Permission.RUN_ANALYSIS)
    cleaned_source_name = source_name.strip()
    cleaned_channel = channel.strip()
    cleaned_product = product.strip()
    cleaned_product_column = product_column.strip()
    cleaned_analysis_provider = analysis_provider.strip().lower()
    if not all(
        (cleaned_source_name, cleaned_channel, cleaned_product, cleaned_product_column)
    ):
        raise HTTPException(status_code=422, detail="来源、渠道、产品线和产品列不能为空")
    assert_product_scope(cleaned_product, principal)
    if cleaned_analysis_provider != "local" and (
        cleaned_analysis_provider not in SUPPORTED_PROVIDERS
    ):
        raise HTTPException(status_code=422, detail="不支持的分析模型提供商")
    settings = request.app.state.settings
    if cleaned_analysis_provider != "local":
        selected_option = next(
            (
                option
                for option in provider_options(settings)
                if option.provider == cleaned_analysis_provider
            ),
            None,
        )
        if selected_option is None or not selected_option.approved:
            raise HTTPException(
                status_code=422,
                detail="该模型提供商未完成密钥、用途和端点批准",
            )
    payload, filename = await _read_csv_upload(request, file)
    parsed_mapping: dict[str, str] | None = None
    if column_mapping:
        try:
            candidate = json.loads(column_mapping)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=422, detail="字段映射不是有效 JSON") from error
        if not isinstance(candidate, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in candidate.items()
        ):
            raise HTTPException(status_code=422, detail="字段映射必须是字符串键值对")
        parsed_mapping = {
            key.strip(): value.strip()
            for key, value in candidate.items()
            if key.strip() and value.strip()
        }

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
        column_mapping=parsed_mapping,
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
        if cleaned_analysis_provider == "local":
            analysis = await run_local_baseline(
                session,
                batch_id=imported.batch_id,
                product=cleaned_product,
                actor_id=principal.subject,
            )
            analysis_mode = "offline_keyword_rules"
            model_calls = 0
            reused = analysis.reused
            notice = "本地规则基线已生成，主题与机会发布前必须人工复核"
        else:
            job, reused = await create_model_analysis_job(
                session,
                batch_id=imported.batch_id,
                product=cleaned_product,
                provider=cleaned_analysis_provider,
                actor_id=principal.subject,
                settings=settings,
            )
            analysis_mode = "governed_ai_semantic"
            model_calls = job.model_calls
            notice = "AI 分析已进入后台队列，可安全离开页面"
        create_object_store(settings).put(object_ref, payload)
        if cleaned_analysis_provider != "local":
            await session.commit()
            if job.status == "dispatch_failed":
                job.status = "queued"
                job.error_code = None
                job.error_message = None
                await session.commit()
            if not reused or job.status == "queued":
                try:
                    await request.app.state.semantic_job_dispatcher.enqueue(
                        job.id, job.workflow_id
                    )
                    job.status = "dispatched"
                    await session.commit()
                except Exception as error:
                    job.status = "dispatch_failed"
                    job.error_code = "temporal_dispatch_failed"
                    job.error_message = "后台任务队列暂不可用"
                    await session.commit()
                    raise HTTPException(
                        status_code=503,
                        detail="数据已安全导入，但后台分析队列暂不可用；请稍后重试相同文件",
                    ) from error
    except ModelBudgetExceeded as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(status_code=503, detail="原始文件安全存储失败") from error

    if cleaned_analysis_provider != "local":
        response.status_code = 202
        return {
            "batch_id": imported.batch_id,
            "job_id": job.id,
            "analysis_run_id": job.analysis_run_id,
            "raw_count": imported.raw_count,
            "deduplicated_count": imported.deduplicated_count,
            "quarantined_count": imported.quarantined_count,
            "signal_count": job.signal_count,
            "cluster_count": job.cluster_count,
            "opportunity_count": job.opportunity_count,
            "status": job.status,
            "reused": reused,
            "analysis_mode": analysis_mode,
            "analysis_provider": cleaned_analysis_provider,
            "model_calls": model_calls,
            "requested_items": job.requested_items,
            "processed_items": job.processed_items,
            "attempt_count": job.attempt_count,
            "reserved_cost_amount": float(job.reserved_cost_amount),
            "notice": notice,
        }

    return {
        "batch_id": imported.batch_id,
        "job_id": None,
        "analysis_run_id": analysis.analysis_run_id,
        "raw_count": imported.raw_count,
        "deduplicated_count": imported.deduplicated_count,
        "quarantined_count": imported.quarantined_count,
        "signal_count": analysis.signal_count,
        "cluster_count": analysis.cluster_count,
        "opportunity_count": analysis.opportunity_count,
        "status": analysis.status,
        "reused": reused,
        "analysis_mode": analysis_mode,
        "analysis_provider": cleaned_analysis_provider,
        "model_calls": model_calls,
        "notice": notice,
    }
