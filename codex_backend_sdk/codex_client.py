"""
Custom SDK for the ChatGPT Codex backend API.

Endpoint base: https://chatgpt.com/backend-api/codex
Auth:          Bearer <access_token> + ChatGPT-Account-ID header

Reverse-engineered from codex-rs source:
  - model-provider-info/src/lib.rs        → base URL selection
  - codex-api/src/endpoint/models.rs      → GET /models
  - codex-api/src/endpoint/responses.rs   → POST /responses (SSE)
  - codex-api/src/endpoint/compact.rs     → POST /responses/compact
  - codex-api/src/endpoint/memories.rs    → POST /memories/trace_summarize
  - codex-api/src/common.rs               → full request schemas

Confirmed live behaviour (2026-04-20):
  - /responses          : stream=True ONLY; tool_choice required
  - /responses/compact  : sync POST; compaction_summary reusable as input
  - /memories/…         : 403 on Plus plan (Pro/Enterprise only)
  - /realtime/calls     : 404 (not deployed)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Generator, Iterator, Literal, Optional, Union

import requests

from .storage import TokenStore, load_tokens, save_tokens, token_needs_refresh

BASE_URL = "https://chatgpt.com/backend-api/codex"
CLIENT_VERSION = "0.1.0"
ORIGINATOR = "codex_cli_rs"

ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh"]
ReasoningSummary = Literal["concise", "detailed", "auto"]
Verbosity = Literal["low", "medium", "high"]
ServiceTier = Literal["flex", "fast"]

# Type for user_message: plain string, or a list of content blocks (text + images)
MessageContent = Union[str, list[dict]]

# Sentinel used as default for per-call parameters so we can distinguish
# "caller did not pass this" from "caller explicitly passed None".
_UNSET: Any = object()


# ---------------------------------------------------------------------------
# Module-level helpers for image content blocks
# ---------------------------------------------------------------------------

def image_url(url: str) -> dict:
    """Content block for an image at the given URL (for use in user_message lists)."""
    return {"type": "input_image", "image_url": url}


def image_b64(data: str, media_type: str = "image/jpeg") -> dict:
    """Content block for a base64-encoded image (for use in user_message lists)."""
    return {"type": "input_image", "image_url": f"data:{media_type};base64,{data}"}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ReasoningLevel:
    effort: str
    description: str


@dataclass
class ModelInfo:
    slug: str
    display_name: str
    description: str
    context_window: Optional[int] = None
    supported_in_api: bool = False
    priority: int = 0
    supports_reasoning_summaries: bool = False
    support_verbosity: bool = False
    default_verbosity: Optional[str] = None
    default_reasoning_level: Optional[str] = None
    supported_reasoning_levels: list[ReasoningLevel] = field(default_factory=list)
    auto_compact_token_limit: Optional[int] = None
    prefer_websockets: bool = False
    input_modalities: list[str] = field(default_factory=list)
    available_in_plans: list[str] = field(default_factory=list)
    base_instructions: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ModelInfo":
        levels = [
            ReasoningLevel(effort=r.get("effort", ""), description=r.get("description", ""))
            for r in d.get("supported_reasoning_levels", [])
        ]
        return cls(
            slug=d.get("slug", ""),
            display_name=d.get("display_name", d.get("slug", "")),
            description=d.get("description", ""),
            context_window=d.get("context_window"),
            supported_in_api=d.get("supported_in_api", False),
            priority=d.get("priority", 0),
            supports_reasoning_summaries=d.get("supports_reasoning_summaries", False),
            support_verbosity=d.get("support_verbosity", False),
            default_verbosity=d.get("default_verbosity"),
            default_reasoning_level=d.get("default_reasoning_level"),
            supported_reasoning_levels=levels,
            auto_compact_token_limit=d.get("auto_compact_token_limit"),
            prefer_websockets=d.get("prefer_websockets", False),
            input_modalities=d.get("input_modalities", []),
            available_in_plans=d.get("available_in_plans", []),
            base_instructions=d.get("base_instructions", ""),
            raw=d,
        )


@dataclass
class TextDelta:
    """Incremental text chunk from a streaming response."""
    text: str


@dataclass
class ReasoningDelta:
    """Reasoning content delivered when include_reasoning=True."""
    text: str
    summary_index: int = 0


@dataclass
class ToolCall:
    """
    Emitted when the model requests a function call.

    Typical tool loop:

        history = []
        for event in client.stream("What's the weather in Paris?", tools=tools):
            if isinstance(event, TextDelta):
                print(event.text, end="")
            elif isinstance(event, ToolCall):
                result = dispatch(event.name, event.parsed_arguments())
                history.append(event.as_history_item())
                history.append(event.to_tool_result(json.dumps(result)))

        # Continue — model sees the tool result and responds
        for event in client.stream(None, conversation_history=history, tools=tools):
            ...
    """
    call_id: str
    name: str
    arguments: str  # JSON string, same convention as the official SDK
    raw: dict = field(default_factory=dict)

    def parsed_arguments(self) -> dict:
        """Deserialize the arguments JSON string to a dict."""
        return json.loads(self.arguments)

    def as_history_item(self) -> dict:
        """The raw function_call dict to append to conversation_history."""
        return self.raw

    def to_tool_result(self, output: str) -> dict:
        """
        Build a function_call_output item for conversation_history.

            history.append(call.as_history_item())
            history.append(call.to_tool_result(json.dumps(result)))
        """
        return {
            "type": "function_call_output",
            "call_id": self.call_id,
            "output": output,
        }


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class ResponseCompleted:
    """Final event emitted when a streaming response finishes successfully."""
    response_id: str
    usage: TokenUsage = field(default_factory=TokenUsage)

    @property
    def input_tokens(self) -> int:
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.usage.output_tokens

    @property
    def total_tokens(self) -> int:
        return self.usage.total_tokens


@dataclass
class ResponseFailed:
    """Emitted on response.failed SSE events."""
    code: str
    message: str


@dataclass
class OutputItem:
    """A completed output item that is not a function call (message, compaction_summary, …)."""
    item_type: str
    role: Optional[str]
    content: list[dict]
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "OutputItem":
        content_raw = d.get("content", [])
        content = []
        for c in content_raw:
            if c.get("type") == "output_text":
                content.append({"type": "text", "text": c.get("text", "")})
            else:
                content.append(c)
        return cls(
            item_type=d.get("type", ""),
            role=d.get("role"),
            content=content,
            raw=d,
        )


@dataclass
class CompactionResult:
    """
    Result of POST /responses/compact.

    output_items can be passed directly as conversation_history to stream().
    It includes original messages plus a compaction_summary item (encrypted
    blob that the model understands — treat it as opaque on the client side).
    """
    response_id: str
    output_items: list[dict]

    @property
    def has_summary(self) -> bool:
        return any(item.get("type") == "compaction_summary" for item in self.output_items)

    @property
    def summary_item(self) -> Optional[dict]:
        for item in self.output_items:
            if item.get("type") == "compaction_summary":
                return item
        return None


# Union type for stream events
StreamEvent = Union[TextDelta, ReasoningDelta, ToolCall, OutputItem, ResponseCompleted, ResponseFailed]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class CodexClient:
    """
    Python SDK for the ChatGPT Codex backend API.

    Session-level defaults can be set on the client and are used for every
    stream()/respond() call unless overridden per-call:

        client = CodexClient.from_saved_tokens(
            model="gpt-5.3-codex",
            instructions="You are a concise assistant.",
            reasoning="medium",
            web_search="cached",
            service_tier="fast",
        )

        # Uses session defaults:
        client.stream("Explain quicksort")

        # Overrides reasoning for this call only:
        client.stream("Quick one-liner?", reasoning="minimal")

        # Explicitly disables a default for this call (None overrides a set default):
        client.stream("No web please", web_search=None)

    Tool use (same tool definition format as the official OpenAI SDK):
        tools = [{"type": "function", "name": "get_weather", ...}]

        history = []
        for event in client.stream("Weather in Paris?", tools=tools):
            if isinstance(event, ToolCall):
                result = dispatch(event.name, event.parsed_arguments())
                history.append(event.as_history_item())
                history.append(event.to_tool_result(json.dumps(result)))

        for event in client.stream(None, conversation_history=history, tools=tools):
            if isinstance(event, TextDelta):
                print(event.text, end="")

    Image input:
        from codex_sdk import image_url, image_b64
        client.stream(["Describe this image:", image_url("https://...")])
    """

    def __init__(
        self,
        store: Optional[TokenStore] = None,
        *,
        model: str = "gpt-5.4",
        instructions: str = "",
        reasoning: Optional[ReasoningEffort] = None,
        reasoning_summary: Optional[ReasoningSummary] = None,
        verbosity: Optional[Verbosity] = None,
        web_search: Optional[str] = None,
        service_tier: Optional[ServiceTier] = None,
        parallel_tool_calls: bool = False,
        tools: Optional[list[dict]] = None,
        persist: bool = False,
        include_reasoning: bool = False,
    ) -> None:
        self._store = store
        self._session = requests.Session()
        if store:
            self._session.headers.update(self._auth_headers())
        # Session-level defaults — resolved by _resolve() in stream()/respond()
        self._defaults: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "reasoning": reasoning,
            "reasoning_summary": reasoning_summary,
            "verbosity": verbosity,
            "web_search": web_search,
            "service_tier": service_tier,
            "parallel_tool_calls": parallel_tool_calls,
            "tools": tools,
            "store": persist,
            "include_reasoning": include_reasoning,
        }

    def _resolve(self, key: str, value: Any) -> Any:
        """Return value if explicitly passed, otherwise fall back to session default."""
        return self._defaults[key] if value is _UNSET else value

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, *, request_api_key: bool = True) -> "CodexClient":
        """
        Ensure this client is authenticated against the server:

        1. Load ~/.codex/auth.json if present.
        2. If token is stale (exp within 5 min or last_refresh > 55 min) → refresh proactively.
        3. If token is fresh → use it directly (no network probe needed).
        4. If still stale after failed refresh → probe /wham/usage as last resort.
        5. If probe fails or no tokens → full OAuth browser flow.

        Tokens are persisted after every refresh or new login.
        Returns self for chaining:

            client = CodexClient().authenticate()
            client = CodexClient(model="gpt-5.4", reasoning="low").authenticate()
        """
        from .oauth import refresh_access_token, run_oauth_flow

        def _do_refresh(store: TokenStore) -> Optional[TokenStore]:
            """Attempt a token refresh; return updated store or None on failure."""
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
            except Exception as exc:
                print(f"[auth] Refresh failed: {exc}")
                return None

        def _probe(store: TokenStore) -> bool:
            """Return True if the server accepts these tokens."""
            try:
                resp = requests.get(
                    "https://chatgpt.com/backend-api/wham/usage",
                    headers={
                        "Authorization": f"Bearer {store.access_token}",
                        "originator": ORIGINATOR,
                        **({"ChatGPT-Account-ID": store.account_id} if store.account_id else {}),
                    },
                    timeout=15,
                )
                return resp.ok
            except Exception:
                return False

        store = load_tokens()

        if store is not None:
            # Proactive refresh: don't wait for a 401
            if token_needs_refresh(store):
                print("[auth] Token stale — refreshing proactively…")
                if store.refresh_token:
                    refreshed = _do_refresh(store)
                    if refreshed:
                        store = refreshed
                        print("[auth] Token refreshed.")
                    else:
                        print("[auth] Proactive refresh failed — trying existing tokens…")

            # If token is now fresh, skip the probe entirely
            if not token_needs_refresh(store):
                self._store = store
                self._session.headers.update(self._auth_headers())
                return self

            # Token still stale (no refresh_token or refresh failed) — probe server
            if _probe(store):
                self._store = store
                self._session.headers.update(self._auth_headers())
                return self

            print("[auth] Tokens rejected — running full login…")

        store = run_oauth_flow(request_api_key=request_api_key)
        self._store = store
        self._session.headers.update(self._auth_headers())
        return self

    @classmethod
    def from_saved_tokens(
        cls,
        *,
        model: str = "gpt-5.4",
        instructions: str = "",
        reasoning: Optional[ReasoningEffort] = None,
        reasoning_summary: Optional[ReasoningSummary] = None,
        verbosity: Optional[Verbosity] = None,
        web_search: Optional[str] = None,
        service_tier: Optional[ServiceTier] = None,
        parallel_tool_calls: bool = False,
        tools: Optional[list[dict]] = None,
        persist: bool = False,
        include_reasoning: bool = False,
    ) -> "CodexClient":
        """
        Shorthand for ``CodexClient(...).authenticate()``.

        Loads saved tokens, refreshes if expired, or runs the OAuth flow
        if no tokens exist. Accepts the same session-level default kwargs as __init__.
        """
        return cls(
            model=model,
            instructions=instructions,
            reasoning=reasoning,
            reasoning_summary=reasoning_summary,
            verbosity=verbosity,
            web_search=web_search,
            service_tier=service_tier,
            parallel_tool_calls=parallel_tool_calls,
            tools=tools,
            persist=persist,
            include_reasoning=include_reasoning,
        ).authenticate()

    def _ensure_auth(self) -> None:
        if not self._store or not self._store.account_id:
            raise RuntimeError(
                "Not authenticated — call authenticate() first."
            )

    def _auth_headers(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self._store.access_token}",
            "originator": ORIGINATOR,
            "OpenAI-Beta": "responses=experimental",
        }
        if self._store.account_id:
            headers["ChatGPT-Account-ID"] = self._store.account_id
        return headers

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def list_models(self) -> list[ModelInfo]:
        """
        GET /models — list models available to this account.

        Returns ModelInfo objects sorted by priority (highest first).
        """
        self._ensure_auth()
        resp = self._session.get(
            f"{BASE_URL}/models",
            params={"client_version": CLIENT_VERSION},
            timeout=15,
        )
        resp.raise_for_status()
        models = [ModelInfo.from_dict(m) for m in resp.json().get("models", [])]
        models.sort(key=lambda m: m.priority, reverse=True)
        return models

    def get_model(self, slug: str) -> Optional[ModelInfo]:
        """Return the ModelInfo for a specific slug, or None if not found."""
        return next((m for m in self.list_models() if m.slug == slug), None)

    # ------------------------------------------------------------------
    # Usage / quota
    # ------------------------------------------------------------------

    def usage(self) -> dict:
        """
        GET /backend-api/wham/usage — query rate limits and quota for this account.

        Returns the raw JSON dict from the backend.
        """
        self._ensure_auth()
        resp = self._session.get(
            "https://chatgpt.com/backend-api/wham/usage",
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Responses — SSE streaming  (stream=True is mandatory by the backend)
    # ------------------------------------------------------------------

    def stream(
        self,
        user_message: Optional[MessageContent] = None,
        *,
        # Per-call params — _UNSET means "use session default"
        model: str = _UNSET,
        instructions: str = _UNSET,
        reasoning: Optional[ReasoningEffort] = _UNSET,
        reasoning_summary: Optional[ReasoningSummary] = _UNSET,
        verbosity: Optional[Verbosity] = _UNSET,
        web_search: Optional[str] = _UNSET,
        service_tier: Optional[ServiceTier] = _UNSET,
        parallel_tool_calls: bool = _UNSET,
        tools: Optional[list[dict]] = _UNSET,
        store: bool = _UNSET,
        include_reasoning: bool = _UNSET,
        # Always per-call (no session default)
        conversation_history: Optional[list[dict]] = None,
        tool_choice: Union[str, dict] = "auto",
        output_schema: Optional[dict] = None,
        prompt_cache_key: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """
        POST /responses — stream a model response via SSE.

        Yields StreamEvent objects:
          TextDelta          — incremental text chunk
          ReasoningDelta     — reasoning summary chunk (if include_reasoning=True)
          ToolCall           — model requests a function call
          OutputItem         — completed non-tool output item (message, …)
          ResponseCompleted  — final event with full token usage breakdown
          ResponseFailed     — error event

        Parameters with a session default (set on the client, overridable per-call):
            model, instructions, reasoning, reasoning_summary, verbosity,
            web_search, service_tier, parallel_tool_calls, tools, store,
            include_reasoning.

        Parameters that are always per-call:
            user_message:        The user's prompt. May be:
                                   - str: plain text message
                                   - list[dict]: content blocks (text + images),
                                     e.g. ["Describe:", image_url("https://...")]
                                   - None: no new user message (use after tool results)
            conversation_history: Prior turns as ResponseItem-compatible dicts.
                                   Can include compaction_summary items from compact().
                                   After a ToolCall, append call.as_history_item() and
                                   call.to_tool_result(output) here before the next call.
            tool_choice:         "auto" | "none" | "required" | {"type": "function",
                                   "name": "..."}.  Ignored when no tools are active.
            output_schema:       JSON Schema dict for structured output. Mutually
                                   exclusive with verbosity.
            prompt_cache_key:    UUID to share across calls that have a common prefix
                                   to hit the server-side prompt cache.
        """
        self._ensure_auth()

        # Resolve session defaults
        model = self._resolve("model", model)
        instructions = self._resolve("instructions", instructions)
        reasoning = self._resolve("reasoning", reasoning)
        reasoning_summary = self._resolve("reasoning_summary", reasoning_summary)
        verbosity = self._resolve("verbosity", verbosity)
        web_search = self._resolve("web_search", web_search)
        service_tier = self._resolve("service_tier", service_tier)
        parallel_tool_calls = self._resolve("parallel_tool_calls", parallel_tool_calls)
        tools = self._resolve("tools", tools)
        store = self._resolve("store", store)
        include_reasoning = self._resolve("include_reasoning", include_reasoning)

        input_items = list(conversation_history or [])

        if user_message is not None and user_message != "":
            if isinstance(user_message, str):
                content: list[dict] = [{"type": "input_text", "text": user_message}]
            else:
                content = []
                for block in user_message:
                    if isinstance(block, str):
                        content.append({"type": "input_text", "text": block})
                    else:
                        content.append(block)
            input_items.append({
                "type": "message",
                "role": "user",
                "content": content,
            })

        # Build tools list — merge user-defined tools + built-in web_search
        tools_payload: list[dict] = list(tools or [])
        if web_search and web_search != "disabled":
            tools_payload.append({"type": "web_search"})

        if tools_payload:
            tc: Any = tool_choice
            ptc = parallel_tool_calls
        else:
            tc = "none"
            ptc = False

        payload: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools_payload,
            "tool_choice": tc,
            "parallel_tool_calls": ptc,
            "store": store,
            "stream": True,
            "include": ["reasoning.encrypted_content"] if include_reasoning else [],
        }

        if service_tier is not None:
            payload["service_tier"] = service_tier
        if prompt_cache_key is not None:
            payload["prompt_cache_key"] = prompt_cache_key

        if reasoning or reasoning_summary:
            reasoning_block: dict[str, Any] = {}
            if reasoning:
                reasoning_block["effort"] = reasoning
            if reasoning_summary:
                reasoning_block["summary"] = reasoning_summary
            payload["reasoning"] = reasoning_block

        if output_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "strict": True,
                    "schema": output_schema,
                    "name": output_schema.get("title", "output"),
                }
            }
        elif verbosity:
            payload["text"] = {"verbosity": verbosity}

        with self._session.post(
            f"{BASE_URL}/responses",
            json=payload,
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            yield from _parse_sse_stream(resp)

    def respond(
        self,
        user_message: Optional[MessageContent] = None,
        *,
        # Per-call params with session defaults
        model: str = _UNSET,
        instructions: str = _UNSET,
        reasoning: Optional[ReasoningEffort] = _UNSET,
        reasoning_summary: Optional[ReasoningSummary] = _UNSET,
        verbosity: Optional[Verbosity] = _UNSET,
        web_search: Optional[str] = _UNSET,
        service_tier: Optional[ServiceTier] = _UNSET,
        parallel_tool_calls: bool = _UNSET,
        tools: Optional[list[dict]] = _UNSET,
        store: bool = _UNSET,
        # Always per-call
        conversation_history: Optional[list[dict]] = None,
        tool_choice: Union[str, dict] = "auto",
        output_schema: Optional[dict] = None,
        prompt_cache_key: Optional[str] = None,
        print_stream: bool = False,
    ) -> tuple[str, ResponseCompleted | None]:
        """
        Collect the full text from a streamed response.

        Returns (text, ResponseCompleted).  For tool-calling scenarios use
        stream() directly — respond() only captures text output.
        """
        text_parts: list[str] = []
        completion: ResponseCompleted | None = None
        for event in self.stream(
            user_message,
            model=model,
            instructions=instructions,
            reasoning=reasoning,
            reasoning_summary=reasoning_summary,
            verbosity=verbosity,
            web_search=web_search,
            service_tier=service_tier,
            parallel_tool_calls=parallel_tool_calls,
            tools=tools,
            store=store,
            conversation_history=conversation_history,
            tool_choice=tool_choice,
            output_schema=output_schema,
            prompt_cache_key=prompt_cache_key,
        ):
            if isinstance(event, TextDelta):
                text_parts.append(event.text)
                if print_stream:
                    print(event.text, end="", flush=True)
            elif isinstance(event, ResponseCompleted):
                completion = event
            elif isinstance(event, ResponseFailed):
                raise RuntimeError(f"[{event.code}] {event.message}")
        if print_stream:
            print()
        return "".join(text_parts), completion

    # ------------------------------------------------------------------
    # Context compaction  POST /responses/compact
    # ------------------------------------------------------------------

    def compact(
        self,
        conversation_history: list[dict],
        *,
        model: str = _UNSET,
        instructions: str = _UNSET,
    ) -> CompactionResult:
        """
        POST /responses/compact — compress a long conversation history.

        Returns a CompactionResult whose output_items can be passed directly
        as conversation_history to stream().  The compaction_summary item is
        an encrypted blob understood by the model — treat it as opaque.

        Typical use:
            result = client.compact(long_history)
            for event in client.stream("next question",
                                       conversation_history=result.output_items):
                ...
        """
        self._ensure_auth()
        payload: dict[str, Any] = {
            "model": self._resolve("model", model),
            "instructions": self._resolve("instructions", instructions),
            "input": conversation_history,
            "tools": [],
            "parallel_tool_calls": False,
        }
        resp = self._session.post(
            f"{BASE_URL}/responses/compact",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return CompactionResult(
            response_id=data.get("id", ""),
            output_items=data.get("output", []),
        )


# ---------------------------------------------------------------------------
# SSE parser
# ---------------------------------------------------------------------------

def _parse_sse_stream(resp: requests.Response) -> Generator[StreamEvent, None, None]:
    """
    Parse a text/event-stream response and yield typed StreamEvent objects.

    SSE wire format: "event: <name>" and "data: <json>" lines separated by
    blank lines.  Mirrors codex-rs/codex-api/src/sse/responses.rs.
    """
    event_name: Optional[str] = None
    data_lines: list[str] = []

    for raw_line in resp.iter_lines():
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8")
        if raw_line is None:
            continue

        if raw_line == "":
            if data_lines:
                data = "\n".join(data_lines)
                event = _dispatch_sse_event(event_name, data)
                if event is not None:
                    yield event
                    if isinstance(event, ResponseCompleted):
                        return
            event_name = None
            data_lines = []
            continue

        if raw_line.startswith("event:"):
            event_name = raw_line[len("event:"):].strip()
        elif raw_line.startswith("data:"):
            data_lines.append(raw_line[len("data:"):].strip())


def _dispatch_sse_event(
    event_name: Optional[str], data: str
) -> Optional[StreamEvent]:
    """Map one SSE event onto a domain object; return None for ignored events."""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None

    kind = event_name or payload.get("type", "")

    if kind == "response.output_text.delta":
        delta = payload.get("delta", "")
        if delta:
            return TextDelta(text=delta)

    elif kind == "response.reasoning_summary_part.delta":
        delta = payload.get("delta", "")
        if delta:
            return ReasoningDelta(
                text=delta,
                summary_index=payload.get("summary_index", 0),
            )

    elif kind == "response.output_item.done":
        item = payload.get("item")
        if item:
            item_type = item.get("type")
            if item_type == "function_call":
                return ToolCall(
                    call_id=item.get("call_id", ""),
                    name=item.get("name", ""),
                    arguments=item.get("arguments", "{}"),
                    raw=item,
                )
            if item_type == "reasoning":
                # Reasoning content is delivered as a completed item, not streaming deltas.
                # encrypted_content is an opaque blob; summary text lives in "summary" list.
                content = ""
                for part in item.get("summary") or []:
                    content += part.get("text", "")
                encrypted = item.get("encrypted_content", "")
                if content or encrypted:
                    return ReasoningDelta(text=content or encrypted, summary_index=0)
                return None
            return OutputItem.from_dict(item)

    elif kind == "response.completed":
        r = payload.get("response", {})
        raw_usage = r.get("usage") or {}
        usage = TokenUsage(
            input_tokens=raw_usage.get("input_tokens", 0),
            output_tokens=raw_usage.get("output_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
            reasoning_tokens=(raw_usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
            cached_tokens=(raw_usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
        )
        return ResponseCompleted(response_id=r.get("id", ""), usage=usage)

    elif kind == "response.failed":
        r = payload.get("response", {})
        error = r.get("error") or {}
        return ResponseFailed(
            code=error.get("code", "unknown"),
            message=error.get("message", "Unknown error"),
        )

    # Silently ignored: response.created, response.in_progress,
    # response.output_item.added, response.content_part.*, rate_limits, …
    return None


# ---------------------------------------------------------------------------
# Back-compat alias
# ---------------------------------------------------------------------------

def client_from_saved_tokens() -> CodexClient:
    """Alias for CodexClient.from_saved_tokens()."""
    return CodexClient.from_saved_tokens()
