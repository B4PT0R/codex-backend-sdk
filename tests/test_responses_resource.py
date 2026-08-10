from dataclasses import dataclass

from pydantic import BaseModel

from codex_backend_sdk import OpenAI, ParsedResponse, Response


class FakeSSE:
    def __init__(self, events):
        self._events = events
        self.closed = False

    def iter_lines(self):
        for event in self._events:
            if event.startswith("event:") or event.startswith("data:"):
                yield event.encode()
            else:
                yield event
        yield b""

    def close(self):
        self.closed = True


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

    def _post(self, path, *, body, stream=False, **options):
        self.posts.append((path, body, stream, options))
        if path == "/responses/compact":
            return FakeJSONResponse({
                "id": "resp_123",
                "output": [{"type": "message", "content": []}],
                "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
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
        self.gets.append((path, params, headers, timeout))
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


class ParsedPerson(BaseModel):
    name: str
    age: int


@dataclass
class TextOptions:
    verbosity: str


class ParseFakeClient(FakeClient):
    def _post(self, path, *, body, stream=False, **options):
        self.posts.append((path, body, stream, options))
        return FakeSSE([
            (
                'data: {"type":"response.output_text.delta","delta":'
                '"{\\"name\\":\\"Ada\\",\\"age\\":37}"}'
            ),
            "",
            (
                'data: {"type":"response.completed","response":'
                '{"id":"resp_parse","model":"gpt-test","output":[{"type":"message",'
                '"role":"assistant","content":[{"type":"output_text",'
                '"text":"{\\"name\\":\\"Ada\\",\\"age\\":37}"}]}]}}'
            ),
        ])


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

    path, payload, stream, _ = client.posts[0]
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


def test_response_exposes_tool_calls_and_reasoning_summary():
    response = Response(
        id="resp_helpers",
        output=[
            {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": "First"},
                    {"type": "summary_text", "text": "Second"},
                ],
            },
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "lookup",
                "arguments": "{}",
            },
        ],
    )

    assert response.reasoning_summary == "First\nSecond"
    assert response.tool_calls == [
        {
            "type": "function_call",
            "call_id": "call_123",
            "name": "lookup",
            "arguments": "{}",
        }
    ]
    assert response.output[0].type == "reasoning"
    assert response.output[1].call_id == "call_123"


def test_responses_parse_sends_strict_schema_and_returns_parsed_response():
    client = ParseFakeClient()

    parsed = client.responses.parse(
        model="gpt-test",
        input="Extract the person",
        text_format=ParsedPerson,
        text=TextOptions(verbosity="low"),
    )

    assert isinstance(parsed, ParsedResponse)
    assert parsed.id == "resp_parse"
    assert parsed.output_parsed == ParsedPerson(name="Ada", age=37)
    path, payload, stream, _ = client.posts[0]
    assert path == "/responses"
    assert stream is True
    assert payload["text"]["verbosity"] == "low"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["name"] == "ParsedPerson"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False


def test_responses_parse_rejects_existing_text_format():
    client = ParseFakeClient()

    try:
        client.responses.parse(
            input="Extract",
            text_format=ParsedPerson,
            text={"format": {"type": "json_object"}},
        )
    except TypeError as exc:
        assert "text_format" in str(exc)
    else:
        raise AssertionError("Expected TypeError")


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
    assert events[-1].response.id == "resp_123"


def test_responses_stream_is_a_closeable_context_manager():
    client = FakeClient()

    with client.responses.create(input="Hi", stream=True) as stream:
        assert next(stream).type == "response.content_part.delta"
        raw_response = stream.response

    assert raw_response.closed is True


def test_responses_create_forwards_official_request_options_and_extra_body():
    client = FakeClient()

    client.responses.create(
        input="Hi",
        extra_headers={"x-test": "header"},
        extra_query={"preview": "1"},
        extra_body={"custom": True},
        timeout=17,
    )

    _, payload, _, options = client.posts[0]
    assert payload["custom"] is True
    assert options == {
        "headers": {"x-test": "header"},
        "params": {"preview": "1"},
        "timeout": 17,
    }


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


def test_models_resource_forwards_official_request_options():
    client = FakeClient()
    client.models.list()

    client.models.list(
        extra_headers={"x-test": "header"},
        extra_query={"preview": "1"},
        timeout=19,
    )

    assert client.gets[1] == (
        "/models",
        {"client_version": "0.130.0", "preview": "1"},
        {"x-test": "header"},
        19,
    )


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
    assert compacted.usage is not None
    assert compacted.usage.input_tokens == 11
    assert compacted.usage.output_tokens == 7
    assert compacted.usage.total_tokens == 18
    path, payload, stream, _ = client.posts[0]
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
        "tools": [{"type": "web_search"}],
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
