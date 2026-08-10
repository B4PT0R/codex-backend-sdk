"""SSE parsing helpers."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Optional

import requests

from ._models import ResponseStreamEvent


class ResponseEventStream(Iterator[ResponseStreamEvent]):
    """Closeable/context-managed event stream compatible with OpenAI streams."""

    def __init__(self, response: requests.Response) -> None:
        self.response = response
        self._events = (
            ResponseStreamEvent.model_validate(payload)
            for payload in iter_sse_payloads(response)
        )

    def __iter__(self) -> "ResponseEventStream":
        return self

    def __next__(self) -> ResponseStreamEvent:
        return next(self._events)

    def close(self) -> None:
        close = getattr(self.response, "close", None)
        if close is not None:
            close()

    def __enter__(self) -> "ResponseEventStream":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def stream_response_events(response: requests.Response) -> ResponseEventStream:
    return ResponseEventStream(response)


def iter_sse_payloads(response: requests.Response) -> Iterator[dict[str, Any]]:
    event_name: Optional[str] = None
    data_lines: list[str] = []

    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line is None:
            continue
        if line == "":
            if data_lines:
                payload = loads_sse_data(data_lines)
                if payload is not None:
                    payload.setdefault("type", event_name or "message")
                    yield payload
            event_name = None
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())


def loads_sse_data(data_lines: list[str]) -> Optional[dict[str, Any]]:
    data = "\n".join(data_lines)
    if data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
