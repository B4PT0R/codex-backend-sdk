import pytest

from codex_backend_sdk import OpenAI


class FakeChatGPTClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _get_chatgpt(self, path, *, params=None):
        self.calls.append(("GET", path, params))
        return {"path": path}

    def _post_chatgpt(self, path, *, body, timeout=None):
        self.calls.append(("POST", path, body))
        return {"path": path}

    def _patch_chatgpt(self, path, *, body=None, params=None):
        self.calls.append(("PATCH", path, body, params))
        return {"path": path}

    def _delete_chatgpt(self, path, *, params=None):
        self.calls.append(("DELETE", path, params))

    def _request_chatgpt(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return object()


def test_chatgpt_account_model_and_voice_reads_are_separate_resources():
    client = FakeChatGPTClient()

    client.chatgpt.account.me()
    client.chatgpt.account.system_hints()
    client.chatgpt.models.list()
    client.chatgpt.voice.voices()

    assert client.calls == [
        ("GET", "/me", None),
        ("GET", "/system_hints", None),
        ("GET", "/models", None),
        ("GET", "/settings/voices", None),
    ]


def test_chatgpt_conversation_crud_builds_desktop_routes():
    client = FakeChatGPTClient()

    client.chatgpt.conversations.list(limit=20, order="updated")
    client.chatgpt.conversations.retrieve("conv_1")
    client.chatgpt.conversations.rename("conv_1", "New title")
    client.chatgpt.conversations.update("conv_1", {"is_archived": True})
    client.chatgpt.conversations.delete("conv_1")

    assert client.calls == [
        ("GET", "/conversations", {"limit": 20, "order": "updated"}),
        ("GET", "/conversation/conv_1", None),
        ("POST", "/conversation/id/conv_1/rename", {"title": "New title"}),
        ("PATCH", "/conversation/conv_1", {"is_archived": True}, None),
        ("DELETE", "/conversation/id/conv_1", None),
    ]


def test_chatgpt_conversation_streams_preserve_raw_response():
    client = FakeChatGPTClient()

    result = client.chatgpt.conversations.create_stream({"action": "next"})

    assert result is not None
    assert client.calls == [
        (
            "POST",
            "/f/conversation",
            {
                "body": {"action": "next"},
                "headers": {"Accept": "text/event-stream"},
                "stream": True,
            },
        )
    ]


@pytest.fixture
def pronunciation_client():
    client = FakeChatGPTClient()
    response = type("Response", (), {"json": lambda self: {
        "base64": "SUQz",
        "contentType": "audio/mpeg",
    }})()
    client._request_chatgpt = lambda method, path, **kwargs: (
        client.calls.append((method, path, kwargs)) or response
    )
    return client


def test_chatgpt_pronunciation_synthesis_matches_desktop_payload(
    pronunciation_client,
):
    client = pronunciation_client

    result = client.chatgpt.voice.synthesize_pronunciation(
        text="Bonjour Baptiste",
        pronunciation_language="fr-FR",
    )

    assert result.content == b"ID3"
    assert result.content_type == "audio/mpeg"
    assert client.calls == [
        (
            "POST",
            "/pronunciation/synthesize",
            {
                "params": {"format": "mp3"},
                "body": {
                    "pronunciation_language": "fr-FR",
                    "speed": 1,
                    "text": "Bonjour Baptiste",
                },
            },
        )
    ]


def test_chatgpt_pronunciation_supports_in_memory_and_file_outputs(
    pronunciation_client,
    tmp_path,
):
    client = pronunciation_client
    data_uri = client.chatgpt.voice.synthesize_pronunciation(
        text="Bonjour",
        pronunciation_language="fr-FR",
        response_format="data_uri",
    )
    buffer = client.chatgpt.voice.synthesize_pronunciation(
        text="Bonjour",
        pronunciation_language="fr-FR",
        response_format="bytes_io",
    )
    output = client.chatgpt.voice.synthesize_pronunciation(
        text="Bonjour",
        pronunciation_language="fr-FR",
        response_format="file",
        output_path=tmp_path / "speech.mp3",
    )

    assert data_uri == "data:audio/mpeg;base64,SUQz"
    assert buffer.read() == b"ID3"
    assert output.read_bytes() == b"ID3"


def test_chatgpt_pronunciation_validates_output_selection(pronunciation_client):
    client = pronunciation_client

    with pytest.raises(ValueError, match="output_path.*required"):
        client.chatgpt.voice.synthesize_pronunciation(
            text="Bonjour",
            pronunciation_language="fr-FR",
            response_format="file",
        )
    with pytest.raises(ValueError, match="only valid"):
        client.chatgpt.voice.synthesize_pronunciation(
            text="Bonjour",
            pronunciation_language="fr-FR",
            output_path="unexpected.mp3",
        )


def test_chatgpt_resources_reject_empty_ids_and_non_object_payloads():
    client = FakeChatGPTClient()

    with pytest.raises(ValueError, match="conversation_id"):
        client.chatgpt.conversations.retrieve("")
    with pytest.raises(ValueError, match="query"):
        client.chatgpt.conversations.search("")
    with pytest.raises(TypeError, match="JSON object"):
        client.chatgpt.sentinel.prepare(["not", "an", "object"])


def test_chatgpt_projects_cover_desktop_project_routes():
    client = FakeChatGPTClient()

    client.chatgpt.projects.list(limit=10, owned_only=False)
    client.chatgpt.projects.retrieve("project_1")
    client.chatgpt.projects.create({"name": "Personal"})
    client.chatgpt.projects.attach_files("project_1", {"file_ids": ["file_1"]})
    client.chatgpt.projects.delete_file("project_1", "file_1")

    assert client.calls == [
        (
            "GET",
            "/gizmos/snorlax/sidebar",
            {
                "conversations_per_gizmo": 0,
                "cursor": None,
                "limit": 10,
                "owned_only": False,
            },
        ),
        ("GET", "/gizmos/project_1", None),
        ("POST", "/projects", {"name": "Personal"}),
        ("POST", "/projects/project_1/files", {"file_ids": ["file_1"]}),
        ("DELETE", "/projects/project_1/files/file_1", None),
    ]


def test_chatgpt_file_library_preserves_filters_and_soft_delete():
    client = FakeChatGPTClient()

    client.chatgpt.files.list_library_nodes(cursor="cursor_1", limit=25)
    client.chatgpt.files.library_directory_path("directory_1")
    client.chatgpt.files.delete_library_file(
        "library_1",
        file_id="file_1",
        file_name="notes.md",
        soft_delete=True,
    )

    assert client.calls == [
        ("GET", "/files/library/nodes", {"cursor": "cursor_1", "limit": 25}),
        (
            "GET",
            "/files/library/directories/path",
            {"directory_id": "directory_1"},
        ),
        (
            "DELETE",
            "/files/library/files/library_1",
            {"file_id": "file_1", "file_name": "notes.md", "soft_delete": True},
        ),
    ]


def test_chatgpt_pins_and_shares_use_explicit_mutations():
    client = FakeChatGPTClient()

    client.chatgpt.pins.set("conversation", "conv_1", pinned=True)
    client.chatgpt.pins.set("conversation", "conv_1", pinned=False)
    client.chatgpt.shares.create({"conversation_id": "conv_1"})
    client.chatgpt.shares.update("share_1", {"is_public": False})

    assert client.calls == [
        ("POST", "/pins/conversation/conv_1", {}),
        ("DELETE", "/pins/conversation/conv_1", None),
        ("POST", "/share/v2/create", {"conversation_id": "conv_1"}),
        ("PATCH", "/share/share_1", {"is_public": False}, None),
    ]
