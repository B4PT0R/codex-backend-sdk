"""Codex's structured Web Search endpoint."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from .._utils import _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


class CodexWebSearch:
    """Execute the same structured search commands used by current Codex."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def search(
        self,
        *,
        id: str,
        model: str,
        commands: Any = None,
        input: Any = None,
        reasoning: Any = None,
        settings: Any = None,
        max_output_tokens: int | None = None,
        originator: str | None = None,
        turn_metadata: str | None = None,
    ) -> dict[str, Any]:
        """Post a forward-compatible ``alpha/search`` request.

        ``commands`` accepts the official command object (search/image queries,
        open, click, find, screenshot, finance, weather, sports, time and
        ``response_length``). Structured result variants intentionally remain
        raw because the backend adds variants independently of the SDK.
        """
        session_id = _required(id, "id")
        model_name = _required(model, "model")
        payload: dict[str, Any] = {"id": session_id, "model": model_name}
        if reasoning is not None:
            payload["reasoning"] = _json_value(reasoning, "reasoning")
        if input is not None:
            value = _json_value(input, "input")
            if not isinstance(value, (str, list)):
                raise TypeError("Expected `input` to serialize to a string or list.")
            payload["input"] = value
        if commands is not None:
            value = _json_value(commands, "commands")
            if not isinstance(value, dict):
                raise TypeError("Expected `commands` to serialize to a JSON object.")
            payload["commands"] = value
        if settings is not None:
            value = _json_value(settings, "settings")
            if not isinstance(value, dict):
                raise TypeError("Expected `settings` to serialize to a JSON object.")
            payload["settings"] = value
        if max_output_tokens is not None:
            if (
                not isinstance(max_output_tokens, int)
                or isinstance(max_output_tokens, bool)
                or max_output_tokens < 1
            ):
                raise ValueError("Expected `max_output_tokens` to be a positive integer.")
            payload["max_output_tokens"] = max_output_tokens

        headers: dict[str, str] = {}
        if originator is not None:
            headers["originator"] = _required(originator, "originator")
        if turn_metadata is not None:
            headers["x-codex-turn-metadata"] = _required(
                turn_metadata, "turn_metadata"
            )
        response = self._client._post_raw(
            "/alpha/search", body=payload, headers=headers or None
        ).json()
        if not isinstance(response, dict):
            raise RuntimeError("Codex Web Search returned a non-object response.")
        if not isinstance(response.get("output"), str):
            raise RuntimeError("Codex Web Search response is missing text output.")
        encrypted = response.get("encrypted_output")
        if encrypted is not None and not isinstance(encrypted, str):
            raise RuntimeError("Codex Web Search returned invalid encrypted output.")
        results = response.get("results")
        if results is not None and not isinstance(results, list):
            raise RuntimeError("Codex Web Search returned invalid structured results.")
        return response


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected `{name}` to be a non-empty string.")
    return value


def _json_value(value: Any, name: str) -> Any:
    try:
        converted = _jsonable(value)
        json.dumps(converted)
        return converted
    except (TypeError, ValueError) as exc:
        raise TypeError(f"Expected `{name}` to be JSON serializable.") from exc
