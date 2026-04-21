# codex-backend-sdk

Unofficial Python SDK for the ChatGPT Codex backend API (`chatgpt.com/backend-api/codex`).

This is a **lower-level** alternative to the official Codex CLI. It gives direct access to the HTTP API so you can build your own agent loop without inheriting OpenAI's design choices.

> **Requirements:** a ChatGPT Plus, Pro, or Enterprise subscription. No OpenAI API key needed — authentication goes through ChatGPT OAuth.

> [!WARNING]
> **Disclaimer:** This is an independent, community-maintained library that reverse-engineers undocumented endpoints of `chatgpt.com`. It is **not** affiliated with, endorsed by, or supported by OpenAI. Usage remains subject to [OpenAI's Terms of Use](https://openai.com/policies/terms-of-use). Endpoints may change or break without notice.

---

## Installation

```bash
git clone https://github.com/B4PT0R/codex-backend-sdk.git
cd codex-backend-sdk
pip install -e .
```

For the agent example (`examples/agent.py`), also install:

```bash
pip install pyyaml
```

---

## Authentication

```python
from codex_backend_sdk import CodexClient

client = CodexClient().authenticate()
```

`authenticate()` handles everything automatically:
- **Tokens present and fresh** → used directly, no network call
- **Tokens stale** → silently refreshed in the background
- **No valid tokens available** → opens your browser for the OAuth flow (blocking, first run only)

Tokens are saved to `~/.codex/auth.json` and shared with the official Codex CLI.

`CodexClient.from_saved_tokens()` is a shorthand for the same call.

---

## Basic usage

```python
from codex_backend_sdk import CodexClient, TextDelta, ResponseCompleted

client = CodexClient.from_saved_tokens()

for event in client.stream("Explain quicksort in one paragraph"):
    if isinstance(event, TextDelta):
        print(event.text, end="", flush=True)
    elif isinstance(event, ResponseCompleted):
        print(f"\n[tokens: in={event.input_tokens} out={event.output_tokens}]")
```

Or collect the full response at once:

```python
text, completion = client.respond("Explain quicksort in one paragraph")
print(text)
```

---

## Models

```python
models = client.list_models()
for m in models:
    print(m.slug, m.display_name, m.context_window)

info = client.get_model("codex-mini-latest")
```

---

## Multi-turn conversation

Pass prior turns as `conversation_history`. Each turn is a raw dict in Responses API format.

```python
history = []

def chat(user_input: str) -> str:
    text, _ = client.respond(user_input, conversation_history=history)
    history.append({
        "type": "message", "role": "user",
        "content": [{"type": "input_text", "text": user_input}],
    })
    history.append({
        "type": "message", "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    })
    return text

print(chat("My name is Alice."))
print(chat("What's my name?"))  # model remembers
```

---

## Tool use

Tool definitions follow the same format as the official OpenAI SDK.

```python
import json
from codex_backend_sdk import CodexClient, TextDelta, ToolCall, ResponseCompleted

client = CodexClient.from_saved_tokens()

tools = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get the current temperature for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
            },
            "required": ["city"],
        },
    }
]

def get_weather(city: str) -> dict:
    return {"city": city, "temperature": 22, "unit": "celsius"}


history = []

# Turn 1 — model may emit a ToolCall
for event in client.stream("What's the weather in Paris?", tools=tools):
    if isinstance(event, TextDelta):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolCall):
        result = get_weather(**event.parsed_arguments())
        history.append(event.as_history_item())           # the function_call item
        history.append(event.to_tool_result(json.dumps(result)))  # function_call_output

# Turn 2 — model sees the tool result and replies
for event in client.stream(None, conversation_history=history, tools=tools):
    if isinstance(event, TextDelta):
        print(event.text, end="", flush=True)
    elif isinstance(event, ResponseCompleted):
        print()
```

`tool_choice` defaults to `"auto"`. Other values: `"none"`, `"required"`, or `{"type": "function", "name": "..."}`.

---

## Image input

```python
from codex_backend_sdk import image_url, image_b64

# From a URL
for event in client.stream(
    ["What's in this image?", image_url("https://example.com/photo.jpg")]
):
    ...

# From a local file (base64)
import base64
with open("photo.jpg", "rb") as f:
    data = base64.b64encode(f.read()).decode()

for event in client.stream(
    ["Describe this image.", image_b64(data, "image/jpeg")]
):
    ...
```

---

## Reasoning

```python
# Enable chain-of-thought (reasoning tokens are billed separately)
for event in client.stream(
    "Solve: if 3x + 7 = 22, what is x?",
    reasoning="medium",
    reasoning_summary="concise",   # "concise" | "detailed" | "auto"
):
    ...
```

`reasoning` values: `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"`.

---

## Structured output (JSON Schema)

```python
import json

schema = {
    "title": "person",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age":  {"type": "integer"},
    },
    "required": ["name", "age"],
    "additionalProperties": False,
}

text, _ = client.respond(
    "Extract: Alice is 30 years old.",
    output_schema=schema,
)
person = json.loads(text)
print(person)  # {"name": "Alice", "age": 30}
```

---

## Context compaction

When a conversation grows long, compact it into an encrypted summary the model can still read:

```python
result = client.compact(history)

# result.output_items replaces the full history
for event in client.stream("Continue…", conversation_history=result.output_items):
    ...
```

---

## Usage / quota

```python
quota = client.usage()
print(quota)  # raw dict from /backend-api/wham/usage
```

---

## Stream events reference

| Type | Emitted when |
|---|---|
| `TextDelta` | incremental text chunk arrives |
| `ReasoningDelta` | reasoning summary chunk (requires `include_reasoning=True`) |
| `ToolCall` | model requests a function call |
| `OutputItem` | a non-tool output item completes (message, compaction_summary, …) |
| `ResponseCompleted` | stream ends successfully; carries full `TokenUsage` |
| `ResponseFailed` | stream ends with an error (`code`, `message`) |

---

## `stream()` parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `user_message` | `str \| list[dict] \| None` | — | User prompt. `None` to continue without a new message (e.g. after tool results). |
| `model` | `str` | `"gpt-5.4"` | Model slug. |
| `instructions` | `str` | `""` | System instructions. |
| `conversation_history` | `list[dict]` | `None` | Prior turns (ResponseItem format). |
| `tools` | `list[dict]` | `None` | Tool definitions (OpenAI function format). |
| `tool_choice` | `str \| dict` | `"auto"` | `"auto"`, `"none"`, `"required"`, or `{"type":"function","name":"..."}`. |
| `parallel_tool_calls` | `bool` | `False` | Allow multiple tool calls in one turn. |
| `reasoning` | `str` | `None` | `"minimal"` / `"low"` / `"medium"` / `"high"` / `"xhigh"`. |
| `reasoning_summary` | `str` | `None` | `"concise"` / `"detailed"` / `"auto"`. |
| `verbosity` | `str` | `None` | `"low"` / `"medium"` / `"high"`. Mutually exclusive with `output_schema`. |
| `output_schema` | `dict` | `None` | JSON Schema for structured output. |
| `include_reasoning` | `bool` | `False` | Emit `ReasoningDelta` events. |
| `web_search` | `str` | `None` | `"cached"` (OpenAI index), `"live"` (real-time fetch), or `"disabled"` / `None` (off). Incompatible with `reasoning="minimal"`. |
| `store` | `bool` | `False` | Persist the response server-side. |
| `service_tier` | `str` | `None` | `"flex"` (higher throughput) or `"fast"` (lower latency). |
| `prompt_cache_key` | `str` | `None` | UUID to share across calls with a common prefix — hits the server-side prompt cache. |

---

## How it works

Authentication uses the same ChatGPT OAuth 2.0 + PKCE flow as the official Codex CLI (`codex-rs`). Tokens are stored in `~/.codex/auth.json` and can be refreshed without re-opening the browser.

The backend (`chatgpt.com/backend-api/codex`) is distinct from `api.openai.com` and is accessed via your ChatGPT subscription rather than an API key. All responses are streamed over SSE — the backend does not support non-streaming requests.
