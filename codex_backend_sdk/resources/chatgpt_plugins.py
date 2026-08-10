"""Plugin discovery feeds used by official Codex clients."""

from __future__ import annotations

from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .._client import CodexClient


class ChatGPTPlugins:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def featured(self, *, platform: Literal["codex", "chat"] = "codex") -> list[str]:
        payload = self._client._get_chatgpt(
            "/plugins/featured", params={"platform": platform}
        )
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise RuntimeError("Featured plugins returned an invalid plugin-id list.")
        return payload

    def curated_export(self) -> dict[str, Any]:
        payload = self._client._get_chatgpt("/plugins/export/curated")
        if not isinstance(payload.get("download_url"), str) or not payload["download_url"]:
            raise RuntimeError("Curated plugin export is missing its download URL.")
        return payload
