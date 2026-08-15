import argparse
import asyncio
import json
from pathlib import Path

from bearvoice.db import async_session_factory
from bearvoice.modules.ingest.legacy import (
    import_legacy_snapshot,
    load_legacy_snapshot,
)
from bearvoice.modules.reporting.export import export_markdown
from bearvoice.modules.reporting.queries import get_dashboard_snapshot


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]


async def import_legacy(repo_root: Path) -> dict[str, object]:
    snapshot = load_legacy_snapshot(repo_root)
    async with async_session_factory() as session:
        run_id = await import_legacy_snapshot(session, snapshot)
        await session.commit()
    return {
        "analysis_run_id": str(run_id),
        "extract_cache_hits": snapshot.extract_cache_count,
        "model_calls": 0,
        "voices": len(snapshot.records),
        "actionable_voices": snapshot.actionable_signal_count,
        "clusters": len(snapshot.clusters),
        "opportunities": len(snapshot.recommendations),
    }


async def export_report(destination: Path) -> Path:
    async with async_session_factory() as session:
        snapshot = await get_dashboard_snapshot(
            session,
            product="养生壶",
        )
    return export_markdown(snapshot, destination)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="bearvoice")
    subcommands = command.add_subparsers(dest="command", required=True)
    import_command = subcommands.add_parser("import-legacy")
    import_command.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
    )
    export_command = subcommands.add_parser("export-markdown")
    export_command.add_argument("destination", type=Path)
    return command


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "import-legacy":
        result = asyncio.run(import_legacy(arguments.repo_root.resolve()))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        path = asyncio.run(export_report(arguments.destination.resolve()))
        print(path)


if __name__ == "__main__":
    main()
