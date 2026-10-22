"""Offline tests for turn-scoped backend routing (no credentials/network)."""

import json

import pytest

from codex_backend_sdk import CodexClient
from codex_backend_sdk.storage import TokenStore


class SSE:
    def __init__(self, token=None, events=()):
        self.headers = {"X-Codex-Turn-State": token} if token else {}
        self.events = events

    def iter_lines(self):
        for event in self.events:
            yield "data: " + json.dumps(event)
            yield ""
        yield 'data: {"type":"response.completed","response":{"id":"resp-test","model":"test"}}'
        yield ""

    def close(self):
        pass


class Client(CodexClient):
    def __init__(self, replies, **kwargs):
        super().__init__(model="test", **kwargs)
        self.replies = iter(replies)
        self.posts = []

    def _post(self, path, **kwargs):
        self.posts.append((path, kwargs))
        return next(self.replies)


def send(responses, **kwargs):
    return responses.create(input="hello", prompt_cache_key="conversation", **kwargs)


def headers(client):
    return [post[1]["headers"] or {} for post in client.posts]


def test_first_server_token_is_replayed_only_inside_its_turn():
    client = Client([SSE("first"), SSE("later"), SSE(), SSE(), SSE()])
    with client.responses.turn() as turn:
        send(turn)
        send(turn)
        send(turn)
    send(client.responses)
    with client.responses.turn() as turn:
        send(turn)
    assert headers(client) == [
        {"session-id": "conversation"},
        {"session-id": "conversation", "x-codex-turn-state": "first"},
        {"session-id": "conversation", "x-codex-turn-state": "first"},
        {"session-id": "conversation"},
        {"session-id": "conversation"},
    ]
    assert all("turn-state" not in json.dumps(post[1]["body"]) for post in client.posts)
    with pytest.raises(RuntimeError, match="turn is closed"):
        send(turn)


def test_stream_metadata_token_is_captured_before_retry_or_next_generation():
    metadata = {"type": "response.metadata", "headers": {"X-CODEX-TURN-STATE": "metadata"}}
    client = Client([SSE(events=[metadata]), SSE()])
    with client.responses.turn() as turn:
        stream = send(turn, stream=True)
        event = next(stream)
        assert event.type == "response.metadata"
        stream.close()
        send(turn)
    assert headers(client)[1]["x-codex-turn-state"] == "metadata"


def test_parallel_resources_on_same_client_do_not_share_routing():
    client = Client([SSE("a"), SSE("b"), SSE(), SSE()])
    with client.responses.turn() as first, client.responses.turn() as second:
        send(first)
        send(second)
        send(first)
        send(second)
    assert [h.get("x-codex-turn-state") for h in headers(client)] == [None, None, "a", "b"]


def test_auth_change_discards_token_and_ignores_old_stream_metadata():
    metadata = {"type": "response.metadata", "headers": {"x-codex-turn-state": "stale"}}
    client = Client([SSE("old", [metadata]), SSE("new"), SSE()])
    with client.responses.turn() as turn:
        stream = send(turn, stream=True)
        client._set_store(TokenStore("synthetic", "", "", account_id="other"))
        list(stream)
        send(turn)
        send(turn)
    assert [h.get("x-codex-turn-state") for h in headers(client)] == [None, None, "new"]


def test_switching_affinity_discards_token_even_when_switching_back():
    client = Client([SSE("a"), SSE("b"), SSE()])
    with client.responses.turn() as turn:
        send(turn)
        turn.create(input="hello", prompt_cache_key="other")
        send(turn)
    assert [h.get("x-codex-turn-state") for h in headers(client)] == [None, None, None]


def test_explicit_headers_are_respected_case_insensitively_without_mutation():
    client = Client([SSE("server"), SSE()])
    explicit = {"Session-ID": "explicit-session", "X-Codex-Turn-State": "explicit-turn"}
    with client.responses.turn() as turn:
        send(turn, extra_headers=explicit)
        send(turn, extra_headers={"Session-ID": "explicit-session"})
    assert headers(client) == [explicit, {"Session-ID": "explicit-session", "x-codex-turn-state": "explicit-turn"}]
    assert explicit == {"Session-ID": "explicit-session", "X-Codex-Turn-State": "explicit-turn"}


def test_client_default_session_header_is_not_overridden_by_body_key():
    client = Client([SSE()], default_headers={"Session-ID": "default-session"})
    send(client.responses)
    assert headers(client) == [{}]
    assert client._session.headers["session-id"] == "default-session"


@pytest.mark.parametrize("token", ["", 12, "bad\r\nheader"])
def test_invalid_metadata_token_is_not_replayed(token):
    metadata = {"type": "response.metadata", "headers": {"x-codex-turn-state": token}}
    client = Client([SSE(events=[metadata]), SSE()])
    with client.responses.turn() as turn:
        send(turn)
        send(turn)
    assert "x-codex-turn-state" not in headers(client)[1]


def test_scoped_parse_reuses_routing_but_compaction_is_separate():
    compact = {"type": "response.output_item.done", "item": {"type": "compaction", "encrypted_content": "opaque"}}
    client = Client([SSE("normal"), SSE("compact", [compact]), SSE(), SSE()])
    with client.responses.turn() as turn:
        send(turn)
        turn.compact(input=[], prompt_cache_key="conversation")
        turn.parse(input="hello", prompt_cache_key="conversation")
    send(client.responses)
    assert [h.get("x-codex-turn-state") for h in headers(client)] == [None, None, "normal", None]


def test_exception_closes_scope_and_late_stream_cannot_reopen_it():
    client = Client([SSE("old"), SSE()])
    with pytest.raises(ValueError):
        with client.responses.turn() as turn:
            stream = send(turn, stream=True)
            raise ValueError("interrupted")
    list(stream)
    with pytest.raises(RuntimeError, match="turn is closed"):
        send(turn)
    send(client.responses)
    assert len(client.posts) == 2


def test_per_request_auth_override_does_not_reuse_another_owners_token():
    client = Client([SSE("original"), SSE("other"), SSE()])
    with client.responses.turn() as turn:
        send(turn)
        send(turn, extra_headers={"Authorization": "Bearer synthetic-other"})
        send(turn)
    assert [h.get("x-codex-turn-state") for h in headers(client)] == [None, None, None]


def test_explicit_empty_session_header_is_not_replaced():
    client = Client([SSE()])
    send(client.responses, extra_headers={"Session-ID": ""})
    assert headers(client) == [{"Session-ID": ""}]


def test_late_metadata_cannot_restore_a_token_after_affinity_switches_back():
    metadata = {"type": "response.metadata", "headers": {"x-codex-turn-state": "stale"}}
    client = Client([SSE(events=[metadata]), SSE(), SSE(), SSE()])
    with client.responses.turn() as turn:
        stream = send(turn, stream=True)
        turn.create(input="hello", prompt_cache_key="other")
        send(turn)
        list(stream)
        send(turn)
    assert all("x-codex-turn-state" not in h for h in headers(client))
