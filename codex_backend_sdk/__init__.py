"""
codex-backend-sdk — Unofficial Python SDK for the ChatGPT Codex backend API.

DISCLAIMER: This is an independent, community-maintained library that
reverse-engineers undocumented endpoints of chatgpt.com. It is not
affiliated with, endorsed by, or supported by OpenAI. Use is subject
to OpenAI's Terms of Use (https://openai.com/policies/terms-of-use).
Endpoints may change or break without notice.

Quickstart:
    from codex_backend_sdk import OpenAI

    client = OpenAI().authenticate()        # opens browser on first run
    # subsequent runs load & refresh tokens automatically

    response = client.responses.create(input="Explain quicksort")
    print(response.output_text)
"""

__version__ = "0.3.0"

from .oauth import run_oauth_flow, refresh_access_token, obtain_api_key
from .storage import load_tokens, save_tokens, TokenStore
from .codex_client import (
    CodexBackendUnsupportedParameterError,
    CodexBaseModel,
    CreateEmbeddingResponse,
    Embedding,
    EmbeddingUsage,
    ReasoningEffort,
    ReasoningSummary,
    ServiceTier,
    Verbosity,
    CodexClient,
    OpenAI,
    Model,
    Response,
    ResponseStreamEvent,
    ResponseUsage,
    RealtimeCallResponse,
    SyncPage,
    CompactedResponse,
    Transcription,
    image_url,
    image_b64,
)

__all__ = [
    "CodexClient",
    "OpenAI",
    "CodexBackendUnsupportedParameterError",
    "CodexBaseModel",
    "CreateEmbeddingResponse",
    "Embedding",
    "EmbeddingUsage",
    "Model",
    "Response",
    "ResponseStreamEvent",
    "ResponseUsage",
    "RealtimeCallResponse",
    "SyncPage",
    "CompactedResponse",
    "Transcription",
    "ReasoningEffort",
    "ReasoningSummary",
    "ServiceTier",
    "Verbosity",
    "image_url",
    "image_b64",
    "run_oauth_flow",
    "refresh_access_token",
    "obtain_api_key",
    "load_tokens",
    "save_tokens",
    "TokenStore",
]
