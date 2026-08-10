import requests

import pytest

from codex_backend_sdk import OpenAI


class FakeProductClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.project_pages = [
            {"items": [{"id": "project-1"}], "cursor": "page-2"},
            {"items": [{"id": "project-2"}], "cursor": None},
        ]

    def _get_chatgpt(self, path, *, params=None):
        self.calls.append(("GET", path, params))
        if path == "/gizmos/snorlax/sidebar":
            return self.project_pages.pop(0)
        if path == "/celsius/ws/user":
            return {"websocket_url": "wss://example.test/conversations"}
        return {"path": path}

    def _post_chatgpt(self, path, *, body, **kwargs):
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


def test_gizmo_and_project_routes_encode_path_parameters():
    client = FakeProductClient()

    client.chatgpt.gizmos.retrieve("gizmo /1")
    client.chatgpt.projects.retrieve("project /1")
    client.chatgpt.projects.update("project /1", {"name": "New"})
    client.chatgpt.projects.delete_file("project /1", "file /1")

    assert client.calls == [
        ("GET", "/gizmos/gizmo%20%2F1", None),
        ("GET", "/gizmos/project%20%2F1", None),
        ("PATCH", "/projects/project%20%2F1", {"name": "New"}, None),
        ("DELETE", "/projects/project%20%2F1/files/file%20%2F1", None),
    ]


def test_projects_list_all_paginates_without_losing_options():
    client = FakeProductClient()

    projects = client.chatgpt.projects.list_all(
        conversations_per_project=2, owned_only=False
    )

    assert [project["id"] for project in projects] == ["project-1", "project-2"]
    assert client.calls == [
        (
            "GET",
            "/gizmos/snorlax/sidebar",
            {
                "conversations_per_gizmo": 2,
                "cursor": None,
                "limit": 20,
                "owned_only": False,
            },
        ),
        (
            "GET",
            "/gizmos/snorlax/sidebar",
            {
                "conversations_per_gizmo": 2,
                "cursor": "page-2",
                "limit": 20,
                "owned_only": False,
            },
        ),
    ]


def test_conversation_subagent_websocket_and_widget_routes():
    client = FakeProductClient()

    assert client.chatgpt.conversations.websocket_url().startswith("wss://")
    client.chatgpt.conversations.subagent_thread_turns(
        "conversation-1", "thread-1", limit=3
    )
    client.chatgpt.conversations.rate("conversation /1", {"rating": "thumbs_up"})
    client.chatgpt.conversations.persist_dil_view_state(
        "conversation /1", "message /1", {"expanded": True}
    )
    client.chatgpt.conversations.refresh_widget(
        "conversation /1", "message /1", ref_index=2
    )

    assert client.calls == [
        ("GET", "/celsius/ws/user", None),
        (
            "GET",
            "/flora/subagent/thread/turns",
            {"conversationId": "conversation-1", "threadId": "thread-1", "limit": 3},
        ),
        (
            "POST",
            "/conversation/conversation%20%2F1/rating",
            {"rating": "thumbs_up"},
        ),
        (
            "POST",
            "/conversation/conversation%20%2F1/message/message%20%2F1/dil/view_state",
            {"expanded": True},
        ),
        (
            "POST",
            "/conversation/conversation%20%2F1/message/message%20%2F1/genui/refresh_widget",
            {"ref_index": 2},
        ),
    ]


def test_model_catalogs_hints_and_optional_slugs_follow_desktop_contract():
    client = FakeProductClient()

    client.chatgpt.models.config("model-1")
    client.chatgpt.models.third_party()
    client.chatgpt.models.system_hints(mode="custom_agents", exclude_logo=False)
    client.chatgpt.models.custom_agent_system_hint(
        "agent /1", system_hint="concise"
    )

    assert client.calls == [
        ("GET", "/models/config", {"slug": "model-1"}),
        ("GET", "/tpp/models/", {"iim": False, "include_icons": False}),
        (
            "GET",
            "/system_hints",
            {"mode": "custom_agents", "exclude_logo": False},
        ),
        (
            "GET",
            "/hermes/agent/agent%20%2F1/system-hint",
            {"system_hint": "concise"},
        ),
    ]

    response = requests.Response()
    response.status_code = 404
    error = requests.HTTPError(response=response)
    client._get_chatgpt = lambda path, params=None: (_ for _ in ()).throw(error)
    assert client.chatgpt.models.slugs() is None


def test_account_preference_mutations_are_explicit_query_updates():
    client = FakeProductClient()

    client.chatgpt.account.set_voice("coral")
    client.chatgpt.account.set_ultra_effort_enabled(True)
    client.chatgpt.account.opt_out_of_trusted_contact_prompts()

    assert client.calls == [
        (
            "PATCH",
            "/settings/account_user_setting",
            {"params": {"feature": "voice_name", "value": "coral"}},
        ),
        (
            "PATCH",
            "/settings/account_user_setting",
            {"params": {"feature": "model_picker_persists_ultra_effort", "value": True}},
        ),
        (
            "PATCH",
            "/settings/account_user_setting",
            {"params": {"feature": "trusted_contacts_opted_out_at", "value": True}},
        ),
    ]


def test_project_and_conversation_helpers_validate_pagination_and_indices():
    client = FakeProductClient()

    with pytest.raises(ValueError, match="positive"):
        client.chatgpt.projects.list(limit=0)
    with pytest.raises(ValueError, match="positive"):
        client.chatgpt.conversations.subagent_thread_turns("conversation", "thread", limit=0)
    with pytest.raises(ValueError, match="non-negative"):
        client.chatgpt.conversations.refresh_widget(
            "conversation", "message", ref_index=-1
        )
