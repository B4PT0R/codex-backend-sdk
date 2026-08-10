# `openai-python` compatibility

The SDK follows an additive compatibility rule: when the Codex or ChatGPT
backend exposes the same capability as the OpenAI developer API, code written
for the official Python SDK should keep the same method name, keyword names,
input conventions, request options, defaults, and observable result shape.
Backend-only helpers and optional parameters may be added, but must not change
the meaning of the official subset.

This matrix was audited against `openai-python` **2.53.0**. The development
dependency and `tests/test_openai_compatibility.py` ensure that a newer official
parameter cannot disappear silently from the backend client surface.

## Common surface

| Surface | Signature | Behavior | Backend differences |
| --- | --- | --- | --- |
| `responses.create` | Official parameters preserved; Codex extensions remain additive | Supported parameters and request options are forwarded | Codex requires ephemeral `store=False` and an SSE wire response; unsupported stored-response and Platform controls raise explicitly |
| `responses.parse` | Official parameters preserved | Pydantic structured output and `verbosity` are normalized locally | Streaming parsed responses are not exposed |
| `responses.compact` | Official parameters preserved; Codex tool/reasoning controls are additive | Supported request options and `extra_body` are forwarded | Stored-response continuation and explicit Platform prompt-cache controls are unavailable |
| `models.list` / `retrieve` | Official parameters preserved; `force_refresh` is additive | Returns iterable OpenAI-shaped model pages | Catalog retrieval is a Codex endpoint and `retrieve` resolves from that catalog |
| `embeddings.create` | Official signature preserved | Uses the OpenAI endpoint with the Codex OAuth bearer | Availability depends on OAuth scopes and account rollout |
| `audio.transcriptions.create` | Official signature preserved | File inputs, JSON/text output, language, prompt, and temperature are supported | Streaming, diarization, timestamps, `keywords`, and multi-language hints raise explicitly |
| `images.generate` | Official signature preserved | GPT Image generation returns OpenAI-shaped base64 results | Codex always returns non-streamed PNG/base64 output; format/compression and Platform user attribution are unavailable |
| `images.edit` | Official signature preserved | Single/multiple file inputs, URLs, data URLs, reference objects, and masks are normalized to Codex JSON | A mask targets the first image; `file_id` is contract-derived but not live-verified; Codex returns non-streamed PNG/base64 output |
| `files.create` | Official signature is present | Not callable with Codex OAuth | Live probe returned missing `api.files.write`; the method raises a scope-specific unsupported error |
| `realtime.calls.create` | Official WebRTC call-creation parameters preserved | SDP and session payloads use the OpenAI endpoint with OAuth | Codex-only Realtime v3 remains an additive method |

The response models also preserve the common access idioms: nested response and
stream values support both mapping and attribute access, image results use the
official `Image` / `ImagesResponse` names (with backward-compatible aliases),
and streamed Responses are iterable, closeable context managers.

## Additive surfaces

These do not have to match `openai-python`, because they expose product backend
capabilities rather than developer API equivalents:

- `client.codex.*`
- `client.chatgpt.*`
- `client.files.upload(path)` for ChatGPT/Codex Apps signed-storage uploads
- `client.realtime.calls.create_v3(...)`
- `client.responses.websocket`

The official SDK's newer reconnecting `responses.connect()` manager is not
claimed as equivalent to the additive low-level WebSocket connection yet.

## Image input normalization

The official `image=` parameter accepts one file or a sequence of files. The
backend transport instead expects `images[]` entries containing an `image_url`
or `file_id`. The SDK accepts official binary inputs, paths, file objects, and
file tuples and converts them to base64 data URLs internally. URL/data-URL and
`{image_url: ...}` / `{file_id: ...}` references are additive conveniences.

The `mask=` parameter accepts the same file forms. With multiple images, the
backend and developer API both apply the mask to the first input image; later
images are references interpreted with the prompt.

## Explicit limitations

An official keyword can be present even when the authenticated product backend
cannot implement it. In that case the SDK raises
`CodexBackendUnsupportedParameterError`; it must never accept and silently drop
the value.

Live probes established the following boundaries:

- Codex image JSON accepts `output_format` and `output_compression` fields but
  currently ignores them and returns PNG. Non-equivalent values are rejected
  locally.
- `gpt-image-2` processes image inputs at high fidelity. Explicit `high` is
  compatible; requesting `low` is rejected.
- OpenAI Files creation reaches the Platform endpoint but fails authorization
  because Codex OAuth lacks `api.files.write`.

## Maintenance procedure

1. Upgrade the development installation of `openai-python`.
2. Run `tests/test_openai_compatibility.py` to identify newly added keywords.
3. Check the current Codex source and backend request contract.
4. Probe uncertain fields without assuming that HTTP acceptance means the field
   was honored.
5. Implement compatible normalization where possible; otherwise add a precise
   unsupported error and record the intrinsic boundary here.
6. Run the full test and build matrix.
