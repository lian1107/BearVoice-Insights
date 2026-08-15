import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PrivacyFindingData:
    entity_type: str
    start_offset: int
    end_offset: int
    recognizer: str
    confidence: float
    action: str
    replacement: str


@dataclass(frozen=True)
class SanitizedVoice:
    text: str
    findings: tuple[PrivacyFindingData, ...]


PrivacyRecognizer = Callable[[str], Iterable[PrivacyFindingData]]

_ADDRESS_MARKER_RE = re.compile(
    r"(?:省|自治区|市|县|区|镇|乡|街道|街|路|巷|村|小区|市场|门口)"
)
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ORDER_RE = re.compile(r"(?:订单号|单号)\s*[:：]?\s*([A-Za-z0-9-]{8,})")
_CUSTOM_RECOGNIZERS: list[PrivacyRecognizer] = []


def _address_findings(text: str) -> Iterable[PrivacyFindingData]:
    for segment in re.finditer(r"[^/]+", text):
        raw = segment.group()
        if len(_ADDRESS_MARKER_RE.findall(raw)) < 2:
            continue
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        start = segment.start() + leading
        end = segment.start() + trailing
        if start < end:
            yield PrivacyFindingData(
                entity_type="address",
                start_offset=start,
                end_offset=end,
                recognizer="zh_address_segment_v1",
                confidence=0.85,
                action="mask",
                replacement="[地址已脱敏]",
            )


def _regex_findings(text: str) -> Iterable[PrivacyFindingData]:
    for match in _PHONE_RE.finditer(text):
        yield PrivacyFindingData(
            entity_type="phone",
            start_offset=match.start(),
            end_offset=match.end(),
            recognizer="zh_mobile_v1",
            confidence=0.99,
            action="mask",
            replacement="[手机号已脱敏]",
        )
    for match in _ORDER_RE.finditer(text):
        yield PrivacyFindingData(
            entity_type="order_id",
            start_offset=match.start(1),
            end_offset=match.end(1),
            recognizer="contextual_order_id_v1",
            confidence=0.95,
            action="mask",
            replacement="[订单号已脱敏]",
        )


def register_privacy_recognizer(recognizer: PrivacyRecognizer) -> None:
    if recognizer not in _CUSTOM_RECOGNIZERS:
        _CUSTOM_RECOGNIZERS.append(recognizer)


def _remove_overlaps(
    findings: list[PrivacyFindingData],
) -> list[PrivacyFindingData]:
    ranked = sorted(
        findings,
        key=lambda item: (
            -(item.end_offset - item.start_offset),
            item.start_offset,
        ),
    )
    accepted: list[PrivacyFindingData] = []
    for candidate in ranked:
        overlaps = any(
            candidate.start_offset < item.end_offset
            and item.start_offset < candidate.end_offset
            for item in accepted
        )
        if not overlaps:
            accepted.append(candidate)
    return sorted(accepted, key=lambda item: item.start_offset)


def sanitize_voice_text(text: str) -> SanitizedVoice:
    findings = list(_address_findings(text))
    findings.extend(_regex_findings(text))
    for recognizer in _CUSTOM_RECOGNIZERS:
        findings.extend(recognizer(text))
    accepted = _remove_overlaps(findings)

    safe_text = text
    for finding in reversed(accepted):
        safe_text = (
            safe_text[: finding.start_offset]
            + finding.replacement
            + safe_text[finding.end_offset :]
        )
    return SanitizedVoice(text=safe_text, findings=tuple(accepted))
