# codex-backend-sdk

Unofficial Python SDK for building independent harnesses and integrations on
top of the backend capabilities available to an authenticated Codex/ChatGPT
subscriber.

The package intentionally separates three kinds of API:

| Surface | Purpose | Typical stability |
| --- | --- | --- |
| `client.*` | OpenAI-shaped inference and media primitives exposed by Codex | Most familiar and typed |
| `client.codex.*` | Codex-specific account, cloud, search, and Remote Control capabilities | Product-specific |
| `client.chatgpt.*` | ChatGPT product surfaces observed in the official Desktop client | Broadest, often raw |

> **Requirements:** a ChatGPT Plus, Pro, or Enterprise subscription.
> Authentication uses the official Codex OAuth client and stores compatible
> credentials in `~/.codex/auth.json`.

> **Independent project:** this library reverse-engineers undocumented backend
> contracts. It is not affiliated with, endorsed by, or supported by OpenAI.
> Availability can vary by plan, workspace, rollout, and backend revision.

## Install

```bash
git clone https://github.com/B4PT0R/codex-backend-sdk.git
cd codex-backend-sdk
pip install -e .
```

## Quickstart

```python
from codex_backend_sdk import OpenAI

client = OpenAI().authenticate()

response = client.responses.create(
    model="gpt-5.4",
    input="Explain quicksort in one paragraph.",
)

print(response.output_text)
```

`authenticate()` reuses existing Codex credentials when possible and otherwise
opens the browser OAuth flow. Most examples below assume an authenticated
`client` created this way.

## Choose the right surface

### Direct client: inference and reusable primitives

Start here for the common building blocks of an agent or application:

```python
client.responses       # text/reasoning/tool inference, parsing, compaction
client.models          # Codex model catalog
client.files           # upload files for Apps/MCP parameters
client.images          # Codex-backed image generation and editing
client.audio           # ChatGPT-backed transcription
client.embeddings      # OpenAI embeddings endpoint through OAuth
client.realtime        # WebRTC call creation and Realtime connection headers
```

These resources follow `openai-python` conventions where the backend overlaps
with the public OpenAI API. Backend-specific restrictions remain explicit.
See the [compatibility matrix](docs/openai-compatibility.md) for the audited
signatures, transport adaptations, and intrinsic OAuth/backend boundaries.

### `client.codex`: Codex product capabilities

Use this namespace for capabilities owned by Codex rather than the general
Responses API:

```python
client.codex.web_search          # structured search/page/weather/etc. commands
client.codex.usage               # quota plus detailed usage
client.codex.tasks               # Codex cloud tasks and turns
client.codex.environments        # cloud environments and machines
client.codex.repositories        # repository and branch discovery
client.codex.remote_control      # Remote Control server and host discovery
client.codex.config              # managed Codex settings/configuration
client.codex.profile             # Codex profile
client.codex.memories            # account memories and trace summarization
client.codex.worktree_snapshots  # cloud-task archive uploads
```

### `client.chatgpt`: Desktop-observed product APIs

Use this namespace when an integration needs ChatGPT product state or hosted
Apps rather than Codex inference:

```python
client.chatgpt.conversations  # ChatGPT history and streaming conversation API
client.chatgpt.projects       # projects, files, saves, connector scopes
client.chatgpt.files          # file library, attachments, downloads, processing
client.chatgpt.search         # cross-product indexed search
client.chatgpt.apps           # hosted Apps/MCP transports and widgets
client.chatgpt.plugins        # plugin catalogs, skills, bundles, sharing
client.chatgpt.connectors     # connector discovery, linking, external actions
client.chatgpt.models         # ChatGPT and third-party model catalogs
client.chatgpt.voice          # voices, dictation metadata, read-aloud speech
client.chatgpt.account        # account metadata and explicit preferences
```

These private product schemas evolve more often. The SDK therefore returns raw
dictionaries or raw streams when imposing a stable model would be misleading.

## Common workflows

### Generate a response

```python
response = client.responses.create(
    model="gpt-5.4",
    instructions="Be concise.",
    input="Summarize the CAP theorem.",
    reasoning={"effort": "medium", "summary": "auto"},
)

print(response.output_text)
print(response.reasoning_summary)
```

The backend always streams internally. Without `stream=True`, the SDK collects
events and returns a typed `Response`.

### Stream output

```python
stream = client.responses.create(
    input="Write a short limerick about Linux.",
    stream=True,
)

for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
```

For long-lived integrations, the alternate WebSocket transport keeps one
connection reusable across sequential turns:

```python
with client.responses.websocket.connect() as ws:
    for event in ws.create({"model": "gpt-5.4", "input": "Say hello."}):
        if event.get("type") == "response.output_text.delta":
            print(event.get("delta", ""), end="")
```

### Maintain a multi-turn conversation

The Codex backend does not expose `previous_response_id`; preserve prior items
in the next request:

```python
history = [{"role": "user", "content": "My name is Alice. Say OK."}]

first = client.responses.create(input=history)
history.extend(first.output)
history.append({"role": "user", "content": "What is my name?"})

print(client.responses.create(input=history).output_text)
```

### Compact a long context

```python
compacted = client.responses.compact(
    model="gpt-5.4",
    instructions="Preserve task-critical decisions and unresolved work.",
    input=history,
)

history = compacted.output
```

Compaction summaries are opaque encrypted backend state. Replay them as input;
do not parse or modify their contents.

### Call a function

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
    input="What is the weather in Paris?",
    tools=tools,
)
call = first.tool_calls[0]

second = client.responses.create(
    input=[
        call,
        {
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": json.dumps({"temperature": 18, "unit": "celsius"}),
        },
    ],
    tools=tools,
)
print(second.output_text)
```

### Parse structured output

```python
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int

result = client.responses.parse(
    input="Extract: Ada is 37 years old.",
    text_format=Person,
)

print(result.output_parsed)
```

### Discover available models

```python
for model in client.models.list():
    print(model.id, model.context_window, model.supported_reasoning_levels)

model = client.models.retrieve("gpt-5.4")
```

### Upload a file

```python
uploaded = client.files.upload("report.csv")
print(uploaded.uri)  # sediment://file_...
```

The helper creates ChatGPT file metadata, uploads to the backend-issued signed
URL, and finalizes the file for Apps/MCP file parameters.

### Transcribe audio

```python
with open("meeting.wav", "rb") as audio:
    transcript = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=("meeting.wav", audio, "audio/wav"),
    )

print(transcript.text)
```

### Generate or edit an image

```python
import base64

image = client.images.generate(
    model="gpt-image-2",
    prompt="A cheerful blue robot holding a red flower",
)

with open("robot.png", "wb") as output:
    output.write(base64.b64decode(image.data[0].b64_json))

edited = client.images.edit(
    image=open("robot.png", "rb"),
    mask=open("mask.png", "rb"),
    prompt="Add a small red star in the center",
)
```

## Codex workflows

### Structured web search

```python
result = client.codex.web_search.search(
    id="search-session-1",
    model="gpt-5-search-api",
    commands={
        "search_query": [{"q": "Python packaging PEP 735"}],
        "response_length": "short",
    },
)

print(result["output"])
continuation = result.get("encrypted_output")
```

The same transport supports page operations, image search, finance, weather,
sports, and time commands. See the API reference for command validation.

### Inspect quota and detailed usage

```python
quota = client.codex.usage()
daily = client.codex.usage_details.daily_token_breakdown()
credits = client.codex.usage_details.credit_events()

print(quota.get("rate_limit", {}).get("primary_window"))
```

### Work with Codex cloud tasks

```python
tasks = client.codex.tasks.list(limit=10)
task = client.codex.tasks.retrieve(tasks["items"][0]["id"])
turns = client.codex.tasks.turns.list(task["task"]["id"])
logs = client.codex.tasks.turns.logs(task["task"]["id"], turns[0]["id"])

environments = client.codex.environments.list()
repositories = client.codex.repositories.search(
    "codex",
    connector_id="github-connector-id",
)
```

Creation, cancellation, environment updates, cache resets, and pull-request
operations are explicit mutations; discovery methods never invoke them.

### Run a Remote Control server

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
    for envelope in connection:
        print(envelope)
```

The transport deliberately leaves protocol-v3 envelopes raw. A bridge must
preserve client, stream, sequence, ACK, chunk, and cursor semantics. Never log
pairing codes or Remote Control tokens.

## ChatGPT product workflows

### Search and retrieve ChatGPT history

```python
page = client.chatgpt.conversations.list(limit=20)
matches = client.chatgpt.conversations.search("release notes")
conversation = client.chatgpt.conversations.retrieve("conv_...")

global_matches = client.chatgpt.search.global_search(
    "release notes",
    sources=("conversation",),
    limit=20,
)
```

ChatGPT conversations are product history, not Codex App Server threads and not
Responses API state.

### Browse projects and files

```python
projects = client.chatgpt.projects.list_all()
project = client.chatgpt.projects.retrieve(projects[0]["id"])
project_conversations = client.chatgpt.projects.conversations(projects[0]["id"])

library = client.chatgpt.files.list_library_files()
content = client.chatgpt.files.download("file_...")
```

Download helpers can return bytes, `BytesIO`, a persisted `Path`, or the raw
HTTP response. OAuth is retained for ChatGPT URLs and omitted from signed CDN
URLs.

### Use hosted Apps/MCP

```python
tools = client.chatgpt.apps.list_tools()
result = client.chatgpt.apps.call_tool("connector_tool_name", {"query": "..."})

with client.chatgpt.apps.connect_hosted_mcp() as mcp:
    hosted_tools = mcp.list_tools()["tools"]
    resources = mcp.list_resources()["resources"]
```

Hosted tools may mutate external services. The calling harness must inspect
tool annotations and own user confirmation; the SDK never auto-invokes tools.

### Discover plugins and skills

```python
plugins = client.chatgpt.plugins.list_all(scope="GLOBAL")
installed = client.chatgpt.plugins.installed_all()
suggested = client.chatgpt.plugins.suggested()
skill = client.chatgpt.plugins.skill("plugins~...", "skill-name")

checkout = client.chatgpt.plugins.bundles.extract_plugin(
    "plugins~...",
    "./plugins/example",
)
```

Bundle helpers enforce HTTPS, download limits, archive limits, safe relative
paths, manifest checks, and atomic extraction. Signed download URLs never
receive the user's OAuth bearer.

### Discover connectors safely

```python
connectors = client.chatgpt.connectors.directory.list_all()
detail = client.chatgpt.connectors.retrieve(
    connectors[0]["id"],
    include_actions=True,
)
links = client.chatgpt.connectors.links.list_accessible()
```

Read-only discovery is separate from
`client.chatgpt.connectors.authentication` and
`client.chatgpt.connectors.external_actions`. Linking, email, contacts, and
Google Drive conversion require explicit method calls and caller-owned approval.

### Generate subscription-backed speech

```python
speech = client.chatgpt.voice.synthesize_pronunciation(
    text="Bonjour Baptiste",
    pronunciation_language="fr-FR",
)

speech.write_to_file("bonjour.mp3")
```

The ChatGPT read-aloud service is smaller than the public speech API: it exposes
language and playback speed, not arbitrary model and voice selection. It can
return a typed in-memory object, bytes, `BytesIO`, a data URI, or a file path.

## Advanced transports

### Realtime voice

```python
answer = client.realtime.calls.create_v3(
    sdp=offer_sdp,
    session={
        "model": "gpt-live-1-codex",
        "instructions": "Speak naturally and stay concise.",
    },
)
print(answer.answer_sdp)
```

Live probes confirmed `gpt-live-1-codex` and
`gpt-live-1-boulder-alpha`. They are Codex Realtime v3 snapshots, not aliases
for the public `gpt-realtime` family.

Voice v2 WebSocket integrations can obtain their connection details separately:

```python
url = client.realtime_websocket_url(model="gpt-realtime-1.5")
headers = client.realtime.websocket_headers(session_id="voice-session")
```

### Embeddings

```python
embedding = client.embeddings.create(
    model="text-embedding-3-small",
    input="Embed this sentence.",
    dimensions=256,
)
print(embedding.data[0].embedding)
```

Unlike ChatGPT transcription and Codex image generation, embeddings target the
OpenAI Platform endpoint and may consume the associated platform quota.

## Authentication and lifecycle

### Browser OAuth

```python
client = OpenAI().authenticate()
```

Use `authenticate(interactive=False)` to require existing usable credentials
without opening a browser, or `force=True` to request a fresh interactive login.

### Device-code OAuth

```python
client = OpenAI().authenticate_device_code(
    on_code=lambda code: print(code.verification_url, code.user_code),
    allowed_workspace_ids=["optional-workspace-id"],
)
```

This is suited to headless or remote harnesses that cannot receive a loopback
OAuth callback.

### Logout versus revocation

```python
client.logout()  # local, offline, idempotent
client.revoke()  # remote OAuth revocation, then local cleanup
```

`logout()` does not invalidate the account session remotely. `revoke()` is an
explicit network mutation and clears local credentials only after success.

## Reliability and safety

- Transient `429`, `5xx`, timeout, and connection failures are retried by
  default; configure `max_retries` and `retry_base_delay` on `OpenAI(...)`.
- Private backend schemas may change without notice. Typed models are used only
  where a stable boundary is useful.
- Mutations are explicitly named and separated from discovery where possible.
- Payments, subscriptions, workspace administration, attestation, reporting,
  telemetry, analytics, and beacons are deliberately not exposed.
- Personal access tokens are outside this OAuth-focused SDK surface.

## Documentation

- **[API reference](docs/api-reference.md):** complete resource tree, methods,
  parameters, return values, and important validation behavior.
- **[Backend protocol notes](docs/backend-api.md):** wire contracts, payload
  details, backend limitations, and live observations.
- **[Endpoint coverage](docs/endpoint-coverage.md):** exposed, live-probed,
  contract-tested, and excluded surfaces.
- **[Desktop endpoint inventory](docs/desktop-endpoint-inventory.md):** audited
  source snapshots and comparison with the official Desktop client.
- **[Changelog](CHANGELOG.md):** user-visible SDK changes.

## Development

```bash
uv sync --extra dev
uv run pytest -q
uv run python -m compileall -q codex_backend_sdk
uv build
```

Live probes are intentionally kept separate from the deterministic test suite:
tests must not consume quota, mutate account state, or depend on rollout state.

## License

MIT. See [LICENSE](LICENSE).
