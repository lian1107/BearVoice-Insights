import json

from pydantic import SecretStr
from sqlalchemy import func, select

from bearvoice.domain.models import (
    AnalysisRun,
    ModelAnalysisJob,
    Source,
    VoiceRecord,
)


CSV_PAYLOAD = """原声id,原声内容,商品标题,渠道,原声日期
demo-1,这个怎么清洗,小熊养生壶,天猫,2026-08-01 10:00:00
demo-2,加热太慢一直烧不开,小熊养生壶,天猫,2026-08-02 11:00:00
demo-3,壶底冒烟有烧焦味,小熊养生壶,天猫,2026-08-03 12:00:00
""".encode()


async def test_upload_creates_a_reviewable_offline_analysis(
    api_client,
    admin_token,
    db_session,
):
    response = await api_client.post(
        "/api/sources/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={
            "source_name": "路演上传",
            "channel": "天猫",
            "product": "养生壶",
            "product_column": "商品标题",
        },
        files={"file": ("voices.csv", CSV_PAYLOAD, "text/csv")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["raw_count"] == 3
    assert body["deduplicated_count"] == 3
    assert body["signal_count"] == 3
    assert body["cluster_count"] == 3
    assert body["opportunity_count"] == 3
    assert body["status"] == "pending_review"
    assert body["analysis_mode"] == "offline_keyword_rules"
    assert body["analysis_provider"] == "local"
    assert body["model_calls"] == 0
    assert await db_session.scalar(select(func.count()).select_from(VoiceRecord)) == 3
    run = await db_session.get(AnalysisRun, body["analysis_run_id"])
    assert run is not None
    assert run.stage_status["current_phase"] == "human_review"

    dashboard = await api_client.get(
        "/api/dashboard?product=养生壶",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["total_voices"] == 3
    assert dashboard.json()["analysis_run_id"] == body["analysis_run_id"]

    repeated = await api_client.post(
        "/api/sources/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={
            "source_name": "路演上传",
            "channel": "天猫",
            "product": "养生壶",
            "product_column": "商品标题",
        },
        files={"file": ("voices.csv", CSV_PAYLOAD, "text/csv")},
    )
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["reused"] is True
    assert repeated.json()["analysis_run_id"] == body["analysis_run_id"]
    assert await db_session.scalar(select(func.count()).select_from(VoiceRecord)) == 3


async def test_upload_rejects_a_csv_without_required_columns(api_client, admin_token):
    response = await api_client.post(
        "/api/sources/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={
            "source_name": "错误文件",
            "channel": "天猫",
            "product": "养生壶",
            "product_column": "商品标题",
        },
        files={"file": ("bad.csv", b"id,text\n1,hello", "text/csv")},
    )

    assert response.status_code == 422
    assert "CSV" in response.json()["detail"]


async def test_preview_profiles_quality_without_persisting_data(
    api_client,
    admin_token,
    db_session,
):
    payload = """随机编号,客户原声,产品名称,时间
1,怎么清洗,养生壶,2026-08-01
1,怎么清洗,养生壶,错误时间
2,怎么清洗2026,养生壶,2026-08-02
3,,养生壶,2026-08-03
""".lstrip().encode()
    response = await api_client.post(
        "/api/sources/preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("voices.csv", payload, "text/csv")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["encoding"] == "utf-8"
    assert body["row_count"] == 4
    assert body["column_mapping"] == {
        "text": "客户原声",
        "product": "产品名称",
        "occurred_at": "时间",
    }
    assert body["missing_required_fields"] == ["voice_id"]
    assert body["required_fields_matched"] is False
    assert body["exact_duplicate_count"] == 1
    assert body["near_duplicate_or_template_count"] == 1
    assert body["date_parse_rate"] == 0.75
    assert body["quarantined_count"] == 1
    assert body["ai_used"] is False
    assert await db_session.scalar(select(func.count()).select_from(Source)) == 0
    assert await db_session.scalar(select(func.count()).select_from(VoiceRecord)) == 0


async def test_preview_rejects_non_utf8_and_reports_bad_rows(api_client, admin_token):
    encoded = "原声id,原声内容,商品标题\n1,测试,养生壶".encode("gb18030")
    encoding_response = await api_client.post(
        "/api/sources/preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("gb.csv", encoded, "text/csv")},
    )
    assert encoding_response.status_code == 422
    assert "UTF-8" in encoding_response.json()["detail"]

    bad_row_response = await api_client.post(
        "/api/sources/preview",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={
            "file": (
                "bad-row.csv",
                "原声id,原声内容,商品标题\n1,测试,养生壶,多余列".encode(),
                "text/csv",
            )
        },
    )
    assert bad_row_response.status_code == 200
    assert bad_row_response.json()["quarantined_count"] == 1
    assert bad_row_response.json()["quarantine_reasons"] == [
        {"reason": "列数多于表头", "count": 1}
    ]


async def test_confirmed_mapping_persists_optional_business_fields_safely(
    api_client,
    admin_token,
    db_session,
):
    payload = """feedback_key,comment,item_name,item_sku,created,source,user_key,order_no,batch_no,firmware
v-1,清洗很麻烦,小熊养生壶,K-01,2026-08-01,京东,user-123,order-456,B202608,v2.1
""".encode()
    mapping = {
        "voice_id": "feedback_key",
        "text": "comment",
        "product": "item_name",
        "sku": "item_sku",
        "occurred_at": "created",
        "channel": "source",
        "anonymous_user_key": "user_key",
        "order_id": "order_no",
        "batch": "batch_no",
        "version": "firmware",
    }
    response = await api_client.post(
        "/api/sources/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={
            "source_name": "经营数据上传",
            "channel": "导入默认渠道",
            "product": "养生壶",
            "product_column": "item_name",
            "column_mapping": json.dumps(mapping, ensure_ascii=False),
        },
        files={"file": ("business.csv", payload, "text/csv")},
    )
    assert response.status_code == 201, response.text
    record = await db_session.scalar(select(VoiceRecord))
    assert record is not None
    assert record.sku == "K-01"
    assert record.channel == "京东"
    assert record.attributes["batch"] == "B202608"
    assert record.attributes["version"] == "v2.1"
    assert record.attributes["sku"] == "K-01"
    assert record.attributes["anonymous_user_key_hash"] != "user-123"
    assert record.attributes["order_id_hash"] != "order-456"
    assert "order-456" not in str(record.attributes)


async def test_analysis_provider_options_are_safe_and_local_is_available(
    api_client,
    admin_token,
):
    response = await api_client.get(
        "/api/analysis/providers",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["provider"] for item in body] == [
        "local",
        "deepseek",
        "glm",
        "minimax",
        "qwen",
        "custom",
    ]
    assert body[0] == {
        "provider": "local",
        "configured": True,
        "approved": True,
        "model": "local-rule-baseline-v1",
    }
    assert "api_key" not in response.text
    assert "base_url" not in response.text


async def test_unapproved_ai_provider_is_rejected_before_business_data_write(
    api_client,
    admin_token,
    db_session,
):
    response = await api_client.post(
        "/api/sources/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={
            "source_name": "未批准 AI 上传",
            "channel": "天猫",
            "product": "养生壶",
            "product_column": "商品标题",
            "analysis_provider": "deepseek",
        },
        files={"file": ("voices.csv", CSV_PAYLOAD, "text/csv")},
    )

    assert response.status_code == 422
    assert "未完成" in response.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(Source)) == 0
    assert await db_session.scalar(select(func.count()).select_from(VoiceRecord)) == 0


async def test_approved_ai_upload_returns_background_job_and_is_idempotent(
    api_client,
    api_settings,
    admin_token,
    db_session,
):
    class FakeDispatcher:
        def __init__(self):
            self.jobs = []

        async def enqueue(self, job_id, workflow_id):
            self.jobs.append((job_id, workflow_id))

    api_settings.model_egress_enabled = True
    api_settings.model_provider_allowlist = ("deepseek",)
    api_settings.model_purpose_allowlist = ("voice_semantic_analysis",)
    api_settings.model_endpoint_allowlist = ("https://api.deepseek.com",)
    api_settings.deepseek_api_key = SecretStr("test-secret")
    app = api_client._transport.app  # type: ignore[attr-defined]
    dispatcher = FakeDispatcher()
    app.state.semantic_job_dispatcher = dispatcher

    request = {
        "headers": {"Authorization": f"Bearer {admin_token}"},
        "data": {
            "source_name": "AI 后台上传",
            "channel": "天猫",
            "product": "养生壶",
            "product_column": "商品标题",
            "analysis_provider": "deepseek",
        },
        "files": {"file": ("voices.csv", CSV_PAYLOAD, "text/csv")},
    }
    response = await api_client.post("/api/sources/upload", **request)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "dispatched"
    assert body["job_id"]
    assert body["analysis_run_id"] is None
    assert body["requested_items"] == 3
    assert body["processed_items"] == 0
    assert body["model_calls"] == 0
    assert len(dispatcher.jobs) == 1
    job = await db_session.get(ModelAnalysisJob, body["job_id"])
    assert job.status == "dispatched"
    assert await db_session.scalar(select(func.count()).select_from(AnalysisRun)) == 0

    status = await api_client.get(
        f"/api/analysis/jobs/{body['job_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert status.status_code == 200
    assert status.json()["status"] == "dispatched"

    repeated = await api_client.post("/api/sources/upload", **request)
    assert repeated.status_code == 202
    assert repeated.json()["reused"] is True
    assert repeated.json()["job_id"] == body["job_id"]
    assert len(dispatcher.jobs) == 1
