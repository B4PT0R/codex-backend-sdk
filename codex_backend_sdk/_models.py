"""Pydantic response models exposed by the SDK."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any, Literal, Optional

import requests
from pydantic import BaseModel, ConfigDict, Field

ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh"]
ReasoningSummary = Literal["concise", "detailed", "auto"]
Verbosity = Literal["low", "medium", "high"]
ServiceTier = Literal["flex", "priority"]


class CodexBaseModel(BaseModel):
    """Pydantic base with convenience helpers matching openai-python objects."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def to_dict(
        self,
        *,
        mode: Literal["json", "python"] = "python",
        use_api_names: bool = True,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        warnings: bool = True,
    ) -> dict[str, Any]:
        return self.model_dump(
            mode=mode,
            by_alias=use_api_names,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            warnings=warnings,
        )

    def to_json(
        self,
        *,
        use_api_names: bool = True,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        warnings: bool = True,
    ) -> str:
        return self.model_dump_json(
            by_alias=use_api_names,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            warnings=warnings,
        )

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class TokenDetails(CodexBaseModel):
    cached_tokens: int = 0
    reasoning_tokens: int = 0


class ResponseUsage(CodexBaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_tokens_details: TokenDetails = Field(default_factory=TokenDetails)
    output_tokens_details: TokenDetails = Field(default_factory=TokenDetails)


class Response(CodexBaseModel):
    id: str
    created_at: float = Field(default_factory=time.time)
    error: Optional[dict[str, Any]] = None
    incomplete_details: Optional[dict[str, Any]] = None
    instructions: Any = None
    metadata: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    object: Literal["response"] = "response"
    output: list[dict[str, Any]] = Field(default_factory=list)
    parallel_tool_calls: bool = False
    temperature: Optional[float] = None
    tool_choice: Any = "auto"
    tools: list[dict[str, Any]] = Field(default_factory=list)
    top_p: Optional[float] = None
    background: Optional[bool] = None
    completed_at: Optional[float] = None
    conversation: Any = None
    max_output_tokens: Optional[int] = None
    max_tool_calls: Optional[int] = None
    previous_response_id: Optional[str] = None
    prompt: Any = None
    prompt_cache_key: Optional[str] = None
    prompt_cache_retention: Optional[str] = None
    reasoning: Any = None
    safety_identifier: Optional[str] = None
    service_tier: Optional[str] = None
    status: Optional[str] = "completed"
    text: Any = None
    top_logprobs: Optional[int] = None
    truncation: Optional[str] = None
    usage: Optional[ResponseUsage] = Field(default_factory=ResponseUsage)
    user: Optional[str] = None

    @property
    def output_text(self) -> str:
        texts: list[str] = []
        for output in self.output:
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        texts.append(content.get("text", ""))
        return "".join(texts)


class ResponseStreamEvent(CodexBaseModel):
    type: str


class Model(CodexBaseModel):
    id: str
    created: int = 0
    object: Literal["model"] = "model"
    owned_by: str = "openai"


class SyncPage(CodexBaseModel):
    object: Literal["list"] = "list"
    data: list[Any] = Field(default_factory=list)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self.data[key]
        return getattr(self, key)

    def has_next_page(self) -> bool:
        return False

    def next_page_info(self) -> None:
        return None


class Embedding(CodexBaseModel):
    embedding: list[float] | str
    index: int
    object: Literal["embedding"] = "embedding"


class EmbeddingUsage(CodexBaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class CreateEmbeddingResponse(CodexBaseModel):
    data: list[Embedding] = Field(default_factory=list)
    model: str
    object: Literal["list"] = "list"
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)


class Transcription(CodexBaseModel):
    text: str = ""


class CompactedResponse(CodexBaseModel):
    id: str
    object: str = "response.compacted"
    output: list[dict[str, Any]] = Field(default_factory=list)


class BinaryResponseContent:
    """Binary response content compatible with openai-python's common helpers."""

    def __init__(self, response: requests.Response) -> None:
        self.response = response

    @property
    def content(self) -> bytes:
        return self.response.content

    @property
    def text(self) -> str:
        return self.response.text

    @property
    def encoding(self) -> Optional[str]:
        return self.response.encoding

    @encoding.setter
    def encoding(self, value: Optional[str]) -> None:
        self.response.encoding = value

    def read(self) -> bytes:
        return self.content

    def json(self, **kwargs: Any) -> Any:
        return self.response.json(**kwargs)

    def iter_bytes(self, chunk_size: int = 1024) -> Iterator[bytes]:
        return self.response.iter_content(chunk_size=chunk_size)

    def iter_lines(self) -> Iterator[bytes]:
        return self.response.iter_lines()

    def close(self) -> None:
        self.response.close()

    def write_to_file(self, file: str) -> None:
        with open(file, "wb") as handle:
            handle.write(self.content)


class RealtimeCallResponse(BinaryResponseContent):
    """Binary SDP response returned by ``client.realtime.calls.create``."""
