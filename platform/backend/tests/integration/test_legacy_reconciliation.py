import json

import pytest

from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)
from bearvoice.modules.reporting.queries import (
    ReconciliationError,
    get_dashboard_snapshot,
    reconcile_legacy_baseline,
)


async def test_api_projection_matches_verified_cluster_detail(
    db_session,
    repo_root,
):
    await import_legacy_snapshot(db_session, load_legacy_snapshot(repo_root))
    dashboard = await get_dashboard_snapshot(
        db_session,
        product="养生壶",
        view="competition",
    )
    detail = json.loads(
        (repo_root / "reports/improve-养生壶/聚类明细.json").read_text(
            encoding="utf-8"
        )
    )

    reconcile_legacy_baseline(dashboard)
    assert {item.name: item.count for item in dashboard.top_clusters} == {
        item["name"]: item["count"] for item in detail["clusters"]
    }
    assert len(dashboard.opportunities) == len(detail["recommendations"])

    with pytest.raises(ReconciliationError, match="total_voices"):
        reconcile_legacy_baseline(
            dashboard.model_copy(update={"total_voices": 369})
        )
