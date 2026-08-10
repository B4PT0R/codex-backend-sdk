import pytest

from codex_backend_sdk import OpenAI


class FakePluginsClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.payloads = {}

    def _get_chatgpt(self, path, *, params=None, headers=None):
        self.calls.append(("GET", path, params, headers))
        payload = self.payloads[path]
        if isinstance(payload, list):
            return payload
        pages = payload if isinstance(payload, list) else None
        return pages.pop(0) if pages else payload

    def _request_chatgpt(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        enabled = path.endswith("/install")
        plugin_id = path.split("/")[-2]
        return FakeResponse({"id": plugin_id, "enabled": enabled})


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_plugin_feeds_match_official_codex_routes():
    client = FakePluginsClient()
    client.payloads = {
        "/plugins/featured": ["github", "google-drive"],
        "/plugins/export/curated": {"download_url": "https://example.test/plugins.zip"},
    }

    assert client.chatgpt.plugins.featured() == ["github", "google-drive"]
    assert client.chatgpt.plugins.featured(platform="chat") == ["github", "google-drive"]
    assert client.chatgpt.plugins.curated_export()["download_url"].endswith("plugins.zip")
    assert client.calls == [
        ("GET", "/plugins/featured", {"platform": "codex"}, None),
        ("GET", "/plugins/featured", {"platform": "chat"}, None),
        ("GET", "/plugins/export/curated", None, None),
    ]


def test_plugin_feeds_validate_private_response_boundaries():
    client = FakePluginsClient()
    client.payloads["/plugins/featured"] = ["valid", 3]
    client.payloads["/plugins/export/curated"] = {}

    with pytest.raises(RuntimeError, match="plugin-id list"):
        client.chatgpt.plugins.featured()
    with pytest.raises(RuntimeError, match="download URL"):
        client.chatgpt.plugins.curated_export()


def test_remote_plugin_catalog_search_and_detail_match_current_codex_contract():
    client = FakePluginsClient()
    page = {"plugins": [{"id": "plugins~linear"}], "pagination": {"next_page_token": None}}
    client.payloads = {
        "/ps/plugins/list": page,
        "/ps/plugins/search": page,
        "/ps/plugins/installed": page,
        "/ps/plugins/workspace/shared": page,
        "/ps/plugins/suggested": {"enabled": True, "plugins": []},
        "/ps/plugins/plugins~linear": {"id": "plugins~linear"},
    }
    plugins = client.chatgpt.plugins

    assert plugins.list()["plugins"][0]["id"] == "plugins~linear"
    assert plugins.search(
        "linear & docs/+", scope="GLOBAL", page_token="next page/+"
    )["plugins"]
    assert plugins.installed(include_download_urls=True)["plugins"]
    assert plugins.workspace_shared()["plugins"]
    assert plugins.suggested()["enabled"] is True
    assert plugins.retrieve("plugins~linear", include_download_urls=True)["id"] == (
        "plugins~linear"
    )

    headers = {"OAI-Product-Sku": "codex"}
    assert client.calls == [
        (
            "GET",
            "/ps/plugins/list",
            {"scope": "GLOBAL", "limit": 200},
            headers,
        ),
        (
            "GET",
            "/ps/plugins/search",
            {
                "q": "linear & docs/+",
                "limit": 16,
                "scope": "GLOBAL",
                "pageToken": "next page/+",
            },
            headers,
        ),
        (
            "GET",
            "/ps/plugins/installed",
            {"limit": 200, "includeDownloadUrls": True},
            headers,
        ),
        (
            "GET",
            "/ps/plugins/workspace/shared",
            {"limit": 200},
            headers,
        ),
        (
            "GET",
            "/ps/plugins/suggested",
            {"scope": "GLOBAL"},
            headers,
        ),
        (
            "GET",
            "/ps/plugins/plugins~linear",
            {"includeDownloadUrls": True},
            headers,
        ),
    ]


def test_remote_plugin_catalog_pagination_and_cycle_detection():
    client = FakePluginsClient()
    pages = iter([
        {"plugins": [{"id": "one"}], "pagination": {"next_page_token": "page-2"}},
        {"plugins": [{"id": "two"}], "pagination": {"next_page_token": None}},
    ])
    client._get_chatgpt = lambda *args, **kwargs: next(pages)

    assert [item["id"] for item in client.chatgpt.plugins.list_all()] == ["one", "two"]

    repeated = {"plugins": [], "pagination": {"next_page_token": "same"}}
    client._get_chatgpt = lambda *args, **kwargs: repeated
    with pytest.raises(RuntimeError, match="repeated"):
        client.chatgpt.plugins.installed_all()


def test_remote_plugin_installation_mutations_are_explicit_and_validated():
    client = FakePluginsClient()
    installation = client.chatgpt.plugins.installation

    assert installation.install("plugins~linear")["enabled"] is True
    assert installation.uninstall("plugins~linear")["enabled"] is False
    assert client.calls == [
        (
            "POST",
            "/ps/plugins/plugins~linear/install",
            {
                "params": {"includeAppsNeedingAuth": True},
                "headers": {"OAI-Product-Sku": "codex"},
            },
        ),
        (
            "POST",
            "/ps/plugins/plugins~linear/uninstall",
            {"params": None, "headers": {"OAI-Product-Sku": "codex"}},
        ),
    ]


def test_remote_plugin_boundaries_reject_invalid_inputs_and_pages():
    client = FakePluginsClient()
    client.payloads["/ps/plugins/list"] = {"plugins": "bad", "pagination": {}}
    with pytest.raises(RuntimeError, match="plugin list"):
        client.chatgpt.plugins.list()
    with pytest.raises(ValueError, match="scope"):
        client.chatgpt.plugins.list(scope="INVALID")
    with pytest.raises(ValueError, match="positive"):
        client.chatgpt.plugins.search("query", limit=0)
    with pytest.raises(ValueError, match="plugin_id"):
        client.chatgpt.plugins.installation.install("")
