"""ChatGPT file upload helpers used by Codex Apps tools."""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

import requests

from .._models import UploadedFile
from .._utils import _UNSET, _is_given

if TYPE_CHECKING:
    from .._client import CodexClient

FILE_URI_PREFIX = "sediment://"
FILE_UPLOAD_LIMIT_BYTES = 512 * 1024 * 1024
FILE_USE_CASE = "codex"


class Files:
    """File uploads for Codex Apps/MCP file parameters."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def upload(
        self,
        path: str | Path,
        *,
        timeout: Any = _UNSET,
        finalize_timeout: float = 30,
        finalize_retry_delay: float = 0.25,
    ) -> UploadedFile:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"path `{file_path}` does not exist")
        if not file_path.is_file():
            raise ValueError(f"path `{file_path}` is not a file")

        size = file_path.stat().st_size
        if size > FILE_UPLOAD_LIMIT_BYTES:
            raise ValueError(
                f"file `{file_path}` is too large: {size} bytes exceeds "
                f"the limit of {FILE_UPLOAD_LIMIT_BYTES} bytes"
            )

        file_name = file_path.name or "file"
        create_payload = self._client._post_chatgpt(
            "/files",
            body={"file_name": file_name, "file_size": size, "use_case": FILE_USE_CASE},
            timeout=timeout,
        )
        file_id = create_payload["file_id"]
        upload_url = create_payload["upload_url"]

        with file_path.open("rb") as handle:
            upload_response = requests.put(
                upload_url,
                data=handle,
                headers={
                    "x-ms-blob-type": "BlockBlob",
                    "Content-Length": str(size),
                },
                timeout=self._request_timeout(timeout),
            )
        upload_response.raise_for_status()

        finalize_payload = self._finalize_upload(
            file_id,
            timeout=timeout,
            finalize_timeout=finalize_timeout,
            finalize_retry_delay=finalize_retry_delay,
        )
        return UploadedFile(
            file_id=file_id,
            uri=f"{FILE_URI_PREFIX}{file_id}",
            download_url=finalize_payload["download_url"],
            file_name=finalize_payload.get("file_name") or file_name,
            file_size_bytes=size,
            mime_type=finalize_payload.get("mime_type") or mimetypes.guess_type(file_name)[0],
            path=str(file_path),
        )

    def _finalize_upload(
        self,
        file_id: str,
        *,
        timeout: Any,
        finalize_timeout: float,
        finalize_retry_delay: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + finalize_timeout
        while True:
            payload = self._client._post_chatgpt(
                f"/files/{file_id}/uploaded",
                body={},
                timeout=timeout,
            )
            status = payload.get("status")
            if status == "success":
                if not payload.get("download_url"):
                    raise RuntimeError(f"OpenAI file upload for `{file_id}` failed: missing download_url")
                return payload
            if status == "retry" and time.monotonic() < deadline:
                time.sleep(finalize_retry_delay)
                continue
            if status == "retry":
                raise TimeoutError(f"OpenAI file upload for `{file_id}` is not ready yet")
            message = payload.get("error_message") or "upload finalization returned an error"
            raise RuntimeError(f"OpenAI file upload for `{file_id}` failed: {message}")

    def _request_timeout(self, timeout: Any) -> Any:
        return self._client._timeout if not _is_given(timeout) else timeout
