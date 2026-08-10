# API reference

This document is the public Python API index for `codex-backend-sdk`. It
describes supported methods, parameters, return values, and important local
validation. For wire-level payload examples and observed backend fields, see
[`backend-api.md`](backend-api.md). For availability and live-probe status, see
[`endpoint-coverage.md`](endpoint-coverage.md).

Private ChatGPT and WHAM schemas are intentionally returned as
`dict[str, Any]` unless a typed boundary provides durable value. Parameters
named `body` accept a dictionary, Pydantic model, dataclass, or another value
that serializes to one JSON object.

## Contents

1. [Client and authentication](#client-and-authentication)
2. [Direct client resources](#direct-client-resources)
3. [`client.codex`](#clientcodex)
4. [`client.chatgpt`](#clientchatgpt)
5. [Typed models and errors](#typed-models-and-errors)
6. [Transport behavior](#transport-behavior)

## Client and authentication

### `OpenAI` / `CodexClient`

`OpenAI` is an alias of `CodexClient`.

```python
OpenAI(
    *,
    store: TokenStore | None = None,
    model: str = "gpt-5.4",
    instructions: str | None = None,
    timeout: float = 120,
    max_retries: int = 2,
    retry_base_delay: float = 0.25,
)
```

| Parameter | Meaning |
| --- | --- |
| `store` | Optional in-memory OAuth token store. No credential file is loaded automatically until `authenticate()` is called. |
| `model` | Default model used by Responses and compaction requests. |
| `instructions` | Default developer instructions for Responses and compaction. |
| `timeout` | Default HTTP timeout in seconds. |
| `max_retries` | Retries for transient `429`, `5xx`, timeout, and connection failures. |
| `retry_base_delay` | Initial exponential retry delay in seconds. |

#### Authentication methods

| Method | Parameters | Returns | Notes |
| --- | --- | --- | --- |
| `authenticate(...)` | `interactive=True`, `force=False` | the same client | Reuses and refreshes `~/.codex/auth.json`; opens browser OAuth when required. `force=True` requires interactive mode. |
| `authenticate_device_code(...)` | `on_code=None`, `persist=True`, `timeout=900`, `allowed_workspace_ids=None` | the same client | Starts official device login, reports a `DeviceCode`, polls, exchanges, optionally persists, then attaches credentials. |
| `account_info()` | none | `dict` | Safe metadata: `authenticated`, `account_id`, `email`, and `plan_type`; never returns tokens. |
| `logout()` | none | `bool` | Clears local stored credentials and client headers. Returns whether the credential file existed. No network request. |
| `revoke()` | none | `bool` | Revokes the refresh token, or access token fallback, then performs local logout. Raises if remote revocation fails. |
| `authenticated` | property | `bool` | Whether the client currently has an account-bearing token store. |
| `realtime_websocket_url(...)` | `model` | `str` | Builds the OpenAI Realtime WebSocket URL; requires a non-empty model. |

#### Low-level OAuth helpers

These are exported for harnesses that own their authentication UI:

| Function | Parameters | Returns |
| --- | --- | --- |
| `run_oauth_flow(...)` | `open_browser=True`, `persist=True`, `workspace_id=None`, `scopes=None` | `TokenStore`, persisted when requested |
| `request_device_code(...)` | `issuer=ISSUER`, `client_id=CLIENT_ID` | short-lived `DeviceCode` |
| `complete_device_code_login(...)` | `device_code`, `timeout=900`, `persist=True`, `allowed_workspace_ids=None` | `TokenStore` |
| `refresh_access_token(...)` | `refresh_token` | raw token response `dict` |
| `revoke_oauth_token(...)` | `token`, `token_type_hint="refresh_token"`, `issuer=ISSUER`, `client_id=CLIENT_ID` | `None` |
| `load_tokens()` | none | `TokenStore | None` from the compatible Codex auth file |
| `save_tokens(store)` | `TokenStore` | `None`; writes the compatible Codex credential shape with restricted Unix permissions |

`token_type_hint` accepts only `refresh_token` or `access_token`. Custom issuers
must use HTTPS, except loopback HTTP issuers used by tests and local harnesses.

## Direct client resources

### Responses

#### `client.responses.create(...)`

```python
client.responses.create(
    *,
    input=UNSET,
    model=UNSET,
    instructions=UNSET,
    include=UNSET,
    parallel_tool_calls=UNSET,
    prompt_cache_key=UNSET,
    reasoning=UNSET,
    service_tier=UNSET,
    store=UNSET,
    stream=UNSET,
    text=UNSET,
    tool_choice=UNSET,
    tools=UNSET,
    extra_headers=None,
    extra_query=None,
    timeout=UNSET,
    ...
) -> Response | Iterator[ResponseStreamEvent]
```

Supported backend fields are `input`, `model`, `instructions`, `include`,
`parallel_tool_calls`, `prompt_cache_key`, `reasoning`, `service_tier`,
`store=False`, `text`, `tool_choice`, and `tools`. `stream=True` returns an event
iterator; otherwise the SDK collects the mandatory backend SSE stream into a
typed `Response`.

The OpenAI-compatible signature also accepts the following names so it can
reject them clearly: `background`, `context_management`, `conversation`,
`max_output_tokens`, `max_tool_calls`, `metadata`, `previous_response_id`,
`prompt`, `prompt_cache_retention`, `safety_identifier`, `stream_options`,
`temperature`, `top_logprobs`, `top_p`, `truncation`, `user`, and `extra_body`.
Supplying one raises `CodexBackendUnsupportedParameterError`. `store` may only
be false.

`Response` exposes `output`, `output_text`, `reasoning_summary`, `tool_calls`,
`usage`, `status`, and preserved extra backend fields.

#### `client.responses.parse(...)`

Accepts the same supported request controls as `create()`, plus required
`text_format: type`, a Pydantic model class. It generates a strict JSON schema
and returns `ParsedResponse`, whose `output_parsed` contains the validated model
instance. Streaming is not exposed by `parse()`.

#### `client.responses.compact(...)`

| Parameter | Type | Notes |
| --- | --- | --- |
| `input` | Responses input | Required conversation/tool items to compact. |
| `model` | string or unset | Uses client default when omitted. |
| `instructions` | string or unset | Uses client default when omitted. |
| `reasoning` | object or unset | Codex reasoning controls. |
| `text` | object or unset | Text verbosity/format controls. |
| `tools`, `tool_choice` | JSON-compatible | Tool context retained during compaction. |
| `parallel_tool_calls`, `prompt_cache_key`, `service_tier` | optional | Forwarded when supplied. |
Returns `CompactedResponse`. Its `output` contains replayable response items and
opaque encrypted `compaction_summary` items; `usage` preserves backend token
accounting.

#### `client.responses.websocket`

`connect(timeout=30, websocket_factory=None)` returns a
`ResponsesWebSocketConnection`. The optional factory supports alternate or test
WebSocket implementations.

Connection methods:

| Method | Parameters | Returns |
| --- | --- | --- |
| `create(request)` | raw Responses request mapping | iterator of raw event dictionaries |
| `events(request)` | raw `response.create` event or request mapping | iterator through terminal completion/error |
| `close()` | none | `None` |

The connection is a context manager and is reusable for sequential, not
concurrent, turns. Backend error envelopes raise `ResponsesWebSocketError` with
`code`, `message`, `event`, and optional `param`.

### Models

| Method | Parameters | Returns |
| --- | --- | --- |
| `client.models.list(...)` | `force_refresh=False`, `extra_headers=None`, `extra_query=None`, `extra_body=None`, `timeout=UNSET` | iterable `SyncPage` with optional `etag`; cached for 5 minutes |
| `client.models.retrieve(...)` | `model`, plus the same transport controls | one typed `Model`; raises `LookupError` if absent |

`Model` preserves Codex fields including display metadata, context window,
reasoning levels, verbosity support, compaction limit, plan availability, input
modalities, WebSocket preference, base instructions, priority, and raw payload.

### Files

#### `client.files.create(...)`

The official `openai-python` signature is exposed, but Codex OAuth currently
lacks the `api.files.write` scope required by the Platform Files API. Calling
the method raises `CodexBackendUnsupportedParameterError` rather than silently
redirecting the request to a semantically different storage product.

#### `client.files.upload(...)`

| Parameter | Type | Notes |
| --- | --- | --- |
| `path` | string or `Path` | Required local regular file, limited to the SDK upload bound. |
| `timeout` | request timeout | Applies to metadata, signed upload, and finalization. |
| `finalize_timeout` | float | Maximum finalization polling time; defaults to 30 seconds. |
| `finalize_retry_delay` | float | Delay between backend readiness polls; defaults to 0.25 seconds. |

Returns typed `UploadedFile` with the backend file ID, filename, local path,
size, MIME type, download URL, and `sediment://` URI. OAuth is not forwarded to the
signed storage upload URL.

### Images

| Method | Required parameters | Optional parameters | Returns |
| --- | --- | --- | --- |
| `client.images.generate(...)` | `prompt` | official generation keywords, request options, and additive `extra_body` | typed `ImagesResponse` |
| `client.images.edit(...)` | `image`, `prompt` | official edit keywords, request options, and additive reference inputs | typed `ImagesResponse` |

`image` follows the official SDK's singular parameter name and accepts one file
or a sequence of files. Paths, binary streams, bytes, and official file tuples
are converted to base64 data URLs. URLs/data URLs and reference objects are
additive inputs. The Codex transport normalizes all values to `images[]`
internally. `mask` accepts the same file forms, plus an object containing
exactly one `image_url` or `file_id`.
`ImagesResponse.data[]` contains base64 image entries and preserves effective
backend options.

The official result names `Image` and `ImagesResponse` are exported;
`ImageData` and `ImageResponse` remain backward-compatible aliases.

`image_url(url)` builds an Responses-compatible `input_image` item from a URL.
`image_b64(data, media_type="image/jpeg")` builds the same item from base64
content and a MIME type.

### Audio transcription

#### `client.audio.transcriptions.create(...)`

Required: `file`, `model`. Supported optional backend parameters are `language`,
`prompt`, `response_format` (`json` or `text`), `temperature`, `extra_headers`,
`extra_query`, `extra_body`, and `timeout`. Returns typed `Transcription` for
JSON or `str` for text.

The OpenAI-compatible signature rejects unsupported `chunking_strategy`,
`include`, `known_speaker_names`, `known_speaker_references`, `stream`, and
`timestamp_granularities` when meaningfully supplied.

### Embeddings

#### `client.embeddings.create(...)`

Required: `input`, `model`. Optional: `dimensions`, `encoding_format`, `user`,
`extra_headers`, `extra_query`, `extra_body`, `timeout`. Returns typed
`CreateEmbeddingResponse` with `data`, `model`, and `usage`.

This resource uses `api.openai.com/v1` with the OAuth bearer and may consume
Platform quota rather than the ChatGPT subscription.

### Realtime

| Method | Parameters | Returns |
| --- | --- | --- |
| `client.realtime.websocket_headers(...)` | `session_id=None` | Realtime authorization/originator headers |
| `client.realtime.calls.create(...)` | `sdp`, optional `session`, `extra_headers`, `extra_query`, `extra_body`, `timeout` | typed `RealtimeCallResponse` |
| `client.realtime.calls.create_v3(...)` | `sdp`, `session`, plus the same transport extensions | typed `RealtimeCallResponse` |

`create_v3()` requires the effective model to be `gpt-live-1-codex` or
`gpt-live-1-boulder-alpha`, removes any caller-supplied session ID, and applies
the current Codex v3 intent/architecture. The result exposes `answer_sdp`,
`call_id`, raw `session`, and original response text.

## `client.codex`

Unless otherwise stated, methods in this section return raw backend
`dict[str, Any]` values.

### Account, quota, profile, and configuration

| Resource/method | Parameters | Returns / behavior |
| --- | --- | --- |
| `client.codex.accounts.check()` | none | account entitlement dictionary |
| `client.codex.usage()` | none | plan, rate-limit, and credit dictionary |
| `.usage_details.daily_token_breakdown()` | none | daily usage dictionary |
| `.usage_details.credit_events()` | none | credit event dictionary |
| `.usage_details.threads(thread_ids)` | non-empty list of IDs | usage attributed to selected threads |
| `.rate_limit_reset_credits.list()` | none | typed `RateLimitResetCredits` |
| `.rate_limit_reset_credits.consume(...)` | `redeem_request_id`, `credit_id=None` | typed `ConsumeRateLimitResetCreditResponse`; explicit quota mutation |
| `.profile.retrieve()` | none | profile dictionary |
| `.profile.update(body)` | JSON object | updated profile dictionary |
| `.profile.upload_photo(...)` | local `path`, optional `content_type` | uploaded asset-pointer string |
| `.profile.set_photo(...)` | same path controls | uploads then applies the photo; updated profile dictionary |
| `.config.requirements()` | none | managed requirement dictionary |
| `.config.bundle()` | none | selected cloud configuration bundle |
| `.config.user_settings()` | none | current Codex user settings |
| `.config.user_preferences_config()` | none | managed preference schema/limits |
| `.config.update_user_settings(body)` | JSON object | updated settings; explicit mutation |
| `.workspace_messages.list()` | none | workspace messages |

### Memories

| Method | Parameters | Returns |
| --- | --- | --- |
| `client.codex.memories.list()` | none | raw account-memory dictionary |
| `.memories.trace_summarize(...)` | `model`, `traces`, optional `reasoning` | typed `MemorySummarizeResponse` |
| `.user_system_messages.retrieve()` | none | raw customization/system-message dictionary |

Each trace may be a `RawMemory` or compatible dictionary containing `id`,
`metadata`, and `items`. The summary response contains typed output entries and
usage.

### Structured web search

#### `client.codex.web_search.search(...)`

| Parameter | Meaning |
| --- | --- |
| `id` | Required non-empty caller/session identifier. |
| `model` | Required non-empty backend search model. |
| `commands` | Optional JSON object grouping command lists and `response_length`. |
| `input` | Optional input string or item list. |
| `reasoning` | Optional JSON-compatible reasoning controls. |
| `settings` | Optional JSON object such as context size/external access controls. |
| `max_output_tokens` | Positive integer when supplied. |
| `originator` | Optional per-request originator header. |
| `turn_metadata` | Optional turn metadata header. |

Returns a raw dictionary containing required string `output`, optional
`results`, and optional string `encrypted_output` continuation state. Supported command families observed in Codex are
`search_query`, `image_query`, `open`, `click`, `find`, `screenshot`, `finance`,
`weather`, `sports`, and `time`. Commands must be JSON-serializable objects.

### Cloud tasks and turns

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `tasks.list(...)` | `limit=None`, `cursor=None`, `task_filter=None`, `environment_id=None` | task page |
| `tasks.retrieve(task_id)` | non-empty ID | task detail |
| `tasks.create(body)` | JSON object | created task; explicit mutation |
| `tasks.archive(task_id)` | ID | action response |
| `tasks.cancel(task_id)` | ID | action response |
| `tasks.recover(task_id)` | ID | action response |
| `tasks.mark_read(task_id)` | ID | action response |
| `tasks.turns.list(task_id)` | IDs | task turn list |
| `tasks.turns.sibling_turns(task_id, turn_id)` | IDs | sibling turns |
| `tasks.turns.retrieve(task_id, turn_id)` | IDs | turn detail |
| `tasks.turns.logs(task_id, turn_id)` | IDs | turn logs |
| `tasks.turns.pull_request(task_id, turn_id, body)` | IDs and JSON object | PR state mutation response |

### Environments and repositories

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `environments.list()` | none | environment collection |
| `environments.search(...)` | `query=""`, `cursor=None`, `limit=20` | search page |
| `environments.retrieve(environment_id)` | ID | expanded creator/machine detail |
| `environments.by_repo(provider, owner, repo)` | non-empty path parts | matching environments |
| `environments.machines()` | none | available machine catalog |
| `environments.create(body)` | JSON object | created environment |
| `environments.update(environment_id, body)` | ID and object | updated environment |
| `environments.delete(environment_id)` | ID | `None` |
| `environments.reset_cache(environment_id)` | ID | reset response |
| `repositories.search(...)` | `query`, required keyword `connector_id`, optional `limit=20` | repositories across installations |
| `repositories.branches(...)` | `repo_id`, `query`, optional `page_size=20`, `cursor=None` | branch search page |

### Worktree snapshots

| Method | Parameters | Returns |
| --- | --- | --- |
| `worktree_snapshots.create_upload(...)` | `repo_name`, `filename`, `content_type`, `anticipated_file_size` | validated signed-upload allocation |
| `.finish_upload(...)` | `file_id`, `etag` | finalized snapshot dictionary |
| `.upload_archive(...)` | local `path`, required `repo_name`, optional `content_type`, `timeout` | finalized snapshot dictionary |

`path` must identify a regular local archive. The upload helper sends no
OAuth token to the signed storage URL and requires the returned ETag before
finalization.

### Remote Control

#### Server role

| Method | Parameters | Returns |
| --- | --- | --- |
| `remote_control.enroll(...)` | `name`, `installation_id`, `os`, `arch`, `app_server_version` | `RemoteControlEnrollment` |
| `.refresh(enrollment, ...)` | `installation_id` | refreshed enrollment, identity-checked |
| `.connect(enrollment, ...)` | `installation_id`, `server_name`, optional `protocol_version="3"`, `subscribe_cursor`, `refresh_before_connect`, `timeout`, `websocket_factory` | `RemoteControlConnection` |
| `.reconnect(connection, ...)` | optional `timeout`, `websocket_factory` | replacement connection resumed from latest cursor |
| `.pairing.start(...)` | enrollment, `manual_code=False` | `RemoteControlPairing` |
| `.pairing.status(...)` | enrollment and exactly one pairing code | `RemoteControlPairingStatus` |
| `.clients.list(...)` | `environment_id`, optional `cursor`, `limit`, `order` | typed client page |
| `.clients.revoke(...)` | `environment_id`, `client_id` | `None`; explicit mutation |

`RemoteControlConnection` is iterable and a context manager. `send(envelope)`
requires a JSON object; `receive()` returns one raw envelope and tracks any
cursor; `connected` reports socket state; `close()` closes the socket.

#### Account-authorized Desktop/browser role

| Method | Parameters | Returns |
| --- | --- | --- |
| `.desktop.mfa_requirement()` | none | requirement string |
| `.desktop.mfa_info()` | none | MFA dictionary |
| `.desktop.clients.list(...)` | optional `cursor`, `limit=100` | typed page |
| `.desktop.clients.list_all(...)` | `include_pending=True` | all typed clients |
| `.desktop.clients.pair(...)` | `client_id`, `manual_pairing_code` | pairing response |
| `.desktop.clients.revoke(client_id)` | ID | `None` |
| `.desktop.environments.list(...)` | optional `client_id`, `cursor`, `limit` | typed page |
| `.desktop.environments.list_all(...)` | optional `client_id` | all typed environments |
| `.desktop.environments.rename(...)` | `environment_id`, `name` | typed environment |
| `.desktop.environments.delete(environment_id)` | ID | `None` |

## `client.chatgpt`

These resources mirror official Desktop product calls. Unless noted otherwise,
they return raw dictionaries and require non-empty identifiers.

### Account, models, voice, and Sentinel

#### Account

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `account.me()` | none | current user dictionary |
| `account.settings()` | none | ChatGPT settings dictionary |
| `account.system_hints()` | none | system-hints dictionary |
| `account.memories()` | none | memory dictionary |
| `account.user_system_messages()` | none | customization dictionary |
| `account.set_user_setting(feature, value)` | feature and JSON value | `None`; explicit mutation |
| `account.set_voice(voice_name)` | non-empty voice | `None` |
| `account.set_ultra_effort_enabled(enabled)` | bool | `None` |
| `account.opt_out_of_trusted_contact_prompts()` | none | `None` |

#### Models

| Method | Parameters | Returns |
| --- | --- | --- |
| `models.list()` | none | ChatGPT model catalog |
| `models.slugs()` | none | slug dictionary or `None` when optional route is unavailable |
| `models.config(slug)` | slug | model configuration |
| `models.third_party()` | none | TPP model catalog |
| `models.system_hints(...)` | optional `mode`, `exclude_logo` | account/model hints |
| `models.custom_agent_system_hint(...)` | `agent_id`, optional `system_hint` | custom-agent hint |

#### Voice

| Method | Parameters | Returns |
| --- | --- | --- |
| `voice.voices(...)` | optional `spoken_language`, `voice_mode` | voice catalog |
| `voice.dictation_connect_info(body)` | JSON object | streaming dictation connection metadata |
| `voice.synthesize_pronunciation(...)` | see below | speech in selected representation |

`synthesize_pronunciation` requires `text` and `pronunciation_language`;
optional parameters are `speed=1`, `response_format="speech"`, and
`output_path`. Formats are `speech` (`ChatGPTSpeech`), `bytes_io`, `data_uri`,
or `file`. `file` requires
`output_path`.

#### Sentinel

`sentinel.prepare(body)` and `sentinel.heartbeat(body)` accept JSON objects and
return raw session dictionaries.

### Conversations, pins, projects, and shares

#### Conversations

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `conversations.list(...)` | optional `offset`, `limit`, `order` | history page |
| `.search(query, **filters)` | non-empty query plus backend filters | search page |
| `.batch(body)` | JSON object | batch result |
| `.websocket_url()` | none | user continuation WebSocket URL string |
| `.subagent_thread_turns(...)` | `conversation_id`, `thread_id`, optional `limit=1` | delegated turns |
| `.retrieve(conversation_id)` | ID | conversation |
| `.update(conversation_id, body)` | ID/object | updated conversation |
| `.delete(conversation_id)` | ID | `None` |
| `.rename(conversation_id, title)` | ID/title | rename result |
| `.branch(body)` | JSON object | branched conversation |
| `.prepare(body)` | JSON object | generation requirements |
| `.create_stream(body)` | JSON object | raw streaming HTTP response |
| `.resume_stream(body)` | JSON object | raw streaming HTTP response |
| `.sidebar_stream(body, ...)` | required JSON body, optional `headers` | raw SSE response |
| `.files(conversation_id)` | ID | attached files |
| `.rate(conversation_id, body)` | ID/object | rating response |
| `.persist_dil_view_state(...)` | conversation/message IDs and `body` | mutation response |
| `.refresh_widget(...)` | conversation/message IDs and non-negative `ref_index` | refreshed widget response |

#### Pins

`pins.list(item_type=None, limit=None)` returns a pin page.
`pins.set(item_type, item_id, pinned=...)` explicitly pins or unpins and returns
the backend result when one is present.

#### Projects and generic GPTs

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `gizmos.retrieve(gizmo_id_or_short_url)` | ID or short URL | generic GPT metadata |
| `projects.list(...)` | `conversations_per_project=0`, `cursor=None`, `limit=20`, `owned_only=True` | project page |
| `projects.list_all(...)` | `conversations_per_project=0`, `owned_only=True` | aggregated list |
| `projects.retrieve(project_id_or_short_url)` | ID/short URL | project detail |
| `projects.create(body)` | object | created project |
| `projects.update(project_id, body)` | ID/object | updated project |
| `projects.delete(project_id)` | ID | `None` |
| `projects.conversations(...)` | `project_id`, `cursor=None`, `limit=5`, `owned_only=True` | project conversation page |
| `projects.connector_scopes(...)` | `project_id`, `cursor=None`, `limit=100` | scopes |
| `projects.saves(...)` | `project_id`, `cursor=None`, `limit=100` | saved items |
| `projects.attach_files(project_id, body)` | ID/object | attachment result |
| `projects.delete_file(project_id, file_id)` | IDs | `None` |

#### Shared conversations

`shares.create(body, use_v2=True)` creates a shared-conversation link.
`shares.update(shared_conversation_id, body)` mutates an existing share. Both
return raw dictionaries.

### Search and files

#### Global search

`search.global_search(query, *, cursor=None, limit=20,
sources=("conversation",))` returns cross-product matches and source status.
`sources` must contain at least one non-empty source name.

#### ChatGPT files

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `files.create(body)` | object | created file metadata |
| `.finalize(file_id, body=None)` | ID/optional object | finalized metadata |
| `.download_link(file_id)` | ID | backend download metadata |
| `.download(file_id, ...)` | ID, `response_format="bytes"`, optional `output_path` | selected representation |
| `.conversation_files(conversation_id)` | ID | conversation file list |
| `.attachment_info(conversation_id, file_id)` | IDs | attachment metadata |
| `.attachment_download_link(conversation_id, file_id)` | IDs | link metadata |
| `.download_attachment(...)` | IDs and output controls | selected representation |
| `.process_upload_events(body)` | object | iterator of NDJSON event dictionaries |
| `.list_library_files(body=None)` | optional object | file-library result |
| `.list_library_nodes(**filters)` | backend filters | node result |
| `.create_library_directory(body)` | object | created directory |
| `.library_directory_path(directory_id)` | ID | directory path |
| `.update_library_file(library_file_id, body)` | ID/object | updated file |
| `.delete_library_file(...)` | `library_file_id`, optional `file_id`, `file_name`, `soft_delete` | `None` |
| `.library_file_thumbnail(library_file_id)` | ID | thumbnail metadata |

Download `response_format` values are `bytes`, `bytes_io`, `file`, or
`response`. `file` requires `output_path`. Backend URLs retain OAuth; signed
external URLs do not.

### Apps and hosted MCP

#### Desktop JSON-RPC transport

| Method | Parameters | Returns |
| --- | --- | --- |
| `apps.request(...)` | `method`, optional `params`, `request_id=1` | validated full JSON-RPC response dictionary |
| `apps.list_tools(...)` | `request_id=1` | tool list |
| `apps.call_tool(...)` | `name`, optional `arguments`, `resource_uri`, `request_id` | tool result |
| `apps.bootstrap_launcher(body)` | object | launcher state |
| `apps.auto_install_launcher(body)` | object | installation mutation result |
| `apps.call_ecosystem_mcp(body)` | object | MCP result |
| `apps.get_widget(**query)` | query parameters | widget metadata |
| `apps.launch_widget(body)` | object | launch mutation result |
| `apps.is_url_safe(url)` | HTTPS/HTTP URL | `bool` |

Malformed JSON-RPC envelopes raise `ChatGPTAppsProtocolError`.

#### Hosted MCP Streamable HTTP

`apps.connect_hosted_mcp(product_sku="codex", originator=None, initialize=True)`
returns an initialized `HostedMCPConnection`.

| Connection method | Parameters | Returns |
| --- | --- | --- |
| `request(method, params=None, request_id=None)` | raw MCP call | result dictionary |
| `notify(method, params=None)` | notification | `None` |
| `initialize(...)` | optional `protocol_version`, `client_name`, `client_version`, `capabilities` | initialization result |
| `list_tools(cursor=None)` | cursor | MCP tool page |
| `call_tool(name, arguments=None, meta=None)` | tool call | MCP result |
| `list_resources(cursor=None)` | cursor | resource page |
| `list_resource_templates(cursor=None)` | cursor | template page |
| `read_resource(uri)` | URI | resource result |
| `close()` | none | closes sessionful transport |

The connection is a context manager, tracks `session_id`, accepts JSON and SSE,
and uses MCP protocol version `2025-06-18`.

### Plugins, skills, bundles, and sharing

#### Catalog and installation

| Method | Parameters | Returns |
| --- | --- | --- |
| `plugins.featured(platform="codex")` | `codex` or `chat` | plugin ID list |
| `.curated_export()` | none | curated archive metadata |
| `.list(...)` | `scope="GLOBAL"`, `limit=200`, `page_token=None`, `collection=None` | validated page |
| `.list_all(...)` | optional `scope`, `collection` | aggregated list |
| `.search(...)` | `query`, optional `scope`, `limit=16`, `page_token` | page |
| `.installed(...)` | optional `scope`, `limit=200`, `page_token`, `include_download_urls` | page |
| `.installed_all(...)` | optional `scope`, `include_download_urls` | aggregated list |
| `.workspace_shared(...)` | `limit=200`, `page_token=None` | page |
| `.suggested(...)` | `scope="GLOBAL"` | suggested plugin dictionary |
| `.retrieve(plugin_id, ...)` | ID, optional `include_download_urls` | detail |
| `.skill(plugin_id, skill_name)` | IDs | skill detail/Markdown |
| `.installation.install(...)` | plugin ID, optional `include_apps_needing_auth=True` | mutation result |
| `.installation.uninstall(plugin_id)` | ID | mutation result |

#### Bundle materialization

| Method | Parameters | Returns |
| --- | --- | --- |
| `plugins.bundles.download_plugin(...)` | plugin ID, optional `response_format`, `output_path`, `max_bytes` | selected representation |
| `.download_skill(...)` | plugin ID/name and same controls | selected representation |
| `.download_curated(...)` | same output/limit controls | selected representation |
| `.extract_plugin(...)` | plugin ID, destination, archive limits | destination `Path` |
| `.extract_curated(...)` | destination, archive limits | destination `Path` |

Download formats are `bytes`, `bytes_io`, or `file`. Extraction
rejects absolute/traversal paths, links and special entries, duplicates,
oversized archives/files, malformed manifests, and non-atomic activation.

#### Workspace plugin sharing

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `plugins.shares.created(...)` | optional pagination | created-plugin page |
| `.created_all()` | none | all created plugins |
| `.create_upload(...)` | `filename`, `size_bytes`, optional `plugin_id` | signed allocation |
| `.finish_upload(...)` | `file_id`, `etag`, optional `plugin_id`, `discoverability`, `share_targets` | published plugin |
| `.publish_archive(...)` | archive and metadata/access controls | published plugin |
| `.publish_directory(...)` | directory and metadata/access controls | published plugin |
| `.update_targets(...)` | plugin ID, required `discoverability`, optional `targets` | updated access state |
| `.delete(plugin_id)` | ID | `None` |

Publication is an explicit workspace mutation. Access controls support the
backend's visibility and target representation; directory publication validates
and packages the plugin before upload.

### Connectors and external actions

#### Discovery

| Method | Parameters | Returns |
| --- | --- | --- |
| `connectors.directory.list(...)` | optional `token`, `workspace=False`, `external_logos=True` | validated page |
| `.directory.list_all(...)` | optional `workspace=False`, `external_logos=True` | aggregated list |
| `.retrieve(...)` | `connector_id`, optional `include_actions`, `include_logo` | connector detail |
| `.product_specific(purpose)` | purpose such as `hermes` | product selection |
| `.terms(connector_id)` | ID | terms metadata |
| `.batch_metadata(...)` | `app_ids`, optional `include_tools`, `product_sku="codex"` | batch result |
| `.logo(...)` | connector ID, `theme="light"` or `"dark"` | logo dictionary |
| `.links.retrieve(connector_id)` | ID | current link state |
| `.links.list_accessible(...)` | optional `principals=()`, `link_refresh_strategy="BLOCKING"` | accessible links |

#### Authentication

| Method | Parameters | Returns / behavior |
| --- | --- | --- |
| `connectors.authentication.connect_without_auth(...)` | `connector_id`, `name`, optional `action_names` | link result |
| `.start_oauth(...)` | `connector_id`, `name`, required `callback_url`, `post_auth_url`, optional `action_names` | OAuth start metadata |
| `.start_reauthentication(...)` | `link_id`, required `callback_url`, `post_auth_url`, optional `requested_scopes` | OAuth start metadata |
| `.complete_oauth(full_redirect_url)` | returned redirect URL | completed link result |

Authentication failures that require user linking may raise
`ConnectorAuthenticationRequiredError`. The SDK never opens or completes
connector OAuth implicitly.

#### External actions

| Method | Parameters | Returns |
| --- | --- | --- |
| `connectors.external_actions.search_contacts(body)` | object | contact search result |
| `.send_email(body)` | object | send result |
| `.unsend_email(body)` | object | unsend result |
| `.email_status(body)` | object | status result |
| `.upload_google_drive_file(...)` | local `path`, optional `title` | converted Google file metadata |

Google Drive upload supports `.docx`, `.pptx`, and `.xlsx` conversion through an
already linked connector. All external actions require caller-owned approval.

### Writing blocks

| Method | Parameters | Returns |
| --- | --- | --- |
| `writing_blocks.update(body)` | raw writing-block object | persisted block |
| `.magic_edit(...)` | `conversation_id`, full/marked Markdown, start/end indices, instruction, optional `num_variations=1`, `mode="edit"`, `timeout` | replacement choices |

Magic-edit indices must form a valid ordered range and the marked Markdown must
contain the expected backend markers around that range.

## Typed models and errors

Important exported models include:

- `Response`, `ParsedResponse`, `CompactedResponse`, `ResponseStreamEvent`, and
  `ResponseUsage`;
- `Model` and `ModelList`;
- `UploadedFile`, `ImagesResponse`, `Transcription`, and
  `CreateEmbeddingResponse`;
- `RealtimeCallResponse` and `ChatGPTSpeech`;
- `RateLimitResetCredits`, `ConsumeRateLimitResetCreditResponse`, `RawMemory`,
  and `MemorySummarizeResponse`;
- Remote Control enrollment, pairing, client, environment, page, and connection
  types;
- `DeviceCode` and `TokenStore`.

All Pydantic models preserve unknown additive backend fields where appropriate.

Public errors with special meaning:

| Error | Meaning |
| --- | --- |
| `CodexBackendUnsupportedParameterError` | OpenAI-shaped option is not supported by this backend contract. |
| `ResponsesWebSocketError` | Structured Responses WebSocket error envelope. |
| `ChatGPTAppsProtocolError` | Malformed or failed hosted Apps JSON-RPC response. |
| `ConnectorAuthenticationRequiredError` | Connector action requires an explicit user linking flow. |

HTTP failures otherwise use `requests` exceptions after retries are exhausted.
Validation failures use `ValueError`, `TypeError`, `RuntimeError`, or Pydantic
validation errors according to the boundary.

## Transport behavior

- The client sends `Authorization`, `ChatGPT-Account-ID`, and Codex originator
  headers to authenticated ChatGPT/Codex routes.
- Signed external upload/download URLs never receive the OAuth bearer.
- Raw streaming methods return `requests.Response`; callers own iteration and
  closure unless a higher-level iterator/context manager is documented.
- Unknown additive response fields are preserved; unknown notification/event
  types are returned rather than discarded.
- Discovery methods do not silently perform installation, linking, publication,
  email, quota, profile, project, conversation, environment, or Remote Control
  mutations.
- Commercial/admin, attestation, reporting, telemetry, analytics, beacon, and
  personal-access-token surfaces are outside the public SDK API.
