import json

import pytest

from codex_backend_sdk import ChatGPTAppsProtocolError, OpenAI


class FakeResponse:
    def __init__(self, payload=None, *, status=200, headers=None, text=None):
        self.status_code = status
        self.headers = headers or {"content-type": "application/json"}
        if text is not None:
            self.text = text
            self.content = text.encode()
        elif payload is None:
            self.text = ""
            self.content = b""
        else:
            self.text = json.dumps(payload)
            self.content = self.text.encode()

    def json(self):
        return json.loads(self.text)


class FakeHostedClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.responses = []

    def _request_chatgpt(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.responses.pop(0)


def rpc_result(request_id, result, **response_kwargs):
    return FakeResponse(
        {"jsonrpc": "2.0", "id": request_id, "result": result}, **response_kwargs
    )


def test_hosted_mcp_initializes_with_official_protocol_and_headers():
    client = FakeHostedClient()
    client.responses = [
        rpc_result(
            1,
            {"protocolVersion": "2025-06-18", "capabilities": {}},
            headers={
                "content-type": "application/json",
                "mcp-session-id": "session-1",
            },
        ),
        FakeResponse(status=204),
    ]

    connection = client.chatgpt.apps.connect_hosted_mcp(originator="test-harness")

    assert connection.session_id == "session-1"
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/ps/mcp")
    assert kwargs["body"] == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "codex-backend-sdk", "version": "0.3.10"},
        },
    }
    assert kwargs["headers"] == {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "X-OpenAI-Product-Sku": "codex",
        "originator": "test-harness",
    }
    assert client.calls[1][2]["headers"]["Mcp-Session-Id"] == "session-1"
    assert client.calls[1][2]["body"]["method"] == "notifications/initialized"


def test_hosted_mcp_exposes_catalog_resources_calls_and_session_close():
    client = FakeHostedClient()
    client.responses = [
        rpc_result(1, {"tools": [{"name": "search"}]}),
        rpc_result(2, {"resources": [{"uri": "ui://widget"}]}),
        rpc_result(3, {"resourceTemplates": []}),
        rpc_result(4, {"contents": [{"uri": "ui://widget", "text": "hello"}]}),
        rpc_result(5, {"content": [{"type": "text", "text": "done"}]}),
        FakeResponse(status=204),
    ]
    connection = client.chatgpt.apps.connect_hosted_mcp(initialize=False)
    connection._session_id = "session-1"

    assert connection.list_tools()["tools"][0]["name"] == "search"
    assert connection.list_resources()["resources"][0]["uri"] == "ui://widget"
    assert connection.list_resource_templates()["resourceTemplates"] == []
    assert connection.read_resource("ui://widget")["contents"][0]["text"] == "hello"
    assert connection.call_tool(
        "search", {"query": "hello"}, meta={"_codex_apps": {"call_id": "call-1"}}
    )["content"]
    connection.close()

    assert client.calls[4][2]["body"]["params"] == {
        "name": "search",
        "arguments": {"query": "hello"},
        "_meta": {"_codex_apps": {"call_id": "call-1"}},
    }
    assert client.calls[5][0:2] == ("DELETE", "/ps/mcp")
    assert connection.session_id is None


def test_hosted_mcp_decodes_sse_and_selects_matching_response():
    client = FakeHostedClient()
    client.responses = [FakeResponse(
        headers={"content-type": "text/event-stream"},
        text=(
            'event: message\n'
            'data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed"}\n\n'
            'event: message\n'
            'data: {"jsonrpc":"2.0","id":"catalog","result":{"tools":[]}}\n\n'
        ),
    )]
    connection = client.chatgpt.apps.connect_hosted_mcp(initialize=False)

    result = connection.request("tools/list", request_id="catalog")

    assert result == {"tools": []}


def test_hosted_mcp_surfaces_json_rpc_errors_and_missing_responses():
    client = FakeHostedClient()
    client.responses = [FakeResponse({
        "jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "unknown"}
    })]
    connection = client.chatgpt.apps.connect_hosted_mcp(initialize=False)

    with pytest.raises(ChatGPTAppsProtocolError, match="unknown"):
        connection.request("missing")

    client.responses = [FakeResponse(status=204)]
    with pytest.raises(ChatGPTAppsProtocolError, match="request id"):
        connection.request("tools/list")


def test_hosted_mcp_context_manager_initializes_and_closes_sessions():
    client = FakeHostedClient()
    client.responses = [
        rpc_result(
            1,
            {"protocolVersion": "2025-06-18", "capabilities": {}},
            headers={"content-type": "application/json", "mcp-session-id": "session-1"},
        ),
        FakeResponse(status=204),
        FakeResponse(status=204),
    ]

    with client.chatgpt.apps.connect_hosted_mcp(initialize=False) as connection:
        assert connection.initialize_result is not None

    assert client.calls[-1][0] == "DELETE"
