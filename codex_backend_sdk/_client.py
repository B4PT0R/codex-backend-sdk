"""Transport client and public entrypoint."""

from __future__ import annotations

import urllib.parse
from typing import Any, Optional

import requests

from ._transport import request_with_retries
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
        from .resources.chatgpt import ChatGPTResources
        from .resources.models import Models
        from .resources.openai_oauth import Audio, Embeddings
        from .resources.files import Files
        from .resources.images import Images
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
        self.images = Images(self)
        self.files = Files(self)
        self.codex = CodexResources(self)
        self.chatgpt = ChatGPTResources(self)

    def authenticate(
        self,
        *,
        interactive: bool = True,
        force: bool = False,
    ) -> "CodexClient":
        from .oauth import obtain_api_key, refresh_access_token, run_oauth_flow

        def refresh(store: TokenStore) -> Optional[TokenStore]:
            try:
                data = refresh_access_token(store.refresh_token)
                id_token = data.get("id_token", store.id_token_raw)
                api_key = store.openai_api_key
                if not api_key and data.get("id_token"):
                    try:
                        api_key = obtain_api_key(id_token)
                    except Exception:
                        pass
                refreshed = TokenStore.from_exchange(
                    access_token=data.get("access_token", store.access_token),
                    refresh_token=data.get("refresh_token", store.refresh_token),
                    id_token=id_token,
                    openai_api_key=api_key,
                )
                save_tokens(refreshed)
                return refreshed
            except Exception:
                return None

        if force and not interactive:
            raise ValueError("Forced authentication requires interactive=True.")

        store = None if force else load_tokens()
        if store is not None:
            if (token_needs_refresh(store) or not store.openai_api_key) and store.refresh_token:
                store = refresh(store) or store
            if not token_needs_refresh(store) or self._probe_auth(store):
                self._set_store(store)
                return self

        if not interactive:
            raise RuntimeError("No usable stored Codex credentials; interactive login required.")

        self._set_store(run_oauth_flow())
        return self

    def authenticate_device_code(
        self,
        *,
        on_code: Any = None,
        persist: bool = True,
        timeout: float = 15 * 60,
        allowed_workspace_ids: list[str] | tuple[str, ...] | None = None,
    ) -> "CodexClient":
        """Authenticate without a callback listener, using Codex device login."""
        from .oauth import complete_device_code_login, request_device_code

        device_code = request_device_code()
        if on_code is None:
            print(
                "Open this URL and enter the one-time code (only continue if you "
                "started this login):\n"
                f"  {device_code.verification_url}\n  {device_code.user_code}"
            )
        else:
            on_code(device_code)
        store = complete_device_code_login(
            device_code,
            timeout=timeout,
            persist=persist,
            allowed_workspace_ids=allowed_workspace_ids,
        )
        self._set_store(store)
        return self

    @property
    def authenticated(self) -> bool:
        """Whether this client currently has OAuth credentials loaded."""
        return bool(self._store and self._store.account_id)

    def account_info(self) -> dict[str, Any]:
        """Return safe non-secret account metadata decoded from stored tokens."""
        store = self._store
        authenticated = bool(store and store.account_id)
        return {
            "authenticated": authenticated,
            "account_id": store.account_id if store else None,
            "email": store.email if store else None,
            "plan_type": store.plan_type if store else None,
        }

    def logout(self) -> bool:
        """Clear local OAuth credentials and unauthenticate this client."""
        from .storage import clear_tokens

        cleared = clear_tokens()
        self._store = None
        self._session.headers.pop("Authorization", None)
        self._session.headers.pop("ChatGPT-Account-ID", None)
        return cleared

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

    def _patch(self, path: str, *, body: dict[str, Any]) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_with_retries(
            "PATCH",
            f"{BASE_URL}{path}",
            json=body,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def _delete(self, path: str) -> None:
        self._ensure_auth()
        response = self._request_with_retries(
            "DELETE", f"{BASE_URL}{path}", timeout=self._timeout
        )
        response.raise_for_status()

    def _openai_headers(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        self._ensure_auth()
        if self._store is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return {"Authorization": f"Bearer {self._store.access_token}", **(extra or {})}

    def _post_openai(
        self,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
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
        response.raise_for_status()
        return response.json()

    def _post_wham(
        self,
        path: str,
        *,
        body: dict[str, Any],
        headers: Optional[dict[str, str]] = None,
        use_oauth_headers: bool = True,
        timeout: Any = _UNSET,
    ) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_with_retries(
            "POST",
            f"{WHAM_BASE_URL}{path}",
            json=body,
            headers=headers,
            timeout=self._timeout if not _is_given(timeout) else timeout,
            _use_session=use_oauth_headers,
        )
        response.raise_for_status()
        return response.json()

    def _patch_wham(
        self,
        path: str,
        *,
        body: dict[str, Any],
        timeout: Any = _UNSET,
    ) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_with_retries(
            "PATCH",
            f"{WHAM_BASE_URL}{path}",
            json=body,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        response.raise_for_status()
        return response.json()

    def _delete_wham(
        self,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        timeout: Any = _UNSET,
    ) -> None:
        self._ensure_auth()
        response = self._request_with_retries(
            "DELETE",
            f"{WHAM_BASE_URL}{path}",
            params=params,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        response.raise_for_status()

    def _get_chatgpt(
        self,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        self._ensure_auth()
        response = self._request_with_retries(
            "GET",
            f"{CHATGPT_BASE_URL}{path}",
            params=params,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _patch_chatgpt(
        self,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return self._request_chatgpt("PATCH", path, body=body, params=params).json()

    def _delete_chatgpt(
        self,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        self._request_chatgpt("DELETE", path, params=params)

    def _request_chatgpt(
        self,
        method: str,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        stream: bool = False,
        timeout: Any = _UNSET,
    ) -> requests.Response:
        self._ensure_auth()
        response = self._request_with_retries(
            method,
            f"{CHATGPT_BASE_URL}{path}",
            json=body,
            params=params,
            headers=headers,
            stream=stream,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        response.raise_for_status()
        return response

    def _post_chatgpt(
        self,
        path: str,
        *,
        body: dict[str, Any],
        timeout: Any = _UNSET,
    ) -> dict[str, Any]:
        response = self._post_chatgpt_raw(path, body=body, timeout=timeout)
        return response.json()

    def _post_chatgpt_raw(
        self,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        files: Any = None,
        data: Any = None,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        timeout: Any = _UNSET,
    ) -> requests.Response:
        self._ensure_auth()
        response = self._request_with_retries(
            "POST",
            f"{CHATGPT_BASE_URL}{path}",
            json=body if files is None and data is None else None,
            files=files,
            data=data,
            headers=headers,
            params=params,
            timeout=self._timeout if not _is_given(timeout) else timeout,
        )
        response.raise_for_status()
        return response

    def _download_chatgpt_link(self, url: str) -> requests.Response:
        """Download a backend-issued URL without leaking OAuth to external hosts."""
        candidate = url.strip()
        if candidate.startswith("/backend-api/"):
            candidate = f"https://chatgpt.com{candidate}"
        elif candidate.startswith("/__codex-api/"):
            candidate = f"https://chatgpt.com/backend-api/{candidate[len('/__codex-api/'):]}"
        parsed = urllib.parse.urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ChatGPT returned an invalid download URL.")
        uses_chatgpt_auth = (
            parsed.hostname == "chatgpt.com" and parsed.path.startswith("/backend-api/")
        )
        response = self._request_with_retries(
            "GET",
            candidate,
            timeout=self._timeout,
            _use_session=uses_chatgpt_auth,
        )
        response.raise_for_status()
        return response

    def _request_with_retries(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        use_session = kwargs.pop("_use_session", True)
        return request_with_retries(
            self._session,
            method,
            url,
            max_retries=self._max_retries,
            retry_base_delay=self._retry_base_delay,
            use_session=use_session,
            **kwargs,
        )

    def realtime_websocket_url(self, *, model: str) -> str:
        """Return the official OpenAI Realtime WebSocket URL for Codex plugins."""
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")
        return "wss://api.openai.com/v1/realtime?" + urllib.parse.urlencode({"model": model})


OpenAI = CodexClient
