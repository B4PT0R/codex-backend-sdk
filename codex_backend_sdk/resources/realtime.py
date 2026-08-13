"""Realtime resources."""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any, Optional, TYPE_CHECKING

import requests
import websocket

from .._models import RealtimeCallResponse
from .._utils import _UNSET, _jsonable

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
        self.sideband = RealtimeSideband(client)

class RealtimeSidebandConnection:
    """JSON transport joined to an existing Realtime v3 WebRTC call."""

    def __init__(self, socket: Any) -> None:
        self._socket = socket
        self._send_lock = threading.Lock()

    def send(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        with self._send_lock:
            self._socket.send(payload)

    def recv(self) -> dict[str, Any]:
        payload = self._socket.recv()
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        event = json.loads(payload)
        if not isinstance(event, dict):
            raise TypeError("Expected a Realtime sideband event to be a JSON object.")
        return event

    def close(self) -> None:
        self._socket.close()


class RealtimeSideband:
    """Join the control/delegation channel of a Realtime v3 WebRTC call."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def connect(
        self,
        *,
        call_id: str,
        session_id: Optional[str] = None,
        timeout: Optional[float] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> RealtimeSidebandConnection:
        if not call_id:
            raise ValueError("Expected a non-empty Realtime `call_id`.")
        store = self._client._store
        if store is None or not store.access_token:
            raise RuntimeError("Realtime v3 sideband requires ChatGPT OAuth authentication.")
        headers = {
            "Authorization": f"Bearer {store.access_token}",
            "openai-alpha": "quicksilver=v2",
            "originator": "codex_cli_rs",
        }
        if store.account_id:
            headers["ChatGPT-Account-ID"] = store.account_id
        if session_id:
            headers["x-session-id"] = session_id
        headers.update(extra_headers or {})
        socket = websocket.create_connection(
            f"wss://api.openai.com/v1/live/{call_id}",
            header=headers,
            timeout=self._client._timeout if timeout is None else timeout,
        )
        return RealtimeSidebandConnection(socket)


class RealtimeCalls:
    """Codex WebRTC call creation over ChatGPT OAuth.

    Realtime v3 uses the JSON call shape with one of the explicitly supported
    Codex ``gpt-live`` snapshots. Arbitrary ``gpt-live`` aliases are not accepted
    on this OAuth-authenticated route.
    """
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create_v3(
        self,
        *,
        sdp: str,
        session: Any,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        extra_headers: Optional[dict[str, str]] = None,
        extra_query: Optional[dict[str, Any]] = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> RealtimeCallResponse:
        """Create a Codex Realtime v3 call using a confirmed Codex model.

        The ChatGPT backend requires both ``session-id`` and ``thread-id`` on
        v3 call creation. Fresh UUIDs are generated when callers do not need
        to correlate the call with their own persistent identities.
        """
        if not sdp:
            raise ValueError(f"Expected a non-empty value for `sdp` but received {sdp!r}")
        session_payload = _jsonable(session)
        if not isinstance(session_payload, dict):
            raise TypeError("Expected `session` to serialize to a JSON object.")
        session_payload.pop("id", None)
        model = session_payload.get("model")
        if model not in CODEX_REALTIME_V3_MODELS:
            supported = ", ".join(sorted(CODEX_REALTIME_V3_MODELS))
            raise ValueError(
                "Codex Realtime v3 over ChatGPT OAuth requires "
                f"one of these `session.model` values: {supported}."
            )
        headers = {
            "session-id": session_id or str(uuid.uuid4()),
            "thread-id": thread_id or str(uuid.uuid4()),
            **(extra_headers or {}),
            "openai-alpha": "quicksilver=v2",
        }
        query = {"intent": "quicksilver", "architecture": "avas"}
        if extra_query:
            query.update(extra_query)
        body = {
            "sdp": sdp,
            "session": session_payload,
            **(_jsonable(extra_body) if extra_body else {}),
        }
        try:
            response = self._client._post_raw(
                "/realtime/calls",
                body=body,
                headers={"Accept": "application/sdp", **headers},
                params=query,
                timeout=timeout,
            )
        except requests.HTTPError as exc:
            response = exc.response
            if response is None:
                raise
            detail = response.text.strip()
            request_id = response.headers.get("x-request-id")
            message = f"Codex Realtime call creation failed ({response.status_code})"
            if detail:
                message += f": {detail}"
            if request_id:
                message += f" [request_id={request_id}]"
            raise requests.HTTPError(message, response=response, request=exc.request) from exc
        return RealtimeCallResponse(response)
