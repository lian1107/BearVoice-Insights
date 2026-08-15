from sqlalchemy import func, select

from bearvoice.domain.models import AnalysisRun, VoiceRecord


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
