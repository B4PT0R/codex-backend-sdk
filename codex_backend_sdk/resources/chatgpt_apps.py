"""Hosted ChatGPT Apps/MCP and ecosystem transports observed in Desktop."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING, Union

from .._utils import _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


JsonRpcId = Union[int, str]


def _required(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"Expected a non-empty value for `{name}` but received {value!r}")
    return value


def _object(value: Any, name: str) -> dict[str, Any]:
    result = _jsonable(value)
    if not isinstance(result, dict):
        raise TypeError(f"Expected `{name}` to serialize to a JSON object.")
    return result


class ChatGPTAppsProtocolError(RuntimeError):
    """A valid HTTP response contained an invalid or failed Apps JSON-RPC envelope."""


def _response_messages(response: Any) -> list[dict[str, Any]]:
    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" not in content_type:
        if not response.content:
            return []
        payload = response.json()
        values = payload if isinstance(payload, list) else [payload]
    else:
        values = []
        data_lines: list[str] = []
        for line in response.text.splitlines():
            if not line:
                if data_lines:
                    data = "\n".join(data_lines)
                    if data != "[DONE]":
                        values.append(json.loads(data))
                    data_lines = []
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            values.append(json.loads("\n".join(data_lines)))
    if not all(isinstance(value, dict) for value in values):
        raise ChatGPTAppsProtocolError("Hosted MCP returned a non-object message.")
    return values


class HostedMCPConnection:
    """Synchronous MCP Streamable HTTP connection to ChatGPT plugin-service."""

    def __init__(
        self,
        client: CodexClient,
        *,
        product_sku: str = "codex",
        originator: str | None = None,
    ) -> None:
        self._client = client
        self._product_sku = _required(product_sku, "product_sku")
        self._originator = originator
        self._session_id: str | None = None
        self._next_request_id = 1
        self.initialize_result: dict[str, Any] | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-OpenAI-Product-Sku": self._product_sku,
        }
        if self._originator is not None:
            headers["originator"] = _required(self._originator, "originator")
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _send(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._client._request_chatgpt(
            "POST", "/ps/mcp", body=body, headers=self._headers()
        )
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        return _response_messages(response)

    def request(
        self,
        method: str,
        params: Any | None = None,
        *,
        request_id: JsonRpcId | None = None,
    ) -> dict[str, Any]:
        if request_id is None:
            request_id = self._next_request_id
            self._next_request_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": _required(method, "method"),
            "params": _object({} if params is None else params, "params"),
        }
        messages = self._send(body)
        response = next((message for message in messages if message.get("id") == request_id), None)
        if response is None:
            raise ChatGPTAppsProtocolError("Hosted MCP response is missing the request id.")
        error = response.get("error")
        if error is not None:
            message = error.get("message") if isinstance(error, dict) else None
            raise ChatGPTAppsProtocolError(message or "Hosted MCP request failed.")
        if not isinstance(response.get("result"), dict):
            raise ChatGPTAppsProtocolError("Hosted MCP response is missing an object result.")
        return response["result"]

    def notify(self, method: str, params: Any | None = None) -> None:
        self._send({
            "jsonrpc": "2.0",
            "method": _required(method, "method"),
            **({} if params is None else {"params": _object(params, "params")}),
        })

    def initialize(
        self,
        *,
        protocol_version: str = "2025-06-18",
        client_name: str = "codex-backend-sdk",
        client_version: str | None = None,
        capabilities: Any | None = None,
    ) -> dict[str, Any]:
        if client_version is None:
            from .. import __version__

            client_version = __version__
        result = self.request("initialize", {
            "protocolVersion": _required(protocol_version, "protocol_version"),
            "capabilities": _object({} if capabilities is None else capabilities, "capabilities"),
            "clientInfo": {
                "name": _required(client_name, "client_name"),
                "version": _required(client_version, "client_version"),
            },
        })
        self.notify("notifications/initialized")
        self.initialize_result = result
        return result

    def list_tools(self, *, cursor: str | None = None) -> dict[str, Any]:
        return self.request("tools/list", {} if cursor is None else {"cursor": cursor})

    def call_tool(
        self,
        name: str,
        arguments: Any | None = None,
        *,
        meta: Any | None = None,
    ) -> dict[str, Any]:
        """Invoke a hosted tool; callers own confirmation for external mutations."""
        params = {
            "name": _required(name, "name"),
            "arguments": _object({} if arguments is None else arguments, "arguments"),
        }
        if meta is not None:
            params["_meta"] = _object(meta, "meta")
        return self.request("tools/call", params)

    def list_resources(self, *, cursor: str | None = None) -> dict[str, Any]:
        return self.request("resources/list", {} if cursor is None else {"cursor": cursor})

    def list_resource_templates(self, *, cursor: str | None = None) -> dict[str, Any]:
        return self.request(
            "resources/templates/list", {} if cursor is None else {"cursor": cursor}
        )

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self.request("resources/read", {"uri": _required(uri, "uri")})

    def close(self) -> None:
        if self._session_id is None:
            return
        self._client._request_chatgpt("DELETE", "/ps/mcp", headers=self._headers())
        self._session_id = None

    def __enter__(self) -> HostedMCPConnection:
        if self.initialize_result is None:
            self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


class ChatGPTApps:
    """Hosted Apps APIs used by ChatGPT and the official Desktop client.

    ``request`` preserves the evolving MCP JSON-RPC envelope. Convenience
    methods validate only the stable envelope fields and otherwise return the
    backend payload unchanged.
    """

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def request(
        self,
        method: str,
        params: Any | None = None,
        *,
        request_id: JsonRpcId = 1,
    ) -> dict[str, Any]:
        method = _required(method, "method")
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": _object({} if params is None else params, "params"),
        }
        response = self._client._post_wham("/wham/apps", body=body)
        if response.get("jsonrpc") != "2.0" or response.get("id") != request_id:
            raise ChatGPTAppsProtocolError("Apps returned a mismatched JSON-RPC response.")
        error = response.get("error")
        if error is not None:
            message = error.get("message") if isinstance(error, dict) else None
            raise ChatGPTAppsProtocolError(message or "Apps JSON-RPC request failed.")
        if not isinstance(response.get("result"), dict):
            raise ChatGPTAppsProtocolError("Apps JSON-RPC response is missing an object result.")
        return response

    def list_tools(self, *, request_id: JsonRpcId = 1) -> list[dict[str, Any]]:
        response = self.request("tools/list", request_id=request_id)
        tools = response["result"].get("tools")
        if not isinstance(tools, list) or not all(isinstance(tool, dict) for tool in tools):
            raise ChatGPTAppsProtocolError("Apps tools/list returned an invalid tool list.")
        return tools

    def call_tool(
        self,
        name: str,
        arguments: Any | None = None,
        *,
        resource_uri: str | None = None,
        request_id: JsonRpcId = 1,
    ) -> dict[str, Any]:
        """Invoke a hosted tool; callers own confirmation for external mutations."""
        params: dict[str, Any] = {
            "name": _required(name, "name"),
            "arguments": _object({} if arguments is None else arguments, "arguments"),
        }
        if resource_uri is not None:
            params["_meta"] = {
                "_codex_apps": {"resource_uri": _required(resource_uri, "resource_uri")}
            }
        response = self.request("tools/call", params, request_id=request_id)
        result = response["result"]
        if result.get("isError") is True:
            raise ChatGPTAppsProtocolError("Apps tool call reported an error result.")
        return result

    def bootstrap_launcher(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/ecosystem/launcher/bootstrap", body=_object(body, "body")
        )

    def auto_install_launcher(self, body: Any) -> dict[str, Any]:
        """Explicitly request the Desktop launcher's installation mutation."""
        return self._client._post_chatgpt(
            "/ecosystem/launcher/auto_install", body=_object(body, "body")
        )

    def call_ecosystem_mcp(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/ecosystem/call_mcp", body=_object(body, "body")
        )

    def get_widget(self, **query: Any) -> dict[str, Any]:
        return self._client._get_chatgpt("/ecosystem/widget", params=query or None)

    def launch_widget(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/ecosystem/launch_widget", body=_object(body, "body")
        )

    def is_url_safe(self, url: str) -> bool:
        response = self._client._post_chatgpt(
            "/ecosystem/url_safe",
            body={"resolved_pineapple_uri": None, "url": _required(url, "url")},
        )
        return response.get("safe") is True

    def connect_hosted_mcp(
        self,
        *,
        product_sku: str = "codex",
        originator: str | None = None,
        initialize: bool = True,
    ) -> HostedMCPConnection:
        connection = HostedMCPConnection(
            self._client, product_sku=product_sku, originator=originator
        )
        if initialize:
            connection.initialize()
        return connection
