from codex_backend_sdk import OpenAI, RealtimeCallResponse
from codex_backend_sdk.storage import TokenStore


class FakeResponse:
    content = b"answer-sdp"
    text = "answer-sdp"
    encoding = "utf-8"

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
            openai_api_key="sk-test",
        ))

    def _post_raw(self, path, **kwargs):
        self.raw_posts.append((path, kwargs))
        return FakeResponse()


def test_realtime_calls_create_posts_plain_sdp_like_official_sdk():
    client = FakeRealtimeClient()

    response = client.realtime.calls.create(sdp="offer-sdp")

    assert isinstance(response, RealtimeCallResponse)
    assert response.read() == b"answer-sdp"
    path, kwargs = client.raw_posts[0]
    assert path == "/realtime/calls"
    assert kwargs["content"] == b"offer-sdp"
    assert kwargs["headers"]["Accept"] == "application/sdp"
    assert kwargs["headers"]["Content-Type"] == "application/sdp"


def test_realtime_calls_create_posts_session_as_multipart():
    client = FakeRealtimeClient()

    client.realtime.calls.create(
        sdp="offer-sdp",
        session={"type": "realtime", "model": "gpt-realtime-1.5"},
    )

    path, kwargs = client.raw_posts[0]
    assert path == "/realtime/calls"
    assert kwargs["files"][0][0] == "sdp"
    assert kwargs["files"][1][0] == "session"
    assert b"gpt-realtime-1.5" in kwargs["files"][1][1][1]


def test_realtime_websocket_helpers_match_codex_agent_plugin_contract():
    client = FakeRealtimeClient()

    assert client.realtime_websocket_url(model="gpt-realtime-1.5") == (
        "wss://api.openai.com/v1/realtime?model=gpt-realtime-1.5"
    )
    assert client.realtime_websocket_headers(session_id="session-123") == {
        "Authorization": "Bearer sk-test",
        "OpenAI-Beta": "realtime=v1",
    }
