"""Realtime resources."""

from __future__ import annotations

import json
import threading
import urllib.parse
import uuid
from collections.abc import Iterator, Mapping
from typing import Any, Callable, Optional, TYPE_CHECKING

import requests
import websocket

from .._models import LiveCreateResponse, LiveEvent, RealtimeCallResponse
from .._utils import (
    CodexBackendUnsupportedParameterError,
    _UNSET,
    _is_given,
    _jsonable,
)

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


class Live:
    """OpenAI-compatible Live resource backed by ChatGPT OAuth.

    The public API creates ``/live/sessions`` resources. The Codex backend
    instead creates an AVAS call and identifies it by its Realtime call ID;
    this adapter presents that ID as ``response.session.id`` so ordinary Live
    client code can attach the sideband without backend-specific plumbing.
    """

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.sideband = LiveSideband(client)

    def create(
        self,
        *,
        session: Any,
        transport: Any,
        extra_headers: Optional[dict[str, str]] = None,
        extra_query: Optional[dict[str, Any]] = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> LiveCreateResponse:
        """Create a WebRTC Live session using the official request shape."""
        transport_payload = _jsonable(transport)
        if not isinstance(transport_payload, dict):
            raise TypeError("Expected `transport` to serialize to a JSON object.")
        transport_type = transport_payload.get("type", "webrtc")
        if transport_type != "webrtc":
            raise CodexBackendUnsupportedParameterError(
                "The Codex OAuth Live adapter currently supports WebRTC transport only."
            )
        sdp = transport_payload.get("sdp")
        if not isinstance(sdp, str) or not sdp:
            raise ValueError("Expected `transport.sdp` to be a non-empty string.")
        call = self._client.realtime.calls.create_v3(
            sdp=sdp,
            session=session,
            extra_headers=extra_headers,
            extra_query=extra_query,
            extra_body=extra_body,
            timeout=timeout,
        )
        return LiveCreateResponse(
            session={"id": call.call_id},
            transport={"type": "webrtc", "sdp": call.answer_sdp},
        )

    def connect(
        self,
        extra_query: Mapping[str, Any] = {},
        extra_headers: Mapping[str, str] = {},
        websocket_connection_options: Mapping[str, Any] = {},
        on_reconnecting: Optional[Callable[..., Any]] = None,
        max_retries: int = 5,
        initial_delay: float = 0.5,
        max_delay: float = 8.0,
        max_queue_size: int = 1_048_576,
    ) -> None:
        """Reject the unsupported primary-WebSocket path explicitly.

        ChatGPT OAuth currently exposes the WebRTC call plus attached sideband
        used by Codex, not the public API's primary ``live.connect()`` socket.
        """
        del (
            extra_query,
            extra_headers,
            websocket_connection_options,
            on_reconnecting,
            max_retries,
            initial_delay,
            max_delay,
            max_queue_size,
        )
        raise CodexBackendUnsupportedParameterError(
            "ChatGPT OAuth does not expose the public primary Live WebSocket; "
            "create a WebRTC session with `client.live.create()` and attach "
            "with `client.live.sideband.connect()`."
        )


class RealtimeSidebandConnection:
    """JSON transport joined to an existing Realtime v3 WebRTC call."""

    def __init__(self, socket: Any, *, graceful_close: bool = False) -> None:
        self._socket = socket
        self._send_lock = threading.Lock()
        self._graceful_close = graceful_close
        self.closed = False

    def send(self, event: Any) -> None:
        if self.closed:
            raise RuntimeError("Realtime sideband connection is closed.")
        payload = json.dumps(_jsonable(event), ensure_ascii=False)
        with self._send_lock:
            self._socket.send(payload)

    def recv(self) -> dict[str, Any]:
        if self.closed:
            raise RuntimeError("Realtime sideband connection is closed.")
        payload = self._socket.recv()
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        event = json.loads(payload)
        if not isinstance(event, dict):
            raise TypeError("Expected a Realtime sideband event to be a JSON object.")
        return event

    def close(self) -> None:
        if self.closed:
            return
        if self._graceful_close:
            try:
                self.send({"type": "session.close"})
            except Exception:
                pass
        self.closed = True
        self._socket.close()

    def __iter__(self) -> Iterator[dict[str, Any]]:
        while not self.closed:
            try:
                yield self.recv()
            except (IndexError, StopIteration):
                return

    def __enter__(self) -> "RealtimeSidebandConnection":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class LiveSidebandConnection(RealtimeSidebandConnection):
    """Live-shaped event stream over the Codex OAuth sideband dialect."""

    def recv(self) -> LiveEvent:
        return LiveEvent.model_validate(super().recv())

    def __iter__(self) -> Iterator[LiveEvent]:
        while not self.closed:
            try:
                yield self.recv()
            except (IndexError, StopIteration):
                return


class LiveSidebandConnectionManager:
    """Lazy context manager mirroring openai-python's Live sideband idiom."""

    def __init__(
        self,
        sideband: "LiveSideband",
        *,
        session_id: str,
        graceful_close: bool,
        extra_query: Mapping[str, Any],
        extra_headers: Mapping[str, str],
        websocket_connection_options: Mapping[str, Any],
        on_reconnecting: Optional[Callable[..., Any]],
        max_retries: int,
        initial_delay: float,
        max_delay: float,
        max_queue_size: int,
    ) -> None:
        self._sideband = sideband
        self._session_id = session_id
        self._graceful_close = graceful_close
        self._extra_query = dict(extra_query)
        self._extra_headers = dict(extra_headers)
        self._websocket_connection_options = dict(websocket_connection_options)
        self._on_reconnecting = on_reconnecting
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self._max_queue_size = max_queue_size
        self._queued: list[Any] = []
        self._queued_bytes = 0
        self._connection: Optional[RealtimeSidebandConnection] = None

    def send(self, event: Any) -> None:
        if self._connection is not None:
            self._connection.send(event)
            return
        encoded = json.dumps(_jsonable(event), ensure_ascii=False)
        size = len(encoded.encode("utf-8"))
        if self._queued_bytes + size > self._max_queue_size:
            raise RuntimeError("Live sideband send queue exceeded `max_queue_size`.")
        self._queued.append(event)
        self._queued_bytes += size

    def __enter__(self) -> LiveSidebandConnection:
        if self._on_reconnecting is not None:
            raise CodexBackendUnsupportedParameterError(
                "Automatic Live sideband reconnection is not yet supported by "
                "the Codex OAuth adapter."
            )
        self._connection = self._sideband._connect(
            session_id=self._session_id,
            graceful_close=self._graceful_close,
            extra_query=self._extra_query,
            extra_headers=self._extra_headers,
            websocket_connection_options=self._websocket_connection_options,
        )
        for event in self._queued:
            self._connection.send(event)
        self._queued.clear()
        self._queued_bytes = 0
        return self._connection

    enter = __enter__

    def __exit__(self, *_: Any) -> None:
        if self._connection is not None:
            self._connection.close()


class LiveSideband:
    """OpenAI-shaped sideband attachment for an OAuth-backed Live call."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def connect(
        self,
        *,
        session_id: str,
        graceful_close: Any = _UNSET,
        extra_query: Mapping[str, Any] = {},
        extra_headers: Mapping[str, str] = {},
        websocket_connection_options: Mapping[str, Any] = {},
        on_reconnecting: Optional[Callable[..., Any]] = None,
        max_retries: int = 5,
        initial_delay: float = 0.5,
        max_delay: float = 8.0,
        max_queue_size: int = 1_048_576,
    ) -> LiveSidebandConnectionManager:
        if not session_id:
            raise ValueError("Expected a non-empty Live `session_id`.")
        return LiveSidebandConnectionManager(
            self,
            session_id=session_id,
            graceful_close=bool(graceful_close) if _is_given(graceful_close) else False,
            extra_query=extra_query,
            extra_headers=extra_headers,
            websocket_connection_options=websocket_connection_options,
            on_reconnecting=on_reconnecting,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            max_queue_size=max_queue_size,
        )

    def _connect(
        self,
        *,
        session_id: str,
        graceful_close: bool,
        extra_query: Mapping[str, Any],
        extra_headers: Mapping[str, str],
        websocket_connection_options: Mapping[str, Any],
    ) -> LiveSidebandConnection:
        store = self._client._store
        if store is None or not store.access_token:
            raise RuntimeError("Live sideband requires ChatGPT OAuth authentication.")
        headers = {
            "Authorization": f"Bearer {store.access_token}",
            "openai-alpha": "quicksilver=v2",
            "originator": "codex_cli_rs",
        }
        if store.account_id:
            headers["ChatGPT-Account-ID"] = store.account_id
        headers.update(extra_headers)
        query = urllib.parse.urlencode(extra_query, doseq=True)
        url = f"wss://api.openai.com/v1/live/{urllib.parse.quote(session_id, safe='')}"
        if query:
            url = f"{url}?{query}"
        options = dict(websocket_connection_options)
        options.setdefault("timeout", self._client._timeout)
        socket = websocket.create_connection(url, header=headers, **options)
        return LiveSidebandConnection(socket, graceful_close=graceful_close)


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
