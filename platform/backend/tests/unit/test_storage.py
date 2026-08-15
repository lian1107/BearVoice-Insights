import pytest

from bearvoice.storage import (
    ApprovedS3ObjectStore,
    FilesystemObjectStore,
    UnapprovedObjectStore,
    UnsafeObjectKey,
)


def test_filesystem_object_store_rejects_path_escape(tmp_path):
    store = FilesystemObjectStore(root=tmp_path / "objects")

    with pytest.raises(UnsafeObjectKey):
        store.put("../outside.txt", b"secret")
    with pytest.raises(UnsafeObjectKey):
        store.put("/absolute.txt", b"secret")
    with pytest.raises(UnsafeObjectKey):
        store.put("nested\\escape.txt", b"secret")

    assert not (tmp_path / "outside.txt").exists()


def test_filesystem_object_store_round_trips_bytes(tmp_path):
    store = FilesystemObjectStore(root=tmp_path / "objects")

    stored = store.put("exports/kettle/report.md", "养生壶".encode())

    assert stored == "exports/kettle/report.md"
    assert store.get(stored).decode() == "养生壶"


def test_s3_store_requires_an_approved_https_endpoint():
    with pytest.raises(UnapprovedObjectStore):
        ApprovedS3ObjectStore(
            endpoint="http://object-store.internal",
            approved_endpoints=("http://object-store.internal",),
            bucket="bearvoice",
            client=object(),
        )
    with pytest.raises(UnapprovedObjectStore):
        ApprovedS3ObjectStore(
            endpoint="https://unapproved.example.com",
            approved_endpoints=("https://objects.example.com",),
            bucket="bearvoice",
            client=object(),
        )
