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

## Supported Backend Endpoints

The SDK exposes the supported backend endpoints through either OpenAI-shaped
resources (`responses`, `models`, `realtime`) or Codex-only resources (`codex`).

| Backend endpoint | SDK method | Notes |
|---|---|---|
| `POST /backend-api/codex/responses` | `client.responses.create(...)` | Stream-only backend; non-streaming SDK calls are collected from SSE events. |
| `POST /backend-api/codex/responses/compact` | `client.responses.compact(...)` | Codex-specific helper for encrypted context compaction. |
| `POST /backend-api/codex/memories/trace_summarize` | `client.codex.memories.trace_summarize(...)` | Raw Codex memory trace summarization helper. |
| `GET /backend-api/codex/models` | `client.models.list()` / `client.models.retrieve(...)` | OpenAI-shaped model objects with Codex metadata preserved as extra fields. |
| `POST /backend-api/codex/realtime/calls` | `client.realtime.calls.create(...)` | OpenAI-shaped SDP call creation for realtime sessions. |
| `wss://api.openai.com/v1/realtime?model=...` | `client.realtime_websocket_url(...)` / `client.realtime_websocket_headers(...)` | Helper surface used by codex-agent's realtime plugin. |
| `POST /v1/embeddings` | `client.embeddings.create(...)` | Uses the Codex OAuth access token against `api.openai.com`; verified with `text-embedding-3-small`. |
| `POST /v1/audio/transcriptions` | `client.audio.transcriptions.create(...)` | Uses the Codex OAuth access token against `api.openai.com`; verified with `gpt-4o-mini-transcribe`. |
| `GET /backend-api/wham/usage` | `client.codex.usage()` | Codex/ChatGPT quota and rate-limit status. |
| `GET /backend-api/wham/config/requirements` | `client.codex.config.requirements()` | Raw managed requirements/config payload for the authenticated account. |
| `GET /backend-api/wham/tasks/list` | `client.codex.tasks.list(...)` | Raw Codex cloud task listing. |
| `GET /backend-api/wham/tasks/{task_id}` | `client.codex.tasks.retrieve(task_id)` | Raw Codex cloud task detail. |
| `GET /backend-api/wham/tasks/{task_id}/turns` | `client.codex.tasks.turns.list(task_id)` | Raw task turn mapping. |
| `GET /backend-api/wham/tasks/{task_id}/turns/{turn_id}/sibling_turns` | `client.codex.tasks.turns.sibling_turns(task_id, turn_id)` | Raw sibling turn list. |
| `GET /backend-api/wham/environments` | `client.codex.environments.list()` | Raw Codex cloud environment list. |
| `POST /backend-api/files` + signed upload | `client.files.upload(...)` | Uploads local files for Codex Apps/MCP file parameters and returns `sediment://...` metadata. |
| `GET /backend-api/memories` | `client.codex.memories.list()` | Raw ChatGPT memory payload for the authenticated account. |
| `GET /backend-api/user_system_messages` | `client.codex.user_system_messages.retrieve()` | Raw ChatGPT customization/system-message payload. |

### Responses

`client.responses.create(...)` follows the official OpenAI Responses API where
the Codex backend overlaps with it.

Supported request fields:

- `model`
- `input`
- `instructions`
- `include`
- `parallel_tool_calls`
- `prompt_cache_key`
- `reasoning`
- `service_tier`
- `store=False`
- `stream`
- `text`
- `tool_choice`
- `tools`

The backend itself requires streaming. When `stream=True`, the SDK yields
`ResponseStreamEvent` objects directly. When `stream` is omitted or false, the
SDK consumes the SSE stream and returns a collected `Response`.

```python
response = client.responses.create(
    model="gpt-5.4",
    instructions="Be concise.",
    input=[
        {"role": "user", "content": "Summarize this API shape."},
    ],
    reasoning={"effort": "medium", "summary": "auto"},
    include=["reasoning.encrypted_content"],
    text={"verbosity": "medium"},
    prompt_cache_key="session-123",
)
```

Unsupported official Responses parameters are rejected explicitly with
`CodexBackendUnsupportedParameterError`, including `temperature`, `top_p`,
`max_output_tokens`, `metadata`, `user`, `safety_identifier`, `truncation`,
`previous_response_id`, `conversation`, `background`, `prompt`,
`prompt_cache_retention`, and `stream_options`.

### Context Compaction

`client.responses.compact(...)` is specific to the Codex backend. It compresses
a long Responses-style input list into an opaque encrypted compaction summary
that can be replayed in later `input` arrays.

```python
compacted = client.responses.compact(
    model="gpt-5.4",
    instructions="Keep task-critical context.",
    input=history,
)

history = compacted.output
```

The returned `CompactedResponse.output` contains regular response items plus
one or more `{"type": "compaction_summary", ...}` items. Treat those summaries
as opaque backend state.

### Models

`client.models.list()` and `client.models.retrieve(model)` mirror the official
OpenAI models resource, while preserving Codex-specific metadata as extra
Pydantic fields.

```python
models = client.models.list()
for model in models:
    print(
        model.id,
        model.context_window,
        model.supported_in_api,
        model.supports_reasoning_summaries,
    )
```

Common extra fields include:

- `display_name`
- `description`
- `context_window`
- `supported_in_api`
- `supports_reasoning_summaries`
- `support_verbosity`
- `default_verbosity`
- `default_reasoning_level`
- `supported_reasoning_levels`
- `auto_compact_token_limit`
- `prefer_websockets`
- `input_modalities`
- `available_in_plans`
- `base_instructions`
- `priority`
- `raw`

### Realtime

The SDK keeps the realtime surface available for integrations that bridge Codex
auth with voice sessions.

`client.realtime.calls.create(...)` mirrors the official OpenAI SDK call shape:

```python
answer = client.realtime.calls.create(
    sdp=offer_sdp,
    session={"type": "realtime", "model": "gpt-realtime-1.5"},
)

print(answer.text)
```

For WebSocket-based plugins such as `codex-agent`, the client also exposes small
helpers that reuse the OpenAI API key stored by the Codex OAuth flow:

```python
url = client.realtime_websocket_url(model="gpt-realtime-1.5")
headers = client.realtime_websocket_headers(session_id="voice-session")
```

`realtime_websocket_headers(...)` requires `~/.codex/auth.json` to contain
`openai_api_key`. The default `authenticate(request_api_key=True)` flow stores
that key when available.

### Embeddings

`client.embeddings.create(...)` mirrors the official OpenAI embeddings resource
and sends the Codex OAuth access token directly to `api.openai.com/v1`.

```python
embedding = client.embeddings.create(
    model="text-embedding-3-small",
    input="Embed this sentence.",
    dimensions=256,
)

print(embedding.data[0].embedding)
```

### Audio Transcriptions

`client.audio.transcriptions.create(...)` mirrors the official OpenAI
transcriptions resource for non-streaming calls.

```python
with open("meeting.wav", "rb") as audio:
    transcription = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=("meeting.wav", audio, "audio/wav"),
        response_format="json",
    )

print(transcription.text)
```

### Quota And Usage

`client.codex.usage()` calls the ChatGPT WHAM usage endpoint. It returns the raw
quota payload from the backend because the shape contains plan-specific fields.

```python
quota = client.codex.usage()
primary = quota.get("rate_limit", {}).get("primary_window", {})
print(primary.get("used_percent"))
```

Typical fields include:

- `plan_type`
- `rate_limit.allowed`
- `rate_limit.limit_reached`
- `rate_limit.primary_window`
- `rate_limit.secondary_window`
- `additional_rate_limits`
- `credits`
- `rate_limit_reached_type`

### Codex Cloud Tasks

The `client.codex.tasks` and `client.codex.environments` namespaces expose
read-only WHAM cloud-task payloads as raw backend dictionaries.

```python
tasks = client.codex.tasks.list(limit=10)
task = client.codex.tasks.retrieve(tasks["items"][0]["id"])
turns = client.codex.tasks.turns.list(task["task"]["id"])
environments = client.codex.environments.list()
```

Supported task-list filters are `limit`, `cursor`, `task_filter`, and
`environment_id`.

### ChatGPT Account Data

The `client.codex` namespace also exposes read-only ChatGPT account data that is
not part of the official OpenAI SDK.

```python
memories = client.codex.memories.list()
customization = client.codex.user_system_messages.retrieve()
requirements = client.codex.config.requirements()
```

These methods return raw backend dictionaries because these payloads can contain
personal account-specific fields and may change without notice.

`client.codex.memories.trace_summarize(...)` exposes the Codex memory
summarization endpoint used by the official client. It returns the raw backend
dictionary:

```python
summary = client.codex.memories.trace_summarize(
    model="gpt-5.4",
    traces=[
        {
            "id": "trace_1",
            "metadata": {"source_path": "memory.jsonl"},
            "items": [{"type": "message", "content": "Remember this"}],
        }
    ],
    reasoning={"effort": "low"},
)
```

### File Uploads

`client.files.upload(...)` follows the official Codex file flow for Apps/MCP
file parameters: create file metadata under ChatGPT, upload bytes to the signed
URL, then finalize the upload.

```python
uploaded = client.files.upload("report.csv")
print(uploaded.uri)  # sediment://file_...
```

### Observed But Not Exposed

The reverse-engineering notes in `docs/backend-api.md` include additional
observed endpoints. They are not exposed as SDK resources yet because they are
plan-gated, unavailable on `chatgpt.com`, or not stable enough:

- `POST /v1/audio/speech` (auth reaches the endpoint, but Pro OAuth lacks
  `api.model.audio.request` in current tests)
