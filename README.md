# codex-backend-sdk

Unofficial Python SDK for the ChatGPT Codex backend API
(`chatgpt.com/backend-api/codex`).

This package mirrors the official OpenAI Python SDK shape for the API surface
that the Codex backend exposes. Use `OpenAI`, `client.responses.create(...)`,
and `client.models.list()` just as you would with `openai-python`, with
Codex-specific authentication and backend limitations under the hood.

> **Requirements:** a ChatGPT Plus, Pro, or Enterprise subscription.
> Authentication goes through ChatGPT OAuth and stores tokens in
> `~/.codex/auth.json`.

> **Disclaimer:** This is an independent, community-maintained library that
> reverse-engineers undocumented endpoints of `chatgpt.com`. It is not
> affiliated with, endorsed by, or supported by OpenAI.

## Installation

```bash
git clone https://github.com/B4PT0R/codex-backend-sdk.git
cd codex-backend-sdk
pip install -e .
```

## Basic Usage

```python
from codex_backend_sdk import OpenAI

client = OpenAI().authenticate()

response = client.responses.create(
    model="gpt-5.4",
    input="Explain quicksort in one paragraph.",
)

print(response.output_text)
```

## Streaming

```python
stream = client.responses.create(
    model="gpt-5.4",
    input="Say 'hi' five times.",
    stream=True,
)

for event in stream:
    if event.type in {"response.output_text.delta", "response.content_part.delta"}:
        delta = event.delta
        print(delta if isinstance(delta, str) else delta.get("text", ""), end="")
```

## Models

```python
models = client.models.list()
for model in models:
    print(model.id, model.display_name, model.context_window)

info = client.models.retrieve("gpt-5.4")
```

## Multi-Turn Input

The Codex backend does not expose `previous_response_id`, so pass prior
input/output items explicitly.

```python
history = [
    {"role": "user", "content": "My name is Alice. Say OK."},
]

reply1 = client.responses.create(input=history).output_text
history.append({"role": "assistant", "content": reply1})
history.append({"role": "user", "content": "What is my name?"})

reply2 = client.responses.create(input=history).output_text
print(reply2)
```

## Function Calling

```python
import json

tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "Get the current weather for a city.",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": False,
    },
}]

first = client.responses.create(
    input="What's the weather in Paris?",
    tools=tools,
)

call = next(item for item in first.output if item["type"] == "function_call")
result = {"temperature": 18, "unit": "celsius", "condition": "cloudy"}

second = client.responses.create(
    input=[
        call,
        {
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": json.dumps(result),
        },
    ],
    tools=tools,
)

print(second.output_text)
```

## Structured Output

```python
schema = {
    "title": "person",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name", "age"],
    "additionalProperties": False,
}

response = client.responses.create(
    input="Extract: Bob is 42 years old.",
    text={
        "format": {
            "type": "json_schema",
            "name": "person",
            "schema": schema,
            "strict": True,
        }
    },
)
```

## Codex-Specific Endpoints

Codex-only operations live under `client.codex`.

```python
quota = client.codex.usage()
```

The backend currently rejects some official Responses parameters, including
`temperature`, `top_p`, `max_output_tokens`, `metadata`, `user`,
`safety_identifier`, `truncation`, and `previous_response_id`. The SDK raises
`CodexBackendUnsupportedParameterError` for those instead of silently dropping
them.
