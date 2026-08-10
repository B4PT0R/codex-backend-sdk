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

__version__ = "0.3.10"

from .oauth import (
    DeviceCode,
    complete_device_code_login,
    refresh_access_token,
    request_device_code,
    revoke_oauth_token,
    run_oauth_flow,
)
from .storage import load_tokens, save_tokens, TokenStore
from .resources.remote_control import (
    RemoteControlClient,
    RemoteControlClientPage,
    RemoteControlConnection,
    RemoteControlDesktop,
    RemoteControlEnrollment,
    RemoteControlEnvironment,
    RemoteControlEnvironmentPage,
    RemoteControlPairing,
    RemoteControlPairingStatus,
)
from .resources.chatgpt_apps import ChatGPTAppsProtocolError, HostedMCPConnection
from .resources.chatgpt_connectors import ConnectorAuthenticationRequiredError
from .resources.responses_websocket import (
    ResponsesWebSocketConnection,
    ResponsesWebSocketError,
)
from .codex_client import (
    CodexBackendUnsupportedParameterError,
    CodexBaseModel,
    ChatGPTSpeech,
    CreateEmbeddingResponse,
    Embedding,
    EmbeddingUsage,
    ImageData,
    ImageResponse,
    RateLimitResetCredit,
    RateLimitResetCredits,
    ConsumeRateLimitResetCreditResponse,
    ReasoningEffort,
    ReasoningSummary,
    ServiceTier,
    Verbosity,
    CodexClient,
    OpenAI,
    MemorySummarizeOutput,
    MemorySummarizeResponse,
    Model,
    RawMemory,
    RawMemoryMetadata,
    ParsedResponse,
    Response,
    ResponseFormatJsonSchema,
    ResponseStreamEvent,
    ResponseUsage,
    RealtimeCallResponse,
    SyncPage,
    CompactedResponse,
    Transcription,
    UploadedFile,
    image_url,
    image_b64,
)

__all__ = [
    "CodexClient",
    "OpenAI",
    "CodexBackendUnsupportedParameterError",
    "CodexBaseModel",
    "ChatGPTSpeech",
    "ChatGPTAppsProtocolError",
    "ConnectorAuthenticationRequiredError",
    "HostedMCPConnection",
    "CreateEmbeddingResponse",
    "Embedding",
    "EmbeddingUsage",
    "DeviceCode",
    "ImageData",
    "ImageResponse",
    "RateLimitResetCredit",
    "RateLimitResetCredits",
    "ConsumeRateLimitResetCreditResponse",
    "MemorySummarizeOutput",
    "MemorySummarizeResponse",
    "Model",
    "ParsedResponse",
    "RawMemory",
    "RawMemoryMetadata",
    "Response",
    "ResponseFormatJsonSchema",
    "ResponseStreamEvent",
    "ResponseUsage",
    "ResponsesWebSocketConnection",
    "ResponsesWebSocketError",
    "RealtimeCallResponse",
    "RemoteControlClient",
    "RemoteControlClientPage",
    "RemoteControlConnection",
    "RemoteControlDesktop",
    "RemoteControlEnrollment",
    "RemoteControlEnvironment",
    "RemoteControlEnvironmentPage",
    "RemoteControlPairing",
    "RemoteControlPairingStatus",
    "SyncPage",
    "CompactedResponse",
    "Transcription",
    "UploadedFile",
    "ReasoningEffort",
    "ReasoningSummary",
    "ServiceTier",
    "Verbosity",
    "image_url",
    "image_b64",
    "run_oauth_flow",
    "refresh_access_token",
    "request_device_code",
    "complete_device_code_login",
    "revoke_oauth_token",
    "load_tokens",
    "save_tokens",
    "TokenStore",
]
