import pytest

from codex_backend_sdk import ChatGPTAppsProtocolError, OpenAI


class FakeAppsClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.wham_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": [{"name": "search", "inputSchema": {}}]},
        }

    def _post_wham(self, path, *, body, **kwargs):
        self.calls.append(("POST", path, body))
        return self.wham_response

    def _get_chatgpt(self, path, *, params=None):
        self.calls.append(("GET", path, params))
        return {"path": path}

    def _post_chatgpt(self, path, *, body, **kwargs):
        self.calls.append(("POST", path, body))
        return {"path": path, "safe": True}


def test_apps_list_tools_uses_wham_json_rpc_transport():
    client = FakeAppsClient()

    tools = client.chatgpt.apps.list_tools()

    assert tools == [{"name": "search", "inputSchema": {}}]
    assert client.calls == [
        (
            "POST",
            "/wham/apps",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
    ]


def test_apps_call_tool_preserves_codex_resource_uri_metadata():
    client = FakeAppsClient()
    client.wham_response = {
        "jsonrpc": "2.0",
        "id": "call-1",
        "result": {"content": [], "structuredContent": {"items": []}},
    }

    result = client.chatgpt.apps.call_tool(
        "sites_list_sites",
        {"limit": 20},
        resource_uri="ui://sites/list",
        request_id="call-1",
    )

    assert result["structuredContent"] == {"items": []}
    assert client.calls[0][2] == {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {
            "name": "sites_list_sites",
            "arguments": {"limit": 20},
            "_meta": {"_codex_apps": {"resource_uri": "ui://sites/list"}},
        },
    }


@pytest.mark.parametrize(
    "response,match",
    [
        ({"jsonrpc": "2.0", "id": 2, "result": {}}, "mismatched"),
        (
            {"jsonrpc": "2.0", "id": 1, "error": {"message": "not linked"}},
            "not linked",
        ),
        ({"jsonrpc": "2.0", "id": 1, "result": []}, "object result"),
    ],
)
def test_apps_request_rejects_invalid_or_failed_envelopes(response, match):
    client = FakeAppsClient()
    client.wham_response = response

    with pytest.raises(ChatGPTAppsProtocolError, match=match):
        client.chatgpt.apps.request("tools/list")


def test_apps_call_tool_surfaces_mcp_error_result():
    client = FakeAppsClient()
    client.wham_response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"isError": True, "content": [{"type": "text", "text": "failed"}]},
    }

    with pytest.raises(ChatGPTAppsProtocolError, match="error result"):
        client.chatgpt.apps.call_tool("search")


def test_apps_ecosystem_helpers_match_desktop_routes():
    client = FakeAppsClient()

    client.chatgpt.apps.bootstrap_launcher({"launcher": "example"})
    client.chatgpt.apps.auto_install_launcher({"launcher": "example"})
    client.chatgpt.apps.call_ecosystem_mcp({"method": "tools/list"})
    client.chatgpt.apps.get_widget(widget_id="widget_1")
    client.chatgpt.apps.launch_widget({"widget_id": "widget_1"})
    assert client.chatgpt.apps.is_url_safe("https://example.com") is True

    assert client.calls == [
        ("POST", "/ecosystem/launcher/bootstrap", {"launcher": "example"}),
        ("POST", "/ecosystem/launcher/auto_install", {"launcher": "example"}),
        ("POST", "/ecosystem/call_mcp", {"method": "tools/list"}),
        ("GET", "/ecosystem/widget", {"widget_id": "widget_1"}),
        ("POST", "/ecosystem/launch_widget", {"widget_id": "widget_1"}),
        (
            "POST",
            "/ecosystem/url_safe",
            {"resolved_pineapple_uri": None, "url": "https://example.com"},
        ),
    ]


def test_apps_reject_non_object_payloads_and_empty_names():
    client = FakeAppsClient()

    with pytest.raises(TypeError, match="arguments"):
        client.chatgpt.apps.call_tool("search", ["not", "an", "object"])
    with pytest.raises(ValueError, match="name"):
        client.chatgpt.apps.call_tool("")
    with pytest.raises(TypeError, match="body"):
        client.chatgpt.apps.launch_widget(["not", "an", "object"])
