import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlparse

from bearvoice.config import Settings


class UnsafeObjectKey(ValueError):
    pass


class UnapprovedObjectStore(ValueError):
    pass


class ObjectStore(Protocol):
    def put(self, key: str, payload: bytes) -> str: ...

    def get(self, key: str) -> bytes: ...


def _validated_parts(key: str) -> tuple[str, ...]:
    if not key or "\\" in key or "\x00" in key:
        raise UnsafeObjectKey("对象键必须使用非空 POSIX 相对路径")
    path = PurePosixPath(key)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeObjectKey("对象键不得使用绝对路径或跳出存储根目录")
    return path.parts


class FilesystemObjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = self.root.joinpath(*_validated_parts(key)).resolve()
        if not candidate.is_relative_to(self.root):
            raise UnsafeObjectKey("对象键跳出存储根目录")
        return candidate

    def put(self, key: str, payload: bytes) -> str:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
        )
        try:
            with os.fdopen(handle, "wb") as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class S3Client(Protocol):
    def put_object(self, **kwargs: object) -> object: ...

    def get_object(self, **kwargs: object) -> dict[str, object]: ...


class ApprovedS3ObjectStore:
    def __init__(
        self,
        *,
        endpoint: str,
        approved_endpoints: tuple[str, ...],
        bucket: str,
        client: S3Client,
    ):
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or endpoint not in approved_endpoints:
            raise UnapprovedObjectStore("S3 端点必须是管理员批准的 HTTPS 地址")
        if not bucket.strip():
            raise UnapprovedObjectStore("S3 bucket 不能为空")
        self.endpoint = endpoint
        self.bucket = bucket
        self.client = client

    def put(self, key: str, payload: bytes) -> str:
        _validated_parts(key)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=payload)
        return key

    def get(self, key: str) -> bytes:
        _validated_parts(key)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        return body.read()


def create_object_store(
    settings: Settings,
    *,
    s3_client: S3Client | None = None,
) -> ObjectStore:
    if settings.storage_backend == "filesystem":
        return FilesystemObjectStore(Path(settings.object_store_root))
    if s3_client is None or settings.s3_endpoint_url is None:
        raise UnapprovedObjectStore("S3 存储需要批准端点和企业客户端")
    return ApprovedS3ObjectStore(
        endpoint=settings.s3_endpoint_url,
        approved_endpoints=settings.s3_endpoint_allowlist,
        bucket=settings.s3_bucket,
        client=s3_client,
    )
