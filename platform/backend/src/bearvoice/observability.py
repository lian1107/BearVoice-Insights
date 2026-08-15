import re
from typing import Any


_SENSITIVE_PATTERNS = (
    re.compile(r"\b(?:sk-|ghp_)[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|token|secret)\s*[:=]\s*[^\s,;]+"
)


def redact_sensitive(message: str) -> str:
    redacted = message
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return _ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )


def build_trace_attributes(
    *,
    run_id: str,
    phase: str,
    provider: str,
    model: str | None,
    input_hash: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "phase": phase,
        "provider": provider,
        "model": model or "none",
        "input_hash": input_hash,
    }
