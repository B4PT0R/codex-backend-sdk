"""ChatGPT Codex image generation resources."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .._models import ImagesResponse
from .._utils import (
    _UNSET,
    CodexBackendUnsupportedParameterError,
    _add_given,
    _default,
    _is_given,
    _jsonable,
)

if TYPE_CHECKING:
    from .._client import CodexClient


class Images:
    """Image generation through the authenticated Codex backend."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def generate(
        self,
        *,
        prompt: str,
        background: Any = _UNSET,
        model: Any = _UNSET,
        moderation: Any = _UNSET,
        n: Any = _UNSET,
        output_compression: Any = _UNSET,
        output_format: Any = _UNSET,
        partial_images: Any = _UNSET,
        quality: Any = _UNSET,
        response_format: Any = _UNSET,
        size: Any = _UNSET,
        stream: Any = _UNSET,
        style: Any = _UNSET,
        user: Any = _UNSET,
        extra_headers: Any = None,
        extra_query: Any = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> ImagesResponse:
        if not prompt:
            raise ValueError(f"Expected a non-empty value for `prompt` but received {prompt!r}")
        model = _default(model, "gpt-image-2")
        if model is None:
            model = "gpt-image-2"
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")

        _validate_nonstreaming_image_options(
            response_format=response_format,
            stream=stream,
            partial_images=partial_images,
            output_format=output_format,
            output_compression=output_compression,
        )
        if _is_given(style) and style is not None:
            raise CodexBackendUnsupportedParameterError(
                "The Codex GPT Image backend does not support the DALL-E `style` parameter."
            )

        if _is_given(moderation) and moderation not in {None, "auto"}:
            raise CodexBackendUnsupportedParameterError(
                "The Codex image backend does not expose configurable moderation."
            )
        if _is_given(user) and user is not None:
            raise CodexBackendUnsupportedParameterError(
                "The Codex image backend does not expose the Platform `user` identifier."
            )

        payload: dict[str, Any] = {"prompt": prompt, "model": model}
        _add_given(payload, "background", background)
        _add_given(payload, "n", n)
        _add_given(payload, "quality", quality)
        _add_given(payload, "size", size)
        if extra_body:
            payload.update(_jsonable(extra_body))

        response = self._client._post_raw(
            "/images/generations",
            body=payload,
            headers=extra_headers,
            params=extra_query,
            timeout=timeout,
        )
        return ImagesResponse.model_validate(response.json())

    def edit(
        self,
        *,
        image: Any,
        prompt: str,
        background: Any = _UNSET,
        input_fidelity: Any = _UNSET,
        mask: Any = _UNSET,
        model: Any = _UNSET,
        n: Any = _UNSET,
        output_compression: Any = _UNSET,
        output_format: Any = _UNSET,
        partial_images: Any = _UNSET,
        quality: Any = _UNSET,
        response_format: Any = _UNSET,
        size: Any = _UNSET,
        stream: Any = _UNSET,
        user: Any = _UNSET,
        extra_headers: Any = None,
        extra_query: Any = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> ImagesResponse:
        images = _image_inputs(image)
        if not images:
            raise ValueError("Expected at least one value for `images`")
        if not prompt:
            raise ValueError(f"Expected a non-empty value for `prompt` but received {prompt!r}")
        model = _default(model, "gpt-image-2")
        if model is None:
            model = "gpt-image-2"
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")
        _validate_nonstreaming_image_options(
            response_format=response_format,
            stream=stream,
            partial_images=partial_images,
            output_format=output_format,
            output_compression=output_compression,
        )
        if _is_given(input_fidelity) and input_fidelity not in {None, "high"}:
            raise CodexBackendUnsupportedParameterError(
                "`gpt-image-2` always processes Codex image inputs at high fidelity."
            )
        if _is_given(user) and user is not None:
            raise CodexBackendUnsupportedParameterError(
                "The Codex image backend does not expose the Platform `user` identifier."
            )

        normalized_images = [
            _normalize_image_reference(item, parameter="image") for item in images
        ]

        payload: dict[str, Any] = {
            "images": normalized_images,
            "prompt": prompt,
            "model": model,
        }
        _add_given(payload, "background", background)
        if mask is not _UNSET:
            payload["mask"] = _normalize_image_reference(mask, parameter="mask")
        _add_given(payload, "n", n)
        _add_given(payload, "quality", quality)
        _add_given(payload, "size", size)
        if extra_body:
            payload.update(_jsonable(extra_body))

        response = self._client._post_raw(
            "/images/edits",
            body=payload,
            headers=extra_headers,
            params=extra_query,
            timeout=timeout,
        )
        return ImagesResponse.model_validate(response.json())


def _normalize_image_reference(
    reference: Any, *, parameter: str
) -> dict[str, str]:
    if isinstance(reference, str):
        if not reference:
            raise ValueError(f"Expected `{parameter}` to be non-empty")
        if reference.startswith(("data:", "http://", "https://")):
            return {"image_url": reference}
        return {"image_url": _file_data_url(Path(reference))}

    if isinstance(reference, dict):
        image_url = reference.get("image_url")
        file_id = reference.get("file_id")
        if bool(image_url) == bool(file_id):
            raise ValueError(
                f"Expected `{parameter}` to contain exactly one non-empty "
                "`image_url` or `file_id`"
            )
        return {"image_url": image_url} if image_url else {"file_id": file_id}

    if isinstance(reference, tuple):
        if len(reference) < 2:
            raise ValueError(f"Expected `{parameter}` file tuple to contain name and content")
        name, content = reference[:2]
        media_type = reference[2] if len(reference) > 2 else None
        return {"image_url": _content_data_url(content, name=str(name), media_type=media_type)}

    if isinstance(reference, (bytes, bytearray)):
        return {"image_url": _content_data_url(bytes(reference), name="image")}

    if isinstance(reference, Path) or hasattr(reference, "__fspath__"):
        return {"image_url": _file_data_url(Path(reference))}

    if hasattr(reference, "read"):
        return {
            "image_url": _content_data_url(
                reference,
                name=str(getattr(reference, "name", "image")),
            )
        }

    raise TypeError(f"Unsupported `{parameter}` image input: {type(reference).__name__}")


def _image_inputs(image: Any) -> list[Any]:
    if isinstance(image, list):
        return image
    if isinstance(image, tuple) and not _looks_like_file_tuple(image):
        return list(image)
    return [image]


def _looks_like_file_tuple(value: tuple[Any, ...]) -> bool:
    return (
        2 <= len(value) <= 4
        and isinstance(value[0], str)
        and not isinstance(value[1], str)
    )


def _content_data_url(content: Any, *, name: str, media_type: Any = None) -> str:
    if hasattr(content, "read"):
        position = content.tell() if hasattr(content, "tell") else None
        raw = content.read()
        if position is not None and hasattr(content, "seek"):
            content.seek(position)
    else:
        raw = bytes(content)
    if not isinstance(raw, bytes):
        raise TypeError("Image file content must be binary")
    mime = media_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _file_data_url(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"image file `{path}` does not exist")
    return _content_data_url(path.read_bytes(), name=path.name)


def _validate_nonstreaming_image_options(
    *,
    response_format: Any,
    stream: Any,
    partial_images: Any,
    output_format: Any,
    output_compression: Any,
) -> None:
    if _is_given(response_format) and response_format not in {None, "b64_json"}:
        raise CodexBackendUnsupportedParameterError(
            "The Codex image backend returns only `b64_json`."
        )
    if _is_given(stream) and stream not in {None, False}:
        raise CodexBackendUnsupportedParameterError(
            "The Codex image wrapper does not yet expose streaming image events."
        )
    if _is_given(partial_images) and partial_images not in {None, 0}:
        raise CodexBackendUnsupportedParameterError(
            "`partial_images` requires image streaming, which is unavailable here."
        )
    if _is_given(output_format) and output_format not in {None, "png"}:
        raise CodexBackendUnsupportedParameterError(
            "The Codex image backend currently returns PNG regardless of `output_format`."
        )
    if _is_given(output_compression) and output_compression is not None:
        raise CodexBackendUnsupportedParameterError(
            "The Codex image backend ignores `output_compression`."
        )
