from dataclasses import dataclass

import pytest

from codex_backend_sdk import OpenAI


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSearchClient(OpenAI):
    def __init__(self, payload=None):
        super().__init__()
        self.payload = {
            "encrypted_output": "encrypted",
            "output": "search result",
            "results": [{"type": "text_result", "future": True}],
            "future_top_level": True,
        } if payload is None else payload
        self.calls = []

    def _post_raw(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return FakeResponse(self.payload)


@dataclass
class Commands:
    search_query: list[dict]


def test_codex_web_search_posts_official_contract_and_preserves_additions():
    client = FakeSearchClient()

    response = client.codex.web_search.search(
        id="session_1",
        model="gpt-test",
        input=[{"type": "message", "role": "user", "content": []}],
        reasoning={"effort": "low"},
        commands=Commands(search_query=[{"q": "OpenAI", "recency": 7}]),
        settings={
            "search_context_size": "low",
            "external_web_access": "live",
        },
        max_output_tokens=2500,
        originator="chatgpt_cca",
        turn_metadata="turn-metadata",
    )

    assert response["future_top_level"] is True
    assert response["results"][0]["future"] is True
    assert client.calls == [
        (
            "/alpha/search",
            {
                "body": {
                    "id": "session_1",
                    "model": "gpt-test",
                    "reasoning": {"effort": "low"},
                    "input": [
                        {"type": "message", "role": "user", "content": []}
                    ],
                    "commands": {
                        "search_query": [{"q": "OpenAI", "recency": 7}]
                    },
                    "settings": {
                        "search_context_size": "low",
                        "external_web_access": "live",
                    },
                    "max_output_tokens": 2500,
                },
                "headers": {
                    "originator": "chatgpt_cca",
                    "x-codex-turn-metadata": "turn-metadata",
                },
            },
        )
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"id": "", "model": "gpt-test"}, "id"),
        ({"id": "session", "model": ""}, "model"),
        ({"id": "session", "model": "gpt-test", "input": {}}, "input"),
        ({"id": "session", "model": "gpt-test", "commands": []}, "commands"),
        ({"id": "session", "model": "gpt-test", "settings": []}, "settings"),
        (
            {"id": "session", "model": "gpt-test", "max_output_tokens": True},
            "max_output_tokens",
        ),
    ],
)
def test_codex_web_search_validates_request(kwargs, message):
    with pytest.raises((TypeError, ValueError), match=message):
        FakeSearchClient().codex.web_search.search(**kwargs)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "non-object"),
        ({"output": None}, "text output"),
        ({"output": "ok", "encrypted_output": 1}, "encrypted output"),
        ({"output": "ok", "results": {}}, "structured results"),
    ],
)
def test_codex_web_search_validates_response_envelope(payload, message):
    with pytest.raises(RuntimeError, match=message):
        FakeSearchClient(payload).codex.web_search.search(
            id="session", model="gpt-test", commands={}
        )
