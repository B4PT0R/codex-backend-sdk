# Codex source compatibility audit — 2026-10-22

Compared `openai/codex` from the previously audited
`7498521d288b9b3b96ffba4eedf089d8d6e06a84` to
`0eb98b46176fd41fc285e5e2f82218bf0ccd70f5` (`origin/main`). The local checkout
was updated by fast-forward and has no local changes. This is a source-contract
audit; the packaged Desktop ASAR was not rescanned and no live backend requests
were used to validate the new contracts.

## Scope and method

Reviewed changed production contracts in `codex-rs/codex-api`, `backend-client`,
`core-plugins` remote catalog/search/sharing, `chatgpt` connectors,
`app-server-transport` Remote Control, `login`, cloud tasks, and `cloud-client`.
Searched changed Rust production sources across `codex-rs` for added backend
route literals and checked request builders, response types, and protocol item
changes. Local app-server JSON-RPC methods, CLI flags, and harness policy are
outside this HTTP backend SDK's scope.

## Findings and disposition

| Upstream change | SDK disposition and verification |
| --- | --- |
| WebSocket `response.interrupt` with `response_id` and `mode: discard_partial_items` | Added `connection.interrupt()`. Tracks the active response, checks the acknowledgement ID, rejects failed/unsolicited acknowledgements, and drains both acknowledgement and terminal event before reuse. Closing an unfinished iterator retires the socket. Tests cover cross-thread interruption and completion arriving before acknowledgement. |
| Numeric custom reasoning effort serialized as an unsigned 64-bit JSON number | HTTP Responses and compaction convert parseable numeric effort strings into integers, matching Codex. Existing numbers, named/custom string efforts, and additive dictionary options remain supported. Attribute-based controls retain `context`. Exported `ReasoningEffort` accepts strings and integers. |
| Messages gain `encrypted_content` and `status`; `phase` gains `partial_answer`; output text gains `annotations`/`logprobs` | Message normalization now retains known replay fields, including `id`, `phase`, and metadata. Content parts and non-message items remain raw. A round-trip test protects opaque fields, empty arrays, `additional_tools`, and `configuration_update`. Local `kind`/`call_id` keys on ordinary messages remain filtered. |
| Installed-plugin pagination always sends `limit`, including scoped requests | Fixed `.plugins.installed(scope=..., limit=...)`; validates and transmits the limit alongside the scope and cursor. Aggregation already rejects repeated cursors. |
| Image edit references allow both `image_url` and `file_id` | Already supported; mixed references are contract-tested. HTTP failures retain the underlying response and headers, including nested ImageGen request IDs. |
| Thread usage and groups gain `native_usage_usd_micros`; plugin release gains `onboarding_skill_name`; new plan names | Existing raw dictionaries preserve additive fields. Contract test distinguishes absent/null/zero/native amounts without estimating them. |
| Base instructions move from the top-level field into developer input messages (`c9253c4977`) | Developer messages are supported, and their explicit IDs/metadata now survive normalization. The OpenAI-shaped `instructions=` argument keeps its existing top-level encoding for compatibility; removing it from Codex's own request struct does not establish backend rejection. No claim of live equivalence or retirement of the old field is made. |
| Responses serializes `model`, `stream`, `service_tier` before large input (`ed0cc1a4ab`) | Values already supported; ordering is an upstream gateway optimization, not a newly required parameter. |
| Provider-specific model catalog URLs and plugin product SKU become configurable | Provider/gateway configuration is outside the SDK's fixed ChatGPT backend routing. Catalog query overrides and plugin `codex` product headers remain supported. |
| Realtime transcript handling, shared HTTP/network policy, proxy fallback, file PUT retries, OAuth storage/provenance changes | Existing endpoint paths and request schemas remain compatible. These client implementation/policy changes do not add required backend parameters. Realtime events and WebSocket envelopes remain raw. |
| Native cloud ThreadService `Resume` and live `Attach` | **Inventory, unsupported.** Separate HTTP/2 gRPC/protobuf transport, not an HTTP JSON endpoint or app-server JSON-RPC. Upstream requires a caller-supplied trusted origin and explicitly does not establish production ingress. Do not guess a URL or send these payloads through the SDK's JSON transport. |

Relevant source locations at the audited commit:

- `codex-rs/codex-api/src/common.rs`
- `codex-rs/codex-api/src/endpoint/responses_websocket.rs`
- `codex-rs/core/src/client.rs` and `core/src/context/base_instructions.rs`
- `codex-rs/protocol/src/models.rs`
- `codex-rs/core-plugins/src/remote.rs`
- `codex-rs/backend-client/src/client/thread_usage.rs`
- `codex-rs/cloud-client/README.md`, `src/lib.rs`, and `src/wire.rs`

No new HTTP route in the reviewed backend families requires a new SDK resource.
The native gRPC surface is explicitly tracked above. Earlier Desktop-only
coverage and exclusions remain as recorded in `desktop-endpoint-inventory.md`.

## Validation

Durable behavioral contracts added by this audit live in
`tests/general/test_codex_source_contracts.py`. Existing local contract tests
are also run; tests using the authenticated `client` fixture are excluded from
the local-only run. No transient diagnostic tests are retained in
`tests/agentic/`, and no backend mutation or inference is performed by these tests.

Result: **310 passed, 12 live tests deselected**. Ruff's correctness rules
(`E4`, `E7`, `E9`, `F`, Python 3.9 target) and `git diff --check` also pass for
the changed Python files. The broader Ruff style rules report existing issues
in these modules and are not a clean project baseline.
