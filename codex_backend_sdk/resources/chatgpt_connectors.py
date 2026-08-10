"""ChatGPT connector discovery, linking, and explicit external actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TYPE_CHECKING
from urllib.parse import quote

from .._utils import _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


class ConnectorAuthenticationRequiredError(RuntimeError):
    """Raised when an explicit connector action requires a linked account."""


def _required(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"Expected a non-empty value for `{name}` but received {value!r}")
    return value


def _path(value: str, name: str) -> str:
    return quote(_required(value, name), safe="")


def _object(value: Any, name: str = "body") -> dict[str, Any]:
    payload = _jsonable(value)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected `{name}` to serialize to a JSON object.")
    return payload


class ChatGPTConnectors:
    """Connector APIs grouped by discovery, authentication, and authority."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.directory = ConnectorDirectory(client)
        self.links = ConnectorLinks(client)
        self.authentication = ConnectorAuthentication(client)
        self.external_actions = ConnectorExternalActions(client)

    def retrieve(
        self,
        connector_id: str,
        *,
        include_actions: bool = False,
        include_logo: bool = False,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/aip/connectors/{_path(connector_id, 'connector_id')}",
            params={"include_actions": include_actions, "include_logo": include_logo},
            headers={"OAI-Product-Sku": "CODEX"},
        )

    def terms(self, connector_id: str) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/aip/connectors/{_path(connector_id, 'connector_id')}/tos",
            headers={"OAI-Product-Sku": "CODEX"},
        )

    def batch_metadata(
        self,
        app_ids: list[str] | tuple[str, ...],
        *,
        include_tools: bool = False,
        product_sku: str = "codex",
    ) -> dict[str, Any]:
        ids = [_required(app_id, "app_id") for app_id in app_ids]
        if not ids:
            return {"apps": []}
        payload = self._client._request_chatgpt(
            "POST",
            "/ps/apps/batch",
            body={"app_ids": ids, "include_tools": include_tools},
            headers={"X-OpenAI-Product-Sku": _required(product_sku, "product_sku")},
        ).json()
        apps = payload.get("apps") if isinstance(payload, dict) else None
        if not isinstance(apps, list) or not all(isinstance(app, dict) for app in apps):
            raise RuntimeError("Connector metadata response contains an invalid app list.")
        return payload

    def logo(
        self,
        connector_id: str,
        *,
        theme: Literal["light", "dark"] = "light",
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/aip/connectors/{_path(connector_id, 'connector_id')}/logo",
            params={"theme": theme},
        )


class ConnectorDirectory:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        *,
        token: str | None = None,
        workspace: bool = False,
        external_logos: bool = True,
    ) -> dict[str, Any]:
        path = "/connectors/directory/list_workspace" if workspace else "/connectors/directory/list"
        params: dict[str, Any] = {"external_logos": external_logos}
        if token is not None:
            params["token"] = _required(token, "token")
        payload = self._client._get_chatgpt(path, params=params)
        apps = payload.get("apps")
        if not isinstance(apps, list) or not all(isinstance(app, dict) for app in apps):
            raise RuntimeError("Connector directory response contains an invalid app list.")
        return payload

    def list_all(
        self,
        *,
        workspace: bool = False,
        external_logos: bool = True,
    ) -> list[dict[str, Any]]:
        apps: list[dict[str, Any]] = []
        token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            page = self.list(
                token=token, workspace=workspace, external_logos=external_logos
            )
            apps.extend(page["apps"])
            next_token = page.get("next_token", page.get("nextToken"))
            if next_token is None:
                return apps
            if not isinstance(next_token, str) or not next_token.strip():
                raise RuntimeError("Connector directory returned an invalid next token.")
            next_token = next_token.strip()
            if next_token in seen_tokens:
                raise RuntimeError("Connector directory returned a repeated next token.")
            seen_tokens.add(next_token)
            token = next_token


class ConnectorLinks:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def retrieve(self, connector_id: str) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/aip/connectors/{_path(connector_id, 'connector_id')}/link"
        )

    def list_accessible(
        self,
        *,
        principals: list[Any] | tuple[Any, ...] = (),
        link_refresh_strategy: str = "BLOCKING",
    ) -> dict[str, Any]:
        payload = self._client._post_chatgpt(
            "/aip/connectors/links/list_accessible",
            body={
                "principals": [_jsonable(principal) for principal in principals],
                "link_refresh_strategy": _required(
                    link_refresh_strategy, "link_refresh_strategy"
                ),
            },
        )
        links = payload.get("links")
        if not isinstance(links, list) or not all(isinstance(link, dict) for link in links):
            raise RuntimeError("Accessible connector response contains an invalid link list.")
        return payload


class ConnectorAuthentication:
    """Explicit connector-link mutations; none are called by discovery methods."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def connect_without_auth(
        self,
        connector_id: str,
        name: str,
        *,
        action_names: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/links/noauth",
            body={
                "connector_id": _required(connector_id, "connector_id"),
                "name": _required(name, "name"),
                "action_names": [_required(item, "action_name") for item in action_names],
            },
        )

    def start_oauth(
        self,
        connector_id: str,
        name: str,
        *,
        callback_url: str,
        post_auth_url: str,
        action_names: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/links/oauth",
            body={
                "connector_id": _required(connector_id, "connector_id"),
                "name": _required(name, "name"),
                "action_names": (
                    None
                    if action_names is None
                    else [_required(item, "action_name") for item in action_names]
                ),
                "callback_url": _required(callback_url, "callback_url"),
                "post_auth_url": _required(post_auth_url, "post_auth_url"),
            },
        )

    def start_reauthentication(
        self,
        link_id: str,
        *,
        callback_url: str,
        post_auth_url: str,
        requested_scopes: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/links/oauth/reauth",
            body={
                "link_id": _required(link_id, "link_id"),
                "callback_url": _required(callback_url, "callback_url"),
                "post_auth_url": _required(post_auth_url, "post_auth_url"),
                "requested_scopes": (
                    None
                    if requested_scopes is None
                    else [_required(scope, "requested_scope") for scope in requested_scopes]
                ),
            },
        )

    def complete_oauth(self, full_redirect_url: str) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/links/oauth/callback",
            body={"full_redirect_url": _required(full_redirect_url, "full_redirect_url")},
        )


class ConnectorExternalActions:
    """Direct external-service calls requiring caller-owned approval policy."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def search_contacts(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/google_contacts/search_contacts", body=_object(body)
        )

    def send_email(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/email/send_email", body=_object(body)
        )

    def unsend_email(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/email/unsend_email", body=_object(body)
        )

    def email_status(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/aip/connectors/email/send_email_status", body=_object(body)
        )

    def upload_google_drive_file(
        self,
        path: str | Path,
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Convert an Office document through the linked Google Drive app."""

        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"path `{file_path}` does not exist")
        if not file_path.is_file():
            raise ValueError(f"path `{file_path}` is not a file")
        mime_type = {
            ".docx": (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            ".pptx": (
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            ".xlsx": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        }.get(file_path.suffix.lower())
        if mime_type is None:
            raise ValueError("Expected a .docx, .pptx, or .xlsx file.")
        resolved_title = file_path.name if title is None else _required(title, "title")

        with file_path.open("rb") as handle:
            response = self._client._post_chatgpt_raw(
                "/wham/apps/google_drive/upload",
                data={"arguments": json.dumps({"title": resolved_title})},
                files={"file": (file_path.name, handle, mime_type)},
            )
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(
            payload.get("connector_result"), dict
        ):
            raise RuntimeError("Google Drive upload returned an invalid connector result.")
        result = payload["connector_result"]
        metadata = result.get("_meta")
        apps_metadata = metadata.get("_codex_apps") if isinstance(metadata, dict) else None
        auth_failure = (
            apps_metadata.get("connector_auth_failure")
            if isinstance(apps_metadata, dict)
            else None
        )
        if isinstance(auth_failure, dict) and auth_failure.get("is_auth_failure") is True:
            raise ConnectorAuthenticationRequiredError(
                "Google Drive connector authentication is required."
            )
        if result.get("isError") is True:
            raise RuntimeError("Google Drive connector could not open the file.")
        return payload
