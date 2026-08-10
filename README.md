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

# Remove the locally stored OAuth credentials when you are done.
client.logout()
```

`authenticate()` reuses stored Codex credentials when possible and starts the
interactive ChatGPT OAuth flow when needed. `logout()` is local and idempotent:
it clears the shared Codex credential file and unauthenticates the current
client; it does not revoke the ChatGPT account session remotely.

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

The SDK exposes the supported backend endpoints through OpenAI-shaped resources
(`responses`, `models`, `realtime`), Codex-only resources (`codex`), and a
separate `chatgpt` namespace for product APIs observed specifically in the
official Desktop app.

| Backend endpoint | SDK method | Notes |
|---|---|---|
| `POST /backend-api/codex/responses` | `client.responses.create(...)` | Stream-only backend; non-streaming SDK calls are collected from SSE events. |
| `POST /backend-api/codex/responses/compact` | `client.responses.compact(...)` | Codex-specific helper for encrypted context compaction. |
| `POST /backend-api/codex/memories/trace_summarize` | `client.codex.memories.trace_summarize(...)` | Raw Codex memory trace summarization helper. |
| `GET /backend-api/codex/models` | `client.models.list()` / `client.models.retrieve(...)` | OpenAI-shaped model objects with Codex metadata preserved as extra fields. |
| `POST /backend-api/codex/realtime/calls` | `client.realtime.calls.create(...)` / `create_v3(...)` | OAuth-authenticated SDP call creation. Realtime v3 accepts the confirmed Codex snapshots `gpt-live-1-codex` and `gpt-live-1-boulder-alpha`. |
| `wss://api.openai.com/v1/realtime?model=...` | `client.realtime_websocket_url(...)` / `client.realtime.websocket_headers(...)` | Voice v2 helpers; requires a Realtime API key obtained during OAuth or supplied by the auth store. |
| `POST /v1/embeddings` | `client.embeddings.create(...)` | Uses the Codex OAuth access token against `api.openai.com`; usage is charged to the associated OpenAI Platform organization. |
| `POST /backend-api/transcribe` | `client.audio.transcriptions.create(...)` | Uses the authenticated ChatGPT backend for non-streaming batch transcription; no developer API key is required. |
| `POST /backend-api/codex/images/generations` | `client.images.generate(...)` | Generates images through the authenticated Codex backend and returns typed base64 image data. |
| `POST /backend-api/codex/images/edits` | `client.images.edit(...)` | Edits one or more URL/data-URL images through the authenticated Codex backend. |
| `GET /backend-api/codex/rate-limit-reset-credits` | `client.codex.rate_limit_reset_credits.list()` | Lists detailed reset credits available to the authenticated account. |
| `POST /backend-api/codex/rate-limit-reset-credits/consume` | `client.codex.rate_limit_reset_credits.consume(...)` | Consumes a reset credit using an idempotent redemption request ID. |
| `GET /backend-api/wham/usage` | `client.codex.usage()` | Codex/ChatGPT quota and rate-limit status. |
| `GET /backend-api/wham/config/requirements` | `client.codex.config.requirements()` | Raw managed requirements/config payload for the authenticated account. |
| `GET /backend-api/wham/config/bundle` | `client.codex.config.bundle()` | Selected cloud-managed Codex configuration bundle. |
| `GET /backend-api/wham/settings/user` | `client.codex.config.user_settings()` | Authenticated Codex user settings. |
| `GET /backend-api/wham/accounts/check` | `client.codex.accounts.check()` | Account availability and entitlement check. |
| `GET/PATCH /backend-api/wham/profiles/me` | `client.codex.profile` | Token-usage profile plus explicit display-name, username, and profile-asset mutations. |
| `POST /backend-api/wham/profiles/me/photo` | `client.codex.profile.upload_photo(...)` / `set_photo(...)` | Multipart image upload returning the asset pointer expected by profile updates. |
| `GET /backend-api/wham/workspace-messages` | `client.codex.workspace_messages.list()` | Workspace-scoped backend messages. |
| `POST /backend-api/wham/tasks` | `client.codex.tasks.create(...)` | Creates a Codex cloud task from a raw evolving backend payload. |
| `POST /backend-api/wham/worktree_snapshots/...` | `client.codex.worktree_snapshots` | Uploads a caller-prepared worktree archive through signed storage and finalizes it for cloud-task use. |
| `POST /backend-api/wham/remote/control/server/enroll` | `client.codex.remote_control.enroll(...)` | Enrolls a Codex-compatible Remote Control server. |
| `POST /backend-api/wham/remote/control/server/refresh` | `client.codex.remote_control.refresh(...)` | Renews its short-lived Remote Control token. |
| `WSS /backend-api/wham/remote/control/server` | `client.codex.remote_control.connect(...)` | Opens the protocol-v3 envelope transport with cursor resume. |
| `GET /backend-api/wham/tasks/list` | `client.codex.tasks.list(...)` | Raw Codex cloud task listing. |
| `GET /backend-api/wham/tasks/{task_id}` | `client.codex.tasks.retrieve(task_id)` | Raw Codex cloud task detail. |
| `GET /backend-api/wham/tasks/{task_id}/turns` | `client.codex.tasks.turns.list(task_id)` | Raw task turn mapping. |
| `GET /backend-api/wham/tasks/{task_id}/turns/{turn_id}/sibling_turns` | `client.codex.tasks.turns.sibling_turns(task_id, turn_id)` | Raw sibling turn list. |
| `GET /backend-api/wham/environments` | `client.codex.environments.list()` | Raw Codex cloud environment list. |
| `POST /backend-api/files` + signed upload | `client.files.upload(...)` | Uploads local files for Codex Apps/MCP file parameters and returns `sediment://...` metadata. |
| `GET /backend-api/memories` | `client.codex.memories.list()` | Raw ChatGPT memory payload for the authenticated account. |
| `GET /backend-api/user_system_messages` | `client.codex.user_system_messages.retrieve()` | Raw ChatGPT customization/system-message payload. |
| `GET /backend-api/wham/remote/control/{mfa_requirement,clients}` | `client.codex.remote_control.desktop` | Desktop/browser-client MFA readiness and paired-client discovery. |
| `GET /backend-api/codex/remote/control/environments` | `client.codex.remote_control.desktop.environments` | Remote host discovery, with explicit rename/delete mutations. |
| `GET /backend-api/global/search` | `client.chatgpt.search.global_search(...)` | Cross-product search with source status and pagination metadata. |
| `POST /backend-api/files/process_upload_stream` | `client.chatgpt.files.process_upload_events(...)` | NDJSON upload-processing event stream. |
| `GET /backend-api/celsius/ws/user` | `client.chatgpt.conversations.websocket_url()` | User-scoped ChatGPT conversation continuation WebSocket URL. |
| `GET /backend-api/tpp/models/` | `client.chatgpt.models.third_party()` | Third-party-provider model catalog available to the account. |
| `GET /backend-api/gizmos/{id}` | `client.chatgpt.gizmos.retrieve(...)` | Generic custom-GPT metadata; projects remain a specialized resource. |
| `POST /backend-api/wham/apps` | `client.chatgpt.apps.list_tools()` / `call_tool(...)` / `request(...)` | Hosted Apps/MCP JSON-RPC transport observed in Desktop. |
| `/backend-api/ecosystem/...` | `client.chatgpt.apps` | Widget, launcher, MCP, and URL-safety helpers; install and launch operations remain explicit mutations. |
| `POST /backend-api/ps/mcp` | `client.chatgpt.apps.connect_hosted_mcp()` | MCP Streamable HTTP connection with initialization, sessions, JSON/SSE responses, tools, and resources. |
| `GET /backend-api/plugins/...` | `client.chatgpt.plugins` | Featured plugin IDs and curated export metadata used by Codex. |
| `GET /backend-api/connectors/directory/...` | `client.chatgpt.connectors.directory` | Public/workspace connector catalogs with validated pagination. |
| `/backend-api/aip/connectors/...` | `client.chatgpt.connectors` | Connector metadata, terms, logos, accessible links, and explicitly separated link-auth mutations. |
| `POST /backend-api/ps/apps/batch` | `client.chatgpt.connectors.batch_metadata(...)` | Batched app metadata and optional tool schemas. |
| `POST /backend-api/conversation/message/writing-blocks[/magic-edit]` | `client.chatgpt.writing_blocks` | Persists writing blocks and requests model-assisted Markdown replacements. |

Desktop-observed ChatGPT surfaces are deliberately separate from the Codex
protocol:

```python
# ChatGPT history, not Codex App Server threads
page = client.chatgpt.conversations.list(limit=20)
conversation = client.chatgpt.conversations.retrieve("conv_...")

# ChatGPT product model and voice metadata
chatgpt_models = client.chatgpt.models.list()
voices = client.chatgpt.voice.voices()

# Hosted ChatGPT Apps/MCP discovery and invocation
tools = client.chatgpt.apps.list_tools()
result = client.chatgpt.apps.call_tool("connector_tool_name", {"query": "..."})

# Full MCP Streamable HTTP protocol, including resources and session cleanup
with client.chatgpt.apps.connect_hosted_mcp() as mcp:
    hosted_tools = mcp.list_tools()["tools"]
    resources = mcp.list_resources()["resources"]

featured = client.chatgpt.plugins.featured(platform="codex")
curated_export = client.chatgpt.plugins.curated_export()

# Connector discovery is read-only; authentication and external actions live
# in separate, explicitly named authority namespaces.
connectors = client.chatgpt.connectors.directory.list_all()
detail = client.chatgpt.connectors.retrieve(
    connectors[0]["id"], include_actions=True
)
links = client.chatgpt.connectors.links.list_accessible()

# Persist a Desktop-compatible writing block, or request replacement choices
# for an explicitly marked Markdown range.
choices = client.chatgpt.writing_blocks.magic_edit(
    conversation_id="conv_...",
    full_block_body_markdown="Hello world",
    start_index=6,
    end_index=11,
    marked_block_body_markdown="Hello ⟦MAGICSTART⟧world⟦MAGICEND⟧",
    instruction="Make this warmer",
)
```

Hosted tools can mutate connected external services. Independent harnesses
must inspect tool annotations and own their user-confirmation policy before
calling them; the SDK does not silently invoke or auto-install anything.
`connect_hosted_mcp()` follows Codex's protocol version `2025-06-18`, sends the
required `X-OpenAI-Product-Sku` header, accepts JSON and SSE responses, carries
an assigned `Mcp-Session-Id`, and closes sessionful transports on context exit.

Connector link creation is available only through
`client.chatgpt.connectors.authentication`; contacts and email endpoints are
under `client.chatgpt.connectors.external_actions`. The latter can affect an
external service, so callers must inspect action safety metadata and own user
confirmation before invoking them. Discovery never authenticates a connector
or executes an action implicitly.

`external_actions.upload_google_drive_file(...)` reproduces Desktop's native
multipart conversion flow for `.docx`, `.pptx`, and `.xlsx` files. It requires
an already linked Google Drive connector and raises
`ConnectorAuthenticationRequiredError` when the backend reports that linking
is required; it never starts OAuth on the caller's behalf.

Remote Control exposes its two roles separately. Server enrollment, pairing,
WebSocket transport, and environment-scoped clients remain directly under
`client.codex.remote_control`; account-authorized Desktop/browser clients and
remote-host discovery live under `client.codex.remote_control.desktop`:

```python
desktop = client.codex.remote_control.desktop
requirement = desktop.mfa_requirement()
browser_clients = desktop.clients.list_all(include_pending=False)
remote_hosts = desktop.environments.list_all()
```

Pairing/revoking browser clients and renaming/deleting remote hosts are explicit
methods and are never performed by discovery calls.

Global ChatGPT search remains distinct from conversation-title search:

```python
matches = client.chatgpt.search.global_search(
    "release notes",
    sources=("conversation",),
    limit=20,
)
```

File download helpers follow backend-issued links and can return `bytes`, a
`BytesIO`, a persisted `Path`, or the raw HTTP response. OAuth headers are kept
for ChatGPT backend links and deliberately omitted from signed external CDN
requests:

```python
content = client.chatgpt.files.download("file_...")
buffer = client.chatgpt.files.download_attachment(
    "conversation_...", "file_...", response_format="bytes_io"
)
events = list(client.chatgpt.files.process_upload_events({"file_id": "file_..."}))
```

Projects and generic custom GPTs are separate concepts even though both use
ChatGPT's gizmo storage:

```python
projects = client.chatgpt.projects.list_all()
gizmo = client.chatgpt.gizmos.retrieve("g-...")
subagent_turns = client.chatgpt.conversations.subagent_thread_turns(
    "conversation_...", "thread_..."
)
conversation_websocket = client.chatgpt.conversations.websocket_url()
```

Model helpers expose the regular and TPP catalogs, system hints, custom-agent
hints, and optional internal slugs. `models.slugs()` returns `None` when that
optional Desktop route is unavailable instead of turning its expected 404 into
a hard failure. Account preference writes (`set_voice`, ultra effort, trusted
contact opt-out) are explicit mutation methods.

`client.chatgpt.conversations` exposes explicit history, search, batch, CRUD,
branch, prepare, streaming-create/resume, and attachment-list operations.
`client.chatgpt.projects`, `.files`, `.pins`, and `.shares` cover persisted
Desktop content and its explicit mutations. `client.chatgpt.account`, `.models`,
`.voice`, and `.sentinel` expose the other verified Desktop session surfaces.
Responses remain raw dictionaries (or raw streaming HTTP responses) because
these undocumented schemas can evolve. See
[`docs/desktop-endpoint-inventory.md`](docs/desktop-endpoint-inventory.md) for
the audited source snapshot and
[`docs/endpoint-coverage.md`](docs/endpoint-coverage.md) for the implementation
and live-probe status of each family.

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

For structured output, `client.responses.parse(...)` accepts a Pydantic model,
sends it as a strict JSON schema, and returns `ParsedResponse`:

```python
from pydantic import BaseModel


class Person(BaseModel):
    name: str
    age: int


parsed = client.responses.parse(
    model="gpt-5.4",
    input="Extract: Ada is 37 years old.",
    text_format=Person,
)
print(parsed.output_parsed.name)
```

Collected responses expose convenience properties for common output items:
`response.output_text`, `response.reasoning_summary`, and
`response.tool_calls`.

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
Pydantic fields. The returned page also exposes the backend `ETag` when present.

```python
models = client.models.list()
print(models.etag)
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

`client.realtime.calls.create(...)` mirrors the SDP call shape. For the current
Codex Realtime v3 protocol, use `create_v3(...)` with the Codex-specific model:

```python
answer = client.realtime.calls.create_v3(
    sdp=offer_sdp,
    session={
        "model": "gpt-live-1-codex",
        "instructions": "Speak naturally and stay concise.",
    },
)

print(answer.text)
```

Live ChatGPT OAuth probes validated both `gpt-live-1-codex` and
`gpt-live-1-boulder-alpha`. The bare `gpt-live` alias, `gpt-live-1`,
`gpt-live-latest`, and an unknown suffix were rejected by the backend, so the
SDK allows only the two confirmed identifiers. These models are not
interchangeable with the public `gpt-realtime` family documented for developer
API-key Realtime sessions.

For WebSocket-based plugins such as `codex-agent`, the client also exposes the
Voice v2 connection details:

```python
url = client.realtime_websocket_url(model="gpt-realtime-1.5")
headers = client.realtime.websocket_headers(session_id="voice-session")
```

During interactive ChatGPT OAuth login, the SDK exchanges the fresh ID token for
the temporary API key required by Realtime and stores it with the other local
credentials. Existing credentials created by older SDK versions may require one
forced interactive login before these headers are available.

For non-interactive checks, you can avoid triggering a browser login flow:

```python
client = OpenAI().authenticate(interactive=False)
print(client.authenticated)
print(client.account_info())
```

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

### ChatGPT Read-Aloud Speech

The official Desktop app exposes a smaller subscription-backed read-aloud
service. It accepts text, a pronunciation language, and playback speed, but
does not expose the voice and model controls of the public OpenAI speech API.

```python
speech = client.chatgpt.voice.synthesize_pronunciation(
    text="Bonjour Baptiste",
    pronunciation_language="fr-FR",
)

speech.write_to_file("bonjour.mp3")
# `speech.content` also provides the decoded bytes directly.

data_uri = client.chatgpt.voice.synthesize_pronunciation(
    text="Bonjour Baptiste",
    pronunciation_language="fr-FR",
    response_format="data_uri",
)

buffer = client.chatgpt.voice.synthesize_pronunciation(
    text="Bonjour Baptiste",
    pronunciation_language="fr-FR",
    response_format="bytes_io",
)

path = client.chatgpt.voice.synthesize_pronunciation(
    text="Bonjour Baptiste",
    pronunciation_language="fr-FR",
    response_format="file",
    output_path="bonjour.mp3",
)
```

This uses `POST /backend-api/pronunciation/synthesize?format=mp3` with ChatGPT
OAuth. The default `speech` format returns `ChatGPTSpeech` without touching the
filesystem; `data_uri`, `bytes_io`, and explicit `file` outputs are also
available. Availability follows the authenticated ChatGPT subscription and may
change independently of the public API.

### Image Generation

`client.images.generate(...)` uses the ChatGPT-authenticated Codex image backend,
not the separately billed OpenAI Platform image endpoint.

```python
image = client.images.generate(
    prompt="A cheerful blue robot holding a red flower",
    model="gpt-image-2",
    quality="auto",
    size="auto",
)

with open("robot.png", "wb") as output:
    output.write(base64.b64decode(image.data[0].b64_json))
```

The Codex contract supports `prompt`, `model`, `background`, `n`, `quality`,
and `size`. Editing accepts one or more ordinary URLs or data URLs:

```python
edited = client.images.edit(
    images=["data:image/png;base64,..."],
    prompt="Add a small red star in the center",
    quality="low",
)
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

Detailed reset credits are available separately:

```python
credits = client.codex.rate_limit_reset_credits.list()
for credit in credits.credits:
    print(credit.id, credit.title, credit.expires_at)

# Consuming a credit is an account mutation. Use a unique idempotency key.
result = client.codex.rate_limit_reset_credits.consume(
    redeem_request_id=str(uuid.uuid4()),
    credit_id=credits.credits[0].id,
)
```

### Codex Cloud Tasks

The `client.codex.tasks` and `client.codex.environments` namespaces expose WHAM
cloud-task payloads as raw backend dictionaries.

```python
tasks = client.codex.tasks.list(limit=10)
task = client.codex.tasks.retrieve(tasks["items"][0]["id"])
turns = client.codex.tasks.turns.list(task["task"]["id"])
environments = client.codex.environments.list()
created = client.codex.tasks.create({"prompt": "Fix the failing checks", "environment_id": "env_1"})
```

Supported task-list filters are `limit`, `cursor`, `task_filter`, and
`environment_id`.

### Remote Control

`client.codex.remote_control` implements the server side used by Codex App
Server: OAuth enrollment, token refresh, pairing, paired-client management, and
the protocol-v3 WebSocket transport.

```python
server = client.codex.remote_control.enroll(
    name="My workstation",
    installation_id="stable-installation-id",
    os="linux",
    arch="x86_64",
    app_server_version="0.147.0",
)

pairing = client.codex.remote_control.pairing.start(server, manual_code=True)
print(pairing.manual_pairing_code)

with client.codex.remote_control.connect(
    server,
    installation_id="stable-installation-id",
    server_name="My workstation",
) as connection:
    for client_envelope in connection:
        print(client_envelope)
```

The WebSocket deliberately exposes raw Codex envelope dictionaries. Callers
implementing an App Server bridge must preserve `client_id`, `stream_id`,
`seq_id`, chunk, ACK, and cursor semantics. `reconnect(connection)` refreshes an
expiring token and resumes from the latest cursor observed by the connection.
Tokens and pairing codes are secrets and must not be logged.

### ChatGPT Account Data

The `client.codex` namespace also exposes read-only ChatGPT account data that is
not part of the official OpenAI SDK.

```python
memories = client.codex.memories.list()
customization = client.codex.user_system_messages.retrieve()
requirements = client.codex.config.requirements()
bundle = client.codex.config.bundle()
settings = client.codex.config.user_settings()
account = client.codex.accounts.check()
profile = client.codex.profile.retrieve()
workspace_messages = client.codex.workspace_messages.list()
```

These methods return raw backend dictionaries because these payloads can contain
personal account-specific fields and may change without notice.
Profile writes remain explicit: `profile.update({...})` patches confirmed
official fields, while `upload_photo(...)` only uploads and returns an asset
pointer. `set_photo(...)` composes upload and profile update when that behavior
is desired.

`client.codex.memories.trace_summarize(...)` exposes the Codex memory
summarization endpoint used by the official client. It accepts dictionaries or
`RawMemory` objects and returns a typed `MemorySummarizeResponse`:

```python
from codex_backend_sdk import RawMemory

summary = client.codex.memories.trace_summarize(
    model="gpt-5.4",
    traces=[
        RawMemory(
            id="trace_1",
            metadata={"source_path": "memory.jsonl"},
            items=[{"type": "message", "content": "Remember this"}],
        )
    ],
    reasoning={"effort": "low"},
)
print(summary.output[0].memory_summary)
```

Transient HTTP failures (`429`, `5xx`, timeouts, and connection errors) are
retried by default. Configure this with `OpenAI(max_retries=..., retry_base_delay=...)`.

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
