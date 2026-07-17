# Changelog

All notable changes to this project will be documented in this file.

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
