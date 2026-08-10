from pathlib import Path

import pytest

from codex_backend_sdk import (
    ConsumeRateLimitResetCreditResponse,
    MemorySummarizeResponse,
    OpenAI,
    RateLimitResetCredits,
    RawMemory,
)


class FakeCodexClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.wham_gets = []
        self.chatgpt_gets = []
        self.posts = []
        self.wham_posts = []
        self.wham_patches = []
        self.wham_deletes = []

    def _get_wham(self, path, *, params=None):
        self.wham_gets.append((path, params))
        if path == "/wham/usage":
            return {"rate_limit": {"allowed": True}}
        if path == "/wham/config/requirements":
            return {"requirements": [{"name": "network"}]}
        if path == "/wham/config/bundle":
            return {"bundle": {"version": "1"}}
        if path == "/wham/settings/user":
            return {"settings": {"theme": "system"}}
        if path == "/wham/settings/configs/user-preferences":
            return {"configs": [{"key": "branch_name_template"}]}
        if path == "/wham/accounts/check":
            return {"account": {"eligible": True}}
        if path == "/wham/profiles/me":
            return {"profile": {"plan_type": "pro"}}
        if path == "/wham/workspace-messages":
            return {"messages": []}
        if path == "/wham/tasks/list":
            return {"items": [{"id": "task_1", "title": "Task"}], "cursor": None}
        if path == "/wham/tasks/task_1":
            return {"task": {"id": "task_1"}}
        if path == "/wham/tasks/task_1/turns":
            return {"turn_mapping": {}, "current_turn_id": "turn_1"}
        if path == "/wham/tasks/task_1/turns/turn_1/sibling_turns":
            return {"sibling_turns": []}
        if path == "/wham/environments":
            return [{"id": "env_1", "label": "default"}]
        if path == "/wham/usage/daily-token-usage-breakdown":
            return {"days": []}
        if path == "/wham/usage/credit-usage-events":
            return {"events": []}
        if path == "/wham/tasks/task_1/turns/turn_1":
            return {"id": "turn_1"}
        if path == "/wham/tasks/task_1/turns/turn_1/logs":
            return {"logs": []}
        if path == "/wham/environments/search":
            return {"items": []}
        if path == "/wham/environments/env_1/with-creator-and-machine":
            return {"id": "env_1", "creator": {"id": "user_1"}}
        if path == "/wham/machines":
            return {"items": []}
        if path == "/wham/github/branches/github-repo_1/search":
            return {"items": []}
        raise AssertionError(f"Unexpected WHAM path: {path}")

    def _post_wham(self, path, *, body=None, timeout=None):
        self.wham_posts.append((path, body))
        if path == "/wham/tasks":
            return {"task": {"id": "task_2"}}
        if path.startswith("/wham/tasks/task_1/"):
            return {"ok": True}
        if path == "/wham/usage/thread_usage/query":
            return {"threads": []}
        if path == "/wham/environments/env_1/reset-cache":
            return {"ok": True}
        raise AssertionError(f"Unexpected WHAM path: {path}")

    def _patch_wham(self, path, *, body, timeout=None):
        self.wham_patches.append((path, body))
        return {"id": "env_1", **body}

    def _delete_wham(self, path, *, params=None, timeout=None):
        self.wham_deletes.append((path, params))

    def _get(self, path, *, params=None):
        if path == "/rate-limit-reset-credits":
            return {
                "available_count": 1,
                "total_earned_count": 2,
                "credits": [{
                    "id": "credit_1",
                    "reset_type": "codex_rate_limits",
                    "status": "available",
                    "granted_at": "2026-07-01T00:00:00Z",
                    "expires_at": "2026-08-01T00:00:00Z",
                    "title": "Full reset",
                }],
            }
        raise AssertionError(f"Unexpected Codex get path: {path}")

    def _get_chatgpt(self, path):
        self.chatgpt_gets.append(path)
        if path == "/memories":
            return {
                "memories": [{"id": "mem_1", "content": "Remember this", "status": "enabled"}],
                "memory_num_tokens": 2,
                "memory_max_tokens": 1000,
            }
        if path == "/user_system_messages":
            return {"object": "user_system_message_detail", "enabled": True}
        raise AssertionError(f"Unexpected path: {path}")

    def _post(self, path, *, body, stream=False):
        self.posts.append((path, body, stream))
        if path == "/memories/trace_summarize":
            return FakeJSONResponse({
                "output": [{"trace_summary": "raw", "memory_summary": "summary"}]
            })
        if path == "/rate-limit-reset-credits/consume":
            return FakeJSONResponse({"code": "reset", "windows_reset": 2})
        raise AssertionError(f"Unexpected Codex post path: {path}")

    def _post_chatgpt_raw(self, path, **kwargs):
        file_tuple = kwargs["files"]["file"]
        self.posts.append(
            (path, file_tuple[0], file_tuple[1].read(), file_tuple[2])
        )
        return FakeJSONResponse({"asset_pointer": "asset://profile-photo"})


class FakeJSONResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_codex_usage_still_calls_wham_usage():
    client = FakeCodexClient()

    usage = client.codex.usage()

    assert usage["rate_limit"]["allowed"] is True
    assert client.wham_gets == [("/wham/usage", None)]


def test_codex_rate_limit_reset_credits_list_returns_typed_details():
    client = FakeCodexClient()

    result = client.codex.rate_limit_reset_credits.list()

    assert isinstance(result, RateLimitResetCredits)
    assert result.available_count == 1
    assert result.total_earned_count == 2
    assert result.credits[0].id == "credit_1"
    assert result.credits[0].title == "Full reset"


def test_codex_rate_limit_reset_credits_consume_posts_idempotency_and_credit_ids():
    client = FakeCodexClient()

    result = client.codex.rate_limit_reset_credits.consume(
        redeem_request_id="redeem_1",
        credit_id="credit_1",
    )

    assert isinstance(result, ConsumeRateLimitResetCreditResponse)
    assert result.code == "reset"
    assert result.windows_reset == 2
    assert client.posts == [
        (
            "/rate-limit-reset-credits/consume",
            {"redeem_request_id": "redeem_1", "credit_id": "credit_1"},
            False,
        )
    ]


def test_codex_rate_limit_reset_credits_rejects_empty_identifiers():
    client = FakeCodexClient()

    with pytest.raises(ValueError, match="redeem_request_id"):
        client.codex.rate_limit_reset_credits.consume(redeem_request_id="")
    with pytest.raises(ValueError, match="credit_id"):
        client.codex.rate_limit_reset_credits.consume(
            redeem_request_id="redeem_1",
            credit_id="",
        )


def test_codex_memories_list_returns_raw_chatgpt_payload():
    client = FakeCodexClient()

    memories = client.codex.memories.list()

    assert memories["memories"][0]["id"] == "mem_1"
    assert client.chatgpt_gets == ["/memories"]


def test_codex_memories_trace_summarize_posts_codex_payload():
    client = FakeCodexClient()

    response = client.codex.memories.trace_summarize(
        model="gpt-test",
        traces=[
            RawMemory(
                id="trace_1",
                metadata={"source_path": "/tmp/memory.jsonl"},
                items=[{"type": "message", "content": "remember me"}],
            )
        ],
        reasoning={"effort": "low"},
    )

    assert isinstance(response, MemorySummarizeResponse)
    assert response.output[0].raw_memory == "raw"
    assert response.output[0].memory_summary == "summary"
    assert client.posts == [
        (
            "/memories/trace_summarize",
            {
                "model": "gpt-test",
                "traces": [
                    {
                        "id": "trace_1",
                        "metadata": {"source_path": "/tmp/memory.jsonl"},
                        "items": [{"type": "message", "content": "remember me"}],
                    }
                ],
                "reasoning": {"effort": "low"},
            },
            False,
        )
    ]


def test_codex_user_system_messages_retrieve_returns_raw_chatgpt_payload():
    client = FakeCodexClient()

    messages = client.codex.user_system_messages.retrieve()

    assert messages == {"object": "user_system_message_detail", "enabled": True}
    assert client.chatgpt_gets == ["/user_system_messages"]


def test_codex_tasks_list_passes_supported_filters():
    client = FakeCodexClient()

    tasks = client.codex.tasks.list(
        limit=2,
        cursor="cursor_1",
        task_filter="active",
        environment_id="env_1",
    )

    assert tasks["items"][0]["id"] == "task_1"
    assert client.wham_gets == [
        (
            "/wham/tasks/list",
            {
                "limit": 2,
                "cursor": "cursor_1",
                "task_filter": "active",
                "environment_id": "env_1",
            },
        )
    ]


def test_codex_tasks_retrieve_and_turns_return_raw_payloads():
    client = FakeCodexClient()

    assert client.codex.tasks.retrieve("task_1") == {"task": {"id": "task_1"}}
    assert client.codex.tasks.turns.list("task_1") == {
        "turn_mapping": {},
        "current_turn_id": "turn_1",
    }
    assert client.codex.tasks.turns.sibling_turns("task_1", "turn_1") == {"sibling_turns": []}
    assert client.wham_gets == [
        ("/wham/tasks/task_1", None),
        ("/wham/tasks/task_1/turns", None),
        ("/wham/tasks/task_1/turns/turn_1/sibling_turns", None),
    ]


def test_codex_environments_list_returns_raw_payload():
    client = FakeCodexClient()

    environments = client.codex.environments.list()

    assert environments == [{"id": "env_1", "label": "default"}]
    assert client.wham_gets == [("/wham/environments", None)]


def test_codex_config_requirements_returns_raw_payload():
    client = FakeCodexClient()

    requirements = client.codex.config.requirements()

    assert requirements == {"requirements": [{"name": "network"}]}
    assert client.wham_gets == [("/wham/config/requirements", None)]


def test_codex_account_profile_and_workspace_messages_return_raw_payloads():
    client = FakeCodexClient()

    assert client.codex.accounts.check() == {"account": {"eligible": True}}
    assert client.codex.profile.retrieve() == {"profile": {"plan_type": "pro"}}
    assert client.codex.workspace_messages.list() == {"messages": []}
    assert client.wham_gets == [
        ("/wham/accounts/check", None),
        ("/wham/profiles/me", None),
        ("/wham/workspace-messages", None),
    ]


def test_codex_profile_update_and_photo_follow_desktop_contract(tmp_path: Path):
    client = FakeCodexClient()
    photo = tmp_path / "avatar.png"
    photo.write_bytes(b"png")

    assert client.codex.profile.update({"display_name": "Ada"}) == {
        "id": "env_1",
        "display_name": "Ada",
    }
    assert client.codex.profile.set_photo(photo) == {
        "id": "env_1",
        "profile_asset_pointer": "asset://profile-photo",
    }
    assert client.posts == [
        (
            "/wham/profiles/me/photo",
            "avatar.png",
            b"png",
            "image/png",
        )
    ]
    assert client.wham_patches == [
        ("/wham/profiles/me", {"display_name": "Ada"}),
        (
            "/wham/profiles/me",
            {"profile_asset_pointer": "asset://profile-photo"},
        ),
    ]


def test_codex_profile_photo_validates_file_and_response(tmp_path: Path):
    client = FakeCodexClient()
    text = tmp_path / "avatar.txt"
    text.write_text("not an image")

    with pytest.raises(ValueError, match="image"):
        client.codex.profile.upload_photo(text)
    with pytest.raises(FileNotFoundError):
        client.codex.profile.upload_photo(tmp_path / "missing.png")

    photo = tmp_path / "avatar.webp"
    photo.write_bytes(b"webp")
    client._post_chatgpt_raw = lambda *args, **kwargs: FakeJSONResponse({})
    with pytest.raises(RuntimeError, match="asset_pointer"):
        client.codex.profile.upload_photo(photo)

    with pytest.raises(TypeError, match="JSON object"):
        client.codex.profile.update(["invalid"])


def test_codex_config_exposes_bundle_and_user_settings():
    client = FakeCodexClient()

    assert client.codex.config.bundle() == {"bundle": {"version": "1"}}
    assert client.codex.config.user_settings() == {"settings": {"theme": "system"}}
    assert client.codex.config.user_preferences_config() == {
        "configs": [{"key": "branch_name_template"}]
    }
    assert client.codex.config.update_user_settings(
        {"branch_name_template": "codex/{task}"}
    ) == {"id": "env_1", "branch_name_template": "codex/{task}"}
    assert client.wham_gets == [
        ("/wham/config/bundle", None),
        ("/wham/settings/user", None),
        ("/wham/settings/configs/user-preferences", None),
    ]
    assert client.wham_patches == [
        ("/wham/settings/user", {"branch_name_template": "codex/{task}"})
    ]
    with pytest.raises(TypeError, match="JSON object"):
        client.codex.config.update_user_settings(["invalid"])


def test_codex_tasks_create_posts_raw_backend_payload():
    client = FakeCodexClient()

    assert client.codex.tasks.create({"prompt": "Fix it"}) == {"task": {"id": "task_2"}}
    assert client.wham_posts == [("/wham/tasks", {"prompt": "Fix it"})]

    with pytest.raises(TypeError, match="JSON object"):
        client.codex.tasks.create(["invalid"])


def test_codex_desktop_usage_detail_routes_are_exposed():
    client = FakeCodexClient()

    assert client.codex.usage_details.daily_token_breakdown() == {"days": []}
    assert client.codex.usage_details.credit_events() == {"events": []}
    assert client.codex.usage_details.threads(["thread_1"]) == {"threads": []}
    assert client.wham_gets == [
        ("/wham/usage/daily-token-usage-breakdown", None),
        ("/wham/usage/credit-usage-events", None),
    ]
    assert client.wham_posts == [
        ("/wham/usage/thread_usage/query", {"thread_ids": ["thread_1"]})
    ]


def test_codex_desktop_task_turn_details_and_actions_are_exposed():
    client = FakeCodexClient()

    assert client.codex.tasks.turns.retrieve("task_1", "turn_1")["id"] == "turn_1"
    assert client.codex.tasks.turns.logs("task_1", "turn_1") == {"logs": []}
    client.codex.tasks.archive("task_1")
    client.codex.tasks.cancel("task_1")
    client.codex.tasks.recover("task_1")
    client.codex.tasks.mark_read("task_1")

    assert client.wham_posts == [
        ("/wham/tasks/task_1/archive", None),
        ("/wham/tasks/task_1/cancel", None),
        ("/wham/tasks/task_1/recover", None),
        ("/wham/tasks/task_1/mark_read", None),
    ]


def test_codex_desktop_environment_lifecycle_is_explicit():
    client = FakeCodexClient()

    client.codex.environments.search("demo", limit=10)
    client.codex.environments.retrieve("env_1")
    client.codex.environments.machines()
    client.codex.environments.update("env_1", {"label": "Updated"})
    client.codex.environments.reset_cache("env_1")
    client.codex.environments.delete("env_1")

    assert client.wham_gets == [
        ("/wham/environments/search", {"query": "demo", "limit": 10}),
        ("/wham/environments/env_1/with-creator-and-machine", None),
        ("/wham/machines", None),
    ]
    assert client.wham_patches == [
        ("/wham/environments/env_1", {"label": "Updated"})
    ]
    assert client.wham_posts == [
        ("/wham/environments/env_1/reset-cache", None)
    ]
    assert client.wham_deletes == [("/wham/environments/env_1", None)]


def test_codex_desktop_repository_branch_search_normalizes_id():
    client = FakeCodexClient()

    client.codex.repositories.branches("repo_1", "main", cursor="cursor_1")

    assert client.wham_gets == [
        (
            "/wham/github/branches/github-repo_1/search",
            {"query": "main", "page_size": 20, "cursor": "cursor_1"},
        )
    ]
