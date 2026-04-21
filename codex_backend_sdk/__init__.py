"""
codex-backend-sdk — Unofficial Python SDK for the ChatGPT Codex backend API.

DISCLAIMER: This is an independent, community-maintained library that
reverse-engineers undocumented endpoints of chatgpt.com. It is not
affiliated with, endorsed by, or supported by OpenAI. Use is subject
to OpenAI's Terms of Use (https://openai.com/policies/terms-of-use).
Endpoints may change or break without notice.

Quickstart:
    from codex_backend_sdk import CodexClient

    client = CodexClient().authenticate()   # opens browser on first run
    # subsequent runs load & refresh tokens automatically

    for event in client.stream("Explain quicksort"):
        ...
"""

__version__ = "0.1.0"

from .oauth import run_oauth_flow, refresh_access_token, obtain_api_key
from .storage import load_tokens, save_tokens, TokenStore
from .codex_client import (
    ReasoningEffort,
    ReasoningSummary,
    Verbosity,
    ServiceTier,
    CodexClient,
    ModelInfo,
    ReasoningLevel,
    TextDelta,
    ReasoningDelta,
    ToolCall,
    OutputItem,
    TokenUsage,
    ResponseCompleted,
    ResponseFailed,
    CompactionResult,
    image_url,
    image_b64,
)

__all__ = [
    "CodexClient",
    "ReasoningEffort",
    "ReasoningSummary",
    "Verbosity",
    "ServiceTier",
    "ModelInfo",
    "ReasoningLevel",
    "TextDelta",
    "ReasoningDelta",
    "ToolCall",
    "OutputItem",
    "TokenUsage",
    "ResponseCompleted",
    "ResponseFailed",
    "CompactionResult",
    "image_url",
    "image_b64",
    "run_oauth_flow",
    "refresh_access_token",
    "obtain_api_key",
    "load_tokens",
    "save_tokens",
    "TokenStore",
]
