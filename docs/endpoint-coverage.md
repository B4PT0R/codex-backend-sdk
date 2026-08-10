# Endpoint coverage matrix

This is the living implementation matrix for backend surfaces found in the
official Codex and Codex Desktop clients. The source snapshot and discovery
method are recorded in `desktop-endpoint-inventory.md`.

Statuses:

- **live**: exercised against the backend with Codex OAuth;
- **contract**: implemented from an official-client request contract and
  covered by local tests, but not invoked live because it mutates state or
  requires user-owned identifiers;
- **inventory**: observed but not yet implemented;
- **excluded**: intentionally outside the SDK's default surface.

Private schemas remain raw unless a stable boundary is useful. A live status
proves current account availability, not a public compatibility guarantee.

## Core Codex and protocol transports

| Method and path | SDK surface | Status |
| --- | --- | --- |
| `POST /backend-api/codex/responses` | `client.responses.create` | live |
| `POST /backend-api/codex/responses/compact` | `client.responses.compact` | live |
| `GET /backend-api/codex/models` | `client.models` | live |
| `POST /backend-api/codex/realtime/calls` | `client.realtime.calls` | live |
| `WSS /v1/realtime?model=...` | `client.realtime.connect` | live |
| `POST /backend-api/wham/remote/control/server/enroll` | `client.codex.remote_control.enroll` | contract |
| `POST /backend-api/wham/remote/control/server/refresh` | `client.codex.remote_control.refresh` | contract |
| `POST /backend-api/wham/remote/control/server/pair[/status]` | `client.codex.remote_control.pairing` | contract |
| `WSS /backend-api/wham/remote/control/server` | `client.codex.remote_control.connect` | contract |
| `GET/DELETE .../remote/control/environments/{id}/clients[/client]` | `client.codex.remote_control.clients` | contract |
| `GET /backend-api/wham/remote/control/mfa_requirement` | `client.codex.remote_control.desktop.mfa_requirement` | live |
| `GET /backend-api/accounts/mfa_info` | `client.codex.remote_control.desktop.mfa_info` | live |
| `GET /backend-api/wham/remote/control/clients` | `client.codex.remote_control.desktop.clients` | live |
| `POST /backend-api/wham/remote/control/client/pair` | `client.codex.remote_control.desktop.clients.pair` | contract; explicit mutation |
| `DELETE /backend-api/wham/remote/control/clients/{id}` | `client.codex.remote_control.desktop.clients.revoke` | contract; explicit mutation |
| `GET /backend-api/codex/remote/control[/clients/{id}]/environments` | `client.codex.remote_control.desktop.environments` | live |
| `PATCH/DELETE /backend-api/codex/remote/control/environments/{id}` | `client.codex.remote_control.desktop.environments.rename/delete` | contract; explicit mutation |

## Apps, MCP, and widgets

| Method and path | SDK surface | Status |
| --- | --- | --- |
| `POST /backend-api/wham/apps` (`tools/list`) | `client.chatgpt.apps.list_tools` | live; 170 tools observed |
| `POST /backend-api/wham/apps` (raw JSON-RPC) | `client.chatgpt.apps.request` | contract |
| `POST /backend-api/wham/apps` (`tools/call`) | `client.chatgpt.apps.call_tool` | contract |
| `POST /backend-api/ecosystem/url_safe` | `client.chatgpt.apps.is_url_safe` | live |
| `POST /backend-api/ecosystem/launcher/bootstrap` | `client.chatgpt.apps.bootstrap_launcher` | contract |
| `POST /backend-api/ecosystem/launcher/auto_install` | `client.chatgpt.apps.auto_install_launcher` | contract; explicit mutation |
| `POST /backend-api/ecosystem/call_mcp` | `client.chatgpt.apps.call_ecosystem_mcp` | contract |
| `GET /backend-api/ecosystem/widget` | `client.chatgpt.apps.get_widget` | contract |
| `POST /backend-api/ecosystem/launch_widget` | `client.chatgpt.apps.launch_widget` | contract; explicit mutation |
| `GET /backend-api/plugins/export/curated` | `client.chatgpt.plugins.curated_export` | live |
| `GET /backend-api/plugins/featured` | `client.chatgpt.plugins.featured` | live; 29 Codex IDs observed |
| `POST /backend-api/ps/mcp` | `client.chatgpt.apps.connect_hosted_mcp` | live; MCP 2025-06-18, 172 tools, 37 resources |
| `GET /backend-api/connectors/directory/list[_workspace]` | `client.chatgpt.connectors.directory` | live; 2,614 apps observed |
| `POST /backend-api/ps/apps/batch` | `client.chatgpt.connectors.batch_metadata` | live |

## ChatGPT product resources

| Family | SDK surface | Status |
| --- | --- | --- |
| Models, voices, system hints, account | `client.chatgpt.models`, `.voice`, `.account` | live reads |
| Conversation list/search/CRUD/streaming | `client.chatgpt.conversations` | live reads; mutations contract |
| Conversation continuation WebSocket URL | `client.chatgpt.conversations.websocket_url` | live |
| Subagent turns, rating, DIL state, widget refresh | `client.chatgpt.conversations` | reads contract; mutations explicit |
| Global indexed search | `client.chatgpt.search.global_search` | live |
| Sidebar conversation SSE | `client.chatgpt.conversations.sidebar_stream` | contract; caller-owned integrity headers |
| Projects and project files | `client.chatgpt.projects` | live reads; mutations contract |
| Generic custom-GPT detail | `client.chatgpt.gizmos.retrieve` | contract |
| File library, downloads, and upload-processing stream | `client.chatgpt.files`, `client.files` | live reads; streams/mutations contract |
| Pins and shared links | `client.chatgpt.pins`, `.shares` | live reads; mutations contract |
| Pronunciation synthesis | `client.chatgpt.voice.synthesize_pronunciation` | live |
| Sentinel session routes | `client.chatgpt.sentinel` | contract |
| TPP models and system/custom-agent hints | `client.chatgpt.models` | live catalogs/hints; custom-agent contract |
| Account preference mutations | `client.chatgpt.account` | contract; explicit mutations |
| Writing-block persistence and magic edit | `client.chatgpt.writing_blocks` | contract; explicit conversation mutation/inference |
| Connector detail, terms, logo, and current link | `client.chatgpt.connectors` | live reads |
| Accessible connector links | `client.chatgpt.connectors.links.list_accessible` | live; 9 links observed |
| Connector no-auth/OAuth linking and reauthentication | `client.chatgpt.connectors.authentication` | contract; explicit mutations |
| Contacts and email actions | `client.chatgpt.connectors.external_actions` | contract; caller-owned external-action approval |

## Codex cloud resources

| Family | SDK surface | Status |
| --- | --- | --- |
| Usage, daily breakdown, credit events, thread query | `client.codex.usage` | live reads; query contract |
| Tasks, turns, logs, archives/cancel/recover/read | `client.codex.tasks` | live reads; mutations contract |
| Environments, machines, repository/branch discovery | `client.codex.environments`, `.repositories` | live reads; mutations contract |
| Profile, preferences, workspace messages | `client.codex.profile`, `.config`, `.workspace_messages` | live reads; mutations contract |
| Worktree snapshot upload/finalize | `client.codex.worktree_snapshots` | contract; explicit storage mutation |
| Desktop onboarding | not exposed | inventory |

## Exclusions

Payments and subscriptions, workspace administration, reports, attestation,
feature bootstrap, telemetry, analytics, and beacon endpoints are excluded by
default. They are commercially sensitive, security-sensitive, administrative,
or observability surfaces rather than useful primitives for independent
harnesses.
