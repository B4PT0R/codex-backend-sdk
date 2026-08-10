# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

## [0.4.0] - 2026-08-10

### Added
- Added a dedicated `client.chatgpt` product namespace covering Desktop
  conversations, projects, files, search, pins, shares, GPTs, account/session,
  models, voice, Sentinel, writing blocks, Apps, connectors, and external
  actions while keeping private schemas raw where appropriate.
- Added Codex cloud resources for detailed usage, tasks/turns/logs, environments,
  machines, repositories/branches, profiles, managed preferences, workspace
  messages, and worktree-snapshot uploads.
- Added the complete independent-server and account-authorized discovery sides
  of Remote Control, including enrollment, pairing, client management, and the
  cursor-aware protocol-v3 WebSocket transport.
- Added hosted Apps MCP, remote plugin catalogs, installation and workspace
  sharing contracts, skill detail, and bounded safe materialization of signed
  plugin, skill, and curated archives.
- Added the Codex Responses WebSocket transport and structured alpha Web Search
  commands, both verified live with reusable/continuation behavior.
- Added browser-callback and device-code Codex OAuth login, explicit remote
  token revocation, connector-scope-preserving refresh, and optional workspace
  selection guards.
- Added guarded Realtime v3 support for the confirmed `gpt-live-1-codex` and
  `gpt-live-1-boulder-alpha` snapshots, plus typed subscription-backed ChatGPT
  pronunciation synthesis with in-memory and persisted output forms.
- Added optional image-edit masks from URLs, base64 data URLs, or uploaded file
  IDs, verified against the authenticated Codex backend.
- Added automated signature drift checks against `openai-python` 2.53.0 and an
  audited compatibility matrix for every common exposed resource.

### Changed
- Grouped surfaces by backend ownership: OpenAI-shaped Codex APIs remain on the
  top-level client, Codex-specific capabilities live under `client.codex`, and
  official-Desktop product APIs live under `client.chatgpt`.
- Preserved the original connector scopes during OAuth refresh instead of
  accidentally narrowing the grant.
- Aligned image editing with `openai-python` by exposing the singular `image`
  parameter while translating it to the Codex backend's `images` array.
- Forwarded official Responses and Models request options that were previously
  accepted but ignored, normalized official image file inputs, and made
  unsupported Files, image-format, streaming, and transcription controls fail
  explicitly instead of degrading silently.

### Documentation
- Reworked the README as a progressive usage guide from Responses and context
  compaction through Codex cloud and ChatGPT product integrations, with an
  explicit map of `client`, `client.codex`, and `client.chatgpt` ownership.
- Added a dedicated API reference covering the complete public resource tree,
  supported parameters, return shapes, validation, and transport behavior.
- Reconciled all production networking modules in the current Codex checkout
  and every concrete HTTP call site in the extracted official Desktop bundle.
- Added an endpoint coverage matrix with live, contract, and explicit exclusion
  status; no useful route remains unclassified in the audited snapshot.
- Documented why commercial/admin, attestation, reporting, telemetry, personal
  access token, and Desktop device-key enrollment surfaces remain excluded.

### Tests
- Expanded behavioral and request-contract coverage to 221 tests and recorded
  read-only live probes separately from stateful or user-interactive contracts.

## [0.3.10] - 2026-07-17

### Added
- Added typed Codex rate-limit reset credit listing and explicit idempotent consumption through `client.codex.rate_limit_reset_credits`.
- Added ChatGPT-authenticated image generation and editing through `client.images.generate(...)` and `client.images.edit(...)`, returning typed base64 image data from the Codex backend.

### Documentation
- Documented that image generation uses the ChatGPT Codex backend rather than the separately billed Platform image endpoint, and that consuming reset credits mutates account quota state.
- Documented the verified Codex JSON image-edit contract using ordinary URLs or base64 data URLs.

### Tests
- Added behavioral coverage for credit payloads, redemption validation, image request construction, defaults, URL normalization, and typed responses; verified read-only credit listing plus real image generation and editing against the authenticated backend.

## [0.3.9] - 2026-07-17

### Fixed
- Detect anonymous audio buffers by their file signature before ChatGPT transcription uploads, correcting filenames and MIME types when callers provide misleading generic names such as `audio.mp3` for WAV data.
- Restored reliable `AIClient.audio_to_text(bytes)` integration with `/backend-api/transcribe` without requiring callers to understand multipart backend constraints.

### Tests
- Added regression coverage for WAV buffers carrying an incorrect `.mp3` name and verified the complete Codex Agent transcription path against the real ChatGPT backend.

## [0.3.8] - 2026-07-17

### Changed
- Routed `client.audio.transcriptions.create(...)` through the ChatGPT-native `/backend-api/transcribe` endpoint instead of the billable Platform `/v1/audio/transcriptions` endpoint.
- Preserved the OpenAI-shaped `json` and `text` response behavior used by Codex Agent while rejecting unsupported streaming, timestamp, speaker, chunking, SRT, and VTT options explicitly.
- Added a reusable raw ChatGPT multipart request helper to the client transport.

### Documentation
- Clarified that embeddings still use the OpenAI Platform endpoint and its developer-account quota, while batch transcription now uses the authenticated ChatGPT backend.

### Tests
- Added coverage for ChatGPT transcription routing, account authentication headers, text responses, and unsupported parameters.

## [0.3.7] - 2026-07-17

### Added
- Added typed Realtime call results through `RealtimeCallResponse.answer_sdp` and `RealtimeCallResponse.call_id`.
- Added Codex AVAS session payload support, including automatic removal of the server-generated session `id` and the required `quicksilver` query parameters.

### Documentation
- Documented that the ChatGPT-authenticated Codex WebRTC route is experimental and rollout-dependent, while the public Realtime WebSocket route still requires a developer API key.

### Tests
- Added coverage for SDP response parsing, call ID validation, AVAS payload construction, and invalid session payloads.

## [0.3.6] - 2026-07-11

### Added
- Added Voice v2 WebSocket headers through `client.realtime.websocket_headers(...)`, using the API key stored by OAuth when available or `OPENAI_API_KEY` as a fallback.
- Added `authenticate(force=True)` for explicit interactive reauthentication.

### Changed
- ChatGPT OAuth now attempts the same optional ID-token-to-API-key exchange as Codex CLI and persists the result in the official `OPENAI_API_KEY` auth field.
- Removed the legacy `request_api_key` authentication option; API-key acquisition is now an internal OAuth concern and never prevents regular Codex login.

### Tests
- Added coverage for forced authentication and Realtime credential selection/error behavior.

## [0.3.5] - 2026-05-18

### Fixed
- Preserved `usage` on `client.responses.compact(...)` results so `CompactedResponse` exposes backend token accounting.

### Tests
- Added coverage to verify compact responses retain `input_tokens`, `output_tokens`, and `total_tokens`.

## [0.3.4] - 2026-05-15

### Added
- Added `authenticate(interactive=False)` to allow non-interactive credential checks without triggering the browser OAuth flow.
- Added `client.authenticated` for simple auth-state introspection.
- Added `client.account_info()` to expose safe non-secret account metadata (`authenticated`, `account_id`, `email`, `plan_type`).

### Documentation
- Documented the non-interactive authentication helpers in `README.md`.
