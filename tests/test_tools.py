"""Tool calling — single call, parallel calls, tool result loop."""

import json

import pytest
from codex_backend_sdk import CodexClient, ResponseCompleted, TextDelta, ToolCall

# ---------------------------------------------------------------------------
# Shared tool definition + fake implementation
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get the current weather for a given city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. 'Paris'"},
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    }
]

_WEATHER_DATA = {
    "Paris": {"temperature": 18, "unit": "celsius", "condition": "cloudy"},
    "Tokyo": {"temperature": 27, "unit": "celsius", "condition": "sunny"},
    "London": {"temperature": 14, "unit": "celsius", "condition": "rainy"},
}


def _get_weather(city: str) -> dict:
    return _WEATHER_DATA.get(city, {"temperature": 15, "unit": "celsius", "condition": "unknown"})


def _run_tool(call: ToolCall) -> str:
    if call.name == "get_weather":
        return json.dumps(_get_weather(**call.parsed_arguments()))
    return json.dumps({"error": f"unknown tool: {call.name}"})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_tool_call(client: CodexClient):
    history = []
    tool_calls: list[ToolCall] = []

    for event in client.stream("What's the weather in Paris?", tools=_TOOLS):
        if isinstance(event, ToolCall):
            history.append(event.as_history_item())
            history.append(event.to_tool_result(_run_tool(event)))
            tool_calls.append(event)

    assert tool_calls, "Model made no tool call"
    assert tool_calls[0].name == "get_weather"
    assert tool_calls[0].parsed_arguments().get("city") == "Paris"

    # Turn 2 — model sees the result and gives a final answer
    text_parts: list[str] = []
    for event in client.stream(None, conversation_history=history, tools=_TOOLS):
        if isinstance(event, TextDelta):
            text_parts.append(event.text)

    full_text = "".join(text_parts)
    assert full_text.strip(), "Empty final answer after tool result"
    assert any(kw in full_text.lower() for kw in ("paris", "18", "cloudy", "celsius"))


def test_parallel_tool_calls(client: CodexClient):
    history = []
    tool_calls: list[ToolCall] = []

    for event in client.stream(
        "What's the weather in Paris and Tokyo right now?",
        tools=_TOOLS,
        parallel_tool_calls=True,
    ):
        if isinstance(event, ToolCall):
            history.append(event.as_history_item())
            history.append(event.to_tool_result(_run_tool(event)))
            tool_calls.append(event)

    assert len(tool_calls) == 2, (
        f"Expected 2 parallel tool calls, got {len(tool_calls)}: "
        + str([tc.parsed_arguments() for tc in tool_calls])
    )
    cities = {tc.parsed_arguments()["city"] for tc in tool_calls}
    assert cities == {"Paris", "Tokyo"}

    # Turn 2
    text_parts: list[str] = []
    for event in client.stream(None, conversation_history=history, tools=_TOOLS):
        if isinstance(event, TextDelta):
            text_parts.append(event.text)

    full_text = "".join(text_parts)
    assert "paris" in full_text.lower()
    assert "tokyo" in full_text.lower()


def test_tool_call_id_roundtrip(client: CodexClient):
    """call_id from ToolCall must be echoed back in the tool_result item."""
    history = []

    for event in client.stream("Weather in London?", tools=_TOOLS):
        if isinstance(event, ToolCall):
            assert event.call_id, "ToolCall has no call_id"
            result_item = event.to_tool_result(_run_tool(event))
            assert result_item["call_id"] == event.call_id
            assert result_item["type"] == "function_call_output"
            history.append(event.as_history_item())
            history.append(result_item)
