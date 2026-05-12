from codex_backend_sdk import OpenAI, Response


class FakeSSE:
    def __init__(self, events):
        self._events = events

    def iter_lines(self):
        for event in self._events:
            if event.startswith("event:") or event.startswith("data:"):
                yield event.encode()
            else:
                yield event
        yield b""


class FakeClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.posts = []
        self.gets = []

    def _post(self, path, *, body, stream=False):
        self.posts.append((path, body, stream))
        return FakeSSE([
            'data: {"type":"response.content_part.delta","delta":{"text":"hel"}}',
            "",
            'data: {"type":"response.content_part.delta","delta":{"text":"lo"}}',
            "",
            (
                'data: {"type":"response.completed","response":'
                '{"id":"resp_123","model":"gpt-test",'
                '"usage":{"input_tokens":2,"output_tokens":1,"total_tokens":3}}}'
            ),
        ])

    def _get(self, path, *, params=None):
        self.gets.append((path, params))
        return {
            "models": [
                {
                    "slug": "gpt-test",
                    "display_name": "GPT Test",
                    "description": "Test model",
                    "context_window": 123,
                    "supported_in_api": True,
                    "priority": 7,
                }
            ]
        }


def test_responses_create_collects_to_pydantic_response():
    client = FakeClient()

    response = client.responses.create(
        model="gpt-test",
        input="Say hello",
        reasoning={"effort": "low", "summary": "auto"},
        text={"verbosity": "low"},
        stream=False,
    )

    assert isinstance(response, Response)
    assert response.id == "resp_123"
    assert response.output_text == "hello"
    assert "output_text" not in response.model_dump()
    assert response.usage.total_tokens == 3

    path, payload, stream = client.posts[0]
    assert path == "/responses"
    assert stream is True
    assert payload["model"] == "gpt-test"
    assert payload["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Say hello"}],
        }
    ]
    assert payload["reasoning"] == {"effort": "low", "summary": "auto"}
    assert payload["text"] == {"verbosity": "low"}


def test_responses_create_normalizes_official_input_items():
    client = FakeClient()

    client.responses.create(
        input=[
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ],
    )

    assert client.posts[0][1]["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hi"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hello"}],
        },
    ]


def test_responses_create_stream_returns_openai_event_objects():
    client = FakeClient()

    events = list(client.responses.create(input="Hi", stream=True))

    assert events[0].type == "response.content_part.delta"
    assert events[0].delta == {"text": "hel"}
    assert events[-1].type == "response.completed"
    assert events[-1].response["id"] == "resp_123"


def test_models_resource_returns_iterable_page():
    client = FakeClient()

    page = client.models.list()
    model = page[0]

    assert len(page) == 1
    assert list(page) == [model]
    assert model.id == "gpt-test"
    assert model.context_window == 123
    assert client.models.retrieve("gpt-test").id == "gpt-test"


def test_responses_create_rejects_official_params_not_exposed_by_codex_backend():
    client = FakeClient()

    try:
        client.responses.create(input="Hi", temperature=0.2)
    except NotImplementedError as exc:
        assert "temperature" in str(exc)
    else:
        raise AssertionError("temperature should be rejected before hitting the backend")
