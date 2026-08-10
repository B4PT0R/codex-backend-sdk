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


class FakeRealtimeClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.raw_posts = []
        self._set_store(TokenStore(
            access_token="chatgpt-token",
            refresh_token="refresh-token",
            id_token_raw="id-token",
            account_id="account-id",
            openai_api_key="realtime-key",
        ))

    def _post_raw(self, path, **kwargs):
        self.raw_posts.append((path, kwargs))
        return FakeResponse()

def test_realtime_calls_create_posts_plain_sdp_like_official_sdk():
    client = FakeRealtimeClient()

    response = client.realtime.calls.create(sdp="offer-sdp")

    assert isinstance(response, RealtimeCallResponse)
    assert response.read() == b"answer-sdp"
    assert response.answer_sdp == "answer-sdp"
    assert response.call_id == "rtc_test"
    path, kwargs = client.raw_posts[0]
    assert path == "/realtime/calls"
    assert kwargs["content"] == b"offer-sdp"
    assert kwargs["headers"]["Accept"] == "application/sdp"
    assert kwargs["headers"]["Content-Type"] == "application/sdp"


def test_realtime_calls_create_posts_session_as_backend_json():
    client = FakeRealtimeClient()

    client.realtime.calls.create(
        sdp="offer-sdp",
        session={"id": "session-id", "type": "realtime", "model": "gpt-realtime-1.5"},
    )

    path, kwargs = client.raw_posts[0]
    assert path == "/realtime/calls"
    assert kwargs["body"] == {
        "sdp": "offer-sdp",
        "session": {"type": "realtime", "model": "gpt-realtime-1.5"},
    }
    assert kwargs["params"] == {"intent": "quicksilver", "architecture": "avas"}
    assert kwargs["headers"]["Accept"] == "application/sdp"


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


def test_realtime_calls_create_rejects_non_object_session():
    client = FakeRealtimeClient()

    try:
        client.realtime.calls.create(sdp="offer-sdp", session=["invalid"])
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


def test_realtime_websocket_uses_api_key_exchanged_during_oauth():
    client = FakeRealtimeClient()

    assert client.realtime.websocket_headers(session_id="session-123") == {
        "Authorization": "Bearer realtime-key",
        "originator": "codex_cli_rs",
        "x-session-id": "session-123",
    }
    assert client.realtime_websocket_url(model="gpt-realtime-1.5") == (
        "wss://api.openai.com/v1/realtime?model=gpt-realtime-1.5"
    )


def test_realtime_websocket_falls_back_to_environment_api_key(monkeypatch):
    client = FakeRealtimeClient()
    client._store.openai_api_key = None
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")

    assert client.realtime.websocket_headers()["Authorization"] == (
        "Bearer environment-key"
    )


def test_realtime_websocket_requires_api_key(monkeypatch):
    client = FakeRealtimeClient()
    client._store.openai_api_key = None
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    try:
        client.realtime.websocket_headers()
    except RuntimeError as exc:
        assert str(exc) == "Realtime Voice v2 requires an OpenAI API key."
    else:
        raise AssertionError("Expected missing Realtime credentials to fail")
