"""Realtime resources."""

from __future__ import annotations

import os
from typing import Any, Optional, TYPE_CHECKING

from .._models import RealtimeCallResponse
from .._utils import _UNSET, _is_given, _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


class Realtime:
    """Realtime resources matching the official OpenAI SDK surface where present."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.calls = RealtimeCalls(client)

    def websocket_headers(self, *, session_id: Optional[str] = None) -> dict[str, str]:
        """Return Voice v2 headers backed by an available Realtime API key."""
        store = self._client._store
        api_key = (store.openai_api_key if store else None) or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Realtime Voice v2 requires an OpenAI API key.")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "originator": "codex_cli_rs",
        }
        if session_id:
            headers["x-session-id"] = session_id
        return headers


class RealtimeCalls:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create(
        self,
        *,
        sdp: str,
        session: Any = _UNSET,
        extra_headers: Optional[dict[str, str]] = None,
        extra_query: Optional[dict[str, Any]] = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> RealtimeCallResponse:
        if not sdp:
            raise ValueError(f"Expected a non-empty value for `sdp` but received {sdp!r}")

        if not _is_given(session):
            response = self._client._post_raw(
                "/realtime/calls",
                content=sdp.encode("utf-8"),
                headers={
                    "Accept": "application/sdp",
                    "Content-Type": "application/sdp",
                    **(extra_headers or {}),
                },
                params=extra_query,
                timeout=timeout,
            )
            return RealtimeCallResponse(response)

        response = self._client._post_raw(
            "/realtime/calls",
            body={
                "sdp": sdp,
                "session": _jsonable(session),
                **(_jsonable(extra_body) if extra_body else {}),
            },
            headers={"Accept": "application/sdp", **(extra_headers or {})},
            params=extra_query,
            timeout=timeout,
        )
        return RealtimeCallResponse(response)
