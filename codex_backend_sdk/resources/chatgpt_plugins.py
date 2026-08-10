"""Plugin discovery feeds used by official Codex clients."""

from __future__ import annotations

from typing import Any, Literal, TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from .._client import CodexClient


class ChatGPTPlugins:
    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.installation = ChatGPTPluginInstallation(client)

    def featured(self, *, platform: Literal["codex", "chat"] = "codex") -> list[str]:
        payload = self._client._get_chatgpt(
            "/plugins/featured", params={"platform": platform}
        )
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise RuntimeError("Featured plugins returned an invalid plugin-id list.")
        return payload

    def curated_export(self) -> dict[str, Any]:
        payload = self._client._get_chatgpt("/plugins/export/curated")
        if not isinstance(payload.get("download_url"), str) or not payload["download_url"]:
            raise RuntimeError("Curated plugin export is missing its download URL.")
        return payload

    def list(
        self,
        *,
        scope: Literal["GLOBAL", "USER", "WORKSPACE"] = "GLOBAL",
        limit: int = 200,
        page_token: str | None = None,
        collection: str | None = None,
    ) -> dict[str, Any]:
        return self._page(
            "/ps/plugins/list",
            params={
                "scope": _scope(scope),
                "limit": _positive(limit, "limit"),
                **({} if collection is None else {"collection": _required(collection, "collection")}),
                **({} if page_token is None else {"pageToken": _required(page_token, "page_token")}),
            },
        )

    def list_all(
        self,
        *,
        scope: Literal["GLOBAL", "USER", "WORKSPACE"] = "GLOBAL",
        collection: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._all_pages(
            lambda token: self.list(
                scope=scope, page_token=token, collection=collection
            )
        )

    def search(
        self,
        query: str,
        *,
        scope: Literal["GLOBAL", "USER", "WORKSPACE"] | None = None,
        limit: int = 16,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        return self._page(
            "/ps/plugins/search",
            params={
                "q": _required(query, "query"),
                "limit": _positive(limit, "limit"),
                **({} if scope is None else {"scope": _scope(scope)}),
                **({} if page_token is None else {"pageToken": _required(page_token, "page_token")}),
            },
        )

    def installed(
        self,
        *,
        scope: Literal["GLOBAL", "USER", "WORKSPACE"] | None = None,
        limit: int = 200,
        page_token: str | None = None,
        include_download_urls: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if scope is None:
            params["limit"] = _positive(limit, "limit")
        else:
            params["scope"] = _scope(scope)
        if page_token is not None:
            params["pageToken"] = _required(page_token, "page_token")
        if include_download_urls:
            params["includeDownloadUrls"] = True
        return self._page("/ps/plugins/installed", params=params)

    def installed_all(
        self,
        *,
        scope: Literal["GLOBAL", "USER", "WORKSPACE"] | None = None,
        include_download_urls: bool = False,
    ) -> list[dict[str, Any]]:
        return self._all_pages(
            lambda token: self.installed(
                scope=scope,
                page_token=token,
                include_download_urls=include_download_urls,
            )
        )

    def workspace_shared(
        self,
        *,
        limit: int = 200,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        return self._page(
            "/ps/plugins/workspace/shared",
            params={
                "limit": _positive(limit, "limit"),
                **({} if page_token is None else {"pageToken": _required(page_token, "page_token")}),
            },
        )

    def suggested(
        self,
        *,
        scope: Literal["GLOBAL", "USER", "WORKSPACE"] = "GLOBAL",
    ) -> dict[str, Any]:
        payload = self._client._get_chatgpt(
            "/ps/plugins/suggested",
            params={"scope": _scope(scope)},
            headers=_headers(),
        )
        if not isinstance(payload.get("plugins"), list):
            raise RuntimeError("Suggested plugins response contains an invalid plugin list.")
        return payload

    def retrieve(
        self,
        plugin_id: str,
        *,
        include_download_urls: bool = False,
    ) -> dict[str, Any]:
        payload = self._client._get_chatgpt(
            f"/ps/plugins/{_path(plugin_id, 'plugin_id')}",
            params=(
                {"includeDownloadUrls": True} if include_download_urls else None
            ),
            headers=_headers(),
        )
        if not isinstance(payload.get("id"), str):
            raise RuntimeError("Plugin detail response is missing its identifier.")
        return payload

    def _page(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        payload = self._client._get_chatgpt(path, params=params, headers=_headers())
        _validate_page(payload)
        return payload

    @staticmethod
    def _all_pages(fetch: Any) -> list[dict[str, Any]]:
        plugins: list[dict[str, Any]] = []
        token: str | None = None
        seen: set[str] = set()
        while True:
            page = fetch(token)
            plugins.extend(page["plugins"])
            token_value = page["pagination"].get("next_page_token")
            if token_value is None:
                return plugins
            if not isinstance(token_value, str) or not token_value:
                raise RuntimeError("Plugin catalog returned an invalid next page token.")
            if token_value in seen:
                raise RuntimeError("Plugin catalog returned a repeated next page token.")
            seen.add(token_value)
            token = token_value


class ChatGPTPluginInstallation:
    """Explicit remote-plugin installation mutations."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def install(
        self,
        plugin_id: str,
        *,
        include_apps_needing_auth: bool = True,
    ) -> dict[str, Any]:
        return self._mutate(
            plugin_id,
            "install",
            expected_enabled=True,
            params={"includeAppsNeedingAuth": include_apps_needing_auth},
        )

    def uninstall(self, plugin_id: str) -> dict[str, Any]:
        return self._mutate(plugin_id, "uninstall", expected_enabled=False)

    def _mutate(
        self,
        plugin_id: str,
        action: str,
        *,
        expected_enabled: bool,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        expected_id = _required(plugin_id, "plugin_id")
        payload = self._client._request_chatgpt(
            "POST",
            f"/ps/plugins/{_path(expected_id, 'plugin_id')}/{action}",
            params=params,
            headers=_headers(),
        ).json()
        if not isinstance(payload, dict) or payload.get("id") != expected_id:
            raise RuntimeError("Plugin mutation returned an unexpected identifier.")
        if payload.get("enabled") is not expected_enabled:
            raise RuntimeError("Plugin mutation returned an unexpected enabled state.")
        return payload


def _headers() -> dict[str, str]:
    return {"OAI-Product-Sku": "codex"}


def _required(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"Expected a non-empty value for `{name}` but received {value!r}")
    return value


def _positive(value: int, name: str) -> int:
    if value < 1:
        raise ValueError(f"Expected `{name}` to be positive.")
    return value


def _scope(value: str) -> str:
    if value not in {"GLOBAL", "USER", "WORKSPACE"}:
        raise ValueError(f"Unsupported plugin scope: {value!r}")
    return value


def _path(value: str, name: str) -> str:
    return quote(_required(value, name), safe="")


def _validate_page(payload: dict[str, Any]) -> None:
    plugins = payload.get("plugins")
    pagination = payload.get("pagination")
    if not isinstance(plugins, list) or not all(isinstance(item, dict) for item in plugins):
        raise RuntimeError("Plugin catalog response contains an invalid plugin list.")
    if not isinstance(pagination, dict):
        raise RuntimeError("Plugin catalog response contains invalid pagination.")
