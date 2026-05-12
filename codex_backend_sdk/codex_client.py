"""OpenAI-shaped Python client for the ChatGPT Codex backend."""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Iterable, Iterator
from typing import Any, Literal, Optional

import requests
from pydantic import BaseModel, ConfigDict, Field

from .storage import TokenStore, load_tokens, save_tokens, token_needs_refresh

BASE_URL = "https://chatgpt.com/backend-api/codex"
WHAM_BASE_URL = "https://chatgpt.com/backend-api"
CLIENT_VERSION = "0.2.0"
ORIGINATOR = "codex_cli_rs"

ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh"]
ReasoningSummary = Literal["concise", "detailed", "auto"]
Verbosity = Literal["low", "medium", "high"]
ServiceTier = Literal["flex", "priority"]

_UNSET: Any = object()

__all__ = [
    "CodexBackendUnsupportedParameterError",
    "CodexBaseModel",
    "CodexClient",
    "CompactedResponse",
    "Model",
    "OpenAI",
    "ReasoningEffort",
    "ReasoningSummary",
    "Response",
    "ResponseStreamEvent",
    "ResponseUsage",
    "RealtimeCallResponse",
    "ServiceTier",
    "SyncPage",
    "TokenDetails",
    "Verbosity",
    "image_b64",
    "image_url",
]


class CodexBackendUnsupportedParameterError(NotImplementedError):
    """Raised when an official OpenAI parameter is absent from the Codex backend."""


def image_url(url: str) -> dict[str, str]:
    return {"type": "input_image", "image_url": url}


def image_b64(data: str, media_type: str = "image/jpeg") -> dict[str, str]:
    return {"type": "input_image", "image_url": f"data:{media_type};base64,{data}"}


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
    reasoning_tokens: int = 0


class ResponseUsage(CodexBaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_tokens_details: TokenDetails = Field(default_factory=TokenDetails)
    output_tokens_details: TokenDetails = Field(default_factory=TokenDetails)


class Response(CodexBaseModel):
    id: str
    created_at: float = Field(default_factory=time.time)
    error: Optional[dict[str, Any]] = None
    incomplete_details: Optional[dict[str, Any]] = None
    instructions: Any = None
    metadata: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    object: Literal["response"] = "response"
    output: list[dict[str, Any]] = Field(default_factory=list)
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

    @property
    def output_text(self) -> str:
        texts: list[str] = []
        for output in self.output:
            if output.get("type") == "message":
                for content in output.get("content", []):
                    if content.get("type") == "output_text":
                        texts.append(content.get("text", ""))
        return "".join(texts)


class ResponseStreamEvent(CodexBaseModel):
    type: str


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


class CompactedResponse(CodexBaseModel):
    id: str
    object: str = "response.compacted"
    output: list[dict[str, Any]] = Field(default_factory=list)


class RealtimeCallResponse:
    """Binary SDP response returned by ``client.realtime.calls.create``.

    This intentionally mirrors the useful parts of openai-python's
    ``HttpxBinaryResponseContent`` while keeping ``requests`` as the local
    transport.
    """

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


class CodexClient:
    """Client entrypoint intentionally shaped like ``openai.OpenAI``.

    The transport targets ``chatgpt.com/backend-api/codex`` and authenticates via
    ChatGPT OAuth tokens, but exposed resources follow openai-python where the
    backend overlaps with the official API.
    """

    def __init__(
        self,
        *,
        store: Optional[TokenStore] = None,
        model: str = "gpt-5.4",
        instructions: Optional[str] = None,
        timeout: float = 120,
    ) -> None:
        self._store = store
        self._timeout = timeout
        self._session = requests.Session()
        self._defaults = {
            "model": model,
            "instructions": instructions,
        }
        if store is not None:
            self._session.headers.update(self._auth_headers())
        self.responses = Responses(self)
        self.models = Models(self)
        self.realtime = Realtime(self)
        self.codex = CodexResources(self)

    def authenticate(self, *, request_api_key: bool = True) -> "CodexClient":
        from .oauth import refresh_access_token, run_oauth_flow

        def refresh(store: TokenStore) -> Optional[TokenStore]:
            try:
                data = refresh_access_token(store.refresh_token)
                refreshed = TokenStore.from_exchange(
                    access_token=data.get("access_token", store.access_token),
                    refresh_token=data.get("refresh_token", store.refresh_token),
                    id_token=data.get("id_token", store.id_token_raw),
                    api_key=store.openai_api_key,
                )
                save_tokens(refreshed)
                return refreshed
            except Exception:
                return None

        store = load_tokens()
        if store is not None:
            if token_needs_refresh(store) and store.refresh_token:
                store = refresh(store) or store
            if not token_needs_refresh(store) or self._probe_auth(store):
                self._set_store(store)
                return self

        self._set_store(run_oauth_flow(request_api_key=request_api_key))
        return self

    def _set_store(self, store: TokenStore) -> None:
        self._store = store
        self._session.headers.update(self._auth_headers())

    def _ensure_auth(self) -> None:
        if self._store is None or not self._store.account_id:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

    def _auth_headers(self) -> dict[str, str]:
        if self._store is None:
            return {}
        headers = {
            "Authorization": f"Bearer {self._store.access_token}",
            "originator": ORIGINATOR,
            "OpenAI-Beta": "responses=experimental",
        }
        if self._store.account_id:
            headers["ChatGPT-Account-ID"] = self._store.account_id
        return headers

    def _probe_auth(self, store: TokenStore) -> bool:
        try:
            response = requests.get(
                f"{WHAM_BASE_URL}/wham/usage",
                headers={
                    "Authorization": f"Bearer {store.access_token}",
                    "originator": ORIGINATOR,
                    **({"ChatGPT-Account-ID": store.account_id} if store.account_id else {}),
                },
                timeout=15,
            )
            return response.ok
        except Exception:
            return False

    def _get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._ensure_auth()
        response = self._session.get(f"{BASE_URL}{path}", params=params, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, *, body: dict[str, Any], stream: bool = False) -> requests.Response:
        self._ensure_auth()
        response = self._session.post(
            f"{BASE_URL}{path}",
            json=body,
            headers={"Accept": "text/event-stream"} if stream else None,
            stream=stream,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response

    def _post_raw(
        self,
        path: str,
        *,
        content: Optional[bytes] = None,
        files: Any = None,
        data: Any = None,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        timeout: Any = _UNSET,
    ) -> requests.Response:
        self._ensure_auth()
        response = self._session.post(
            f"{BASE_URL}{path}",
            data=content if files is None else data,
            files=files,
            headers=headers,
            params=params,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        response.raise_for_status()
        return response

    def _get_wham(self, path: str) -> dict[str, Any]:
        self._ensure_auth()
        response = self._session.get(f"{WHAM_BASE_URL}{path}", timeout=30)
        response.raise_for_status()
        return response.json()

    def realtime_websocket_url(self, *, model: str) -> str:
        """Return the official OpenAI Realtime WebSocket URL for Codex plugins."""
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")
        return "wss://api.openai.com/v1/realtime?" + urllib.parse.urlencode({"model": model})

    def realtime_websocket_headers(self, *, session_id: Optional[str] = None) -> dict[str, str]:
        """Return headers for an OpenAI Realtime WebSocket connection.

        Codex OAuth can mint and persist an OpenAI API key in ``~/.codex/auth.json``.
        The realtime plugin in codex-agent uses that key for official Realtime
        WebSocket sessions while sharing the Codex authentication lifecycle.
        """
        self._ensure_auth()
        if self._store is None or not self._store.openai_api_key:
            raise RuntimeError(
                "Realtime WebSocket requires an OpenAI API key. "
                "Call authenticate(request_api_key=True) to persist one."
            )
        return {
            "Authorization": f"Bearer {self._store.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }


OpenAI = CodexClient


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
        events = _stream_response_events(response)
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


class Models:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        *,
        extra_headers: Any = None,
        extra_query: Any = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> SyncPage:
        data = self._client._get("/models", params={"client_version": CLIENT_VERSION})
        models = [_model_from_backend(item) for item in data.get("models", [])]
        models.sort(key=lambda model: getattr(model, "priority", 0), reverse=True)
        return SyncPage(data=models)

    def retrieve(
        self,
        model: str,
        *,
        extra_headers: Any = None,
        extra_query: Any = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> Model:
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")
        for candidate in self.list():
            if candidate.id == model:
                return candidate
        raise LookupError(f"Model not found: {model}")


class Realtime:
    """Realtime resources matching the official OpenAI SDK surface where present."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.calls = RealtimeCalls(client)


class RealtimeCalls:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create(
        self,
        *,
        sdp: str,
        session: Any = _UNSET,
        extra_headers: Optional[dict[str, str]] = None,
        extra_query: Optional[dict[str, Any]] = None,
        extra_body: Any = None,
        timeout: Any = _UNSET,
    ) -> RealtimeCallResponse:
        if not sdp:
            raise ValueError(f"Expected a non-empty value for `sdp` but received {sdp!r}")

        if not _is_given(session):
            response = self._client._post_raw(
                "/realtime/calls",
                content=sdp.encode("utf-8"),
                headers={
                    "Accept": "application/sdp",
                    "Content-Type": "application/sdp",
                    **(extra_headers or {}),
                },
                params=extra_query,
                timeout=timeout,
            )
            return RealtimeCallResponse(response)

        files = [
            ("sdp", (None, sdp.encode("utf-8"), "application/sdp")),
            (
                "session",
                (None, json.dumps(_jsonable(session)).encode("utf-8"), "application/json"),
            ),
        ]
        response = self._client._post_raw(
            "/realtime/calls",
            files=files,
            data=extra_body,
            headers={"Accept": "application/sdp", **(extra_headers or {})},
            params=extra_query,
            timeout=timeout,
        )
        return RealtimeCallResponse(response)


class CodexResources:
    """Codex-only endpoints that do not exist on the official OpenAI API."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def usage(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/usage")


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
        parallel_tool_calls = (
            bool(_default(params["parallel_tool_calls"], False)) if tools else False
        )

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


def _stream_response_events(response: requests.Response) -> Iterator[ResponseStreamEvent]:
    for payload in _iter_sse_payloads(response):
        yield ResponseStreamEvent.model_validate(payload)


def _iter_sse_payloads(response: requests.Response) -> Iterator[dict[str, Any]]:
    event_name: Optional[str] = None
    data_lines: list[str] = []

    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line is None:
            continue
        if line == "":
            if data_lines:
                payload = _loads_sse_data(data_lines)
                if payload is not None:
                    payload.setdefault("type", event_name or "message")
                    yield payload
            event_name = None
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())


def _loads_sse_data(data_lines: list[str]) -> Optional[dict[str, Any]]:
    data = "\n".join(data_lines)
    if data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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
        elif event.type == "response.output_item.done" and isinstance(
            getattr(event, "item", None),
            dict,
        ):
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


def _model_from_backend(raw: dict[str, Any]) -> Model:
    return Model(
        id=raw.get("slug", ""),
        created=0,
        owned_by="openai",
        display_name=raw.get("display_name", raw.get("slug", "")),
        description=raw.get("description", ""),
        context_window=raw.get("context_window"),
        supported_in_api=raw.get("supported_in_api", False),
        priority=raw.get("priority", 0),
        supports_reasoning_summaries=raw.get("supports_reasoning_summaries", False),
        support_verbosity=raw.get("support_verbosity", False),
        default_verbosity=raw.get("default_verbosity"),
        default_reasoning_level=raw.get("default_reasoning_level"),
        supported_reasoning_levels=raw.get("supported_reasoning_levels", []),
        auto_compact_token_limit=raw.get("auto_compact_token_limit"),
        prefer_websockets=raw.get("prefer_websockets", False),
        input_modalities=raw.get("input_modalities", []),
        available_in_plans=raw.get("available_in_plans", []),
        base_instructions=raw.get("base_instructions", ""),
        raw=raw,
    )


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


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
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
