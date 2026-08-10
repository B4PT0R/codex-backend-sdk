import json

import pytest

from codex_backend_sdk import (
    OpenAI,
    ResponsesWebSocketConnection,
    ResponsesWebSocketError,
)
from codex_backend_sdk.resources.responses_websocket import (
    RESPONSES_WEBSOCKET_URL,
)


class Handshake:
    headers = {
        "X-Reasoning-Included": "true",
        "X-Models-Etag": "models-v1",
        "OpenAI-Model": "gpt-server",
        "X-Codex-Turn-State": "turn-state",
    }


class FakeSocket:
    def __init__(self, events=()):
        self.connected = True
        self.sent = []
        self.received = [
            event if isinstance(event, bytes) else json.dumps(event) for event in events
        ]
        self.handshake_response = Handshake()

    def send(self, message):
        self.sent.append(message)

    def recv(self):
        return self.received.pop(0) if self.received else ""

    def close(self):
        self.connected = False


class FakeAuthenticatedClient(OpenAI):
    def __init__(self):
        super().__init__(timeout=17)
        self.checked = False

    def _ensure_auth(self):
        self.checked = True

    def _auth_headers(self):
        return {
            "Authorization": "Bearer secret",
            "ChatGPT-Account-ID": "account-1",
            "originator": "codex_cli_rs",
        }


def test_responses_websocket_connects_with_oauth_and_handshake_metadata():
    client = FakeAuthenticatedClient()
    socket = FakeSocket()
    calls = []

    def factory(url, **kwargs):
        calls.append((url, kwargs))
        return socket

    connection = client.responses.websocket.connect(
        extra_headers={"x-custom": "value"}, websocket_factory=factory
    )

    assert client.checked is True
    assert calls == [
        (
            RESPONSES_WEBSOCKET_URL,
            {
                "header": [
                    "Authorization: Bearer secret",
                    "ChatGPT-Account-ID: account-1",
                    "originator: codex_cli_rs",
                    "x-custom: value",
                ],
                "timeout": 17,
            },
        )
    ]
    assert connection.reasoning_included is True
    assert connection.models_etag == "models-v1"
    assert connection.server_model == "gpt-server"
    assert connection.turn_state == "turn-state"


def test_responses_websocket_streams_raw_events_and_reuses_connection():
    socket = FakeSocket(
        [
            {"type": "response.created", "response": {"id": "resp-1"}},
            {"type": "future.event", "additive": True},
            {"type": "response.completed", "response": {"id": "resp-1"}},
            {"type": "response.completed", "response": {"id": "resp-2"}},
        ]
    )
    connection = ResponsesWebSocketConnection(socket, url=RESPONSES_WEBSOCKET_URL)

    first = list(connection.create({"model": "gpt-test", "input": []}))
    second = list(
        connection.events(
            {
                "type": "response.create",
                "model": "gpt-test",
                "previous_response_id": "resp-1",
                "input": [],
            }
        )
    )

    assert [event["type"] for event in first] == [
        "response.created",
        "future.event",
        "response.completed",
    ]
    assert second[0]["response"]["id"] == "resp-2"
    assert json.loads(socket.sent[0])["type"] == "response.create"
    assert json.loads(socket.sent[1])["previous_response_id"] == "resp-1"
    assert connection.closed is False


def test_responses_websocket_maps_error_and_closes_connection():
    socket = FakeSocket(
        [{
            "type": "error",
            "status_code": 409,
            "error": {"code": "previous_response_not_found"},
        }]
    )
    connection = ResponsesWebSocketConnection(socket, url=RESPONSES_WEBSOCKET_URL)

    with pytest.raises(ResponsesWebSocketError, match="full request") as caught:
        list(connection.events({"model": "gpt-test"}))

    assert caught.value.code == "previous_response_not_found"
    assert caught.value.status == 409
    assert caught.value.event["type"] == "error"
    assert connection.closed is True
    assert socket.connected is False


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "mapping"),
        ({"type": "session.update"}, "response.create"),
        ({"model": object()}, "JSON serializable"),
    ],
)
def test_responses_websocket_validates_requests(payload, message):
    connection = ResponsesWebSocketConnection(FakeSocket(), url=RESPONSES_WEBSOCKET_URL)
    with pytest.raises((TypeError, ValueError), match=message):
        list(connection.events(payload))


def test_responses_websocket_rejects_binary_and_premature_close():
    binary = ResponsesWebSocketConnection(
        FakeSocket([b"binary"]), url=RESPONSES_WEBSOCKET_URL
    )
    with pytest.raises(RuntimeError, match="binary"):
        list(binary.events({"model": "gpt-test"}))
    assert binary.closed is True

    closed = ResponsesWebSocketConnection(FakeSocket(), url=RESPONSES_WEBSOCKET_URL)
    with pytest.raises(RuntimeError, match="closed before"):
        list(closed.events({"model": "gpt-test"}))
    assert closed.closed is True


def test_responses_websocket_context_manager_closes_once():
    socket = FakeSocket()
    with ResponsesWebSocketConnection(socket, url=RESPONSES_WEBSOCKET_URL) as connection:
        assert connection.closed is False
    assert connection.closed is True
    connection.close()
