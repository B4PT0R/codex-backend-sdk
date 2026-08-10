import pytest

from codex_backend_sdk import OpenAI


class FakePluginsClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.payloads = {}

    def _get_chatgpt(self, path, *, params=None):
        self.calls.append(("GET", path, params))
        return self.payloads[path]


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
        ("GET", "/plugins/featured", {"platform": "codex"}),
        ("GET", "/plugins/featured", {"platform": "chat"}),
        ("GET", "/plugins/export/curated", None),
    ]


def test_plugin_feeds_validate_private_response_boundaries():
    client = FakePluginsClient()
    client.payloads["/plugins/featured"] = ["valid", 3]
    client.payloads["/plugins/export/curated"] = {}

    with pytest.raises(RuntimeError, match="plugin-id list"):
        client.chatgpt.plugins.featured()
    with pytest.raises(RuntimeError, match="download URL"):
        client.chatgpt.plugins.curated_export()
