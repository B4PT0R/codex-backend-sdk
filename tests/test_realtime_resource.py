import json

import pytest
import requests

from codex_backend_sdk import OpenAI, RealtimeCallResponse
from codex_backend_sdk.storage import TokenStore


class FakeResponse:
    content = b"answer-sdp"
    text = "answer-sdp"
    encoding = "utf-8"
    headers = {"Location": "/v1/realtime/calls/calls/rtc_test"}

    def json(self, **kwargs):
        return {"ok": True}

    def iter_content(self, chunk_size=1024):
        yield self.content

    def iter_lines(self):
        yield self.content

    def close(self):
        self.closed = True


class FakeWebSocket:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.sent = []
        self.closed = False

    def send(self, payload):
        self.sent.append(payload)

    def recv(self):
        return self.messages.pop(0)

    def close(self):
        self.closed = True


class FakeRealtimeClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.raw_posts = []
        self._set_store(TokenStore(
            access_token="chatgpt-token",
            refresh_token="refresh-token",
            id_token_raw="id-token",
            account_id="account-id",
        ))

    def _post_raw(self, path, **kwargs):
        self.raw_posts.append((path, kwargs))
        return FakeResponse()


class ErrorRealtimeClient(FakeRealtimeClient):
    def _post_raw(self, path, **kwargs):
        response = requests.Response()
        response.status_code = 400
        response.url = "https://chatgpt.com/backend-api/codex/realtime/calls"
        response.headers["x-request-id"] = "request-123"
        response._content = b'{"error":{"message":"Unknown parameter: phase"}}'
        request = requests.Request("POST", response.url).prepare()
        raise requests.HTTPError("400 Client Error", response=response, request=request)


def test_realtime_calls_create_v3_accepts_confirmed_models_and_sets_alpha_header():
    client = FakeRealtimeClient()

    for model in ("gpt-live-1-codex", "gpt-live-1-boulder-alpha"):
        client.realtime.calls.create_v3(
            sdp="offer-sdp",
            session={"model": model, "instructions": "Be concise."},
        )

    path, kwargs = client.raw_posts[0]
    assert path == "/realtime/calls"
    assert kwargs["body"]["session"] == {
        "model": "gpt-live-1-codex",
        "instructions": "Be concise.",
    }
    assert kwargs["headers"]["openai-alpha"] == "quicksilver=v2"
    assert kwargs["headers"]["session-id"]
    assert kwargs["headers"]["thread-id"]
    assert kwargs["params"] == {"intent": "quicksilver", "architecture": "avas"}
    assert client.raw_posts[1][1]["body"]["session"]["model"] == (
        "gpt-live-1-boulder-alpha"
    )

    try:
        client.realtime.calls.create_v3(
            sdp="offer-sdp",
            session={"model": "gpt-live"},
        )
    except ValueError as exc:
        assert "gpt-live" in str(exc)
    else:
        raise AssertionError("Expected an unsupported gpt-live alias to be rejected")


def test_realtime_calls_create_v3_exposes_backend_error_detail():
    client = ErrorRealtimeClient()

    with pytest.raises(requests.HTTPError) as exc_info:
        client.realtime.calls.create_v3(
            sdp="offer-sdp",
            session={"model": "gpt-live-1-codex"},
        )

    message = str(exc_info.value)
    assert "Unknown parameter: phase" in message
    assert "request_id=request-123" in message


def test_realtime_calls_create_v3_preserves_explicit_backend_ids():
    client = FakeRealtimeClient()

    client.realtime.calls.create_v3(
        sdp="offer-sdp",
        session={"model": "gpt-live-1-codex"},
        session_id="session-123",
        thread_id="thread-456",
    )

    headers = client.raw_posts[0][1]["headers"]
    assert headers["session-id"] == "session-123"
    assert headers["thread-id"] == "thread-456"


def test_realtime_sideband_connects_with_oauth_and_json_transport(monkeypatch):
    client = FakeRealtimeClient()
    socket = FakeWebSocket([json.dumps({"type": "delegation.created"})])
    captured = {}

    def create_connection(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return socket

    monkeypatch.setattr(
        "codex_backend_sdk.resources.realtime.websocket.create_connection",
        create_connection,
    )

    connection = client.realtime.sideband.connect(
        call_id="rtc_test",
        session_id="session-123",
        timeout=15,
    )
    connection.send({"type": "delegation.context.append", "content": []})

    assert captured["url"] == "wss://api.openai.com/v1/live/rtc_test"
    assert captured["timeout"] == 15
    assert captured["header"] == {
        "Authorization": "Bearer chatgpt-token",
        "ChatGPT-Account-ID": "account-id",
        "openai-alpha": "quicksilver=v2",
        "originator": "codex_cli_rs",
        "x-session-id": "session-123",
    }
    assert connection.recv() == {"type": "delegation.created"}
    assert json.loads(socket.sent[0]) == {
        "type": "delegation.context.append",
        "content": [],
    }
    connection.close()
    assert socket.closed is True


def test_realtime_sideband_requires_oauth_store():
    client = FakeRealtimeClient()
    client._store = None

    try:
        client.realtime.sideband.connect(call_id="rtc_test")
    except RuntimeError as exc:
        assert "ChatGPT OAuth" in str(exc)
    else:
        raise AssertionError("Expected unauthenticated sideband to fail")


def test_realtime_calls_create_v3_rejects_non_object_session():
    client = FakeRealtimeClient()

    try:
        client.realtime.calls.create_v3(sdp="offer-sdp", session=["invalid"])
    except TypeError as exc:
        assert str(exc) == "Expected `session` to serialize to a JSON object."
    else:
        raise AssertionError("Expected non-object session to fail")


def test_realtime_call_response_requires_valid_location():
    response = FakeResponse()
    response.headers = {"Location": "/v1/realtime/calls/not-a-call"}

    try:
        RealtimeCallResponse(response).call_id
    except RuntimeError as exc:
        assert "does not contain a valid call id" in str(exc)
    else:
        raise AssertionError("Expected invalid Location to fail")
