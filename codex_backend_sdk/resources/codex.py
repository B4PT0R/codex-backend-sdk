"""Codex and ChatGPT-only resources."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .._client import CodexClient


class CodexResources:
    """Codex-only endpoints that do not exist on the official OpenAI API."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.memories = CodexMemories(client)
        self.tasks = CodexTasks(client)
        self.environments = CodexEnvironments(client)
        self.config = CodexConfig(client)
        self.user_system_messages = CodexUserSystemMessages(client)

    def usage(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/usage")


class CodexMemories:
    """ChatGPT memory data for the authenticated account."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/memories")

    def trace_summarize(
        self,
        *,
        model: str,
        traces: list[dict[str, Any]],
        reasoning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")
        payload: dict[str, Any] = {"model": model, "traces": traces}
        if reasoning is not None:
            payload["reasoning"] = reasoning
        return self._client._post("/memories/trace_summarize", body=payload).json()


class CodexConfig:
    """Codex WHAM account configuration resources."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def requirements(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/config/requirements")


class CodexTasks:
    """Codex cloud task data for the authenticated account."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.turns = CodexTaskTurns(client)

    def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        task_filter: str | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        params = _clean_params({
            "limit": limit,
            "cursor": cursor,
            "task_filter": task_filter,
            "environment_id": environment_id,
        })
        return self._client._get_wham("/wham/tasks/list", params=params or None)

    def retrieve(self, task_id: str) -> dict[str, Any]:
        if not task_id:
            raise ValueError(f"Expected a non-empty value for `task_id` but received {task_id!r}")
        return self._client._get_wham(f"/wham/tasks/{task_id}")


class CodexTaskTurns:
    """Turn data for Codex cloud tasks."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(self, task_id: str) -> dict[str, Any]:
        if not task_id:
            raise ValueError(f"Expected a non-empty value for `task_id` but received {task_id!r}")
        return self._client._get_wham(f"/wham/tasks/{task_id}/turns")

    def sibling_turns(self, task_id: str, turn_id: str) -> dict[str, Any]:
        if not task_id:
            raise ValueError(f"Expected a non-empty value for `task_id` but received {task_id!r}")
        if not turn_id:
            raise ValueError(f"Expected a non-empty value for `turn_id` but received {turn_id!r}")
        return self._client._get_wham(f"/wham/tasks/{task_id}/turns/{turn_id}/sibling_turns")


class CodexEnvironments:
    """Codex cloud environment data for the authenticated account."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/environments")


class CodexUserSystemMessages:
    """ChatGPT customization instructions for the authenticated account."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def retrieve(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/user_system_messages")


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}
