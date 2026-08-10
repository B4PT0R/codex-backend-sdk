"""Hosted ChatGPT Apps/MCP and ecosystem transports observed in Desktop."""

from __future__ import annotations

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
