import hashlib
import json
from pathlib import Path
from typing import Any


class CacheMiss(RuntimeError):
    """Raised when cache-only migration cannot find a verified artifact."""


def strict_cache_path(
    prompt: str,
    tag: str,
    build_dir: Path,
) -> Path:
    key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    return build_dir / f"{tag}-{key}.json"


def load_cached_json(
    prompt: str,
    tag: str,
    build_dir: Path,
) -> Any:
    path = strict_cache_path(prompt, tag, build_dir)
    if not path.is_file():
        raise CacheMiss(f"缓存缺失，禁止补算：{path.name}")
    return json.loads(path.read_text(encoding="utf-8"))
