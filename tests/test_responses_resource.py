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


class FakeJSONResponse:
    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.posts = []
        self.gets = []

    def _post(self, path, *, body, stream=False):
        self.posts.append((path, body, stream))
        if path == "/responses/compact":
            return FakeJSONResponse({
                "id": "resp_123",
                "output": [{"type": "message", "content": []}],
            })
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

    def _get_raw(self, path, *, params=None, headers=None, timeout=None):
        self.gets.append((path, params))
        return FakeJSONResponse(
            {
                "models": [
                    {
                        "slug": "gpt-lower-priority",
                        "display_name": "GPT Lower Priority",
                        "description": "Test model",
                        "context_window": 123,
                        "supported_in_api": True,
                        "priority": 7,
                    },
                    {
                        "slug": "gpt-test",
                        "display_name": "GPT Test",
                        "description": "Test model",
                        "context_window": 456,
                        "supported_in_api": True,
                        "priority": 1,
                    },
                ]
            },
            headers={"ETag": "models-etag"},
        )


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

    assert len(page) == 2
    assert model.id == "gpt-test"
    assert model.context_window == 456
    assert page.etag == "models-etag"
    assert client.models.retrieve("gpt-test").id == "gpt-test"
    assert len(client.gets) == 1


def test_models_resource_can_force_refresh_cached_page():
    client = FakeClient()

    assert client.models.list() is client.models.list()
    client.models.list(force_refresh=True)

    assert len(client.gets) == 2


def test_responses_compact_sends_shared_request_fields():
    client = FakeClient()

    compacted = client.responses.compact(
        model="gpt-test",
        input=[{"role": "user", "content": "Long context"}],
        instructions="Compact this.",
        tools=[{"type": "web_search"}],
        parallel_tool_calls=True,
        reasoning={"effort": "medium"},
        service_tier="priority",
        prompt_cache_key="cache-key",
        text={"verbosity": "low"},
    )

    assert compacted.id == "resp_123"
    path, payload, stream = client.posts[0]
    assert path == "/responses/compact"
    assert stream is False
    assert payload == {
        "model": "gpt-test",
        "instructions": "Compact this.",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Long context"}],
            }
        ],
        "tools": [{"type": "web_search_preview"}],
        "parallel_tool_calls": True,
        "reasoning": {"effort": "medium"},
        "service_tier": "priority",
        "prompt_cache_key": "cache-key",
        "text": {"verbosity": "low"},
    }


def test_responses_create_rejects_official_params_not_exposed_by_codex_backend():
    client = FakeClient()

    try:
        client.responses.create(input="Hi", temperature=0.2)
    except NotImplementedError as exc:
        assert "temperature" in str(exc)
    else:
        raise AssertionError("temperature should be rejected before hitting the backend")
