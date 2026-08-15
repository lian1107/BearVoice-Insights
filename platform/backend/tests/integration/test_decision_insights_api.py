import uuid
from datetime import UTC, datetime

from bearvoice.domain.models import (
    AnalysisRun,
    IngestionBatch,
    Signal,
    Source,
    VoiceRecord,
)
from bearvoice.security.auth import issue_dev_token


async def _seed_insights(db_session) -> tuple[uuid.UUID, list[uuid.UUID]]:
    source = Source(
        source_type="csv",
        name=f"decision-{uuid.uuid4()}",
        channel="天猫",
        authorization_scope={},
    )
    db_session.add(source)
    await db_session.flush()
    batch = IngestionBatch(
        source_id=source.id,
        file_hash="d" * 64,
        raw_count=3,
        deduplicated_count=3,
        quarantined_count=0,
        status="completed",
    )
    run = AnalysisRun(
        dataset_hash="d" * 64,
        code_version="decision-test",
        model_version="test-model",
        parameters={},
        stage_status={"persist": "completed"},
    )
    db_session.add_all([batch, run])
    await db_session.flush()

    voices = [
        VoiceRecord(
            source_id=source.id,
            ingestion_batch_id=batch.id,
            external_id=f"decision-{index}",
            product="养生壶",
            sku="K-01" if index < 2 else "K-02",
            channel="天猫" if index < 2 else "京东",
            occurred_at=datetime(2026, 8, index + 1, tzinfo=UTC),
            normalized_text=f"原声 {index}",
            content_hash=f"{index + 1:064x}",
            privacy_status="passed",
            attributes={
                "batch": "B-01" if index < 2 else "B-02",
                "version": "v1" if index < 2 else "v2",
            },
        )
        for index in range(3)
    ]
    db_session.add_all(voices)
    await db_session.flush()

    signals = [
        Signal(
            analysis_run_id=run.id,
            voice_record_id=voices[0].id,
            signal_index=0,
            signal_type="safety",
            lifecycle_stage="use",
            object_name="加热系统",
            issue="干烧后没有及时断电",
            latent_need="异常时自动停机",
            scenario="用户忘记加水时",
            evidence_text="忘记加水后还在加热",
            confidence=0.8,
            calibration_status="uncalibrated",
            risk_level="low",
            root_cause_hypotheses=["液位检测或保护逻辑需要排查"],
            missing_information=["断电时间", "固件版本"],
            improvement_directions=["评估双重防干烧保护"],
            validation_suggestions=["在隔离环境复现并记录断电时间"],
        ),
        Signal(
            analysis_run_id=run.id,
            voice_record_id=voices[1].id,
            signal_index=0,
            signal_type="safety",
            lifecycle_stage="use",
            object_name="加热系统",
            issue="干烧后没有及时断电",
            latent_need="异常时自动停机",
            scenario="低水位加热",
            evidence_text="水少的时候机器特别烫",
            confidence=0.7,
            calibration_status="uncalibrated",
            risk_level="high",
            root_cause_hypotheses=["液位检测或保护逻辑需要排查"],
            missing_information=["表面温度"],
            improvement_directions=["增加独立热保护路径"],
            validation_suggestions=["完成失效模式与安全评审"],
        ),
        Signal(
            analysis_run_id=run.id,
            voice_record_id=voices[2].id,
            signal_index=0,
            signal_type="expectation",
            lifecycle_stage="onboarding",
            object_name="面板",
            issue="首次使用时功能名称不易理解",
            latent_need="快速理解常用模式",
            scenario="拆箱后第一次操作",
            evidence_text="第一次用不知道选哪个模式",
            confidence=0.9,
            calibration_status="uncalibrated",
            risk_level="low",
            root_cause_hypotheses=["功能文案与用户任务表述不一致"],
            missing_information=["主要用户群的首次任务成功率"],
            improvement_directions=["测试任务导向的模式文案"],
            validation_suggestions=["对照原文案做首次任务测试"],
        ),
    ]
    db_session.add_all(signals)
    await db_session.flush()
    return run.id, [signal.id for signal in signals]


async def test_decision_insights_builds_explainable_cube_and_cards(
    api_client,
    admin_token,
    db_session,
):
    run_id, signal_ids = await _seed_insights(db_session)

    response = await api_client.get(
        "/api/insights/decision?product=养生壶",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_run_id"] == str(run_id)
    assert payload["coverage"]["total_voices"] == 3
    assert payload["coverage"]["total_signals"] == 3
    assert payload["coverage"]["has_business_denominator"] is False
    assert "缺少企业经营分母" in payload["coverage"]["denominator_notice"]
    assert payload["coverage"]["trend_allowed"] is False
    assert set(payload["dimensions"]) == {
        "channel",
        "sku",
        "batch",
        "version",
        "lifecycle_stage",
        "risk_level",
    }
    tmall = next(
        item for item in payload["dimensions"]["channel"] if item["value"] == "天猫"
    )
    assert tmall == {
        "value": "天猫",
        "count": 2,
        "percentage": 66.7,
        "denominator": 3,
    }

    assert len(payload["patterns"]) == 2
    safety = payload["patterns"][0]
    assert safety["risk_level"] == "high"
    assert safety["voice_count"] == 2
    assert safety["share"] == 66.7
    assert set(safety["supporting_evidence_ids"]) == {
        str(signal_ids[0]),
        str(signal_ids[1]),
    }
    assert "最高风险排序" in safety["conflict_notice"]
    assert "多个未验证" in safety["conflict_notice"]

    card = payload["decision_cards"][0]
    assert card["human_review_required"] is True
    assert card["evidence_level"] == "directional"
    assert "质量/安全负责人" in card["human_owner"]
    assert card["recommended_direction"].startswith("候选方向（未经验证）")
    assert "不使用虚构加权分" in card["priority_explanation"]
    assert "成本与 ROI 因缺经营分母为 TBD" in card["priority_explanation"]
    assert any("不得把根因假设" in claim for claim in card["forbidden_claims"])
    assert any("ROI" in claim for claim in card["forbidden_claims"])
    assert "priority_score" not in card
    assert "不得表述为已证实因果" in payload["governance"]["causality_notice"]


async def test_decision_insights_rejects_missing_blank_and_empty_data(
    api_client,
    admin_token,
):
    headers = {"Authorization": f"Bearer {admin_token}"}
    assert (await api_client.get("/api/insights/decision", headers=headers)).status_code == 422
    assert (
        await api_client.get("/api/insights/decision?product=%20", headers=headers)
    ).status_code == 422
    empty = await api_client.get(
        "/api/insights/decision?product=不存在的产品",
        headers=headers,
    )
    assert empty.status_code == 404
    assert "没有可用洞察数据" in empty.json()["detail"]


async def test_decision_insights_requires_run_analysis_and_product_scope(
    api_client,
    management_token,
    api_settings,
    db_session,
):
    await _seed_insights(db_session)
    no_permission = await api_client.get(
        "/api/insights/decision?product=养生壶",
        headers={"Authorization": f"Bearer {management_token}"},
    )
    assert no_permission.status_code == 403

    wrong_scope_token = issue_dev_token(
        api_settings,
        subject="other-product-manager",
        roles=("product_manager",),
        product_lines=("电饭煲",),
    )
    wrong_scope = await api_client.get(
        "/api/insights/decision?product=养生壶",
        headers={"Authorization": f"Bearer {wrong_scope_token}"},
    )
    assert wrong_scope.status_code == 403
