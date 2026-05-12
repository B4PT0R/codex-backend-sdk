"""Shared helpers for the Codex backend SDK."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from pydantic import BaseModel

_UNSET: Any = object()


class CodexBackendUnsupportedParameterError(NotImplementedError):
    """Raised when an official OpenAI parameter is absent from the Codex backend."""


def image_url(url: str) -> dict[str, str]:
    return {"type": "input_image", "image_url": url}


def image_b64(data: str, media_type: str = "image/jpeg") -> dict[str, str]:
    return {"type": "input_image", "image_url": f"data:{media_type};base64,{data}"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _add_given(payload: dict[str, Any], key: str, value: Any) -> None:
    if _is_given(value) and value is not None:
        payload[key] = _jsonable(value)


def _coerce_file(file: Any) -> Any:
    if isinstance(file, tuple):
        return file
    if isinstance(file, (bytes, bytearray)):
        return ("audio", bytes(file))
    return file


def _form_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _default(value: Any, default: Any) -> Any:
    return default if not _is_given(value) else value


def _is_given(value: Any) -> bool:
    return value is not _UNSET and value.__class__.__name__ not in {"Omit", "NotGiven"}


def _reject_backend_unsupported(**values: Any) -> None:
    unsupported = [name for name, value in values.items() if _is_given(value) and value is not None]
    if unsupported:
        raise CodexBackendUnsupportedParameterError(
            "The Codex backend rejects these official Responses parameters: "
            f"{', '.join(sorted(unsupported))}."
        )


def decode_base64_json(data: str) -> Any:
    return json.loads(base64.b64decode(data).decode("utf-8"))
