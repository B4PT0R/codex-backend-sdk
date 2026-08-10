"""Realtime resources."""

from __future__ import annotations

import os
from typing import Any, Optional, TYPE_CHECKING

from .._models import RealtimeCallResponse
from .._utils import _UNSET, _is_given, _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


CODEX_REALTIME_V3_MODELS = frozenset({
    "gpt-live-1-codex",
    "gpt-live-1-boulder-alpha",
})


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
    """Codex WebRTC call creation over ChatGPT OAuth.

    Realtime v3 uses the JSON call shape with one of the explicitly supported
    Codex ``gpt-live`` snapshots. Arbitrary ``gpt-live`` aliases are not accepted
    on this OAuth-authenticated route. The
    public ``gpt-realtime`` model belongs to the API-key Realtime surface and is
    not interchangeable with the OAuth-authenticated Codex v3 route.
    """
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

        session_payload = _jsonable(session)
        if not isinstance(session_payload, dict):
            raise TypeError("Expected `session` to serialize to a JSON object.")
        session_payload.pop("id", None)
        body = {
            "sdp": sdp,
            "session": session_payload,
            **(_jsonable(extra_body) if extra_body else {}),
        }
        query = {"intent": "quicksilver", "architecture": "avas"}
        if extra_query:
            query.update(extra_query)
        response = self._client._post_raw(
            "/realtime/calls",
            body=body,
            headers={"Accept": "application/sdp", **(extra_headers or {})},
            params=query,
            timeout=timeout,
        )
        return RealtimeCallResponse(response)

    def create_v3(
        self,
        *,
        sdp: str,
        session: Any,
        extra_headers: Optional[dict[str, str]] = None,
        extra_query: Optional[dict[str, Any]] = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> RealtimeCallResponse:
        """Create a Codex Realtime v3 call using a confirmed Codex model."""
        session_payload = _jsonable(session)
        if not isinstance(session_payload, dict):
            raise TypeError("Expected `session` to serialize to a JSON object.")
        model = session_payload.get("model")
        if model not in CODEX_REALTIME_V3_MODELS:
            supported = ", ".join(sorted(CODEX_REALTIME_V3_MODELS))
            raise ValueError(
                "Codex Realtime v3 over ChatGPT OAuth requires "
                f"one of these `session.model` values: {supported}."
            )
        headers = {**(extra_headers or {}), "openai-alpha": "quicksilver=v2"}
        return self.create(
            sdp=sdp,
            session=session_payload,
            extra_headers=headers,
            extra_query=extra_query,
            extra_body=extra_body,
            timeout=timeout,
        )
