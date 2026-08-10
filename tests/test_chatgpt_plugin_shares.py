from io import BytesIO
from pathlib import Path
import tarfile

import pytest

from codex_backend_sdk import OpenAI


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakePluginShareClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []

    def account_info(self):
        return {"account_id": "workspace-1"}

    def _get_chatgpt(self, path, *, params=None, headers=None):
        self.calls.append(("GET", path, params, headers))
        return {"plugins": [], "pagination": {"next_page_token": None}}

    def _request_chatgpt(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path.endswith("upload-url"):
            return FakeResponse(
                {
                    "file_id": "file-1",
                    "upload_url": "https://storage.example.test/signed",
                    "etag": "opaque-etag",
                }
            )
        if method == "PUT":
            return FakeResponse(
                {
                    "principals": kwargs["body"]["targets"],
                    "discoverability": kwargs["body"]["discoverability"],
                }
            )
        if method == "DELETE":
            return FakeResponse(status_code=204)
        return FakeResponse(
            {
                "plugin_id": "plugins~demo",
                "share_url": "https://example.test/share",
            }
        )


def test_plugin_share_created_page_matches_current_codex_contract():
    client = FakePluginShareClient()

    assert client.chatgpt.plugins.shares.created() == {
        "plugins": [],
        "pagination": {"next_page_token": None},
    }
    assert client.calls == [
        (
            "GET",
            "/ps/plugins/workspace/created",
            {"limit": 200},
            {"OAI-Product-Sku": "codex"},
        )
    ]


def test_plugin_share_publish_archive_uses_signed_azure_upload(
    tmp_path: Path, monkeypatch
):
    client = FakePluginShareClient()
    archive = tmp_path / "demo.tar.gz"
    archive.write_bytes(b"archive")
    uploaded = {}

    def fake_put(url, *, data, headers, timeout):
        uploaded.update(url=url, data=data, headers=headers, timeout=timeout)
        return FakeResponse(status_code=201)

    monkeypatch.setattr(
        "codex_backend_sdk.resources.chatgpt_plugin_shares.requests.put", fake_put
    )

    result = client.chatgpt.plugins.shares.publish_archive(
        archive,
        discoverability="PRIVATE",
        share_targets=[
            {"principal_type": "user", "principal_id": "user-1", "role": "editor"}
        ],
    )

    assert result["plugin_id"] == "plugins~demo"
    assert uploaded == {
        "url": "https://storage.example.test/signed",
        "data": b"archive",
        "headers": {
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": "application/gzip",
        },
        "timeout": 120,
    }
    assert "Authorization" not in uploaded["headers"]
    assert client.calls == [
        (
            "POST",
            "/public/plugins/workspace/upload-url",
            {
                "body": {
                    "filename": "demo.tar.gz",
                    "mime_type": "application/gzip",
                    "size_bytes": 7,
                },
                "headers": {"OAI-Product-Sku": "codex"},
            },
        ),
        (
            "POST",
            "/public/plugins/workspace",
            {
                "body": {
                    "file_id": "file-1",
                    "etag": "opaque-etag",
                    "discoverability": "PRIVATE",
                    "share_targets": [
                        {
                            "principal_type": "user",
                            "principal_id": "user-1",
                            "role": "editor",
                        }
                    ],
                },
                "headers": {"OAI-Product-Sku": "codex"},
            },
        ),
    ]


def test_unlisted_plugin_share_adds_workspace_reader_target():
    client = FakePluginShareClient()
    result = client.chatgpt.plugins.shares.update_targets(
        "plugins~demo",
        discoverability="UNLISTED",
        targets=[
            {"principal_type": "group", "principal_id": "group-1", "role": "reader"}
        ],
    )

    assert result["discoverability"] == "UNLISTED"
    body = client.calls[0][2]["body"]
    assert body == {
        "discoverability": "UNLISTED",
        "targets": [
            {"principal_type": "group", "principal_id": "group-1", "role": "reader"},
            {
                "principal_type": "workspace",
                "principal_id": "workspace-1",
                "role": "reader",
            },
        ],
    }


def test_plugin_share_delete_requires_official_no_content_status():
    client = FakePluginShareClient()
    client.chatgpt.plugins.shares.delete("plugins~demo")
    assert client.calls == [
        (
            "DELETE",
            "/public/plugins/workspace/plugins~demo",
            {"headers": {"OAI-Product-Sku": "codex"}},
        )
    ]


def test_plugin_directory_pack_is_rootless_and_rejects_links(tmp_path: Path, monkeypatch):
    client = FakePluginShareClient()
    plugin = tmp_path / "demo"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin/plugin.json").write_text('{"name":"demo"}')
    (plugin / "skills").mkdir()
    (plugin / "skills/example.md").write_text("skill")
    captured = {}

    def fake_publish(filename, content, **kwargs):
        captured.update(filename=filename, content=content, kwargs=kwargs)
        return {"plugin_id": "plugins~demo"}

    monkeypatch.setattr(client.chatgpt.plugins.shares, "_publish_bytes", fake_publish)
    client.chatgpt.plugins.shares.publish_directory(plugin)

    with tarfile.open(fileobj=BytesIO(captured["content"]), mode="r:gz") as archive:
        names = archive.getnames()
    assert captured["filename"] == "demo.tar.gz"
    assert ".codex-plugin/plugin.json" in names
    assert "skills/example.md" in names
    assert all(not name.startswith("demo/") for name in names)

    (plugin / "linked").symlink_to(plugin / "skills/example.md")
    with pytest.raises(ValueError, match="Unsupported"):
        client.chatgpt.plugins.shares.publish_directory(plugin)


def test_plugin_share_boundaries_reject_invalid_policy_and_uploads(tmp_path: Path):
    client = FakePluginShareClient()
    with pytest.raises(ValueError, match="discoverability"):
        client.chatgpt.plugins.shares.update_targets(
            "plugins~demo", discoverability="PUBLIC"
        )
    with pytest.raises(ValueError, match="principal"):
        client.chatgpt.plugins.shares.update_targets(
            "plugins~demo",
            discoverability="PRIVATE",
            targets=[{"principal_type": "alien", "principal_id": "x", "role": "reader"}],
        )
    with pytest.raises(ValueError, match="size_bytes"):
        client.chatgpt.plugins.shares.create_upload(
            filename="demo.tar.gz", size_bytes=60 * 1024 * 1024
        )
    with pytest.raises(ValueError, match="manifest"):
        client.chatgpt.plugins.shares.publish_directory(tmp_path)
