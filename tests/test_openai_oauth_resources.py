import pytest

from codex_backend_sdk import CreateEmbeddingResponse, OpenAI, Transcription
from codex_backend_sdk._utils import CodexBackendUnsupportedParameterError
from codex_backend_sdk.storage import TokenStore


class FakeJSONResponse:
    headers = {"content-type": "application/json"}
    text = '{"text":"hello"}'

    def json(self):
        return {"text": "hello"}

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(())


class FakeOpenAIClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.openai_posts = []
        self.chatgpt_raw_posts = []
        self._set_store(TokenStore(
            access_token="chatgpt-token",
            refresh_token="refresh-token",
            id_token_raw="id-token",
            account_id="account-id",
        ))

    def _post_openai(self, path, **kwargs):
        self.openai_posts.append((path, kwargs, self._openai_headers()))
        return {
            "object": "list",
            "data": [{"object": "embedding", "embedding": [0.1, 0.2, 0.3], "index": 0}],
            "model": kwargs["body"]["model"],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        }

    def _post_chatgpt_raw(self, path, **kwargs):
        self.chatgpt_raw_posts.append((path, kwargs, self._auth_headers()))
        return FakeJSONResponse()


def test_embeddings_create_posts_to_openai_with_codex_oauth_token():
    client = FakeOpenAIClient()

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input="ping",
        dimensions=3,
        encoding_format="float",
    )

    assert isinstance(response, CreateEmbeddingResponse)
    assert response.data[0].embedding == [0.1, 0.2, 0.3]
    path, kwargs, headers = client.openai_posts[0]
    assert path == "/embeddings"
    assert kwargs["body"] == {
        "input": "ping",
        "model": "text-embedding-3-small",
        "dimensions": 3,
        "encoding_format": "float",
    }
    assert headers["Authorization"] == "Bearer chatgpt-token"


def test_audio_transcriptions_create_posts_to_chatgpt_backend():
    client = FakeOpenAIClient()

    response = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=("clip.wav", b"wav", "audio/wav"),
        response_format="json",
        language="fr",
    )

    assert isinstance(response, Transcription)
    assert response.text == "hello"
    path, kwargs, headers = client.chatgpt_raw_posts[0]
    assert path == "/transcribe"
    assert kwargs["files"]["file"] == ("clip.wav", b"wav", "audio/wav")
    assert kwargs["data"] == {
        "model": "gpt-4o-mini-transcribe",
        "language": "fr",
        "response_format": "json",
    }
    assert headers["Authorization"] == "Bearer chatgpt-token"
    assert headers["ChatGPT-Account-ID"] == "account-id"


def test_audio_transcriptions_text_format_returns_string():
    client = FakeOpenAIClient()

    response = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=("clip.wav", b"wav", "audio/wav"),
        response_format="text",
    )

    assert response == "hello"


def test_audio_transcriptions_rejects_unsupported_options():
    client = FakeOpenAIClient()

    with pytest.raises(CodexBackendUnsupportedParameterError, match="stream"):
        client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=("clip.wav", b"wav", "audio/wav"),
            stream=True,
        )

    with pytest.raises(CodexBackendUnsupportedParameterError, match="json.*text"):
        client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=("clip.wav", b"wav", "audio/wav"),
            response_format="srt",
        )
