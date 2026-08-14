"""Responses resource."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any, TYPE_CHECKING

from .._models import CompactedResponse, ParsedResponse, Response, ResponseStreamEvent
from .._streaming import stream_response_events
from .._utils import _UNSET, _default, _is_given, _jsonable, _reject_backend_unsupported
from ._responses_payloads import (
    ResponsesCreateRequest,
    _usage_from_backend,
    collect_response,
    merge_text_format,
    normalize_input_item,
    normalize_reasoning,
    normalize_text,
    normalize_tools,
    pydantic_to_format,
)

if TYPE_CHECKING:
    from .._client import CodexClient


class Responses:
    def __init__(self, client: CodexClient) -> None:
        from .responses_websocket import ResponsesWebSocket

        self._client = client
        self.websocket = ResponsesWebSocket(client)

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
        moderation: Any = _UNSET,
        parallel_tool_calls: Any = _UNSET,
        previous_response_id: Any = _UNSET,
        prompt: Any = _UNSET,
        prompt_cache_key: Any = _UNSET,
        prompt_cache_options: Any = _UNSET,
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
            moderation=moderation,
            prompt_cache_options=prompt_cache_options,
        )

        if _is_given(store) and store is not False:
            raise NotImplementedError("The Codex backend only accepts store=False.")

        request = ResponsesCreateRequest.from_openai_params(
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
        payload = dict(request.payload)
        if extra_body:
            payload.update(_jsonable(extra_body))
        response = self._client._post(
            "/responses",
            body=payload,
            stream=True,
            headers=extra_headers,
            params=extra_query,
            timeout=timeout,
        )
        events = stream_response_events(response)
        stream_enabled = bool(stream) if _is_given(stream) else False

        if stream_enabled:
            return events
        return collect_response(events, request=request)

    def parse(
        self,
        *,
        text_format: Any = _UNSET,
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
        moderation: Any = _UNSET,
        parallel_tool_calls: Any = _UNSET,
        previous_response_id: Any = _UNSET,
        prompt: Any = _UNSET,
        prompt_cache_key: Any = _UNSET,
        prompt_cache_options: Any = _UNSET,
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
        verbosity: Any = _UNSET,
        extra_headers: Any = None,
        extra_query: Any = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> ParsedResponse[Any]:
        if _is_given(stream) and stream not in {None, False}:
            raise NotImplementedError("responses.parse() does not support streaming responses.")
        if _is_given(verbosity) and verbosity is not None:
            if _is_given(text) and text is not None:
                text = {**normalize_text(text), "verbosity": verbosity}
            else:
                text = {"verbosity": verbosity}
        fmt = pydantic_to_format(text_format) if _is_given(text_format) else None
        response = self.create(
            background=background,
            context_management=context_management,
            conversation=conversation,
            include=include,
            input=input,
            instructions=instructions,
            max_output_tokens=max_output_tokens,
            max_tool_calls=max_tool_calls,
            metadata=metadata,
            model=model,
            moderation=moderation,
            parallel_tool_calls=parallel_tool_calls,
            previous_response_id=previous_response_id,
            prompt=prompt,
            prompt_cache_key=prompt_cache_key,
            prompt_cache_options=prompt_cache_options,
            prompt_cache_retention=prompt_cache_retention,
            reasoning=reasoning,
            safety_identifier=safety_identifier,
            service_tier=service_tier,
            store=store,
            stream=False,
            stream_options=stream_options,
            temperature=temperature,
            text=merge_text_format(text, fmt) if fmt is not None else text,
            tool_choice=tool_choice,
            tools=tools,
            top_logprobs=top_logprobs,
            top_p=top_p,
            truncation=truncation,
            user=user,
            extra_headers=extra_headers,
            extra_query=extra_query,
            extra_body=extra_body,
            timeout=timeout,
        )
        if not isinstance(response, Response):
            raise TypeError("responses.parse() expected a non-streaming Response")
        output_parsed = (
            text_format.model_validate_json(response.output_text)
            if _is_given(text_format)
            else None
        )
        return ParsedResponse(response=response, output_parsed=output_parsed)

    def compact(
        self,
        *,
        input: Any = _UNSET,
        model: Any = _UNSET,
        instructions: Any = _UNSET,
        tools: Any = _UNSET,
        parallel_tool_calls: Any = _UNSET,
        reasoning: Any = _UNSET,
        service_tier: Any = _UNSET,
        prompt_cache_key: Any = _UNSET,
        previous_response_id: Any = _UNSET,
        prompt_cache_options: Any = _UNSET,
        prompt_cache_retention: Any = _UNSET,
        text: Any = _UNSET,
        extra_headers: Any = None,
        extra_query: Any = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> CompactedResponse:
        _reject_backend_unsupported(
            previous_response_id=previous_response_id,
            prompt_cache_options=prompt_cache_options,
            prompt_cache_retention=prompt_cache_retention,
        )
        normalized_tools = normalize_tools(tools)
        normalized_input = (
            []
            if not _is_given(input) or input is None
            else [normalize_input_item(item) for item in input]
        )
        normalized_input.append({"type": "compaction_trigger"})

        installation_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        window_id = f"{thread_id}:1"
        turn_metadata = json.dumps(
            {
                "installation_id": installation_id,
                "session_id": session_id,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "window_id": window_id,
                "request_kind": "compaction",
                "compaction": {
                    "trigger": "manual",
                    "reason": "user_requested",
                    "implementation": "responses_compaction_v2",
                    "phase": "standalone_turn",
                    "strategy": "memento",
                },
            },
            separators=(",", ":"),
        )
        payload = {
            "model": _default(model, self._client._defaults["model"]),
            "instructions": _default(instructions, self._client._defaults["instructions"]) or "",
            "input": normalized_input,
            "tools": normalized_tools,
            "tool_choice": "auto" if normalized_tools else "none",
            "parallel_tool_calls": (
                bool(_default(parallel_tool_calls, False)) if normalized_tools else False
            ),
            "store": False,
            "stream": True,
            "include": [],
            "client_metadata": {
                "x-codex-installation-id": installation_id,
                "session_id": session_id,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "x-codex-window-id": window_id,
                "x-codex-turn-metadata": turn_metadata,
            },
        }
        if _is_given(reasoning) and reasoning is not None:
            payload["reasoning"] = normalize_reasoning(reasoning)
        if _is_given(service_tier) and service_tier is not None:
            payload["service_tier"] = service_tier
        if _is_given(prompt_cache_key) and prompt_cache_key is not None:
            payload["prompt_cache_key"] = prompt_cache_key
        if _is_given(text) and text is not None:
            payload["text"] = normalize_text(text)
        if extra_body:
            payload.update(_jsonable(extra_body))
        if not isinstance(payload.get("input"), list):
            raise TypeError("responses.compact() extra_body.input must be a list")
        if not payload["input"] or payload["input"][-1].get("type") != "compaction_trigger":
            payload["input"].append({"type": "compaction_trigger"})

        headers = dict(extra_headers or {})
        beta_features = [
            value.strip()
            for value in headers.get("x-codex-beta-features", "").split(",")
            if value.strip()
        ]
        if "remote_compaction_v2" not in beta_features:
            beta_features.append("remote_compaction_v2")
        headers["x-codex-beta-features"] = ",".join(beta_features)
        headers.setdefault("x-codex-window-id", window_id)
        headers.setdefault("x-codex-turn-metadata", turn_metadata)

        response = self._client._post(
            "/responses",
            body=payload,
            stream=True,
            headers=headers,
            params=extra_query,
            timeout=timeout,
        )
        output: list[Any] = []
        completed: dict[str, Any] = {}
        for event in stream_response_events(response):
            if event.type == "response.output_item.done":
                item = getattr(event, "item", None)
                if isinstance(item, dict):
                    output.append(item)
            elif event.type == "response.completed":
                completed_value = getattr(event, "response", None) or {}
                completed = (
                    completed_value
                    if isinstance(completed_value, dict)
                    else completed_value.model_dump()
                )
            elif event.type in {"response.failed", "error"}:
                raise RuntimeError("Remote compaction v2 failed")

        compaction_items = [item for item in output if item.get("type") == "compaction"]
        if len(compaction_items) != 1:
            raise RuntimeError(
                "Remote compaction v2 expected one compaction output item, "
                f"received {len(compaction_items)} from {len(output)} output items"
            )
        return CompactedResponse(
            id=completed.get("id", ""),
            output=output,
            usage=_usage_from_backend(completed.get("usage")),
        )
