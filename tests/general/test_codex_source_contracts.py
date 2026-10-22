"""Durable wire guarantees for evolving Codex backend contracts."""

import json
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from types import SimpleNamespace

import pytest

from codex_backend_sdk import OpenAI, ResponsesWebSocketConnection


class CapturingClient(OpenAI):
    def __init__(self):
        super().__init__(model="test-model")
        self.calls = []

    def _post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return SimpleNamespace(
            iter_lines=lambda: iter([
                b'data: {"type":"response.completed","response":{"id":"r1"}}', b""
            ]),
            close=lambda: None,
        )

    def _post_raw(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return SimpleNamespace(json=lambda: {"created": 1, "data": []})

    def _get_chatgpt(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {"plugins": [], "pagination": {"nextPageToken": None}}

    def _post_wham(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {"threads": [{
            "thread_id": "t1", "native_usage_usd_micros": None,
            "groups": [{}, {"native_usage_usd_micros": 0}, {"native_usage_usd_micros": 250}],
        }]}


@pytest.mark.parametrize("effort,expected", [
    (4096, 4096), ("4096", 4096), ("+4096", 4096), ("000", 0),
    ("18446744073709551615", 2**64 - 1),
    ("18446744073709551616", "18446744073709551616"),
    ("high", "high"), ("custom-budget", "custom-budget"), ("-1", "-1"),
])
@pytest.mark.parametrize("compact", [False, True])
def test_numeric_reasoning_and_context_reach_both_http_transports(effort, expected, compact):
    client = CapturingClient()
    reasoning = {"effort": effort, "context": "all_turns", "future_option": True}
    if compact:
        # Compaction needs an opaque result; inspect the request even if the fixture has none.
        with pytest.raises(RuntimeError):
            client.responses.compact(input=[], reasoning=reasoning)
    else:
        client.responses.create(input="hello", reasoning=reasoning)
    assert client.calls[0][1]["body"]["reasoning"] == {
        "effort": expected, "context": "all_turns", "future_option": True,
    }
    assert reasoning["effort"] == effort


def test_reasoning_attribute_objects_preserve_context():
    client = CapturingClient()
    client.responses.create(
        input="hello", reasoning=SimpleNamespace(effort="8192", context="current_turn")
    )
    assert client.calls[0][1]["body"]["reasoning"] == {
        "effort": 8192, "context": "current_turn",
    }


def test_response_replay_preserves_opaque_message_fields_and_new_item_types():
    client = CapturingClient()
    items = [
        {"type": "message", "id": "m1", "role": "developer", "content": [],
         "internal_chat_message_metadata_passthrough": {
             "content_item_kinds": ["model.base_instructions"],
         }},
        {"type": "message", "id": "m2", "role": "assistant", "status": "completed",
         "phase": "partial_answer", "encrypted_content": "opaque", "content": [
             {"type": "output_text", "text": "hello", "annotations": [], "logprobs": []},
         ]},
        {"type": "additional_tools", "role": "developer", "tools": []},
        {"type": "configuration_update", "reasoning": {"effort": 4096}},
    ]
    client.responses.create(input=items)
    assert client.calls[0][1]["body"]["input"] == items


def test_installed_plugins_scope_keeps_limit_and_cursor():
    client = CapturingClient()
    client.chatgpt.plugins.installed(scope="WORKSPACE", limit=7, page_token="next")
    assert client.calls[0][1]["params"] == {
        "scope": "WORKSPACE", "limit": 7, "pageToken": "next",
    }
    with pytest.raises(ValueError):
        client.chatgpt.plugins.installed(scope="WORKSPACE", limit=0)


def test_image_file_references_and_native_usage_are_preserved():
    client = CapturingClient()
    images = [{"image_url": "data:image/png;base64,Zm9v"}, {"file_id": "file-image"}]
    client.images.edit(image=images, prompt="add a red hat")
    assert client.calls[0][1]["body"]["images"] == images
    assert client.codex.usage_details.threads(["t1"]) == {"threads": [{
        "thread_id": "t1", "native_usage_usd_micros": None,
        "groups": [{}, {"native_usage_usd_micros": 0}, {"native_usage_usd_micros": 250}],
    }]}


class Socket:
    def __init__(self, events):
        self.events = iter(events)
        self.sent = []
        self.closed = False

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self):
        event = next(self.events, None)
        return "" if event is None else json.dumps(event)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("ack_first", [True, False])
def test_interrupt_drains_ack_and_completion_before_socket_reuse(ack_first):
    ack = {"type": "response.interrupt.accepted", "response_id": "r1"}
    terminal = {"type": "response.completed", "response": {"id": "r1"}}
    socket = Socket([
        {"type": "response.created", "response": {"id": "r1"}},
        *([ack, terminal] if ack_first else [terminal, ack]),
        {"type": "response.completed", "response": {"id": "r2"}},
    ])
    connection = ResponsesWebSocketConnection(socket, url="wss://example.test")
    with pytest.raises(RuntimeError, match="No active"):
        connection.interrupt()
    stream = connection.events({"model": "test-model"})
    next(stream)
    connection.interrupt()
    assert socket.sent[-1] == {
        "type": "response.interrupt", "response_id": "r1", "mode": "discard_partial_items",
    }
    with pytest.raises(RuntimeError, match="No active"):
        connection.interrupt()
    assert len(list(stream)) == 2
    second = list(connection.events({"model": "test-model"}))
    assert second[0]["response"]["id"] == "r2"
    assert not socket.closed


@pytest.mark.parametrize("ack", [
    {"type": "response.interrupt.accepted", "response_id": "wrong"},
    {"type": "response.interrupt.failed", "response_id": "r1"},
    {"type": "response.interrupt.accepted"},
])
def test_invalid_interrupt_ack_retires_socket(ack):
    socket = Socket([{"type": "response.created", "response": {"id": "r1"}}, ack])
    connection = ResponsesWebSocketConnection(socket, url="wss://example.test")
    stream = connection.events({"model": "test-model"})
    next(stream)
    connection.interrupt()
    with pytest.raises(RuntimeError, match="interruption"):
        list(stream)
    assert socket.closed and connection.closed


def test_abandoned_stream_cannot_reuse_socket_with_unread_events():
    socket = Socket([{"type": "response.created", "response": {"id": "r1"}}])
    connection = ResponsesWebSocketConnection(socket, url="wss://example.test")
    stream = connection.events({"model": "test-model"})
    next(stream)
    stream.close()
    assert socket.closed and connection.closed


@pytest.mark.parametrize("remaining", [
    [],
    [{"type": "response.completed", "response": {"id": "r1"}}],
    [{"type": "response.interrupt.accepted", "response_id": "r1"}],
])
def test_incomplete_interrupt_drain_closes_socket(remaining):
    socket = Socket([{"type": "response.created", "response": {"id": "r1"}}, *remaining])
    connection = ResponsesWebSocketConnection(socket, url="wss://example.test")
    stream = connection.events({"model": "test-model"})
    next(stream)
    connection.interrupt()
    with pytest.raises(RuntimeError, match="closed before"):
        list(stream)
    assert socket.closed and connection.closed


def test_interrupt_from_another_thread_while_receiving():
    ready = Event()
    incoming = Queue()
    incoming.put({"type": "response.created", "response": {"id": "r1"}})

    class BlockingSocket(Socket):
        def recv(self):
            if len(self.sent) == 1 and incoming.empty():
                ready.set()
            return json.dumps(incoming.get(timeout=3))

        def send(self, message):
            super().send(message)
            if self.sent[-1]["type"] == "response.interrupt":
                incoming.put({"type": "response.interrupt.accepted", "response_id": "r1"})
                incoming.put({"type": "response.completed", "response": {"id": "r1"}})

    socket = BlockingSocket([])
    connection = ResponsesWebSocketConnection(socket, url="wss://example.test")
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(lambda: list(connection.events({"model": "test-model"})))
        try:
            assert ready.wait(timeout=3)
            connection.interrupt()
            assert [event["type"] for event in result.result(timeout=3)] == [
                "response.created", "response.interrupt.accepted", "response.completed",
            ]
        finally:
            connection.close()
