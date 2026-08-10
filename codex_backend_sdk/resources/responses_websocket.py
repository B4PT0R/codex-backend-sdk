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
        try:
            self._socket.send(encoded)
            while True:
                raw = self._socket.recv()
                if raw in {None, "", b""}:
                    self.closed = True
                    raise RuntimeError(
                        "Responses WebSocket closed before a terminal response event."
                    )
                if isinstance(raw, bytes):
                    self.closed = True
                    raise RuntimeError("Responses WebSocket returned unexpected binary data.")
                try:
                    event = json.loads(raw)
                except (TypeError, json.JSONDecodeError) as exc:
                    self.closed = True
                    raise RuntimeError("Responses WebSocket returned invalid JSON.") from exc
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    self.closed = True
                    raise RuntimeError(
                        "Responses WebSocket returned an invalid event envelope."
                    )
                if event["type"] == "error":
                    raise _event_error(event)
                yield event
                if event["type"] in _TERMINAL_EVENTS:
                    return
        except Exception:
            if not self.closed:
                try:
                    self.close()
                except Exception:
                    self.closed = True
            raise
        finally:
            self._request_lock.release()

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
