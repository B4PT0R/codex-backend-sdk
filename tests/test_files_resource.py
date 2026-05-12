from pathlib import Path

from codex_backend_sdk import OpenAI, UploadedFile
from codex_backend_sdk.storage import TokenStore


class FakePutResponse:
    def __init__(self):
        self.raised = False

    def raise_for_status(self):
        self.raised = True


class FakeFilesClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.chatgpt_posts = []
        self._set_store(TokenStore(
            access_token="chatgpt-token",
            refresh_token="refresh-token",
            id_token_raw="id-token",
            account_id="account-id",
        ))

    def _post_chatgpt(self, path, *, body, timeout=None):
        self.chatgpt_posts.append((path, body, timeout))
        if path == "/files":
            return {"file_id": "file_123", "upload_url": "https://upload.example/file_123"}
        if path == "/files/file_123/uploaded":
            return {
                "status": "success",
                "download_url": "https://download.example/file_123",
                "file_name": "report.txt",
                "mime_type": "text/plain",
            }
        raise AssertionError(f"Unexpected ChatGPT post path: {path}")


def test_files_upload_uses_chatgpt_file_flow(tmp_path, monkeypatch):
    client = FakeFilesClient()
    file_path = tmp_path / "report.txt"
    file_path.write_text("hello")
    put_calls = []

    def fake_put(url, *, data, headers, timeout):
        put_calls.append((url, data.read(), headers, timeout))
        return FakePutResponse()

    monkeypatch.setattr("codex_backend_sdk.resources.files.requests.put", fake_put)

    uploaded = client.files.upload(file_path)

    assert isinstance(uploaded, UploadedFile)
    assert uploaded.file_id == "file_123"
    assert uploaded.uri == "sediment://file_123"
    assert uploaded.download_url == "https://download.example/file_123"
    assert uploaded.file_name == "report.txt"
    assert uploaded.file_size_bytes == 5
    assert uploaded.mime_type == "text/plain"
    assert uploaded.path == str(file_path)
    assert client.chatgpt_posts[0][:2] == (
        "/files",
        {"file_name": "report.txt", "file_size": 5, "use_case": "codex"},
    )
    assert client.chatgpt_posts[1][:2] == ("/files/file_123/uploaded", {})
    assert put_calls == [
        (
            "https://upload.example/file_123",
            b"hello",
            {"x-ms-blob-type": "BlockBlob", "Content-Length": "5"},
            120,
        )
    ]


def test_files_upload_rejects_missing_path():
    client = FakeFilesClient()

    try:
        client.files.upload(Path("/does/not/exist"))
    except FileNotFoundError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("missing path should fail before network calls")


def test_files_upload_retries_finalize_payload(tmp_path, monkeypatch):
    class RetryFilesClient(FakeFilesClient):
        def __init__(self):
            super().__init__()
            self.finalize_calls = 0

        def _post_chatgpt(self, path, *, body, timeout=None):
            if path == "/files/file_123/uploaded":
                self.finalize_calls += 1
                if self.finalize_calls == 1:
                    return {"status": "retry"}
            return super()._post_chatgpt(path, body=body, timeout=timeout)

    client = RetryFilesClient()
    file_path = tmp_path / "report.txt"
    file_path.write_text("hello")

    monkeypatch.setattr(
        "codex_backend_sdk.resources.files.requests.put",
        lambda *args, **kwargs: FakePutResponse(),
    )
    monkeypatch.setattr("codex_backend_sdk.resources.files.time.sleep", lambda delay: None)

    uploaded = client.files.upload(file_path, finalize_retry_delay=0)

    assert uploaded.file_id == "file_123"
    assert client.finalize_calls == 2
