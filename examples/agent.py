"""Minimal function-calling loop using the OpenAI-shaped Codex client."""

from __future__ import annotations

import json

from codex_backend_sdk import OpenAI


TOOLS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
    }
]


def get_weather(city: str) -> dict:
    return {"city": city, "temperature": 18, "unit": "celsius", "condition": "cloudy"}


def main() -> None:
    client = OpenAI().authenticate()
    history: list[dict] = [{"role": "user", "content": "What's the weather in Paris?"}]

    first = client.responses.create(input=history, tools=TOOLS)
    history.extend(first.output)

    for item in first.output:
        if item.get("type") != "function_call":
            continue
        if item["name"] == "get_weather":
            result = get_weather(**json.loads(item["arguments"]))
        else:
            result = {"error": f"unknown tool: {item['name']}"}
        history.append({
            "type": "function_call_output",
            "call_id": item["call_id"],
            "output": json.dumps(result),
        })

    second = client.responses.create(input=history, tools=TOOLS)
    print(second.output_text)


if __name__ == "__main__":
    main()
