# Official Codex Desktop endpoint inventory

This inventory complements `backend-api.md` with OAuth-authenticated ChatGPT
routes referenced by the official Codex Desktop application but not necessarily
by `codex-rs`. It is an implementation survey, not a stability guarantee or an
assertion that every route is enabled for every account.

## Audited snapshot and method

- Linux-port checkout: `openai/codex-desktop-linux` at
  `05bbbc6cb4b7729e01b15348c0082a086816da84`.
- Bundled official application: `openai-codex-electron` `26.721.31836`.
- `Codex.dmg` SHA-256:
  `ff6e8ac9985aec44caa305787552e4ea517a7c745aef283bd4cbcab992de64b7`.
- `app.asar` SHA-256:
  `674dab67fe39f9912493f640c1dd80f222f6062ad0f50b182a6cc87eebd0d3dc`.

The ASAR was extracted and all Electron and webview JavaScript chunks were
searched, including lazy feature chunks. Routes below are backed by a concrete
HTTP-client invocation in the bundle. This avoids counting ordinary UI routes
such as `/settings/voice` as backend endpoints. "Desktop-only" below means that
the route string was not found in the contemporaneous `codex-rs` checkout; it
does not imply that no other OpenAI client uses it.

## OAuth comparison

The official Desktop app does not request a broader general-purpose OAuth grant
than Codex. Its normal login is delegated to App Server and uses the same
`app_EMoamEEZ73f0CkXaXp7hrann` client ID and scopes as `codex-rs`:

`openid profile email offline_access api.connectors.read api.connectors.invoke`

Desktop's `/codex/desktop-auth` page decorates that flow with application and
workspace metadata. For embedded authenticated ChatGPT pages, Electron passes
the same Codex access token to `/api/auth/link-session`; this creates a browser
session but does not produce a second, more broadly scoped bearer token.

Remote Control has a separate step-up flow requesting only the specialized
`codex.remote_control.enroll` scope. It is narrower and purpose-bound, not a
replacement for the normal SDK token.

The SDK therefore uses the ordinary Codex OAuth flow as the most permissive
reusable bearer path currently present in the official clients. Refresh requests
intentionally omit a `scope` parameter, matching `codex-rs`, so the authorization
server preserves the original connector scopes rather than narrowing them.

A read-only live probe with an existing Codex OAuth access token returned HTTP
200 for representative Desktop-only reads: ChatGPT models, voices, system
hints, conversations, projects and pins, plus WHAM daily token and credit usage.
This confirms that the normal Codex bearer grant, rather than a hidden Desktop
grant, is the reusable authorization path for these surfaces.

## High-value Codex/WHAM routes absent from `codex-rs`

These are the closest fit for future SDK resources because they extend existing
Codex account, cloud-task, environment, and Remote Control concepts.

| Method | Path | Observed role |
| --- | --- | --- |
| GET | `/backend-api/wham/usage/daily-token-usage-breakdown` | Daily token usage detail. |
| GET | `/backend-api/wham/usage/credit-usage-events` | Credit consumption history. |
| POST | `/backend-api/wham/usage/thread_usage/query` | Usage attributed to selected threads. |
| GET | `/backend-api/wham/github/repositories/search/all-installations` | Repository search across GitHub installations. |
| GET | `/backend-api/wham/github/branches/{repo_id}/search` | Branch search for a cloud repository. |
| GET | `/backend-api/wham/environments/search` | Cloud-environment search. |
| GET | `/backend-api/wham/environments/by-repo/{provider}/{repo_owner}/{repo_name}` | Resolve environments for a repository. |
| GET | `/backend-api/wham/environments/{environment_id}/with-creator-and-machine` | Expanded environment detail. |
| POST | `/backend-api/wham/environments` | Create an environment. |
| PATCH | `/backend-api/wham/environments/{environment_id}` | Update an environment. |
| DELETE | `/backend-api/wham/environments/{environment_id}` | Delete an environment. |
| POST | `/backend-api/wham/environments/{environment_id}/reset-cache` | Reset an environment cache. |
| GET | `/backend-api/wham/machines` | List available cloud machines. |
| POST | `/backend-api/wham/worktree_snapshots/upload_url` | Begin a worktree snapshot upload. |
| POST | `/backend-api/wham/worktree_snapshots/finish_upload` | Finalize a worktree snapshot upload. |
| GET | `/backend-api/wham/tasks/{task_id}/turns/{turn_id}` | Retrieve a specific cloud-task turn. |
| GET | `/backend-api/wham/tasks/{task_id}/turns/{turn_id}/logs` | Retrieve task-turn logs. |
| POST | `/backend-api/wham/tasks/{task_id}/turns/{turn_id}/pr` | Create or update task pull-request state. |
| POST | `/backend-api/wham/tasks/{task_id}/archive` | Archive a cloud task. |
| POST | `/backend-api/wham/tasks/{task_id}/cancel` | Cancel a cloud task. |
| POST | `/backend-api/wham/tasks/{task_id}/recover` | Recover a cloud task. |
| POST | `/backend-api/wham/tasks/{task_id}/mark_read` | Mark a cloud task read. |
| GET | `/backend-api/wham/onboarding/context` | Desktop onboarding state. |
| POST | `/backend-api/wham/onboarding/desktop/complete` | Complete Desktop onboarding. |
| GET/PATCH | `/backend-api/wham/profiles/me` | Read or update the Codex profile. |
| POST | `/backend-api/wham/profiles/me/photo` | Multipart profile-photo upload. |
| GET/PATCH | `/backend-api/wham/settings/user` | Read or update Codex user settings. |
| GET | `/backend-api/wham/settings/configs/user-preferences` | Managed user-preference configuration. |
| GET | `/backend-api/wham/remote/control/mfa_requirement` | Determine Remote Control step-up requirements. |
| GET | `/backend-api/wham/remote/control/clients` | List paired clients in the Desktop flow. |
| POST | `/backend-api/wham/remote/control/client/pair` | Pair a Remote Control client. |

The bundle also calls `POST /backend-api/wham/apps` as a JSON-RPC
`tools/list`/`tools/call` transport, including site-access tools. It is exposed
under `client.chatgpt.apps` with a raw request method and narrow validated
convenience methods. A live OAuth probe returned 170 advertised tools.

## General ChatGPT conversation surface

The official Desktop renderer contains a substantial ChatGPT client that is
not present in `codex-rs`. Its main conversation transport is streaming:

| Method | Path | Observed role |
| --- | --- | --- |
| POST (stream) | `/backend-api/f/conversation` | Start or continue a ChatGPT generation. |
| POST (stream) | `/backend-api/f/conversation/resume` | Resume a generation stream. |
| POST | `/backend-api/f/conversation/prepare` | Prepare conversation requirements. |
| GET | `/backend-api/conversations` | Paginated conversation history. |
| GET | `/backend-api/conversations/search` | Search conversation history. |
| POST | `/backend-api/conversations/batch` | Fetch conversations in a batch. |
| GET/PATCH | `/backend-api/conversation/{conversation_id}` | Retrieve or update a conversation. |
| DELETE | `/backend-api/conversation/id/{conversation_id}` | Delete a conversation. |
| POST | `/backend-api/conversation/id/{conversation_id}/rename` | Rename a conversation. |
| POST | `/backend-api/conversation/new_branch` | Branch a conversation. |
| POST | `/backend-api/conversation/{conversation_id}/rating` | Submit conversation feedback. |
| POST (stream) | `/backend-api/sidebar/conversation` | Stream sidebar conversation metadata. |
| GET | `/backend-api/conversations/{conversation_id}/files` | List conversation files. |
| GET | `/backend-api/conversation/{id}/attachment/{file_id}` | Retrieve attachment metadata. |
| GET | `/backend-api/conversation/{id}/attachment/{file_id}/download` | Download an attachment. |

The same client includes pins, projects, shared links, GPTs (`/gizmos/...`),
global search, file-library operations, and writing-block/widget endpoints.
Pins, projects, shared links, and file-library operations are now exposed under
`client.chatgpt`; GPTs, global search, and writing blocks remain inventory-only.

## General ChatGPT model, voice, and session routes

| Method | Path | Observed role |
| --- | --- | --- |
| GET | `/backend-api/models` | Available ChatGPT models. |
| GET | `/backend-api/models/slugs` | Model slug metadata. |
| GET | `/backend-api/models/config` | Model configuration. |
| GET | `/backend-api/settings/voices` | Available ChatGPT voices. |
| POST | `/backend-api/transcribe` | Multipart audio transcription; already exposed by this SDK. |
| POST | `/backend-api/codex/dictation-stream-connect-info` | Connection information for streaming dictation. |
| POST | `/backend-api/pronunciation/synthesize?format=mp3` | Read-aloud synthesis returning base64 MP3 audio. |
| GET | `/backend-api/system_hints` | Account/session system hints. |
| GET | `/backend-api/settings/user` | ChatGPT user settings. |
| GET | `/backend-api/me` | Current ChatGPT user. |
| POST | `/backend-api/sentinel/chat-requirements/prepare` | Prepare Sentinel session requirements. |
| POST | `/backend-api/sentinel/heartbeat` | Maintain Sentinel session state. |

These routes use ChatGPT product schemas rather than the public OpenAI API
schemas. In particular, the Desktop bundle's ChatGPT conversation and voice
paths should not be presented as alternate implementations of Codex Responses
or Realtime without protocol-level tests.

The focused conversation, account/session, model, voice, Sentinel, project,
file-library, pin, and share routes are exposed under `client.chatgpt`. The SDK
returns raw payloads and raw streaming responses so it does not falsely
stabilize these private schemas. Existing `client.codex.memories` and
`client.codex.user_system_messages` access remains as a compatibility alias;
their clearer ownership is now also available through `client.chatgpt.account`.

## Apps, connectors, and files

Verified route families include:

- `/backend-api/aip/connectors/...` for connector metadata, OAuth linking,
  accessible-link resolution, contacts, and email actions;
- `/backend-api/ecosystem/...` for widget bootstrap/launch, MCP calls, URL
  safety, and auto-installation;
- `/backend-api/files`, `/files/{file_id}/uploaded`, downloads, and the
  streaming `/files/process_upload_stream` pipeline;
- `/backend-api/files/library/...` for ChatGPT's file library;
- `/backend-api/projects/...` for project metadata, files, saves, and connector
  scopes;
- `/backend-api/wham/apps/google_drive/upload` for native Google Workspace file
  conversion/upload.

The connector email actions and OAuth link mutations can affect external state.
They must not be wrapped as generic convenience methods without explicit safety
semantics and confirmation ownership.

## Deliberately excluded from SDK exposure

The bundle also references endpoints for subscriptions and payments, referrals,
workspace administration, report flows, attestation, feature bootstrap,
telemetry, beacons, and analytics. Examples include
`/subscriptions/update`, `/accounts/{account_id}/workspace_admin_requests`,
`/report_flow/report`, `/ios/attestation_challenge`, `/wham/statsig/bootstrap`,
and `/wham/analytics-events/events`.

Their presence proves that the official application calls them; it does not
make them suitable SDK primitives. They are stateful, commercially sensitive,
security-sensitive, or internal observability surfaces and remain documented
only at the family level.

## Recommended SDK follow-up order

1. Add read-only usage detail and cloud task-turn/log helpers.
2. Complete environment and repository discovery with explicit mutation
   methods separated from reads.
3. Add Remote Control MFA-requirement and Desktop pairing compatibility.
4. Probe model/voice/system-hint reads with OAuth and record response schemas.
5. Add curated plugin discovery and the distinct `/ps/mcp` transport after
   validating their lifecycle and response contracts.
