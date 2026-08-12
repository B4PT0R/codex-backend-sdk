"""Pydantic response models exposed by the SDK."""

from __future__ import annotations

import base64
import time
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, Generic, Literal, Optional, TypeVar

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh"]
ReasoningSummary = Literal["concise", "detailed", "auto"]
Verbosity = Literal["low", "medium", "high"]
ServiceTier = Literal["flex", "priority"]
ParsedT = TypeVar("ParsedT")


class APIObject(dict[str, Any]):
    """Dictionary with the attribute access used by openai-python models."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def _api_value(value: Any) -> Any:
    if isinstance(value, dict):
        return APIObject({key: _api_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_api_value(item) for item in value]
    return value


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
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0


class ResponseUsage(CodexBaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_tokens_details: TokenDetails = Field(default_factory=TokenDetails)
    output_tokens_details: TokenDetails = Field(default_factory=TokenDetails)


class ResponseFormatJsonSchema(CodexBaseModel):
    type: Literal["json_schema"] = "json_schema"
    name: str
    schema_: dict[str, Any] = Field(alias="schema")
    strict: Optional[bool] = None
    description: Optional[str] = None


class Response(CodexBaseModel):
    id: str
    created_at: float = Field(default_factory=time.time)
    error: Optional[dict[str, Any]] = None
    incomplete_details: Optional[dict[str, Any]] = None
    instructions: Any = None
    metadata: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    object: Literal["response"] = "response"
    output: list[Any] = Field(default_factory=list)
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

    @field_validator("output", mode="before")
    @classmethod
    def _normalize_output_objects(cls, value: Any) -> Any:
        return _api_value(value)

    @property
    def output_text(self) -> str:
        texts: list[str] = []
        for output in self.output:
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        texts.append(content.get("text", ""))
        return "".join(texts)

    @property
    def reasoning_summary(self) -> str | None:
        texts: list[str] = []
        for output in self.output:
            if output.get("type") == "reasoning":
                for summary in output.get("summary", []):
                    if isinstance(summary, dict):
                        texts.append(summary.get("text", ""))
        return "\n".join(text for text in texts if text) or None

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [output for output in self.output if output.get("type") == "function_call"]


class ParsedResponse(CodexBaseModel, Generic[ParsedT]):
    response: Response
    output_parsed: ParsedT

    @property
    def id(self) -> str:
        return self.response.id

    @property
    def model(self) -> Optional[str]:
        return self.response.model

    @property
    def output(self) -> list[dict[str, Any]]:
        return self.response.output

    @property
    def output_text(self) -> str:
        return self.response.output_text

    @property
    def status(self) -> Optional[str]:
        return self.response.status

    @property
    def usage(self) -> Optional[ResponseUsage]:
        return self.response.usage

    def __getattr__(self, name: str) -> Any:
        try:
            return super().__getattr__(name)
        except AttributeError:
            response = object.__getattribute__(self, "response")
            return getattr(response, name)


class ResponseStreamEvent(CodexBaseModel):
    type: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_nested_objects(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {key: _api_value(item) for key, item in value.items()}


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


class ChatGPTSpeech(CodexBaseModel):
    """Base64 audio returned by ChatGPT Desktop's limited read-aloud service."""

    base64_data: str = Field(alias="base64")
    content_type: str = Field(alias="contentType")

    @property
    def content(self) -> bytes:
        return base64.b64decode(self.base64_data, validate=True)

    @property
    def data_uri(self) -> str:
        return f"data:{self.content_type};base64,{self.base64_data}"

    def to_bytes_io(self) -> BytesIO:
        return BytesIO(self.content)

    def write_to_file(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.write_bytes(self.content)
        return destination


class Image(CodexBaseModel):
    b64_json: Optional[str] = None
    revised_prompt: Optional[str] = None
    url: Optional[str] = None


class ImagesResponse(CodexBaseModel):
    created: int
    data: list[Image] = Field(default_factory=list)
    background: Optional[str] = None
    output_format: Optional[str] = None
    quality: Optional[str] = None
    size: Optional[str] = None
    usage: Any = None


# Backward-compatible names used before the public models were aligned.
ImageData = Image
ImageResponse = ImagesResponse


class RateLimitResetCredit(CodexBaseModel):
    id: str
    reset_type: str
    status: str
    granted_at: str
    expires_at: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class RateLimitResetCredits(CodexBaseModel):
    available_count: int = 0
    total_earned_count: int = 0
    credits: list[RateLimitResetCredit] = Field(default_factory=list)


class ConsumeRateLimitResetCreditResponse(CodexBaseModel):
    code: str
    windows_reset: int = 0


class RawMemoryMetadata(CodexBaseModel):
    source_path: str


class RawMemory(CodexBaseModel):
    id: str
    metadata: RawMemoryMetadata
    items: list[Any] = Field(default_factory=list)


class MemorySummarizeOutput(CodexBaseModel):
    raw_memory: str = Field(default="", alias="trace_summary")
    memory_summary: str = ""


class MemorySummarizeResponse(CodexBaseModel):
    output: list[MemorySummarizeOutput] = Field(default_factory=list)


class UploadedFile(CodexBaseModel):
    file_id: str
    uri: str
    download_url: str
    file_name: str
    file_size_bytes: int
    mime_type: Optional[str] = None
    path: str


class CompactedResponse(CodexBaseModel):
    id: str
    object: str = "response.compacted"
    output: list[Any] = Field(default_factory=list)
    usage: Optional[ResponseUsage] = Field(default_factory=ResponseUsage)

    @field_validator("output", mode="before")
    @classmethod
    def _normalize_output_objects(cls, value: Any) -> Any:
        return _api_value(value)


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
    """SDP answer and call identifier returned by Realtime call creation."""

    @property
    def answer_sdp(self) -> str:
        return self.text

    @property
    def call_id(self) -> str:
        location = self.response.headers.get("Location")
        if not location:
            raise RuntimeError("Realtime call response is missing the Location header.")
        path = location.split("?", 1)[0].rstrip("/")
        call_id = path.rsplit("/", 1)[-1]
        if call_id.startswith("rtc_") or _is_uuid(call_id):
            return call_id
        raise RuntimeError(
            f"Realtime call Location does not contain a valid call id: {location}"
        )


def _is_uuid(value: str) -> bool:
    if len(value) != 36:
        return False
    return all(
        char == "-" if index in {8, 13, 18, 23} else char in "0123456789abcdefABCDEF"
        for index, char in enumerate(value)
    )
