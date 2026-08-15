from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)


async def test_kettle_dashboard_reconciles_with_verified_legacy_report(
    api_client,
    management_token,
    db_session,
    repo_root,
):
    await import_legacy_snapshot(db_session, load_legacy_snapshot(repo_root))

    response = await api_client.get(
        "/api/dashboard?product=养生壶&view=competition",
        headers={"Authorization": f"Bearer {management_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_voices"] == 370
    assert payload["actionable_voices"] == 254
    assert payload["denominator"] == 370
    assert len(payload["top_clusters"]) == 10
    assert sum(item["count"] for item in payload["top_clusters"]) == 370
    assert len(payload["opportunities"]) == 9
    assert all(item["impact_scope"] for item in payload["opportunities"])
    assert payload["coverage"] == {
        "channel": "天猫",
        "period_start": "2026-08-01",
        "period_end": "2026-08-03",
        "days": 3,
        "trend_allowed": False,
        "limitation": "仅支持截面分析，不支持趋势、同比或环比判断",
    }
