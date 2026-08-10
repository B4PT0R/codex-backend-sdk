# Codex Backend API — Reverse-Engineering Notes

Sourced from live observation and `codex-rs` source (`openai/codex`).  
Last updated: 2026-08-10.

---

## Base URLs

| Path style | Base URL |
|---|---|
| Codex API (direct) | `https://chatgpt.com/backend-api/codex` |
| WHAM (account/quota) | `https://chatgpt.com/backend-api` |
| OpenAI API with Codex OAuth | `https://api.openai.com/v1` |

---

## Authentication headers

Every request must carry:

```
Authorization: Bearer <access_token>
ChatGPT-Account-ID: <account_id>
originator: codex_cli_rs
```

- `access_token` and `account_id` come from `~/.codex/auth.json` (written by the OAuth flow).
- `account_id` is extracted from the `id_token` JWT claim `https://api.openai.com/auth` → `chatgpt_account_id`.
- Tokens are obtained via ChatGPT OAuth 2.0 + PKCE (issuer: `https://auth.openai.com`, client_id: `app_EMoamEEZ73f0CkXaXp7hrann`).
- Some `api.openai.com/v1` endpoints accept the ChatGPT OAuth access token
  directly. In observed Pro-plan tests, `POST /v1/embeddings` and
  `POST /v1/audio/transcriptions` work with `Authorization: Bearer <access_token>`.

---

## Codex API endpoints

### `GET /codex/models`

List models available to this account.

**SDK method**: `client.models.list()` / `client.models.retrieve(model)`

**Query params**
- `client_version` — Codex CLI protocol/client version string (e.g. `"0.130.0"`).

**Response** — JSON `{ "models": [ ModelObject, … ] }`

The backend may include an `ETag` header. The SDK preserves it as
`client.models.list().etag`.

Key fields per model:
| Field | Type | Notes |
|---|---|---|
| `slug` | string | Model identifier, e.g. `"gpt-5.2"`, `"gpt-5.4"` |
| `display_name` | string | |
| `context_window` | int | |
| `supported_in_api` | bool | False for models only available via ChatGPT UI |
| `supports_reasoning_summaries` | bool | Whether `reasoning_summary` param works |
| `support_verbosity` | bool | |
| `default_verbosity` | string? | |
| `default_reasoning_level` | string? | |
| `supported_reasoning_levels` | list | `[{ effort, description }]` |
| `auto_compact_token_limit` | int? | Token count that triggers auto-compaction |
| `prefer_websockets` | bool | |
| `input_modalities` | list | e.g. `["text", "image"]` |
| `available_in_plans` | list | e.g. `["plus", "pro", "enterprise"]` |
| `base_instructions` | string | Default system prompt baked into the model |
| `priority` | int | Higher = shown first |

**Notes**
- `gpt-5.4` is the current default and works for inference but appears as `supported_in_api: false`.
- `gpt-5.2` has `supports_reasoning_summaries: true` and `supported_in_api: true`.

---

### `POST /codex/responses`

Main inference endpoint. **Stream-only** — `stream: true` is mandatory; the
backend never returns a non-streaming HTTP response. In SDK calls,
`client.responses.create(..., stream=False)` still returns a collected
`Response`, but this is assembled client-side from the SSE stream.

**SDK method**: `client.responses.create(...)`

`client.responses.parse(..., text_format=MyPydanticModel)` is a convenience
wrapper over the same endpoint. It populates `text.format` with a strict JSON
schema and returns `ParsedResponse`.

**Request body** (JSON):

```json
{
  "model": "gpt-5.4",
  "stream": true,
  "tools": [],
  "tool_choice": "auto",
  "parallel_tool_calls": false,
  "input": [ /* ResponseItem list */ ],
  "instructions": "",
  "reasoning": { "effort": "medium", "summary": "concise" },
  "text": { "format": { "type": "text" } },
  "store": false,
  "service_tier": null,
  "prompt_cache_key": null
}
```

Key fields:
| Field | Type | Notes |
|---|---|---|
| `model` | string | Model slug |
| `stream` | bool | Must be `true` |
| `input` | list | ResponseItem list (user messages, history, tool results) |
| `instructions` | string | System prompt |
| `tools` | list | OpenAI function-call format |
| `tool_choice` | string\|object | `"auto"` / `"none"` / `"required"` / `{"type":"function","name":"..."}` |
| `parallel_tool_calls` | bool | |
| `reasoning` | object? | `{ "effort": "low"\|"medium"\|"high"\|"xhigh", "summary": "concise"\|"detailed"\|"auto" }` |
| `text.format` | object | `{"type": "text"}` or `{"type": "json_schema", "name": "...", "schema": {...}, "strict": true}` |
| `store` | bool | Must be `false` |
| `service_tier` | string? | `"priority"` is accepted; `"auto"` is rejected |
| `prompt_cache_key` | string? | UUID for shared prompt cache across calls |
| `include` | list? | Include extra fields, e.g. `["reasoning.encrypted_content"]` |

**Prompt cache retention**

`prompt_cache_retention` is not accepted as a request parameter on this
endpoint. Sending either `"in_memory"` or `"24h"` returns:

```json
{"detail":"Unsupported parameter: prompt_cache_retention"}
```

Successful SSE events currently still report:

```json
"prompt_cache_retention": "24h"
```

This appears to be a backend-selected Codex policy rather than a client
configuration knob. It is important for long sessions: with stable
instructions, tools, schemas, and early conversation prefix, the 24h retention
can preserve prompt-cache hits across much longer idle gaps than default
in-memory prompt caching.

**Web search** (added to request when enabled):
```json
{ "tools": [{ "type": "web_search_preview", "search_context_size": "medium" }] }
```
Values: `"cached"` → OpenAI index; `"live"` → real-time fetch. Incompatible with `reasoning.effort = "minimal"`.

**Response** — SSE stream. Each event: `data: { ... }\n\n`

SSE event types:
| `type` field | Meaning |
|---|---|
| `response.output_item.added` | New output item started |
| `response.output_item.done` | Output item complete (message, reasoning, function_call, …) |
| `response.content_part.delta` | Incremental text chunk (`delta.text`) |
| `response.content_part.done` | Text part finished |
| `response.function_call_arguments.delta` | Tool call argument chunk |
| `response.function_call_arguments.done` | Tool call complete |
| `response.completed` | Stream finished; carries `usage` |
| `response.failed` | Stream ended with error; carries `error.code` and `error.message` |

**Reasoning delivery**  
Reasoning content is NOT delivered as streaming deltas. It arrives as a completed `response.output_item.done` event with `item.type = "reasoning"`:
```json
{
  "type": "response.output_item.done",
  "item": {
    "type": "reasoning",
    "summary": [{ "type": "summary_text", "text": "..." }],
    "encrypted_content": "<opaque blob>"
  }
}
```
- `summary` is populated only when `reasoning_summary` is set AND the model supports it (e.g. `gpt-5.2`).
- `encrypted_content` is always present; treat as opaque.

**Usage object** (in `response.completed`):
```json
{
  "input_tokens": 123,
  "output_tokens": 45,
  "output_tokens_details": { "reasoning_tokens": 30 },
  "total_tokens": 168
}
```

---

### `POST /codex/responses/compact`

Compact a long conversation into an encrypted summary the model can still read.

**Request body**:
```json
{
  "model": "gpt-5.4",
  "input": [ /* full conversation history */ ],
  "instructions": "Compact the conversation.",
  "tools": [],
  "parallel_tool_calls": false,
  "reasoning": { "effort": "medium" },
  "service_tier": "priority",
  "prompt_cache_key": "cache-key",
  "text": { "verbosity": "low" }
}
```

**Response** — synchronous JSON (not SSE):
```json
{
  "id": "resp_...",
  "output": [
    { "type": "message", "role": "user", ... },
    { "type": "compaction_summary", "encrypted_content": "..." },
    ...
  ]
}
```
- `output` replaces the original history; pass it as `input` in subsequent calls.
- The `compaction_summary` item is opaque on the client side.

**SDK method**: `client.responses.compact(...)`

---

### `POST /codex/memories/trace_summarize`

Summarize traces into persistent memories.

**SDK method**: `client.codex.memories.trace_summarize(...)`

**Status**: Supported as a typed helper. May return `403 Forbidden` depending
on plan/account capabilities.

**Request body**:
```json
{
  "model": "gpt-5.4",
  "traces": [
    {
      "id": "trace_1",
      "metadata": { "source_path": "memory.jsonl" },
      "items": [ /* normalized trace items */ ]
    }
  ],
  "reasoning": { "effort": "low" }
}
```

**Response** — JSON `{ "output": [...] }`, exposed by the SDK as
`MemorySummarizeResponse`.

---

### `POST /codex/realtime/calls`

Realtime audio/video call initiation.

**SDK methods**: `client.realtime.calls.create(...)`,
`client.realtime.calls.create_v3(...)`

**Status**: Supported by the current Codex client over ChatGPT OAuth. The SDK
follows the Codex client protocol:

- plain SDP offer: `client.realtime.calls.create(sdp=offer_sdp)`
- AVAS SDP offer plus session payload:
  `client.realtime.calls.create(sdp=offer_sdp, session={...})`
- Realtime v3 frameless call:
  `client.realtime.calls.create_v3(sdp=offer_sdp, session={"model": "gpt-live-1-codex"})`

For Realtime v3, Codex sends `openai-alpha: quicksilver=v2`, the AVAS query
parameters `intent=quicksilver&architecture=avas`, and a `gpt-live` session.
Live WebRTC call-creation probes against the ChatGPT OAuth route validated both
`gpt-live-1-codex` and `gpt-live-1-boulder-alpha`: each returned an SDP answer
and a Realtime call id. The aliases `gpt-live`, `gpt-live-1`,
`gpt-live-latest`, and an unknown suffix returned HTTP 400. `create_v3`
therefore accepts exactly the two confirmed identifiers rather than every
`gpt-live` prefix.

This is distinct from the public Realtime API documented for developer API keys.
On the OpenAI API host, the same Codex implementation uses `/v1/live` for the
frameless v3 call, whereas the ChatGPT OAuth backend keeps the
`/backend-api/codex/realtime/calls` route and its JSON `{sdp, session}` body.

The response exposes `.answer_sdp` and `.call_id`, while preserving the binary
helpers `.content`, `.text`, `.read()`, `.iter_bytes()`, and
`.write_to_file(...)`.

### `POST /codex/alpha/search`

**SDK method**: `client.codex.web_search.search(...)`

This is the structured Web Search transport used by current Codex when the
dedicated search-request feature is enabled. It accepts a stable request
envelope (`id`, `model`, optional input/reasoning/settings/token budget) and the
full command object currently defined by Codex: text and image queries, open,
click, find, PDF screenshots, finance, weather, sports, time, and response
length. Optional `originator` and `x-codex-turn-metadata` headers are preserved.

The SDK validates the request envelope and the stable response fields while
leaving individual structured result objects and additive top-level fields raw
for forward compatibility. A live OAuth probe using the harmless `time`
command returned text plus encrypted continuation state successfully.

---

### Realtime WebSocket helpers

The `codex-agent` realtime plugin uses OpenAI Realtime WebSocket sessions while
sharing the Codex OAuth/token store.

**SDK methods**:

- `client.realtime_websocket_url(model="gpt-realtime-1.5")`
- `client.realtime.websocket_headers(session_id="...")`

The URL helper returns:

```text
wss://api.openai.com/v1/realtime?model=...
```

The headers helper returns `Authorization: Bearer <openai_api_key>`, the Codex
originator, and the optional session id. Interactive ChatGPT OAuth attempts to
exchange its fresh ID token for this Realtime API key and persists it when the
account is entitled to one. If that exchange is unavailable, regular Codex OAuth
continues to work but Voice v2 requires a separately provisioned API key.

---

## Embeddings and Transcription

These OpenAI-shaped resources deliberately use different upstreams. Embeddings
remain an OpenAI Platform call and consume the associated developer-account
quota. Batch transcription uses the authenticated ChatGPT backend and does not
require a developer API key.

### `POST /v1/embeddings`

**SDK method**: `client.embeddings.create(...)`

**Status**: Supported. Verified with:

```json
{
  "model": "text-embedding-3-small",
  "input": "ping",
  "dimensions": 3
}
```

The response matches the official embeddings shape:
`{ "object": "list", "data": [{ "object": "embedding", ... }], "usage": ... }`.
The request is accounted against the OpenAI Platform organization returned by
the API; ChatGPT OAuth authenticates it but does not include it in a ChatGPT
subscription.

### `POST /backend-api/transcribe`

**SDK method**: `client.audio.transcriptions.create(...)`

**Status**: Supported for non-streaming ChatGPT batch transcription. The SDK
uploads multipart audio with the OAuth bearer and `ChatGPT-Account-ID`, and
supports the `model`, `language`, `prompt`, `temperature`, and `json`/`text`
response options used by Codex Agent. Streaming, timestamps, speaker references,
chunking, SRT, and VTT are rejected locally rather than falling back to a
billable Platform endpoint.

### `POST /backend-api/codex/images/generations`

**SDK method**: `client.images.generate(...)`

**Status**: Supported through ChatGPT OAuth. Verified with `gpt-image-2`; the
response contains `created` and `data[].b64_json`, plus optional effective
`background`, `quality`, and `size` fields. Supported request fields mirror the
current Codex client: `prompt`, `model`, `background`, `n`, `quality`, and
`size`. This uses the Codex/ChatGPT backend rather than the OpenAI Platform
image endpoint.

### `POST /backend-api/codex/images/edits`

**SDK method**: `client.images.edit(...)`

**Status**: Supported through ChatGPT OAuth. Accepts one or more remote URLs or
`data:` URLs as `images[].image_url`, plus the same prompt/model/background/count/
quality/size controls as generation. Verified by generating a source image and
editing it through the authenticated backend.

### `POST /v1/audio/speech`

**Status**: Observed but not exposed. A malformed request reaches payload
validation, but a valid Pro-plan request currently returns `401` with missing
`api.model.audio.request` scope.

---

## WHAM endpoints

WHAM is the ChatGPT account/quota management layer, distinct from the Codex API.
The official Desktop application references a broader set of WHAM and general
ChatGPT routes than `codex-rs`; see
[`desktop-endpoint-inventory.md`](desktop-endpoint-inventory.md) for the audited
snapshot, Desktop-only comparison, and exposure recommendations.

### Worktree snapshots

`client.codex.worktree_snapshots` implements Desktop's transport for attaching
a local worktree snapshot to a cloud-task environment:

1. `create_upload(...)` sends repository/archive metadata to
   `/wham/worktree_snapshots/upload_url`;
2. the archive is uploaded to the returned signed URL without the ChatGPT OAuth
   session or `Authorization` header;
3. `finish_upload(...)` sends the returned `file_id` and `etag` to
   `/wham/worktree_snapshots/finish_upload`.

`upload_archive(...)` composes those steps for an existing archive. It does not
invent Desktop's private Git/archive-preparation policy: independent harnesses
remain responsible for selecting files, preserving repository metadata, and
constructing the tarball they intend to send. The backend allocation/finalize
contract is covered locally but was not invoked live because it mutates storage.

### `GET /backend-api/wham/usage`

Rate limits and quota for this account. Used as the auth probe — a 200 response confirms valid tokens.

**SDK method**: `client.codex.usage()`

**Response** — JSON:
```json
{
  "plan_type": "plus",
  "rate_limit": {
    "allowed": true,
    "limit_reached": false,
    "primary_window": {
      "used_percent": 12,
      "limit_window_seconds": 3600,
      "reset_after_seconds": 2847,
      "reset_at": 1745180000
    },
    "secondary_window": { ... }
  },
  "credits": { ... },
  "additional_rate_limits": [ ... ],
  "rate_limit_reached_type": null
}
```

Known `plan_type` values: `guest`, `free`, `go`, `plus`, `pro`, `prolite`, `free_workspace`, `team`, `business`, `enterprise`, `edu`, `education`, `quorum`, `k12`, `unknown`.

Known `rate_limit_reached_type.type` values: `rate_limit_reached`, `workspace_owner_credits_depleted`, `workspace_member_credits_depleted`, `workspace_owner_usage_limit_reached`, `workspace_member_usage_limit_reached`.

---

### `GET /backend-api/codex/rate-limit-reset-credits`

**SDK method**: `client.codex.rate_limit_reset_credits.list()`

Returns a typed detail payload containing `available_count`,
`total_earned_count`, and credit rows with IDs, reset type, status, grant and
expiry timestamps, title, and description. The equivalent WHAM path is also
currently accepted by ChatGPT, but the SDK follows the active Codex client
path.

### `POST /backend-api/codex/rate-limit-reset-credits/consume`

**SDK method**: `client.codex.rate_limit_reset_credits.consume(...)`

Consumes a reset credit. `redeem_request_id` is required as the idempotency key;
`credit_id` selects a specific available credit when supplied. This mutates
account quota state and is never called implicitly by the SDK.

### `GET /backend-api/wham/config/requirements`

Fetch managed requirements/config for this account (plan-gated settings).

**SDK method**: `client.codex.config.requirements()`

**Response** — JSON config blob; schema defined in `codex-rs/cloud-requirements`.

---

### `GET /backend-api/wham/config/bundle`

Fetch the selected cloud-managed Codex configuration bundle.

**SDK method**: `client.codex.config.bundle()`

---

### `GET /backend-api/wham/settings/user`

Fetch authenticated Codex user settings. Current Codex requests this with
cache bypass headers; callers should treat the raw payload as evolving.

**SDK method**: `client.codex.config.user_settings()`

---

### `GET /backend-api/wham/accounts/check`

Check account availability and Codex entitlements.

**SDK method**: `client.codex.accounts.check()`

---

### `GET/PATCH /backend-api/wham/profiles/me`

Fetch or explicitly update the authenticated token-usage profile.

**SDK methods**: `client.codex.profile.retrieve()` and `.update(body)`

Desktop also uploads image bytes as multipart data to
`POST /backend-api/wham/profiles/me/photo`. The response's `asset_pointer` is
then supplied as `profile_asset_pointer` to the profile patch. The SDK exposes
the two operations separately through `upload_photo(...)`, and composes them in
`set_photo(...)`. These mutations are contract-tested but not invoked live.

---

### `GET /backend-api/wham/workspace-messages`

List workspace-scoped messages supplied by the Codex backend.

**SDK method**: `client.codex.workspace_messages.list()`

---

### `GET /backend-api/wham/tasks/list`

List cloud tasks (Pro/Enterprise cloud execution feature).

**SDK method**: `client.codex.tasks.list(...)`

**Query params**: `limit`, `task_filter`, `environment_id`, `cursor`.

---

### `POST /backend-api/wham/tasks`

Create a Codex cloud task. The request schema evolves with the cloud-task
product, so the SDK currently accepts a JSON-serializable object and returns the
raw response.

**SDK method**: `client.codex.tasks.create(body)`

---

### `GET /backend-api/wham/tasks/{task_id}`

Get details for a specific cloud task.

**SDK method**: `client.codex.tasks.retrieve(task_id)`

Observed response includes `task`, `current_user_turn`,
`current_assistant_turn`, and `current_diff_task_turn`.

---

### `GET /backend-api/wham/tasks/{task_id}/turns`

List task turns as a mapping.

**SDK method**: `client.codex.tasks.turns.list(task_id)`

Observed response includes `turn_mapping` and `current_turn_id`.

---

### `GET /backend-api/wham/tasks/{task_id}/turns/{turn_id}/sibling_turns`

List sibling turns for a task turn.

**SDK method**: `client.codex.tasks.turns.sibling_turns(task_id, turn_id)`

---

### `GET /backend-api/wham/environments`

List Codex cloud environments for the authenticated account.

**SDK method**: `client.codex.environments.list()`

Observed response is a raw list of environment objects, including repository
metadata, network settings, permissions, and cache settings. Secrets are present
as backend metadata, not plaintext values.

---

### WebSocket: `wss://chatgpt.com/backend-api/wham/remote/control/server`

Remote control / agent-as-a-service websocket. The current Codex transport also
uses these OAuth-authenticated lifecycle routes:

- `POST /backend-api/wham/remote/control/server/enroll`
- `POST /backend-api/wham/remote/control/server/refresh`
- `POST /backend-api/wham/remote/control/server/pair`
- `POST /backend-api/wham/remote/control/server/pair/status`
- `GET /backend-api/wham/remote/control/environments/{environment_id}/clients`
  with optional `cursor`, `limit`, and `order` query parameters.
- `DELETE /backend-api/wham/remote/control/environments/{environment_id}/clients/{client_id}`

**SDK namespace**: `client.codex.remote_control`

The SDK exposes enrollment and refresh as typed `RemoteControlEnrollment`
objects, pairing and paired-client management as focused resources, and the
WebSocket as a synchronous raw-envelope connection. It uses protocol version 3,
base64-encodes `x-codex-name`, refreshes tokens within five minutes of expiry,
and can reconnect with the latest observed subscription cursor.

The transport intentionally does not reinterpret the embedded App Server
JSON-RPC messages. Callers must preserve the Codex `ClientEnvelope` and
`ServerEnvelope` fields and implement their expected chunk/ACK routing.

### Desktop/mobile Remote Control role

The official Desktop client also acts as a Remote Control client. These
account-authorized routes are exposed separately under
`client.codex.remote_control.desktop`:

- `GET /backend-api/wham/remote/control/mfa_requirement`
- `GET /backend-api/accounts/mfa_info`
- `GET /backend-api/wham/remote/control/clients`
- `POST /backend-api/wham/remote/control/client/pair`
- `DELETE /backend-api/wham/remote/control/clients/{client_id}`
- `GET /backend-api/codex/remote/control/environments`
- `GET /backend-api/codex/remote/control/clients/{client_id}/environments`
- `PATCH/DELETE /backend-api/codex/remote/control/environments/{environment_id}`

MFA state, browser-client listing, and environment listing were verified live
with ordinary Codex OAuth. Pair, revoke, rename, and delete follow the official
payloads but were deliberately not invoked during probing. Pagination detects
repeated cursors rather than looping forever, and pending enrollment entries
can be retained or filtered explicitly.

---

## Plugins and hosted Apps/MCP

The current Codex and Desktop codepaths also use the following ChatGPT OAuth
surfaces:

- `GET /backend-api/plugins/export/curated` — metadata and signed download for
  the curated plugin bundle.
- `GET /backend-api/plugins/featured` — legacy remote plugin discovery.
- `POST /backend-api/ps/mcp` — hosted Apps/MCP JSON-RPC transport.

`POST /backend-api/wham/apps`, the transport used by current Desktop Apps, is
exposed under `client.chatgpt.apps`. `list_tools()` and `call_tool()` validate
the stable JSON-RPC envelope while preserving tool schemas and results; the
lower-level `request()` remains available so the SDK does not pretend that the
evolving MCP payload is a stable REST schema. A live OAuth probe returned 170
tools. The same resource exposes the observed `/ecosystem` launcher, widget,
MCP, and URL-safety calls, with installation and launch kept as explicitly
named mutations.

The distinct `/ps/mcp` endpoint is exposed by
`client.chatgpt.apps.connect_hosted_mcp()`. It implements the MCP Streamable
HTTP lifecycle used by current `codex-rs`: protocol version `2025-06-18`, the
`X-OpenAI-Product-Sku: codex` header, `initialize` followed by
`notifications/initialized`, JSON or SSE responses, optional
`Mcp-Session-Id`, and session deletion on close. It provides raw requests plus
tools and resource convenience methods. A live OAuth probe returned 172 tools,
37 resources, no resource templates, and no session ID for the current
stateless deployment.

The legacy read-only feeds remain exposed through `client.chatgpt.plugins`:
`featured()` returned 29 plugin IDs for the `codex` platform in a live probe,
and `curated_export()` returned the backend-supplied signed archive URL.
`plugins.bundles.download_curated()` downloads that URL without forwarding the
OAuth bearer; `extract_curated()` strips the generated archive wrapper, rejects
unsafe entries, enforces compressed and expanded limits, validates
`.agents/plugins/marketplace.json`, and activates a new destination atomically.
The current 17,933,003-byte export was downloaded and extracted successfully in
a read-only live probe. Nothing is installed implicitly.

Current `codex-rs` additionally uses the `/ps/plugins` service. The same SDK
resource now exposes paginated `list`, `search`, `installed`,
`workspace_shared`, `suggested`, and `retrieve` methods. All requests carry the
official `OAI-Product-Sku: codex` header; pagination preserves `pageToken` and
rejects repeated tokens. `include_download_urls` is opt-in so ordinary catalog
reads do not mint signed bundle URLs unnecessarily.

`skill(plugin_id, skill_name)` retrieves the backend-authored `SKILL.md`
contents and additive bundle metadata while verifying that both returned
identifiers match the request. A live probe returned a valid skill detail and
Markdown body from the current global catalog.

A read-only live probe returned 184 global catalog entries, three installed
plugins, 40 suggestions, valid search/detail responses, and an empty workspace
shared page for the test account. `plugins.installation.install/uninstall`
follows the official mutations and verifies the returned plugin ID and enabled
state, but neither mutation was invoked live.

`client.chatgpt.plugins.shares` covers the current workspace publication
protocol. `publish_directory(...)` validates a plugin manifest, rejects links
and special filesystem entries, builds the same rootless gzip tar archive as
Codex, enforces the 50 MiB compressed limit, obtains a signed upload URL, and
uploads with Azure's `x-ms-blob-type: BlockBlob` header without forwarding the
OAuth session. `publish_archive(...)` accepts an already prepared archive.
Finalization supports create or update plus `LISTED`, `UNLISTED`, and `PRIVATE`
policies; unlisted shares automatically retain the authenticated workspace as a
reader, matching Codex.

Created-share discovery was live-probed successfully (empty on the test
account). Publication, target updates, and deletion are explicit mutations and
were contract-tested without touching the live workspace. `update_targets()`
accepts only the official user/group/workspace principals and reader/editor
roles; `delete()` requires the official HTTP 204 response.

`client.chatgpt.plugins.bundles` completes the remote materialization flow.
Plugin detail is requested with `includeDownloadUrls=true`, then the
backend-issued bundle is downloaded without ChatGPT authorization headers.
Initial and redirected URLs must use HTTPS; declared and streamed sizes are
bounded to 100 MiB. Downloads can return bytes, `BytesIO`, or a persisted file.

`extract_plugin(...)` stages extraction beside the destination, rejects
absolute/traversing paths, links, and special tar entries, caps total extracted
data at 512 MiB, validates the standard JSON manifest and its plugin name, then
renames the staging directory atomically. A live 80,440-byte bundle was
downloaded and extracted successfully. Skill bundles use the same transport
when `skill_bundle_download_url` is present; the probed skill exposed Markdown
but no auxiliary bundle URL, so that variant remains contract-tested.

---

## Connector discovery, linking, and external authority

`client.chatgpt.connectors` exposes the connector contracts shared by current
Codex and Desktop clients without conflating catalog reads with authority:

- `directory.list()` / `list_all()` cover the public and workspace directory
  routes and validate app lists and pagination tokens;
- `retrieve()`, `terms()`, `logo()`, and `batch_metadata()` return connector
  metadata, action safety annotations, legal text, branding, and optional tool
  schemas;
- `links.retrieve()` and `links.list_accessible()` inspect the account's current
  link state;
- `authentication` contains the no-auth, OAuth, reauthentication, and callback
  mutations; discovery methods never call these implicitly;
- `external_actions` contains the Desktop contacts and email routes. Sending or
  undoing email may modify an external service, so an independent harness must
  apply its own confirmation policy.

The same external-action namespace exposes
`upload_google_drive_file(path, title=...)`. It sends Desktop's exact multipart
shape (`arguments` JSON plus an Office document) to
`/wham/apps/google_drive/upload`, accepts `.docx`, `.pptx`, and `.xlsx`, and
surfaces connector-auth failures as `ConnectorAuthenticationRequiredError`.
The method converts/creates a file in the linked Google Drive account and is
therefore an explicit external mutation, not a generic file upload.

The ordinary Codex OAuth grant already includes `api.connectors.read` and
`api.connectors.invoke`; Desktop does not obtain a broader reusable bearer
grant. Read-only live probes returned 2,614 directory apps, valid batch/detail/
terms/link payloads, and nine accessible links for the test account. These
counts describe one account and date, not a stable service guarantee. Auth and
external-action mutations were contract-tested but deliberately not invoked.

---

## Writing blocks and magic edit

`client.chatgpt.writing_blocks.update(body)` persists the complete writing-block
envelope used by Desktop, including conversation/message/block identity and the
nested block content. The envelope remains raw because it is a private product
schema and includes variant-specific metadata.

`magic_edit(...)` exposes the reusable model-assisted editing primitive. It
accepts the full Markdown document, a validated character range, Desktop's
marked-range representation, an instruction, one or more requested variations,
and the observed `generate`, `edit`, or `full-edit` mode. The SDK validates the
response's replacement-choice list while preserving additive fields such as the
backend model slug. Both routes modify conversation state or consume inference,
so they are contract-tested but were not invoked during read-only probing.

---

## ChatGPT search and conversation-side streams

`client.chatgpt.search.global_search()` exposes
`GET /backend-api/global/search` independently from
`client.chatgpt.conversations.search()`. Global search accepts a source list
and preserves `source_statuses` and `partial_results`, which are important when
one indexed source times out. A live OAuth probe of the conversation source
returned the observed `cursor`, `items`, `partial_results`, and
`source_statuses` shape.

`client.chatgpt.conversations.sidebar_stream()` exposes the raw Desktop
`POST /backend-api/sidebar/conversation` SSE response. It accepts explicit
integrity headers because those are owned by the caller's Sentinel/session
lifecycle; the SDK does not fabricate them.

File metadata and download-link APIs remain under `client.chatgpt.files`.
`download()` and `download_attachment()` resolve backend-issued links into
bytes, `BytesIO`, a file, or a raw response. Authenticated ChatGPT backend links
use the OAuth session, while external signed links are fetched without OAuth
headers. `process_upload_events()` exposes the official
`/files/process_upload_stream` NDJSON pipeline and always closes its response.

### Projects, custom GPTs, and subagent data

`client.chatgpt.projects` covers the complete project subset observed in
Desktop: paginated sidebar discovery, detail, conversations, connector scopes,
saves, creation/update/deletion, and file attachment. `list_all()` validates
page shapes and rejects repeated cursors. The live account returned a valid
empty project page; mutations were not probed.

`client.chatgpt.gizmos.retrieve()` exposes generic custom-GPT metadata without
misclassifying every gizmo as a project. Conversation helpers expose the
read-only `/flora/subagent/thread/turns` mapping and the live-verified
`/celsius/ws/user` continuation WebSocket URL. Rating, DIL view-state, and
generated-widget refresh operations are explicitly named mutations.

`client.chatgpt.models.third_party()` returned four TPP models in a live probe.
System hints and custom-agent system hints follow the exact Desktop query
contract. The optional `/models/slugs` route currently returns 404 and is
normalized to `None`, matching the official client's compatibility behavior;
other HTTP failures remain visible.

---

## ChatGPT File Uploads

### `POST /backend-api/files`

Create file upload metadata for Codex Apps/MCP file parameters.

**SDK method**: `client.files.upload(path)`

The official flow is:

1. `POST /backend-api/files` with `file_name`, `file_size`, and
   `use_case: "codex"`.
2. `PUT` the file bytes to the returned signed `upload_url`.
3. `POST /backend-api/files/{file_id}/uploaded` until the backend returns
   `status: "success"`.

The SDK returns an `UploadedFile` object with `file_id`, canonical
`sediment://...` URI, download URL, file name, size, MIME type, and local path.

---

## ChatGPT Account Data

These endpoints are under `https://chatgpt.com/backend-api`, not
`/backend-api/codex`. They return account-level ChatGPT data and are exposed
under `client.codex` as raw dictionaries.

### `GET /backend-api/memories`

**SDK method**: `client.codex.memories.list()`

**Status**: Supported. Returns a payload shaped like:

```json
{
  "memories": [
    {
      "id": "mem_...",
      "content": "...",
      "updated_at": "...",
      "status": "..."
    }
  ],
  "memory_max_tokens": 12000,
  "memory_num_tokens": 123
}
```

Memory items may include additional fields such as `conversation_id`,
`created_timestamp`, `gizmo_id`, `last_updated`, and `labels`.

### `GET /backend-api/user_system_messages`

**SDK method**: `client.codex.user_system_messages.retrieve()`

**Status**: Supported. Returns the raw ChatGPT customization payload, including
fields such as `enabled`, `about_user_message`, `about_model_message`,
`traits_model_message`, `disabled_tools`, and personality-related settings.

---

## Input format (ResponseItem)

Messages passed to `input`:

**User message:**
```json
{ "type": "message", "role": "user", "content": [{ "type": "input_text", "text": "..." }] }
```

**Assistant message:**
```json
{ "type": "message", "role": "assistant", "content": [{ "type": "output_text", "text": "..." }] }
```

**Image input (URL):**
```json
{ "type": "input_image", "image_url": "https://..." }
```

**Image input (base64):**
```json
{ "type": "input_image", "image_url": "data:image/jpeg;base64,..." }
```

**Tool call (function_call):**
Returned verbatim from `response.output_item.done` with `item.type = "function_call"`. Append raw item to history.

**Tool result:**
```json
{ "type": "function_call_output", "call_id": "call_...", "output": "..." }
```

---

## Known limitations / quirks

- `stream: true` is **mandatory** — there is no sync endpoint.
- `store: false` is **mandatory**; `store: true` returns a 400.
- `prompt_cache_retention` is server-selected (`"24h"` observed in SSE events)
  and rejected if sent in the request body.
- Public Responses API fields such as `temperature`, `top_p`,
  `max_output_tokens`, `metadata`, `user`, `safety_identifier`, `truncation`,
  penalties, and `previous_response_id` are rejected as unsupported parameters.
- `tool_choice` field is **required** when `tools` is non-empty (omitting it causes a 400).
- `memories/trace_summarize` — 403 on Plus; Pro/Enterprise only.
- Reasoning tokens are billed separately from output tokens.
- The `reasoning.summary` field only populates for models with `supports_reasoning_summaries: true` (e.g. `gpt-5.2`); on other models the field is absent and only `encrypted_content` is present.
- `gpt-5.4` works for inference but is not listed as `supported_in_api: true` in `/models`.
