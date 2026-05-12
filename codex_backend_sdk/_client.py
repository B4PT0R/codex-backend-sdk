"""Transport client and public entrypoint."""

from __future__ import annotations

import urllib.parse
import time
from typing import Any, Optional

import requests

from ._utils import _UNSET, _is_given
from .storage import TokenStore, load_tokens, save_tokens, token_needs_refresh

BASE_URL = "https://chatgpt.com/backend-api/codex"
CHATGPT_BASE_URL = "https://chatgpt.com/backend-api"
WHAM_BASE_URL = CHATGPT_BASE_URL
OPENAI_BASE_URL = "https://api.openai.com/v1"
ORIGINATOR = "codex_cli_rs"


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
        max_retries: int = 2,
        retry_base_delay: float = 0.25,
    ) -> None:
        from .resources.codex import CodexResources
        from .resources.models import Models
        from .resources.openai_oauth import Audio, Embeddings
        from .resources.files import Files
        from .resources.realtime import Realtime
        from .resources.responses import Responses

        self._store = store
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
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
        self.embeddings = Embeddings(self)
        self.audio = Audio(self)
        self.files = Files(self)
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
        return self._get_raw(path, params=params).json()

    def _get_raw(
        self,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: Any = _UNSET,
    ) -> requests.Response:
        self._ensure_auth()
        response = self._request_with_retries(
            "GET",
            f"{BASE_URL}{path}",
            params=params,
            headers=headers,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        return response

    def _post(self, path: str, *, body: dict[str, Any], stream: bool = False) -> requests.Response:
        self._ensure_auth()
        response = self._request_with_retries(
            "POST",
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
        body: Optional[dict[str, Any]] = None,
        content: Optional[bytes] = None,
        files: Any = None,
        data: Any = None,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        timeout: Any = _UNSET,
    ) -> requests.Response:
        self._ensure_auth()
        response = self._request_with_retries(
            "POST",
            f"{BASE_URL}{path}",
            json=body if files is None and data is None and content is None else None,
            data=content if content is not None else data,
            files=files,
            headers=headers,
            params=params,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        response.raise_for_status()
        return response

    def _openai_headers(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        self._ensure_auth()
        if self._store is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return {"Authorization": f"Bearer {self._store.access_token}", **(extra or {})}

    def _post_openai(
        self,
        path: str,
        *,
        body: dict[str, Any],
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        timeout: Any = _UNSET,
    ) -> dict[str, Any]:
        response = self._request_with_retries(
            "POST",
            f"{OPENAI_BASE_URL}{path}",
            json=body,
            headers=self._openai_headers(headers),
            params=params,
            timeout=self._timeout if not _is_given(timeout) else timeout,
            _use_session=False,
        )
        response.raise_for_status()
        return response.json()

    def _post_openai_raw(
        self,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        files: Any = None,
        data: Any = None,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        timeout: Any = _UNSET,
        stream: bool = False,
    ) -> requests.Response:
        response = self._request_with_retries(
            "POST",
            f"{OPENAI_BASE_URL}{path}",
            json=body if files is None and data is None else None,
            data=data,
            files=files,
            headers=self._openai_headers(headers),
            params=params,
            stream=stream,
            timeout=self._timeout if not _is_given(timeout) else timeout,
            _use_session=False,
        )
        response.raise_for_status()
        return response

    def _get_wham(self, path: str, *, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_with_retries(
            "GET",
            f"{WHAM_BASE_URL}{path}",
            params=params,
            timeout=30,
        )
        return response.json()

    def _get_chatgpt(self, path: str) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_with_retries("GET", f"{CHATGPT_BASE_URL}{path}", timeout=30)
        return response.json()

    def _post_chatgpt(
        self,
        path: str,
        *,
        body: dict[str, Any],
        timeout: Any = _UNSET,
    ) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_with_retries(
            "POST",
            f"{CHATGPT_BASE_URL}{path}",
            json=body,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        return response.json()

    def _request_with_retries(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last_error: requests.RequestException | None = None
        use_session = kwargs.pop("_use_session", True)
        for attempt in range(self._max_retries + 1):
            try:
                request = self._session.request if use_session else requests.request
                response = request(method, url, **kwargs)
                if self._should_retry_response(response, attempt):
                    self._sleep_before_retry(response, attempt)
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    raise
                self._sleep_before_retry(None, attempt)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Request retry loop exhausted")

    def _should_retry_response(self, response: requests.Response, attempt: int) -> bool:
        if attempt >= self._max_retries:
            return False
        return response.status_code == 429 or 500 <= response.status_code < 600

    def _sleep_before_retry(self, response: requests.Response | None, attempt: int) -> None:
        retry_after = response.headers.get("Retry-After") if response is not None else None
        delay = _parse_retry_after(retry_after)
        if delay is None:
            delay = self._retry_base_delay * (2 ** attempt)
        time.sleep(delay)

    def realtime_websocket_url(self, *, model: str) -> str:
        """Return the official OpenAI Realtime WebSocket URL for Codex plugins."""
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")
        return "wss://api.openai.com/v1/realtime?" + urllib.parse.urlencode({"model": model})

    def realtime_websocket_headers(self, *, session_id: Optional[str] = None) -> dict[str, str]:
        """Return headers for an OpenAI Realtime WebSocket connection."""
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


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
