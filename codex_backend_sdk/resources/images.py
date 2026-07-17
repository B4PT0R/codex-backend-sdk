"""ChatGPT Codex image generation resources."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from .._models import ImageResponse
from .._utils import _UNSET, _add_given, _jsonable

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
        model: str = "gpt-image-2",
        background: Any = _UNSET,
        n: Any = _UNSET,
        quality: Any = _UNSET,
        size: Any = _UNSET,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> ImageResponse:
        if not prompt:
            raise ValueError(f"Expected a non-empty value for `prompt` but received {prompt!r}")
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")

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
            timeout=timeout,
        )
        return ImageResponse.model_validate(response.json())

    def edit(
        self,
        *,
        images: list[str | dict[str, str]],
        prompt: str,
        model: str = "gpt-image-2",
        background: Any = _UNSET,
        n: Any = _UNSET,
        quality: Any = _UNSET,
        size: Any = _UNSET,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> ImageResponse:
        if not images:
            raise ValueError("Expected at least one value for `images`")
        if not prompt:
            raise ValueError(f"Expected a non-empty value for `prompt` but received {prompt!r}")
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")

        normalized_images = []
        for image in images:
            if isinstance(image, str):
                if not image:
                    raise ValueError("Expected every image URL to be non-empty")
                normalized_images.append({"image_url": image})
                continue
            image_url = image.get("image_url")
            if not image_url:
                raise ValueError("Expected every image object to contain a non-empty `image_url`")
            normalized_images.append({"image_url": image_url})

        payload: dict[str, Any] = {
            "images": normalized_images,
            "prompt": prompt,
            "model": model,
        }
        _add_given(payload, "background", background)
        _add_given(payload, "n", n)
        _add_given(payload, "quality", quality)
        _add_given(payload, "size", size)
        if extra_body:
            payload.update(_jsonable(extra_body))

        response = self._client._post_raw(
            "/images/edits",
            body=payload,
            timeout=timeout,
        )
        return ImageResponse.model_validate(response.json())
