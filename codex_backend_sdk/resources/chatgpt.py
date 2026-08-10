"""ChatGPT product resources observed in the official Codex Desktop app."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Literal, TYPE_CHECKING

from .._models import ChatGPTSpeech
from .._utils import _jsonable
from .chatgpt_apps import ChatGPTApps

if TYPE_CHECKING:
    from .._client import CodexClient


def _required(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"Expected a non-empty value for `{name}` but received {value!r}")
    return value


def _object(value: Any, name: str = "body") -> dict[str, Any]:
    result = _jsonable(value)
    if not isinstance(result, dict):
        raise TypeError(f"Expected `{name}` to serialize to a JSON object.")
    return result


def _params(values: dict[str, Any]) -> dict[str, Any] | None:
    result = {key: value for key, value in values.items() if value is not None}
    return result or None


class ChatGPTResources:
    """Desktop-observed ChatGPT APIs kept separate from Codex APIs."""

    def __init__(self, client: CodexClient) -> None:
        self.account = ChatGPTAccount(client)
        self.apps = ChatGPTApps(client)
        self.conversations = ChatGPTConversations(client)
        self.files = ChatGPTFiles(client)
        self.models = ChatGPTModels(client)
        self.pins = ChatGPTPins(client)
        self.projects = ChatGPTProjects(client)
        self.shares = ChatGPTShares(client)
        self.voice = ChatGPTVoice(client)
        self.sentinel = ChatGPTSentinel(client)


class ChatGPTAccount:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def me(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/me")

    def settings(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/settings/user")

    def system_hints(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/system_hints")

    def memories(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/memories")

    def user_system_messages(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/user_system_messages")


class ChatGPTModels:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/models")

    def slugs(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/models/slugs")

    def config(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/models/config")


class ChatGPTVoice:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def voices(
        self,
        *,
        spoken_language: str | None = None,
        voice_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            "/settings/voices",
            params=_params({
                "spoken_language": spoken_language,
                "voice_mode": voice_mode,
            }),
        )

    def dictation_connect_info(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/codex/dictation-stream-connect-info", body=_object(body)
        )

    def synthesize_pronunciation(
        self,
        *,
        text: str,
        pronunciation_language: str,
        speed: float = 1,
        response_format: Literal["speech", "data_uri", "bytes_io", "file"] = "speech",
        output_path: str | Path | None = None,
    ) -> ChatGPTSpeech | str | BytesIO | Path:
        """Synthesize read-aloud audio without writing to disk by default."""
        _required(text, "text")
        _required(pronunciation_language, "pronunciation_language")
        if response_format not in {"speech", "data_uri", "bytes_io", "file"}:
            raise ValueError(f"Unsupported `response_format`: {response_format!r}")
        if response_format == "file" and output_path is None:
            raise ValueError("`output_path` is required when `response_format='file'`.")
        if response_format != "file" and output_path is not None:
            raise ValueError("`output_path` is only valid when `response_format='file'`.")

        speech = ChatGPTSpeech.model_validate(
            self._client._request_chatgpt(
                "POST",
                "/pronunciation/synthesize",
                params={"format": "mp3"},
                body={
                    "pronunciation_language": pronunciation_language,
                    "speed": speed,
                    "text": text,
                },
            ).json()
        )
        if response_format == "data_uri":
            return speech.data_uri
        if response_format == "bytes_io":
            return speech.to_bytes_io()
        if response_format == "file":
            return speech.write_to_file(output_path)
        return speech


class ChatGPTSentinel:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def prepare(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/sentinel/chat-requirements/prepare", body=_object(body)
        )

    def heartbeat(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt("/sentinel/heartbeat", body=_object(body))


class ChatGPTConversations:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        order: str | None = None,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            "/conversations",
            params=_params({"offset": offset, "limit": limit, "order": order}),
        )

    def search(self, query: str, **filters: Any) -> dict[str, Any]:
        _required(query, "query")
        return self._client._get_chatgpt(
            "/conversations/search", params={"query": query, **filters}
        )

    def batch(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt("/conversations/batch", body=_object(body))

    def retrieve(self, conversation_id: str) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/conversation/{_required(conversation_id, 'conversation_id')}"
        )

    def update(self, conversation_id: str, body: Any) -> dict[str, Any]:
        return self._client._patch_chatgpt(
            f"/conversation/{_required(conversation_id, 'conversation_id')}",
            body=_object(body),
        )

    def delete(self, conversation_id: str) -> None:
        self._client._delete_chatgpt(
            f"/conversation/id/{_required(conversation_id, 'conversation_id')}"
        )

    def rename(self, conversation_id: str, title: str) -> dict[str, Any]:
        _required(title, "title")
        return self._client._post_chatgpt(
            f"/conversation/id/{_required(conversation_id, 'conversation_id')}/rename",
            body={"title": title},
        )

    def branch(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt("/conversation/new_branch", body=_object(body))

    def prepare(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt("/f/conversation/prepare", body=_object(body))

    def create_stream(self, body: Any) -> requests.Response:
        return self._client._request_chatgpt(
            "POST",
            "/f/conversation",
            body=_object(body),
            headers={"Accept": "text/event-stream"},
            stream=True,
        )

    def resume_stream(self, body: Any) -> requests.Response:
        return self._client._request_chatgpt(
            "POST",
            "/f/conversation/resume",
            body=_object(body),
            headers={"Accept": "text/event-stream"},
            stream=True,
        )

    def files(self, conversation_id: str) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/conversations/{_required(conversation_id, 'conversation_id')}/files"
        )


class ChatGPTPins:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        *,
        item_type: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            "/pins", params=_params({"item_type": item_type, "limit": limit})
        )

    def set(self, item_type: str, item_id: str, *, pinned: bool) -> dict[str, Any] | None:
        item_type = _required(item_type, "item_type")
        item_id = _required(item_id, "item_id")
        path = f"/pins/{item_type}/{item_id}"
        if pinned:
            return self._client._post_chatgpt(path, body={})
        self._client._delete_chatgpt(path)
        return None


class ChatGPTProjects:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        *,
        conversations_per_project: int = 0,
        cursor: str | None = None,
        limit: int = 20,
        owned_only: bool = True,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            "/gizmos/snorlax/sidebar",
            params={
                "conversations_per_gizmo": conversations_per_project,
                "cursor": cursor,
                "limit": limit,
                "owned_only": owned_only,
            },
        )

    def retrieve(self, project_id_or_short_url: str) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/gizmos/{_required(project_id_or_short_url, 'project_id_or_short_url')}"
        )

    def create(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt("/projects", body=_object(body))

    def update(self, project_id: str, body: Any) -> dict[str, Any]:
        return self._client._patch_chatgpt(
            f"/projects/{_required(project_id, 'project_id')}", body=_object(body)
        )

    def delete(self, project_id: str) -> None:
        self._client._delete_chatgpt(f"/gizmos/{_required(project_id, 'project_id')}")

    def conversations(
        self,
        project_id: str,
        *,
        cursor: str | None = None,
        limit: int = 5,
        owned_only: bool = True,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/gizmos/{_required(project_id, 'project_id')}/conversations",
            params={"cursor": cursor, "limit": limit, "owned_only": owned_only},
        )

    def connector_scopes(
        self,
        project_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/projects/{_required(project_id, 'project_id')}/connector_scopes",
            params={"cursor": cursor, "limit": limit},
        )

    def saves(
        self,
        project_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/projects/{_required(project_id, 'project_id')}/saves",
            params={"cursor": cursor, "limit": limit},
        )

    def attach_files(self, project_id: str, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            f"/projects/{_required(project_id, 'project_id')}/files",
            body=_object(body),
        )

    def delete_file(self, project_id: str, file_id: str) -> None:
        self._client._delete_chatgpt(
            f"/projects/{_required(project_id, 'project_id')}/files/"
            f"{_required(file_id, 'file_id')}"
        )


class ChatGPTShares:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create(self, body: Any, *, use_v2: bool = True) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/share/v2/create" if use_v2 else "/share/create", body=_object(body)
        )

    def update(self, shared_conversation_id: str, body: Any) -> dict[str, Any]:
        return self._client._patch_chatgpt(
            f"/share/{_required(shared_conversation_id, 'shared_conversation_id')}",
            body=_object(body),
        )


class ChatGPTFiles:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def create(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt("/files", body=_object(body))

    def finalize(self, file_id: str, body: Any | None = None) -> dict[str, Any]:
        return self._client._post_chatgpt(
            f"/files/{_required(file_id, 'file_id')}/uploaded",
            body={} if body is None else _object(body),
        )

    def download_link(
        self,
        file_id: str,
        *,
        conversation_id: str | None = None,
        gizmo_id: str | None = None,
        post_id: str | None = None,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/files/download/{_required(file_id, 'file_id')}",
            params=_params({
                "conversation_id": conversation_id,
                "gizmo_id": gizmo_id,
                "post_id": post_id,
            }),
        )

    def conversation_files(
        self,
        conversation_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/conversations/{_required(conversation_id, 'conversation_id')}/files",
            params=_params({"cursor": cursor, "limit": limit}),
        )

    def attachment_info(
        self,
        conversation_id: str,
        file_id: str,
        *,
        gizmo_id: str | None = None,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/conversation/{_required(conversation_id, 'conversation_id')}/attachment/"
            f"{_required(file_id, 'file_id')}",
            params=_params({"gizmo_id": gizmo_id}),
        )

    def attachment_download_link(
        self,
        conversation_id: str,
        file_id: str,
        *,
        gizmo_id: str | None = None,
    ) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/conversation/{_required(conversation_id, 'conversation_id')}/attachment/"
            f"{_required(file_id, 'file_id')}/download",
            params=_params({"gizmo_id": gizmo_id}),
        )

    def list_library_files(self, body: Any | None = None) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/files/library", body={} if body is None else _object(body)
        )

    def list_library_nodes(self, **filters: Any) -> dict[str, Any]:
        return self._client._get_chatgpt(
            "/files/library/nodes", params=filters or None
        )

    def create_library_directory(self, body: Any) -> dict[str, Any]:
        return self._client._post_chatgpt(
            "/files/library/directories", body=_object(body)
        )

    def library_directory_path(self, directory_id: str) -> dict[str, Any]:
        return self._client._get_chatgpt(
            "/files/library/directories/path",
            params={"directory_id": _required(directory_id, "directory_id")},
        )

    def update_library_file(self, library_file_id: str, body: Any) -> dict[str, Any]:
        return self._client._patch_chatgpt(
            f"/files/library/files/{_required(library_file_id, 'library_file_id')}",
            body=_object(body),
        )

    def delete_library_file(
        self,
        library_file_id: str,
        *,
        file_id: str | None = None,
        file_name: str | None = None,
        soft_delete: bool | None = None,
    ) -> None:
        self._client._delete_chatgpt(
            f"/files/library/files/{_required(library_file_id, 'library_file_id')}",
            params=_params({
                "file_id": file_id,
                "file_name": file_name,
                "soft_delete": soft_delete,
            }),
        )

    def library_file_thumbnail(self, library_file_id: str) -> dict[str, Any]:
        return self._client._get_chatgpt(
            f"/files/library/files/{_required(library_file_id, 'library_file_id')}/thumbnail"
        )
