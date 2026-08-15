import csv
import hashlib
import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bearvoice.domain.models import (
    IngestionBatch,
    PrivacyFinding,
    Source,
    VoiceRecord,
)
from bearvoice.modules.ingest.privacy import SanitizedVoice, sanitize_voice_text


@dataclass(frozen=True)
class ImportResult:
    batch_id: uuid.UUID
    raw_count: int
    deduplicated_count: int
    quarantined_count: int


class SourceAdapter(Protocol):
    def validate(self, rows: list[dict[str, str]]) -> None: ...

    def normalize(self, row: dict[str, str]) -> dict[str, str]: ...

    def dedupe(self, rows: list[dict[str, str]]) -> list[dict[str, str]]: ...

    def privacy_gate(self, text: str) -> SanitizedVoice: ...

    async def persist(
        self,
        session: AsyncSession,
        rows: list[dict[str, str]],
        *,
        file_path: Path,
        file_hash: str,
        raw_count: int,
    ) -> ImportResult: ...


class CsvVoiceAdapter:
    def __init__(self, source_name: str, product_column: str) -> None:
        self.source_name = source_name
        self.product_column = product_column

    def validate(self, rows: list[dict[str, str]]) -> None:
        required = {"原声id", "原声内容", self.product_column}
        if not rows:
            raise ValueError("CSV 没有可导入的原声")
        missing = required - set(rows[0])
        if missing:
            raise ValueError(f"CSV 缺少字段：{', '.join(sorted(missing))}")

    def normalize(self, row: dict[str, str]) -> dict[str, str]:
        normalized = dict(row)
        normalized["_文本"] = re.sub(
            r"\s+",
            " ",
            (row.get("原声内容") or "").replace("<br>", " / "),
        ).strip()
        return normalized

    def dedupe(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for row in rows:
            key = row.get("原声id") or hashlib.sha256(
                row["_文本"].encode("utf-8")
            ).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    def privacy_gate(self, text: str) -> SanitizedVoice:
        return sanitize_voice_text(text)

    async def import_file(
        self,
        session: AsyncSession,
        file_path: Path,
    ) -> ImportResult:
        content = file_path.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        text = content.decode("utf-8-sig")
        raw_rows = [
            row
            for row in csv.DictReader(io.StringIO(text))
            if (row.get("原声内容") or "").strip()
        ]
        self.validate(raw_rows)
        normalized = [self.normalize(row) for row in raw_rows]
        unique = self.dedupe(normalized)
        return await self.persist(
            session,
            unique,
            file_path=file_path,
            file_hash=file_hash,
            raw_count=len(raw_rows),
        )

    async def persist(
        self,
        session: AsyncSession,
        rows: list[dict[str, str]],
        *,
        file_path: Path,
        file_hash: str,
        raw_count: int,
    ) -> ImportResult:
        source = await session.scalar(
            select(Source).where(Source.name == self.source_name)
        )
        if source is None:
            source = Source(
                id=uuid.uuid4(),
                source_type="csv",
                name=self.source_name,
                channel="天猫",
                connection_status="verified",
                authorization_scope={"mode": "local_file"},
            )
            session.add(source)
            await session.flush()

        existing = await session.scalar(
            select(IngestionBatch).where(
                IngestionBatch.source_id == source.id,
                IngestionBatch.file_hash == file_hash,
            )
        )
        if existing is not None:
            return ImportResult(
                batch_id=existing.id,
                raw_count=existing.raw_count,
                deduplicated_count=existing.deduplicated_count,
                quarantined_count=existing.quarantined_count,
            )

        batch = IngestionBatch(
            id=uuid.uuid4(),
            source_id=source.id,
            file_hash=file_hash,
            raw_count=raw_count,
            deduplicated_count=len(rows),
            quarantined_count=0,
            status="imported",
        )
        session.add(batch)

        records: list[VoiceRecord] = []
        findings: list[PrivacyFinding] = []
        for row in rows:
            privacy = self.privacy_gate(row["_文本"])
            record_id = uuid.uuid4()
            record = VoiceRecord(
                id=record_id,
                source_id=source.id,
                ingestion_batch_id=batch.id,
                external_id=row.get("原声id")
                or hashlib.sha256(row["_文本"].encode("utf-8")).hexdigest(),
                product=row.get(self.product_column) or "未识别",
                sku=row.get("商品id") or None,
                channel=row.get("渠道") or "未知",
                occurred_at=_parse_source_datetime(row.get("原声日期")),
                raw_object_ref=file_path.name,
                normalized_text=privacy.text,
                content_hash=hashlib.sha256(
                    row["_文本"].encode("utf-8")
                ).hexdigest(),
                privacy_status="masked" if privacy.findings else "clean",
                attributes={
                    "sentiment": row.get("原声情感") or "",
                    "voice_type": row.get("原声类型") or "",
                    "store": row.get("店铺名称") or "",
                },
            )
            records.append(record)
            findings.extend(
                PrivacyFinding(
                    id=uuid.uuid4(),
                    voice_record_id=record_id,
                    entity_type=item.entity_type,
                    start_offset=item.start_offset,
                    end_offset=item.end_offset,
                    recognizer=item.recognizer,
                    confidence=item.confidence,
                    action=item.action,
                    review_status="automatic",
                )
                for item in privacy.findings
            )

        session.add_all(records)
        await session.flush()
        session.add_all(findings)
        await session.flush()
        return ImportResult(
            batch_id=batch.id,
            raw_count=raw_count,
            deduplicated_count=len(records),
            quarantined_count=0,
        )


def _parse_source_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        local = datetime.fromisoformat(value)
    except ValueError:
        return None
    if local.tzinfo is None:
        local = local.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return local
