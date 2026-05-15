"""Internal builders and collectors for the Codex Responses resource."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any, Optional

from pydantic import BaseModel

from .._models import (
    CodexBaseModel,
    Response,
    ResponseFormatJsonSchema,
    ResponseStreamEvent,
    ResponseUsage,
    TokenDetails,
)
from .._utils import _UNSET, _default, _is_given, _jsonable


class ResponsesCreateRequest(CodexBaseModel):
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
    ) -> "ResponsesCreateRequest":
        input_items = normalize_input(params["input"])
        tools = normalize_tools(params["tools"])
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
            payload["reasoning"] = normalize_reasoning(reasoning)
        if text is not None:
            payload["text"] = normalize_text(text)

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


def collect_response(
    events: Iterable[ResponseStreamEvent],
    *,
    request: ResponsesCreateRequest,
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


def normalize_input(input_value: Any) -> list[dict[str, Any]]:
    if not _is_given(input_value) or input_value is None:
        return []
    if isinstance(input_value, str):
        return [_message("user", [{"type": "input_text", "text": input_value}])]
    if isinstance(input_value, list):
        return [normalize_input_item(item) for item in input_value]
    return [normalize_input_item(input_value)]


def normalize_input_item(item: Any) -> dict[str, Any]:
    raw = _as_dict(item)
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


def normalize_tools(tools: Any) -> list[dict[str, Any]]:
    if not _is_given(tools) or tools is None:
        return []
    return [_as_dict(tool) for tool in tools]


def normalize_reasoning(reasoning: Any) -> dict[str, Any]:
    reasoning = _jsonable(reasoning)
    if isinstance(reasoning, dict):
        return {key: value for key, value in reasoning.items() if value is not None}
    return {
        key: value
        for key in ("effort", "summary")
        if (value := getattr(reasoning, key, None)) is not None
    }


def normalize_text(text: Any) -> dict[str, Any]:
    text_dict = _as_dict(text)
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


def merge_text_format(text: Any, fmt: ResponseFormatJsonSchema) -> dict[str, Any]:
    if not _is_given(text) or text is None:
        text_dict: dict[str, Any] = {}
    else:
        text_dict = normalize_text(text)
    if text_dict.get("format") is not None:
        raise TypeError("Cannot pass both text_format and text.format.")
    text_dict["format"] = fmt.model_dump(mode="json", by_alias=True, exclude_none=True)
    return text_dict


def pydantic_to_format(model_class: type[Any]) -> ResponseFormatJsonSchema:
    try:
        schema = model_class.model_json_schema()
        model_class.model_validate_json
    except AttributeError:
        raise TypeError("responses.parse() requires a Pydantic BaseModel class.") from None

    schema = _ensure_strict_schema(schema)
    return ResponseFormatJsonSchema(
        name=getattr(model_class, "__name__", "output"),
        schema=schema,
        strict=True,
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


def _message(role: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "message", "role": role, "content": content}


def _as_dict(value: Any) -> dict[str, Any]:
    value = _jsonable(value)
    if isinstance(value, dict):
        return value
    return dict(value)


def _ensure_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    schema = dict(schema)
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
        props = schema.get("properties")
        if isinstance(props, dict):
            schema["properties"] = {
                key: _ensure_strict_schema(value) if isinstance(value, dict) else value
                for key, value in props.items()
            }
    items = schema.get("items")
    if isinstance(items, dict):
        schema["items"] = _ensure_strict_schema(items)
    for key in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(key)
        if isinstance(variants, list):
            schema[key] = [
                _ensure_strict_schema(value) if isinstance(value, dict) else value
                for value in variants
            ]
    defs = schema.get("$defs")
    if isinstance(defs, dict):
        schema["$defs"] = {
            key: _ensure_strict_schema(value) if isinstance(value, dict) else value
            for key, value in defs.items()
        }
    return schema


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
