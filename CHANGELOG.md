# Changelog

All notable changes to this project will be documented in this file.

## [0.3.4] - 2026-05-15

### Added
- Added `authenticate(interactive=False)` to allow non-interactive credential checks without triggering the browser OAuth flow.
- Added `client.authenticated` for simple auth-state introspection.
- Added `client.account_info()` to expose safe non-secret account metadata (`authenticated`, `account_id`, `email`, `plan_type`).

### Documentation
- Documented the non-interactive authentication helpers in `README.md`.
