"""Realtime resources."""

from __future__ import annotations

import json
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

        files = [
            ("sdp", (None, sdp.encode("utf-8"), "application/sdp")),
            (
                "session",
                (None, json.dumps(_jsonable(session)).encode("utf-8"), "application/json"),
            ),
        ]
        response = self._client._post_raw(
            "/realtime/calls",
            files=files,
            data=extra_body,
            headers={"Accept": "application/sdp", **(extra_headers or {})},
            params=extra_query,
            timeout=timeout,
        )
        return RealtimeCallResponse(response)
