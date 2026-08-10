from io import BytesIO
from pathlib import Path
import stat
import tarfile
import zipfile

import pytest

from codex_backend_sdk import OpenAI


def bundle_bytes(*, name="demo", extra=None):
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        manifest = f'{{"name":"{name}"}}'.encode()
        info = tarfile.TarInfo(".codex-plugin/plugin.json")
        info.size = len(manifest)
        archive.addfile(info, BytesIO(manifest))
        if extra is not None:
            archive.addfile(*extra)
    return buffer.getvalue()


def curated_bytes(*, manifest='{"plugins": []}', extra=None):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr("openai-plugins/.agents/plugins/marketplace.json", manifest)
        if extra is not None:
            archive.writestr(*extra)
    return buffer.getvalue()


class FakeDownloadResponse:
    def __init__(self, content, *, url="https://cdn.example.test/bundle", headers=None):
        self.content = content
        self.url = url
        self.headers = headers or {"Content-Length": str(len(content))}
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.content[:3]
        yield self.content[3:]

    def close(self):
        self.closed = True


class FakeBundleClient(OpenAI):
    def __init__(self, content):
        super().__init__()
        self.content = content
        self.calls = []


def configure_plugin_details(client):
    client.chatgpt.plugins.retrieve = lambda plugin_id, **kwargs: {
        "id": plugin_id,
        "name": "demo",
        "release": {
            "version": "1.0.0",
            "bundle_download_url": "https://cdn.example.test/plugin",
        },
    }
    client.chatgpt.plugins.skill = lambda plugin_id, skill_name: {
        "plugin_id": plugin_id,
        "name": skill_name,
        "skill_bundle_download_url": "https://cdn.example.test/skill",
    }
    client.chatgpt.plugins.curated_export = lambda: {
        "download_url": "https://cdn.example.test/curated.zip"
    }


def test_plugin_bundle_download_formats_do_not_forward_oauth(tmp_path: Path, monkeypatch):
    content = bundle_bytes()
    client = FakeBundleClient(content)
    configure_plugin_details(client)
    requests_seen = []
    responses = []

    def fake_get(url, **kwargs):
        requests_seen.append((url, kwargs))
        response = FakeDownloadResponse(content, url=url)
        responses.append(response)
        return response

    monkeypatch.setattr(
        "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get", fake_get
    )
    bundles = client.chatgpt.plugins.bundles

    assert bundles.download_plugin("plugins~demo") == content
    assert bundles.download_curated() == content
    assert bundles.download_skill(
        "plugins~demo", "skill", response_format="bytes_io"
    ).read() == content
    output = tmp_path / "bundle.tar.gz"
    assert bundles.download_plugin(
        "plugins~demo", response_format="file", output_path=output
    ) == output
    assert output.read_bytes() == content
    assert all("headers" not in kwargs for _, kwargs in requests_seen)
    assert all(response.closed for response in responses)


def test_curated_archive_extracts_atomically_and_strips_wrapper(
    tmp_path: Path, monkeypatch
):
    content = curated_bytes()
    client = FakeBundleClient(content)
    configure_plugin_details(client)
    monkeypatch.setattr(
        "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get",
        lambda *args, **kwargs: FakeDownloadResponse(content),
    )
    destination = tmp_path / "curated"

    result = client.chatgpt.plugins.bundles.extract_curated(destination)

    assert result == destination
    assert (destination / ".agents/plugins/marketplace.json").is_file()
    assert not (destination / "openai-plugins").exists()
    assert not list(tmp_path.glob("curated-plugins-*"))


def test_curated_archive_rejects_unsafe_entries_and_invalid_manifest(
    tmp_path: Path, monkeypatch
):
    client = FakeBundleClient(b"")
    configure_plugin_details(client)
    symlink = zipfile.ZipInfo("openai-plugins/link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    cases = [
        (curated_bytes(extra=("openai-plugins/../escape", b"x")), "unsafe path"),
        (curated_bytes(extra=(symlink, b"target")), "unsupported type"),
        (curated_bytes(manifest="[]"), "not a JSON object"),
    ]

    for index, (content, message) in enumerate(cases):
        monkeypatch.setattr(
            "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get",
            lambda *args, content=content, **kwargs: FakeDownloadResponse(content),
        )
        with pytest.raises(ValueError, match=message):
            client.chatgpt.plugins.bundles.extract_curated(
                tmp_path / f"curated-{index}"
            )


def test_plugin_bundle_extracts_atomically_and_validates_manifest(
    tmp_path: Path, monkeypatch
):
    content = bundle_bytes()
    client = FakeBundleClient(content)
    configure_plugin_details(client)
    monkeypatch.setattr(
        "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get",
        lambda *args, **kwargs: FakeDownloadResponse(content),
    )
    destination = tmp_path / "checkout"

    result = client.chatgpt.plugins.bundles.extract_plugin(
        "plugins~demo", destination
    )

    assert result == destination
    assert (destination / ".codex-plugin/plugin.json").is_file()
    assert not list(tmp_path.glob("remote-plugin-*"))


def test_plugin_bundle_rejects_links_traversal_and_name_mismatch(
    tmp_path: Path, monkeypatch
):
    client = FakeBundleClient(b"")
    configure_plugin_details(client)

    cases = []
    link = tarfile.TarInfo("linked")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    cases.append((bundle_bytes(extra=(link,)), "link"))

    traversal = tarfile.TarInfo("../escape")
    traversal.size = 1
    cases.append((bundle_bytes(extra=(traversal, BytesIO(b"x"))), "unsafe path"))
    cases.append((bundle_bytes(name="different"), "does not match"))

    for index, (content, message) in enumerate(cases):
        monkeypatch.setattr(
            "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get",
            lambda *args, content=content, **kwargs: FakeDownloadResponse(content),
        )
        with pytest.raises(ValueError, match=message):
            client.chatgpt.plugins.bundles.extract_plugin(
                "plugins~demo", tmp_path / f"checkout-{index}"
            )


def test_plugin_bundle_enforces_download_and_extracted_limits(tmp_path: Path, monkeypatch):
    content = bundle_bytes()
    client = FakeBundleClient(content)
    configure_plugin_details(client)
    monkeypatch.setattr(
        "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get",
        lambda *args, **kwargs: FakeDownloadResponse(
            content, headers={"Content-Length": "999"}
        ),
    )
    with pytest.raises(ValueError, match="download bytes"):
        client.chatgpt.plugins.bundles.download_plugin(
            "plugins~demo", max_bytes=10
        )

    monkeypatch.setattr(
        "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get",
        lambda *args, **kwargs: FakeDownloadResponse(content),
    )
    with pytest.raises(ValueError, match="extracted bytes"):
        client.chatgpt.plugins.bundles.extract_plugin(
            "plugins~demo", tmp_path / "checkout", max_extracted_bytes=1
        )

    curated = curated_bytes()
    monkeypatch.setattr(
        "codex_backend_sdk.resources.chatgpt_plugin_bundles.requests.get",
        lambda *args, **kwargs: FakeDownloadResponse(curated),
    )
    with pytest.raises(ValueError, match="extracted bytes"):
        client.chatgpt.plugins.bundles.extract_curated(
            tmp_path / "curated", max_extracted_bytes=1
        )


def test_plugin_bundle_rejects_insecure_urls_and_invalid_format(tmp_path: Path):
    client = FakeBundleClient(b"")
    client.chatgpt.plugins.retrieve = lambda *args, **kwargs: {
        "name": "demo",
        "release": {"bundle_download_url": "http://example.test/bundle"},
    }
    with pytest.raises(ValueError, match="HTTPS"):
        client.chatgpt.plugins.bundles.download_plugin("plugins~demo")
    with pytest.raises(ValueError, match="response_format"):
        client.chatgpt.plugins.bundles.download_plugin(
            "plugins~demo", response_format="path"
        )
    with pytest.raises(ValueError, match="output_path"):
        client.chatgpt.plugins.bundles.download_plugin(
            "plugins~demo", response_format="file"
        )
