import csv
import hashlib
import io
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
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


CANONICAL_FIELDS: dict[str, dict[str, object]] = {
    "voice_id": {
        "label": "原声 ID",
        "required": True,
        "aliases": (
            "原声id",
            "原声ID",
            "原声_id",
            "评论id",
            "评论ID",
            "评论编号",
            "反馈id",
            "voice_id",
            "feedback_id",
            "id",
        ),
    },
    "text": {
        "label": "原声内容",
        "required": True,
        "aliases": ("原声内容", "客户原声", "评论内容", "反馈内容", "内容", "文本", "voice_text", "comment"),
    },
    "product": {
        "label": "商品标题",
        "required": True,
        "aliases": ("商品标题", "商品名称", "产品", "产品名称", "product", "product_name"),
    },
    "sku": {
        "label": "SKU",
        "required": False,
        "aliases": ("SKU", "sku", "商品id", "商品ID", "商品编码", "型号"),
    },
    "occurred_at": {
        "label": "时间",
        "required": False,
        "aliases": ("原声日期", "时间", "日期", "创建时间", "occurred_at", "created_at"),
    },
    "channel": {
        "label": "渠道",
        "required": False,
        "aliases": ("渠道", "来源渠道", "平台", "channel"),
    },
    "anonymous_user_key": {
        "label": "匿名用户键",
        "required": False,
        "aliases": ("匿名用户键", "匿名用户ID", "用户id", "用户ID", "buyer_key", "user_id"),
    },
    "order_id": {
        "label": "订单",
        "required": False,
        "aliases": ("订单号", "订单ID", "订单id", "order_id", "order_no"),
    },
    "batch": {
        "label": "生产批次",
        "required": False,
        "aliases": ("生产批次", "批次号", "批次", "batch", "batch_no"),
    },
    "version": {
        "label": "版本",
        "required": False,
        "aliases": ("产品版本", "固件版本", "版本", "version", "firmware_version"),
    },
    "sentiment": {
        "label": "情感",
        "required": False,
        "aliases": ("原声情感", "情感", "sentiment"),
    },
    "voice_type": {
        "label": "原声类型",
        "required": False,
        "aliases": ("原声类型", "类型", "voice_type"),
    },
    "store": {
        "label": "店铺",
        "required": False,
        "aliases": ("店铺名称", "店铺", "store"),
    },
}


def _normalized_header(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value).casefold()


def suggest_field_mapping(columns: list[str]) -> list[dict[str, object]]:
    """Return deterministic, explainable candidates; no model is called here."""
    normalized_columns = {_normalized_header(column): column for column in columns}
    suggestions: list[dict[str, object]] = []
    for canonical, metadata in CANONICAL_FIELDS.items():
        aliases = metadata["aliases"]
        assert isinstance(aliases, tuple)
        match = next(
            (
                normalized_columns[_normalized_header(alias)]
                for alias in aliases
                if _normalized_header(alias) in normalized_columns
            ),
            None,
        )
        suggestions.append(
            {
                "field": canonical,
                "label": metadata["label"],
                "required": metadata["required"],
                "suggested_column": match,
                "confidence": 1.0 if match else 0.0,
                "method": "deterministic_alias_rules",
                "reason": "列名命中已知别名" if match else "未找到可靠别名，需人工选择",
            }
        )
    return suggestions


def _decode_csv(content: bytes) -> tuple[str, str]:
    encoding = "utf-8-sig" if content.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        return content.decode(encoding), encoding
    except UnicodeDecodeError as error:
        raise ValueError("CSV 必须使用 UTF-8 编码；请转码后重试") from error


def _read_csv(content: bytes) -> tuple[list[str], list[dict[str | None, Any]], str]:
    text, encoding = _decode_csv(content)
    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        raw_columns = reader.fieldnames or []
        columns = [column.strip() for column in raw_columns if column]
        raw_rows = list(reader)
    except csv.Error as error:
        raise ValueError("CSV 内容无法解析，请检查引号、换行和分隔符") from error
    if not columns:
        raise ValueError("CSV 缺少表头")
    if len(columns) != len(set(columns)):
        raise ValueError("CSV 存在重复列名，请先重命名")
    rows: list[dict[str | None, Any]] = []
    for raw_row in raw_rows:
        row: dict[str | None, Any] = {}
        for key, value in raw_row.items():
            if key is None:
                row[None] = value
            elif key.strip():
                row[key.strip()] = value
            elif value and str(value).strip():
                row[None] = [value]
        rows.append(row)
    return columns, rows, encoding


def _duplicate_counts(values: list[str]) -> int:
    return sum(count - 1 for count in Counter(values).values() if count > 1)


def _template_signature(value: str) -> str:
    normalized = re.sub(r"\d+", "", value.casefold())
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)


def preview_csv_bytes(content: bytes) -> dict[str, object]:
    columns, rows, encoding = _read_csv(content)
    suggestions = suggest_field_mapping(columns)
    mapping = {
        str(item["field"]): str(item["suggested_column"])
        for item in suggestions
        if item["suggested_column"]
    }
    quarantine_reasons: Counter[str] = Counter()
    quarantined_rows: set[int] = set()
    for index, row in enumerate(rows):
        if None in row:
            quarantine_reasons["列数多于表头"] += 1
            quarantined_rows.add(index)
        if any(value is None for key, value in row.items() if key is not None):
            quarantine_reasons["列数少于表头"] += 1
            quarantined_rows.add(index)
        text_column = mapping.get("text")
        if text_column and not str(row.get(text_column) or "").strip():
            quarantine_reasons["原声内容为空"] += 1
            quarantined_rows.add(index)
        id_column = mapping.get("voice_id")
        if id_column and not str(row.get(id_column) or "").strip():
            quarantine_reasons["原声 ID 为空"] += 1
            quarantined_rows.add(index)
        product_column = mapping.get("product")
        if product_column and not str(row.get(product_column) or "").strip():
            quarantine_reasons["商品标题为空"] += 1
            quarantined_rows.add(index)

    profiles: list[dict[str, object]] = []
    for column in columns:
        values = [str(row.get(column) or "").strip() for row in rows]
        non_empty = [value for value in values if value]
        profiles.append(
            {
                "column": column,
                "null_rate": round((len(values) - len(non_empty)) / len(values), 4)
                if values
                else 0.0,
                "unique_rate": round(len(set(non_empty)) / len(non_empty), 4)
                if non_empty
                else 0.0,
            }
        )

    text_column = mapping.get("text")
    id_column = mapping.get("voice_id")
    texts = [
        re.sub(r"\s+", " ", str(row.get(text_column) or "")).strip()
        for row in rows
        if text_column and str(row.get(text_column) or "").strip()
    ]
    ids = [
        str(row.get(id_column) or "").strip()
        for row in rows
        if id_column and str(row.get(id_column) or "").strip()
    ]
    exact_duplicate_count = _duplicate_counts(texts)
    duplicate_id_count = _duplicate_counts(ids)
    signatures = [_template_signature(value) for value in texts]
    template_noise_count = max(0, _duplicate_counts(signatures) - exact_duplicate_count)
    date_column = mapping.get("occurred_at")
    date_values = [
        str(row.get(date_column) or "").strip()
        for row in rows
        if date_column and str(row.get(date_column) or "").strip()
    ]
    date_parse_rate = (
        round(
            sum(_parse_source_datetime(value) is not None for value in date_values)
            / len(date_values),
            4,
        )
        if date_values
        else None
    )
    missing_required = [
        str(item["field"])
        for item in suggestions
        if item["required"] and not item["suggested_column"]
    ]
    hints: list[str] = []
    if missing_required:
        labels = [
            str(CANONICAL_FIELDS[field]["label"])
            for field in missing_required
        ]
        hints.append(f"未自动匹配必填字段：{', '.join(labels)}，请手动确认")
    if duplicate_id_count:
        hints.append(f"发现 {duplicate_id_count} 条重复原声 ID，导入时会去重")
    if exact_duplicate_count:
        hints.append(f"发现 {exact_duplicate_count} 条完全重复文本")
    if template_noise_count:
        hints.append(f"发现约 {template_noise_count} 条近重复或模板化文本，建议抽样复核")
    if date_parse_rate is not None and date_parse_rate < 1:
        hints.append(f"时间字段解析率为 {date_parse_rate:.0%}，失败值将保留但时间置空")
    return {
        "encoding": encoding,
        "row_count": len(rows),
        "columns": columns,
        "required_fields_matched": not missing_required,
        "missing_required_fields": missing_required,
        "mapping_suggestions": suggestions,
        "column_mapping": mapping,
        "column_profiles": profiles,
        "date_parse_rate": date_parse_rate,
        "duplicate_id_count": duplicate_id_count,
        "exact_duplicate_count": exact_duplicate_count,
        "near_duplicate_or_template_count": template_noise_count,
        "quality_hints": hints,
        "quarantined_count": len(quarantined_rows),
        "quarantine_reasons": [
            {"reason": reason, "count": count}
            for reason, count in quarantine_reasons.items()
        ],
        "suggestion_method": "deterministic_alias_rules",
        "ai_used": False,
    }


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
    def __init__(
        self,
        source_name: str,
        product_column: str,
        *,
        channel: str = "天猫",
        product_name: str | None = None,
        column_mapping: dict[str, str] | None = None,
    ) -> None:
        self.source_name = source_name
        self.product_column = product_column
        self.channel = channel
        self.product_name = product_name
        self._mapping_was_explicit = column_mapping is not None
        self.column_mapping = column_mapping or {
            "voice_id": "原声id",
            "text": "原声内容",
            "product": product_column,
            "sku": "商品id",
            "occurred_at": "原声日期",
            "channel": "渠道",
            "sentiment": "原声情感",
            "voice_type": "原声类型",
            "store": "店铺名称",
        }

    def _column(self, canonical: str) -> str | None:
        return self.column_mapping.get(canonical)

    def _value(self, row: dict[str, str], canonical: str) -> str:
        column = self._column(canonical)
        return (row.get(column) or "").strip() if column else ""

    def validate(self, rows: list[dict[str, str]]) -> None:
        if not rows:
            raise ValueError("CSV 没有可导入的原声")
        required_fields = ("voice_id", "text", "product")
        missing_mapping = [field for field in required_fields if not self._column(field)]
        if missing_mapping:
            raise ValueError(f"字段映射缺少必填项：{', '.join(missing_mapping)}")
        unknown = set(self.column_mapping) - set(CANONICAL_FIELDS)
        if unknown:
            raise ValueError(f"字段映射包含未知项：{', '.join(sorted(unknown))}")
        mapped_columns = [column for column in self.column_mapping.values() if column]
        if len(mapped_columns) != len(set(mapped_columns)):
            raise ValueError("同一 CSV 列不能映射到多个字段")
        columns_to_validate = (
            set(mapped_columns)
            if self._mapping_was_explicit
            else {self._column(field) for field in required_fields}
        )
        missing = columns_to_validate - set(rows[0])
        if missing:
            raise ValueError(f"CSV 不存在已映射列：{', '.join(sorted(missing))}")

    def normalize(self, row: dict[str, str]) -> dict[str, str]:
        normalized = dict(row)
        normalized["_文本"] = re.sub(
            r"\s+",
            " ",
            self._value(row, "text").replace("<br>", " / "),
        ).strip()
        return normalized

    def dedupe(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for row in rows:
            key = self._value(row, "voice_id") or hashlib.sha256(
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
        return await self.import_bytes(
            session,
            content,
            object_ref=file_path.name,
        )

    async def import_bytes(
        self,
        session: AsyncSession,
        content: bytes,
        *,
        object_ref: str,
    ) -> ImportResult:
        file_hash = hashlib.sha256(content).hexdigest()
        _columns, all_rows, _encoding = _read_csv(content)
        typed_rows = [
            {str(key): str(value or "") for key, value in row.items() if key is not None}
            for row in all_rows
            if None not in row and all(value is not None for value in row.values())
        ]
        self.validate(typed_rows)
        raw_rows = [
            row
            for row in typed_rows
            if all(self._value(row, field) for field in ("voice_id", "text", "product"))
        ]
        if not raw_rows:
            raise ValueError("CSV 没有通过必填字段校验的可导入原声")
        normalized = [self.normalize(row) for row in raw_rows]
        unique = self.dedupe(normalized)
        return await self.persist(
            session,
            unique,
            object_ref=object_ref,
            file_hash=file_hash,
            raw_count=len(all_rows),
            quarantined_count=len(all_rows) - len(raw_rows),
        )

    async def persist(
        self,
        session: AsyncSession,
        rows: list[dict[str, str]],
        *,
        object_ref: str,
        file_hash: str,
        raw_count: int,
        quarantined_count: int = 0,
    ) -> ImportResult:
        source = await session.scalar(
            select(Source).where(Source.name == self.source_name)
        )
        if source is None:
            source = Source(
                id=uuid.uuid4(),
                source_type="csv",
                name=self.source_name,
                channel=self.channel,
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

        external_ids = [
            self._value(row, "voice_id")
            or hashlib.sha256(row["_文本"].encode("utf-8")).hexdigest()
            for row in rows
        ]
        existing_external_ids = set(
            await session.scalars(
                select(VoiceRecord.external_id).where(
                    VoiceRecord.source_id == source.id,
                    VoiceRecord.external_id.in_(external_ids),
                )
            )
        )
        new_rows = [
            row
            for row, external_id in zip(rows, external_ids, strict=True)
            if external_id not in existing_external_ids
        ]

        occurred_values = [
            parsed
            for row in new_rows
            if (parsed := _parse_source_datetime(self._value(row, "occurred_at"))) is not None
        ]
        batch = IngestionBatch(
            id=uuid.uuid4(),
            source_id=source.id,
            file_hash=file_hash,
            period_start=min(occurred_values, default=None),
            period_end=max(occurred_values, default=None),
            raw_count=raw_count,
            deduplicated_count=len(new_rows),
            quarantined_count=quarantined_count,
            status="imported",
        )
        session.add(batch)

        records: list[VoiceRecord] = []
        findings: list[PrivacyFinding] = []
        for row in new_rows:
            privacy = self.privacy_gate(row["_文本"])
            record_id = uuid.uuid4()
            record = VoiceRecord(
                id=record_id,
                source_id=source.id,
                ingestion_batch_id=batch.id,
                external_id=self._value(row, "voice_id")
                or hashlib.sha256(row["_文本"].encode("utf-8")).hexdigest(),
                product=self.product_name or self._value(row, "product") or "未识别",
                sku=self._value(row, "sku") or None,
                channel=self._value(row, "channel") or self.channel,
                occurred_at=_parse_source_datetime(self._value(row, "occurred_at")),
                raw_object_ref=object_ref,
                normalized_text=privacy.text,
                content_hash=hashlib.sha256(
                    row["_文本"].encode("utf-8")
                ).hexdigest(),
                privacy_status="masked" if privacy.findings else "clean",
                attributes=self._business_attributes(row),
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
            quarantined_count=quarantined_count,
        )

    def _business_attributes(self, row: dict[str, str]) -> dict[str, str]:
        attributes = {
            key: self._value(row, key)
            for key in ("sku", "batch", "version", "sentiment", "voice_type", "store")
            if self._value(row, key)
        }
        for source_key, target_key in (
            ("anonymous_user_key", "anonymous_user_key_hash"),
            ("order_id", "order_id_hash"),
        ):
            value = self._value(row, source_key)
            if value:
                attributes[target_key] = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return attributes


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
