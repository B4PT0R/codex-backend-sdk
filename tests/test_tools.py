"""Function calling with official Responses output items."""

import json

from codex_backend_sdk import CodexClient

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


def _tool_result(call: dict) -> dict:
    args = json.loads(call["arguments"])
    result = _WEATHER_DATA.get(args["city"], {"temperature": 15, "condition": "unknown"})
    return {
        "type": "function_call_output",
        "call_id": call["call_id"],
        "output": json.dumps(result),
    }


def test_single_tool_call(client: CodexClient):
    first = client.responses.create(
        input="What's the weather in Paris?",
        tools=_TOOLS,
    )
    calls = [item for item in first.output if item.get("type") == "function_call"]

    assert calls, "Model made no tool call"
    assert calls[0]["name"] == "get_weather"
    assert json.loads(calls[0]["arguments"]).get("city") == "Paris"

    second = client.responses.create(
        input=[calls[0], _tool_result(calls[0])],
        tools=_TOOLS,
    )

    assert any(kw in second.output_text.lower() for kw in ("paris", "18", "cloudy", "celsius"))


def test_tool_call_id_roundtrip(client: CodexClient):
    response = client.responses.create(input="Weather in London?", tools=_TOOLS)
    call = next(item for item in response.output if item.get("type") == "function_call")
    result_item = _tool_result(call)

    assert call["call_id"]
    assert result_item["call_id"] == call["call_id"]
    assert result_item["type"] == "function_call_output"
