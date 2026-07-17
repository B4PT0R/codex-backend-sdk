"""OpenAI-shaped resources authenticated through the Codex ChatGPT session."""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from .._models import CreateEmbeddingResponse, Transcription
from .._utils import (
    _UNSET,
    CodexBackendUnsupportedParameterError,
    _add_given,
    _coerce_file,
    _form_value,
    _is_given,
    _jsonable,
)

if TYPE_CHECKING:
    from .._client import CodexClient


class Embeddings:
    """Embeddings resource backed by the Codex OAuth access token."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create(
        self,
        *,
        input: Any,
        model: str,
        dimensions: Any = _UNSET,
        encoding_format: Any = _UNSET,
        user: Any = _UNSET,
        extra_headers: Optional[dict[str, str]] = None,
        extra_query: Optional[dict[str, Any]] = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> CreateEmbeddingResponse:
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")

        payload = {"input": input, "model": model}
        _add_given(payload, "dimensions", dimensions)
        _add_given(payload, "encoding_format", encoding_format)
        _add_given(payload, "user", user)
        if extra_body:
            payload.update(_jsonable(extra_body))

        data = self._client._post_openai(
            "/embeddings",
            body=payload,
            headers=extra_headers,
            params=extra_query,
            timeout=timeout,
        )
        return CreateEmbeddingResponse.model_validate(data)


class Audio:
    """Audio resources matching the official OpenAI SDK surface where available."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.transcriptions = AudioTranscriptions(client)


class AudioTranscriptions:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create(
        self,
        *,
        file: Any,
        model: str,
        chunking_strategy: Any = _UNSET,
        include: Any = _UNSET,
        known_speaker_names: Any = _UNSET,
        known_speaker_references: Any = _UNSET,
        language: Any = _UNSET,
        prompt: Any = _UNSET,
        response_format: Any = _UNSET,
        stream: Any = _UNSET,
        temperature: Any = _UNSET,
        timestamp_granularities: Any = _UNSET,
        extra_headers: Optional[dict[str, str]] = None,
        extra_query: Optional[dict[str, Any]] = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> str | Transcription:
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")

        if _is_given(response_format) and response_format not in {None, "json", "text"}:
            raise CodexBackendUnsupportedParameterError(
                "The ChatGPT transcription backend supports only `json` and `text` response formats."
            )

        unsupported = {
            "chunking_strategy": chunking_strategy,
            "include": include,
            "known_speaker_names": known_speaker_names,
            "known_speaker_references": known_speaker_references,
            "stream": stream,
            "timestamp_granularities": timestamp_granularities,
        }
        given_unsupported = [
            name for name, value in unsupported.items()
            if _is_given(value) and value not in {None, False}
        ]
        if given_unsupported:
            raise CodexBackendUnsupportedParameterError(
                "The ChatGPT transcription backend does not support: "
                + ", ".join(sorted(given_unsupported))
            )

        data = {"model": model}
        _add_given(data, "language", language)
        _add_given(data, "prompt", prompt)
        _add_given(data, "response_format", response_format)
        _add_given(data, "temperature", temperature)
        if extra_body:
            data.update(_jsonable(extra_body))

        response = self._client._post_chatgpt_raw(
            "/transcribe",
            files={"file": _coerce_file(file)},
            data={key: _form_value(value) for key, value in data.items()},
            headers=extra_headers,
            params=extra_query,
            timeout=timeout,
        )
        transcription = Transcription.model_validate(response.json())
        if _is_given(response_format) and response_format == "text":
            return transcription.text
        return transcription
