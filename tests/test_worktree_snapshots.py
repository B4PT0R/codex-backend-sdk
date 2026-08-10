from pathlib import Path

import pytest

from codex_backend_sdk import OpenAI


class FakeResponse:
    def __init__(self, status_code=201):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSnapshotClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _post_wham(self, path, *, body, **kwargs):
        self.calls.append((path, body))
        if path.endswith("upload_url"):
            return {
                "file_id": "snapshot-1",
                "upload_url": "https://storage.example.test/signed",
                "etag": "opaque-etag",
            }
        return {"file_id": body["file_id"]}


def test_worktree_snapshot_create_and_finish_follow_desktop_contract():
    client = FakeSnapshotClient()

    created = client.codex.worktree_snapshots.create_upload(
        repo_name="sdk",
        filename="snapshot.tar.gz",
        content_type="application/gzip",
        anticipated_file_size=42,
    )
    finished = client.codex.worktree_snapshots.finish_upload(
        file_id=created["file_id"], etag=created["etag"]
    )

    assert finished == {"file_id": "snapshot-1"}
    assert client.calls == [
        (
            "/wham/worktree_snapshots/upload_url",
            {
                "repo_name": "sdk",
                "filename": "snapshot.tar.gz",
                "content_type": "application/gzip",
                "anticipated_file_size": 42,
            },
        ),
        (
            "/wham/worktree_snapshots/finish_upload",
            {"file_id": "snapshot-1", "etag": "opaque-etag"},
        ),
    ]


def test_worktree_snapshot_upload_uses_unsigned_storage_request(
    tmp_path: Path, monkeypatch
):
    client = FakeSnapshotClient()
    archive = tmp_path / "snapshot.tar.gz"
    archive.write_bytes(b"archive")
    uploaded = {}

    def fake_put(url, *, data, headers, timeout):
        uploaded.update(
            url=url,
            body=data.read(),
            headers=headers,
            timeout=timeout,
        )
        return FakeResponse()

    monkeypatch.setattr(
        "codex_backend_sdk.resources.worktree_snapshots.requests.put", fake_put
    )

    result = client.codex.worktree_snapshots.upload_archive(
        archive, repo_name="sdk", timeout=12
    )

    assert result == {"file_id": "snapshot-1"}
    assert uploaded == {
        "url": "https://storage.example.test/signed",
        "body": b"archive",
        "headers": {
            "Content-Length": "7",
            "Content-Type": "application/gzip",
        },
        "timeout": 12,
    }
    assert "Authorization" not in uploaded["headers"]


def test_worktree_snapshot_validates_local_and_remote_boundaries(tmp_path: Path):
    client = FakeSnapshotClient()

    with pytest.raises(FileNotFoundError):
        client.codex.worktree_snapshots.upload_archive(
            tmp_path / "missing.tar.gz", repo_name="sdk"
        )
    with pytest.raises(ValueError, match="anticipated_file_size"):
        client.codex.worktree_snapshots.create_upload(
            repo_name="sdk",
            filename="snapshot.tar.gz",
            content_type="application/gzip",
            anticipated_file_size=-1,
        )
    with pytest.raises(ValueError, match="repo_name"):
        client.codex.worktree_snapshots.create_upload(
            repo_name="",
            filename="snapshot.tar.gz",
            content_type="application/gzip",
            anticipated_file_size=0,
        )

    client._post_wham = lambda *args, **kwargs: {"file_id": "snapshot-1"}
    with pytest.raises(RuntimeError, match="upload_url"):
        client.codex.worktree_snapshots.create_upload(
            repo_name="sdk",
            filename="snapshot.tar.gz",
            content_type="application/gzip",
            anticipated_file_size=0,
        )
