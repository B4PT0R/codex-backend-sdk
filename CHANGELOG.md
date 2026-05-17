# Changelog

All notable changes to this project will be documented in this file.

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
