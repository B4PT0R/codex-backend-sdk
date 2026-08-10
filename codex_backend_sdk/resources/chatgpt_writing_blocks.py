"""ChatGPT writing-block persistence and model-assisted edits."""

from __future__ import annotations

from typing import Any, Literal, TYPE_CHECKING

from .._utils import _UNSET, _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


def _required(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"Expected a non-empty value for `{name}` but received {value!r}")
    return value


def _object(value: Any, name: str = "body") -> dict[str, Any]:
    payload = _jsonable(value)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected `{name}` to serialize to a JSON object.")
    return payload


class ChatGPTWritingBlocks:
    """Conversation writing-block mutations observed in Codex Desktop."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def update(self, body: Any) -> dict[str, Any]:
        """Persist a complete official-client writing-block update payload."""

        return self._client._post_chatgpt(
            "/conversation/message/writing-blocks", body=_object(body)
        )

    def magic_edit(
        self,
        *,
        conversation_id: str,
        full_block_body_markdown: str,
        start_index: int,
        end_index: int,
        marked_block_body_markdown: str,
        instruction: str,
        num_variations: int = 1,
        mode: Literal["generate", "edit", "full-edit"] = "edit",
        timeout: Any = _UNSET,
    ) -> dict[str, Any]:
        """Generate replacement choices for a selected Markdown range."""

        if start_index < 0:
            raise ValueError("Expected `start_index` to be non-negative.")
        if end_index < start_index:
            raise ValueError("Expected `end_index` not to precede `start_index`.")
        if end_index > len(full_block_body_markdown):
            raise ValueError("Expected `end_index` within `full_block_body_markdown`.")
        if num_variations < 1:
            raise ValueError("Expected `num_variations` to be positive.")
        if mode not in {"generate", "edit", "full-edit"}:
            raise ValueError(f"Unsupported writing-block edit mode: {mode!r}")

        payload = self._client._post_chatgpt(
            "/conversation/message/writing-blocks/magic-edit",
            body={
                "conversation_id": _required(conversation_id, "conversation_id"),
                "full_block_body_markdown": full_block_body_markdown,
                "start_index": start_index,
                "end_index": end_index,
                "marked_block_body_markdown": marked_block_body_markdown,
                "instruction": _required(instruction, "instruction"),
                "num_variations": num_variations,
                "mode": mode,
            },
            timeout=timeout,
        )
        choices = payload.get("choices")
        if not isinstance(choices, list):
            raise RuntimeError("Writing-block edit response contains invalid `choices`.")
        return payload
