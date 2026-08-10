import json

import pytest

from codex_backend_sdk import OpenAI


class FakeResponse:
    def __init__(self, content=b"file-bytes", *, lines=None):
        self.content = content
        self._lines = lines or []
        self.closed = False

    def iter_lines(self, *, decode_unicode=False):
        return iter(self._lines)

    def close(self):
        self.closed = True


class FakeSearchFilesClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.download_response = FakeResponse()
        self.stream_response = FakeResponse()

    def _get_chatgpt(self, path, *, params=None):
        self.calls.append(("GET", path, params))
        if "/download" in path:
            return {"download_url": "https://cdn.example.test/signed"}
        return {"items": [], "cursor": None}

    def _request_chatgpt(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.stream_response

    def _download_chatgpt_link(self, url):
        self.calls.append(("DOWNLOAD", url))
        return self.download_response


def test_global_search_preserves_sources_cursor_and_limit():
    client = FakeSearchFilesClient()

    result = client.chatgpt.search.global_search(
        "codex", cursor="next", limit=5, sources=("conversation", "file")
    )

    assert result["items"] == []
    assert client.calls == [
        (
            "GET",
            "/global/search",
            {
                "query": "codex",
                "limit": 5,
                "sources": ["conversation", "file"],
                "cursor": "next",
            },
        )
    ]


def test_global_search_validates_query_limit_and_sources():
    client = FakeSearchFilesClient()

    with pytest.raises(ValueError, match="query"):
        client.chatgpt.search.global_search("")
    with pytest.raises(ValueError, match="positive"):
        client.chatgpt.search.global_search("query", limit=0)
    with pytest.raises(ValueError, match="search source"):
        client.chatgpt.search.global_search("query", sources=())


def test_sidebar_stream_preserves_raw_response_and_integrity_headers():
    client = FakeSearchFilesClient()

    response = client.chatgpt.conversations.sidebar_stream(
        {"action": "next"}, headers={"openai-sentinel-chat-requirements-token": "token"}
    )

    assert response is client.stream_response
    assert client.calls == [
        (
            "POST",
            "/sidebar/conversation",
            {
                "body": {"action": "next"},
                "headers": {
                    "Accept": "text/event-stream",
                    "openai-sentinel-chat-requirements-token": "token",
                },
                "stream": True,
            },
        )
    ]


def test_file_download_supports_bytes_memory_file_and_raw_response(tmp_path):
    client = FakeSearchFilesClient()

    content = client.chatgpt.files.download("file-1")
    buffer = client.chatgpt.files.download_attachment(
        "conversation-1", "file-1", response_format="bytes_io"
    )
    destination = client.chatgpt.files.download(
        "file-1", response_format="file", output_path=tmp_path / "file.bin"
    )
    response = client.chatgpt.files.download("file-1", response_format="response")

    assert content == b"file-bytes"
    assert buffer.read() == b"file-bytes"
    assert destination.read_bytes() == b"file-bytes"
    assert response is client.download_response


def test_file_download_validates_backend_link_and_output_selection():
    client = FakeSearchFilesClient()

    with pytest.raises(ValueError, match="output_path.*required"):
        client.chatgpt.files.download("file-1", response_format="file")
    with pytest.raises(ValueError, match="only valid"):
        client.chatgpt.files.download("file-1", output_path="unexpected")
    client._get_chatgpt = lambda path, params=None: {}
    with pytest.raises(RuntimeError, match="download_url"):
        client.chatgpt.files.download("file-1")


def test_process_upload_events_yields_ndjson_and_closes_response():
    client = FakeSearchFilesClient()
    client.stream_response = FakeResponse(lines=[
        json.dumps({"type": "progress", "progress": 0.5}),
        "",
        json.dumps({"type": "complete", "library_file_id": "library-1"}),
    ])

    events = list(client.chatgpt.files.process_upload_events({"file_id": "file-1"}))

    assert events[-1]["library_file_id"] == "library-1"
    assert client.stream_response.closed is True
    assert client.calls == [
        (
            "POST",
            "/files/process_upload_stream",
            {
                "body": {"file_id": "file-1"},
                "headers": {"Accept": "application/x-ndjson"},
                "stream": True,
            },
        )
    ]


def test_process_upload_events_rejects_non_object_events_and_closes():
    client = FakeSearchFilesClient()
    client.stream_response = FakeResponse(lines=["[]"])

    with pytest.raises(RuntimeError, match="non-object"):
        list(client.chatgpt.files.process_upload_events({"file_id": "file-1"}))
    assert client.stream_response.closed is True
