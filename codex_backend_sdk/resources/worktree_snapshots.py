"""Cloud worktree snapshot uploads used as Codex task environments."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

import requests

from .._utils import _UNSET, _is_given

if TYPE_CHECKING:
    from .._client import CodexClient


def _required(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"Expected a non-empty value for `{name}` but received {value!r}")
    return value


class CodexWorktreeSnapshots:
    """Upload prepared worktree archives for use by Codex cloud tasks.

    Archive construction is intentionally caller-owned: the official Desktop
    client derives Git metadata and prepares its tarball locally before using
    this transport.
    """

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create_upload(
        self,
        *,
        repo_name: str,
        filename: str,
        content_type: str,
        anticipated_file_size: int,
    ) -> dict[str, Any]:
        if anticipated_file_size < 0:
            raise ValueError("Expected `anticipated_file_size` to be non-negative.")
        payload = self._client._post_wham(
            "/wham/worktree_snapshots/upload_url",
            body={
                "repo_name": _required(repo_name, "repo_name"),
                "filename": _required(filename, "filename"),
                "content_type": _required(content_type, "content_type"),
                "anticipated_file_size": anticipated_file_size,
            },
        )
        self._validate_upload(payload)
        return payload

    def finish_upload(self, *, file_id: str, etag: str) -> dict[str, Any]:
        payload = self._client._post_wham(
            "/wham/worktree_snapshots/finish_upload",
            body={
                "file_id": _required(file_id, "file_id"),
                "etag": _required(etag, "etag"),
            },
        )
        if not isinstance(payload.get("file_id"), str) or not payload["file_id"]:
            raise RuntimeError("Worktree snapshot finalization is missing `file_id`.")
        return payload

    def upload_archive(
        self,
        path: str | Path,
        *,
        repo_name: str,
        content_type: str = "application/gzip",
        timeout: Any = _UNSET,
    ) -> dict[str, Any]:
        archive = Path(path)
        if not archive.exists():
            raise FileNotFoundError(f"path `{archive}` does not exist")
        if not archive.is_file():
            raise ValueError(f"path `{archive}` is not a file")
        size = archive.stat().st_size
        upload = self.create_upload(
            repo_name=repo_name,
            filename=archive.name,
            content_type=content_type,
            anticipated_file_size=size,
        )
        with archive.open("rb") as handle:
            response = requests.put(
                upload["upload_url"],
                data=handle,
                headers={
                    "Content-Length": str(size),
                    "Content-Type": content_type,
                },
                timeout=self._client._timeout if not _is_given(timeout) else timeout,
            )
        response.raise_for_status()
        return self.finish_upload(file_id=upload["file_id"], etag=upload["etag"])

    @staticmethod
    def _validate_upload(payload: dict[str, Any]) -> None:
        for field in ("file_id", "upload_url", "etag"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                raise RuntimeError(
                    f"Worktree snapshot upload response is missing `{field}`."
                )
