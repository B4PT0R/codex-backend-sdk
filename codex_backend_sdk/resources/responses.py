"""Responses resource."""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel

from .._models import (
    CodexBaseModel,
    CompactedResponse,
    Response,
    ResponseStreamEvent,
    ResponseUsage,
    TokenDetails,
)
from .._streaming import stream_response_events
from .._utils import _UNSET, _default, _is_given, _reject_backend_unsupported

if TYPE_CHECKING:
    from .._client import CodexClient


class Responses:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create(
        self,
        *,
        background: Any = _UNSET,
        context_management: Any = _UNSET,
        conversation: Any = _UNSET,
        include: Any = _UNSET,
        input: Any = _UNSET,
        instructions: Any = _UNSET,
        max_output_tokens: Any = _UNSET,
        max_tool_calls: Any = _UNSET,
        metadata: Any = _UNSET,
        model: Any = _UNSET,
        parallel_tool_calls: Any = _UNSET,
        previous_response_id: Any = _UNSET,
        prompt: Any = _UNSET,
        prompt_cache_key: Any = _UNSET,
        prompt_cache_retention: Any = _UNSET,
        reasoning: Any = _UNSET,
        safety_identifier: Any = _UNSET,
        service_tier: Any = _UNSET,
        store: Any = _UNSET,
        stream: Any = _UNSET,
        stream_options: Any = _UNSET,
        temperature: Any = _UNSET,
        text: Any = _UNSET,
        tool_choice: Any = _UNSET,
        tools: Any = _UNSET,
        top_logprobs: Any = _UNSET,
        top_p: Any = _UNSET,
        truncation: Any = _UNSET,
        user: Any = _UNSET,
        extra_headers: Any = None,
        extra_query: Any = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> Response | Iterator[ResponseStreamEvent]:
        _reject_backend_unsupported(
            background=background,
            context_management=context_management,
            conversation=conversation,
            max_output_tokens=max_output_tokens,
            max_tool_calls=max_tool_calls,
            metadata=metadata,
            previous_response_id=previous_response_id,
            prompt=prompt,
            prompt_cache_retention=prompt_cache_retention,
            safety_identifier=safety_identifier,
            stream_options=stream_options,
            temperature=temperature,
            top_logprobs=top_logprobs,
            top_p=top_p,
            truncation=truncation,
            user=user,
            extra_body=extra_body,
        )

        if _is_given(store) and store is not False:
            raise NotImplementedError("The Codex backend only accepts store=False.")

        request = _ResponsesCreateRequest.from_openai_params(
            client_defaults=self._client._defaults,
            input=input,
            include=include,
            instructions=instructions,
            model=model,
            parallel_tool_calls=parallel_tool_calls,
            prompt_cache_key=prompt_cache_key,
            reasoning=reasoning,
            service_tier=service_tier,
            text=text,
            tool_choice=tool_choice,
            tools=tools,
        )
        response = self._client._post("/responses", body=request.payload, stream=True)
        events = stream_response_events(response)
        stream_enabled = bool(stream) if _is_given(stream) else False

        if stream_enabled:
            return events
        return _collect_response(events, request=request)

    def compact(
        self,
        *,
        input: list[dict[str, Any]],
        model: Any = _UNSET,
        instructions: Any = _UNSET,
    ) -> CompactedResponse:
        payload = {
            "model": _default(model, self._client._defaults["model"]),
            "instructions": _default(instructions, self._client._defaults["instructions"]) or "",
            "input": [_normalize_input_item(item) for item in input],
            "tools": [],
            "parallel_tool_calls": False,
        }
        data = self._client._post("/responses/compact", body=payload).json()
        return CompactedResponse(id=data.get("id", ""), output=data.get("output", []))


class _ResponsesCreateRequest(CodexBaseModel):
    model: str
    instructions: Optional[str]
    input: list[dict[str, Any]]
    include: list[str]
    parallel_tool_calls: bool
    prompt_cache_key: Optional[str]
    reasoning: Any
    service_tier: Optional[str]
    text: Any
    tool_choice: Any
    tools: list[dict[str, Any]]
    payload: dict[str, Any]

    @classmethod
    def from_openai_params(
        cls,
        *,
        client_defaults: dict[str, Any],
        **params: Any,
    ) -> "_ResponsesCreateRequest":
        input_items = _normalize_input(params["input"])
        tools = _normalize_tools(params["tools"])
        include = (
            []
            if not _is_given(params["include"]) or params["include"] is None
            else list(params["include"])
        )
        reasoning = None if not _is_given(params["reasoning"]) else params["reasoning"]
        text = None if not _is_given(params["text"]) else params["text"]
        tool_choice = "auto" if not _is_given(params["tool_choice"]) else params["tool_choice"]
        parallel_tool_calls = bool(_default(params["parallel_tool_calls"], False)) if tools else False

        payload = {
            "model": _default(params["model"], client_defaults["model"]),
            "instructions": _default(params["instructions"], client_defaults["instructions"]) or "",
            "input": input_items,
            "tools": tools,
            "tool_choice": tool_choice if tools else "none",
            "parallel_tool_calls": parallel_tool_calls,
            "store": False,
            "stream": True,
            "include": include,
        }

        prompt_cache_key = (
            None if not _is_given(params["prompt_cache_key"]) else params["prompt_cache_key"]
        )
        service_tier = None if not _is_given(params["service_tier"]) else params["service_tier"]
        if prompt_cache_key is not None:
            payload["prompt_cache_key"] = prompt_cache_key
        if service_tier is not None:
            payload["service_tier"] = service_tier
        if reasoning is not None:
            payload["reasoning"] = _normalize_reasoning(reasoning)
        if text is not None:
            payload["text"] = _normalize_text(text)

        return cls(
            model=payload["model"],
            instructions=payload["instructions"],
            input=input_items,
            include=include,
            parallel_tool_calls=payload["parallel_tool_calls"],
            prompt_cache_key=prompt_cache_key,
            reasoning=payload.get("reasoning"),
            service_tier=service_tier,
            text=payload.get("text"),
            tool_choice=payload["tool_choice"],
            tools=tools,
            payload=payload,
        )


def _collect_response(
    events: Iterable[ResponseStreamEvent],
    *,
    request: _ResponsesCreateRequest,
) -> Response:
    output: list[dict[str, Any]] = []
    text_parts: list[str] = []
    completed: Optional[dict[str, Any]] = None

    for event in events:
        if event.type in {"response.output_text.delta", "response.content_part.delta"}:
            text_parts.append(_event_delta_text(event))
        elif event.type == "response.output_item.done" and isinstance(getattr(event, "item", None), dict):
            output.append(event.item)
        elif event.type == "response.completed":
            completed = _event_response_dict(event)
        elif event.type in {"response.failed", "error"}:
            raise RuntimeError(_event_error_message(event))

    if not any(item.get("type") == "message" for item in output) and text_parts:
        output.append({
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "".join(text_parts)}],
        })

    raw = completed or {}
    return Response(
        id=raw.get("id", ""),
        created_at=raw.get("created_at", time.time()),
        completed_at=raw.get("completed_at", time.time()),
        error=raw.get("error"),
        incomplete_details=raw.get("incomplete_details"),
        instructions=raw.get("instructions", request.instructions),
        model=raw.get("model", request.model),
        output=raw.get("output") or output,
        parallel_tool_calls=raw.get("parallel_tool_calls", request.parallel_tool_calls),
        tool_choice=raw.get("tool_choice", request.tool_choice),
        tools=raw.get("tools", request.tools),
        prompt_cache_key=raw.get("prompt_cache_key", request.prompt_cache_key),
        prompt_cache_retention=raw.get("prompt_cache_retention"),
        reasoning=raw.get("reasoning", request.reasoning),
        service_tier=raw.get("service_tier", request.service_tier),
        status=raw.get("status", "completed"),
        text=raw.get("text", request.text),
        usage=_usage_from_backend(raw.get("usage")),
    )


def _event_delta_text(event: ResponseStreamEvent) -> str:
    delta = getattr(event, "delta", None)
    if isinstance(delta, str):
        return delta
    if isinstance(delta, dict):
        return delta.get("text", "")
    return ""


def _event_response_dict(event: ResponseStreamEvent) -> dict[str, Any]:
    response = getattr(event, "response", None)
    if isinstance(response, BaseModel):
        return response.model_dump()
    return response if isinstance(response, dict) else {}


def _event_error_message(event: ResponseStreamEvent) -> str:
    response = _event_response_dict(event)
    error = response.get("error") or getattr(event, "error", None) or {}
    if isinstance(error, dict):
        return error.get("message", "Response failed")
    return str(error)


def _normalize_input(input_value: Any) -> list[dict[str, Any]]:
    if not _is_given(input_value) or input_value is None:
        return []
    if isinstance(input_value, str):
        return [_message("user", [{"type": "input_text", "text": input_value}])]
    if isinstance(input_value, list):
        return [_normalize_input_item(item) for item in input_value]
    return [_normalize_input_item(input_value)]


def _normalize_input_item(item: Any) -> dict[str, Any]:
    raw = dict(item)
    if raw.get("type") and raw.get("type") != "message":
        return raw
    if "role" not in raw:
        return raw

    role = raw["role"]
    content = raw.get("content", [])
    if isinstance(content, str):
        content_type = "output_text" if role == "assistant" else "input_text"
        content = [{"type": content_type, "text": content}]
    elif isinstance(content, list):
        content = [
            {"type": "input_text", "text": part} if isinstance(part, str) else part
            for part in content
        ]
    return _message(role, content)


def _message(role: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "message", "role": role, "content": content}


def _normalize_tools(tools: Any) -> list[dict[str, Any]]:
    if not _is_given(tools) or tools is None:
        return []
    normalized = []
    for tool in tools:
        item = dict(tool)
        if item.get("type") == "web_search":
            item["type"] = "web_search_preview"
        normalized.append(item)
    return normalized


def _normalize_reasoning(reasoning: Any) -> dict[str, Any]:
    if isinstance(reasoning, dict):
        return {key: value for key, value in reasoning.items() if value is not None}
    return {
        key: value
        for key in ("effort", "summary")
        if (value := getattr(reasoning, key, None)) is not None
    }


def _normalize_text(text: Any) -> dict[str, Any]:
    text_dict = dict(text)
    fmt = text_dict.get("format")
    if isinstance(fmt, dict) and fmt.get("type") == "json_schema":
        schema = fmt.get("schema")
        if schema is not None and "title" not in schema and fmt.get("name"):
            schema = {**schema, "title": fmt["name"]}
        text_dict["format"] = {
            "type": "json_schema",
            "name": fmt.get("name") or (schema or {}).get("title", "output"),
            "schema": schema,
            "strict": fmt.get("strict", True),
        }
    return text_dict


def _usage_from_backend(raw: Any) -> ResponseUsage:
    raw = raw or {}
    return ResponseUsage(
        input_tokens=raw.get("input_tokens", 0),
        output_tokens=raw.get("output_tokens", 0),
        total_tokens=raw.get("total_tokens", 0),
        input_tokens_details=TokenDetails(
            cached_tokens=(raw.get("input_tokens_details") or {}).get("cached_tokens", 0),
        ),
        output_tokens_details=TokenDetails(
            reasoning_tokens=(raw.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
        ),
    )
