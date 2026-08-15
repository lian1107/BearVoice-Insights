from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)
from bearvoice.modules.reporting.export import export_markdown
from bearvoice.modules.reporting.queries import get_dashboard_snapshot


async def test_markdown_export_reconciles_with_dashboard_snapshot(
    tmp_path,
    db_session,
    repo_root,
):
    await import_legacy_snapshot(db_session, load_legacy_snapshot(repo_root))
    snapshot = await get_dashboard_snapshot(
        db_session,
        product="养生壶",
    )

    path = export_markdown(snapshot, tmp_path / "报告.md")
    text = path.read_text(encoding="utf-8")

    assert "本品类 **370 条**" in text
    assert "产品改进信号 **254 条**" in text
    assert "10 个反馈聚类" in text
    assert "9 条产品机会" in text
    assert "仅支持截面分析，不支持趋势、同比或环比判断" in text
    assert text.endswith("\n")
