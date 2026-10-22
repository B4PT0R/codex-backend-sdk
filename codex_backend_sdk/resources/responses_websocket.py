"""Low-level Responses WebSocket transport used by current Codex."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
import threading
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .._client import CodexClient

RESPONSES_WEBSOCKET_URL = "wss://chatgpt.com/backend-api/codex/responses"
_TERMINAL_EVENTS = {"response.completed", "response.failed", "response.incomplete"}


class ResponsesWebSocketError(RuntimeError):
    """Error envelope returned inside an upgraded Responses connection."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        event: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.event = event


class ResponsesWebSocketConnection:
    """One sequential, reusable Responses WebSocket connection."""

    def __init__(self, socket: Any, *, url: str) -> None:
        self._socket = socket
        self.url = url
        self._request_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._response_id: str | None = None
        self._interrupt_requested = False
        self._interrupt_pending = False
        self.closed = False
        headers = _handshake_headers(socket)
        self.reasoning_included = "x-reasoning-included" in headers
        self.models_etag = headers.get("x-models-etag")
        self.server_model = headers.get("openai-model")
        self.turn_state = headers.get("x-codex-turn-state")

    def events(self, request: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        """Send one ``response.create`` request and yield raw JSON events.

        A connection handles one active response at a time, matching Codex's
        exclusive stream ownership. It can be reused sequentially until closed.
        """
        if self.closed:
            raise RuntimeError("Responses WebSocket connection is closed.")
        if not isinstance(request, Mapping):
            raise TypeError("Expected `request` to be a mapping.")
        payload = dict(request)
        kind = payload.setdefault("type", "response.create")
        if kind != "response.create":
            raise ValueError("Responses WebSocket currently supports `response.create` only.")
        try:
            encoded = json.dumps(payload, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise TypeError("Responses WebSocket request is not JSON serializable.") from exc

        if not self._request_lock.acquire(blocking=False):
            raise RuntimeError(
                "Responses WebSocket connection already has an active response."
            )
        finished = False
        try:
            with self._state_lock:
                self._response_id = None
                self._interrupt_requested = False
                self._interrupt_pending = False
                self._socket.send(encoded)
            terminal = False
            while True:
                raw = self._socket.recv()
                if raw in {None, "", b""}:
                    raise RuntimeError(
                        "Responses WebSocket closed before a terminal response event."
                    )
                if isinstance(raw, bytes):
                    raise RuntimeError("Responses WebSocket returned unexpected binary data.")
                try:
                    event = json.loads(raw)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("Responses WebSocket returned invalid JSON.") from exc
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise RuntimeError(
                        "Responses WebSocket returned an invalid event envelope."
                    )
                if event["type"] == "error":
                    raise _event_error(event)
                with self._state_lock:
                    if event["type"] == "response.created":
                        response = event.get("response")
                        response_id = response.get("id") if isinstance(response, dict) else None
                        if isinstance(response_id, str) and response_id:
                            self._response_id = response_id
                    elif event["type"] in {
                        "response.interrupt.accepted", "response.interrupt.failed"
                    }:
                        if (
                            not self._interrupt_pending
                            or event.get("response_id") != self._response_id
                        ):
                            raise RuntimeError("Unexpected response interruption acknowledgement.")
                        if event["type"] == "response.interrupt.failed":
                            raise RuntimeError("Response interruption was rejected.")
                        self._interrupt_pending = False
                    if event["type"] in _TERMINAL_EVENTS:
                        terminal = True
                        # Prevent a late interrupt after completion while draining its ack.
                        self._interrupt_requested = True
                    done = terminal and not self._interrupt_pending
                    if done:
                        self._response_id = None
                        finished = True
                yield event
                if done:
                    return
        except Exception:
            if not self.closed:
                try:
                    self.close()
                except Exception:
                    self.closed = True
            raise
        finally:
            try:
                with self._state_lock:
                    self._response_id = None
                    if not finished:
                        self.close()
            finally:
                self._request_lock.release()

    def interrupt(self) -> None:
        """Interrupt the active response, discarding partial items.

        Call after ``response.created``, including from another thread while
        reading events. Continue consuming through both the acknowledgement
        and terminal response event before reusing the connection.
        """
        with self._state_lock:
            if self.closed:
                raise RuntimeError("Responses WebSocket connection is closed.")
            if self._response_id is None or self._interrupt_requested:
                raise RuntimeError("No active response is available to interrupt.")
            self._interrupt_requested = True
            self._interrupt_pending = True
            try:
                self._socket.send(json.dumps({
                    "type": "response.interrupt",
                    "response_id": self._response_id,
                    "mode": "discard_partial_items",
                }, separators=(",", ":")))
            except Exception:
                self.close()
                raise

    def create(self, request: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        """Alias for :meth:`events` using Responses resource terminology."""
        return self.events(request)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._socket.close()

    def __enter__(self) -> "ResponsesWebSocketConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class ResponsesWebSocket:
    """Create authenticated Responses WebSocket connections."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def connect(
        self,
        *,
        extra_headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        websocket_factory: Any = None,
    ) -> ResponsesWebSocketConnection:
        self._client._ensure_auth()
        headers = self._client._auth_headers()
        if extra_headers is not None:
            for name, value in extra_headers.items():
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("Expected WebSocket header names to be non-empty strings.")
                if not isinstance(value, str) or not value:
                    raise ValueError("Expected WebSocket header values to be non-empty strings.")
                headers[name] = value
        if websocket_factory is None:
            try:
                import websocket
            except ImportError as exc:  # pragma: no cover - installation error
                raise RuntimeError(
                    "Responses WebSocket support requires `websocket-client`."
                ) from exc
            websocket_factory = websocket.create_connection
        socket = websocket_factory(
            RESPONSES_WEBSOCKET_URL,
            header=[f"{name}: {value}" for name, value in headers.items()],
            timeout=self._client._timeout if timeout is None else timeout,
        )
        return ResponsesWebSocketConnection(socket, url=RESPONSES_WEBSOCKET_URL)


def _handshake_headers(socket: Any) -> dict[str, str]:
    response = getattr(socket, "handshake_response", None)
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        return {}
    return {str(name).lower(): str(value) for name, value in headers.items()}


def _event_error(event: dict[str, Any]) -> ResponsesWebSocketError:
    error = event.get("error")
    error = error if isinstance(error, dict) else {}
    code = error.get("code") if isinstance(error.get("code"), str) else None
    message = error.get("message") if isinstance(error.get("message"), str) else None
    status = event.get("status", event.get("status_code"))
    if not isinstance(status, int) or isinstance(status, bool):
        status = None
    fallbacks = {
        "websocket_connection_limit_reached": (
            "Responses WebSocket connection limit reached; create a new connection."
        ),
        "previous_response_not_found": (
            "Previous response was not found; retry with the full request."
        ),
    }
    return ResponsesWebSocketError(
        message or fallbacks.get(code) or "Responses WebSocket returned an error.",
        code=code,
        status=status,
        event=event,
    )
