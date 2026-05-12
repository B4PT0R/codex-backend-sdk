"""OpenAI-shaped Python client for the ChatGPT Codex backend.

This module is kept as a compatibility facade. Implementation lives in
``codex_backend_sdk._client`` and ``codex_backend_sdk.resources``.
"""

from __future__ import annotations

from ._client import CodexClient, OpenAI
from ._models import (
    CodexBaseModel,
    CompactedResponse,
    CreateEmbeddingResponse,
    Embedding,
    EmbeddingUsage,
    Model,
    MemorySummarizeOutput,
    MemorySummarizeResponse,
    ParsedResponse,
    RawMemory,
    RawMemoryMetadata,
    ReasoningEffort,
    ReasoningSummary,
    RealtimeCallResponse,
    Response,
    ResponseFormatJsonSchema,
    ResponseStreamEvent,
    ResponseUsage,
    ServiceTier,
    SyncPage,
    TokenDetails,
    Transcription,
    UploadedFile,
    Verbosity,
)
from ._utils import CodexBackendUnsupportedParameterError, image_b64, image_url

__all__ = [
    "CodexBackendUnsupportedParameterError",
    "CodexBaseModel",
    "CodexClient",
    "CreateEmbeddingResponse",
    "Embedding",
    "EmbeddingUsage",
    "CompactedResponse",
    "MemorySummarizeOutput",
    "MemorySummarizeResponse",
    "Model",
    "OpenAI",
    "ParsedResponse",
    "RawMemory",
    "RawMemoryMetadata",
    "ReasoningEffort",
    "ReasoningSummary",
    "Response",
    "ResponseFormatJsonSchema",
    "ResponseStreamEvent",
    "ResponseUsage",
    "RealtimeCallResponse",
    "ServiceTier",
    "SyncPage",
    "TokenDetails",
    "Transcription",
    "UploadedFile",
    "Verbosity",
    "image_b64",
    "image_url",
]
