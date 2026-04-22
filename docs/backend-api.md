# Codex Backend API — Reverse-Engineering Notes

Sourced from live observation and `codex-rs` source (`openai/codex`).  
Last updated: 2026-04-22.

---

## Base URLs

| Path style | Base URL |
|---|---|
| Codex API (direct) | `https://chatgpt.com/backend-api/codex` |
| WHAM (account/quota) | `https://chatgpt.com/backend-api` |

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

---

## Codex API endpoints

### `GET /codex/models`

List models available to this account.

**Query params**
- `client_version` — SDK/CLI version string (e.g. `"0.1.0"`).

**Response** — JSON `{ "models": [ ModelObject, … ] }`

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

Main inference endpoint. **Stream-only** — `stream: true` is mandatory; the backend never returns a non-streaming response.

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
  "input": [ /* full conversation history */ ]
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
- `output` replaces the original history; pass it as `conversation_history` in subsequent calls.
- The `compaction_summary` item is opaque on the client side.

---

### `POST /codex/memories/trace_summarize`

Summarize traces into persistent memories.

**Status**: Returns `403 Forbidden` on Plus plan. Requires Pro or Enterprise.

---

### `POST /codex/realtime/calls`

Realtime audio/video call initiation.

**Status**: Returns `404 Not Found` — not deployed on the ChatGPT backend.

---

## WHAM endpoints

WHAM is the ChatGPT account/quota management layer, distinct from the Codex API.

### `GET /backend-api/wham/usage`

Rate limits and quota for this account. Used as the auth probe — a 200 response confirms valid tokens.

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

### `GET /backend-api/wham/config/requirements`

Fetch managed requirements/config for this account (plan-gated settings).

**Response** — JSON config blob; schema defined in `codex-rs/cloud-requirements`.

---

### `GET /backend-api/wham/tasks/list`

List cloud tasks (Pro/Enterprise cloud execution feature).

**Query params**: `limit`, `task_filter`, `environment_id`, `cursor`.

---

### `GET /backend-api/wham/tasks/{task_id}`

Get details for a specific cloud task.

---

### `GET /backend-api/wham/tasks/{task_id}/turns/{turn_id}/sibling_turns`

List sibling turns for a task turn.

---

### WebSocket: `wss://chatgpt.com/backend-api/wham/remote/control/server`

Remote control / agent-as-a-service websocket. Enrollment via:  
`POST /backend-api/wham/remote/control/server/enroll`

---

## Input format (ResponseItem)

Messages passed to `input` / `conversation_history`:

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
- `realtime/calls` — 404, not deployed on chatgpt.com backend.
- `memories/trace_summarize` — 403 on Plus; Pro/Enterprise only.
- Reasoning tokens are billed separately from output tokens.
- The `reasoning.summary` field only populates for models with `supports_reasoning_summaries: true` (e.g. `gpt-5.2`); on other models the field is absent and only `encrypted_content` is present.
- `gpt-5.4` works for inference but is not listed as `supported_in_api: true` in `/models`.
