from codex_backend_sdk import OpenAI


class FakeCodexClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.wham_gets = []
        self.chatgpt_gets = []
        self.posts = []

    def _get_wham(self, path, *, params=None):
        self.wham_gets.append((path, params))
        if path == "/wham/usage":
            return {"rate_limit": {"allowed": True}}
        if path == "/wham/config/requirements":
            return {"requirements": [{"name": "network"}]}
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
        raise AssertionError(f"Unexpected WHAM path: {path}")

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
            return FakeJSONResponse({"output": [{"memory_summary": "summary"}]})
        raise AssertionError(f"Unexpected Codex post path: {path}")


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
            {
                "id": "trace_1",
                "metadata": {"source_path": "/tmp/memory.jsonl"},
                "items": [{"type": "message", "content": "remember me"}],
            }
        ],
        reasoning={"effort": "low"},
    )

    assert response == {"output": [{"memory_summary": "summary"}]}
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
