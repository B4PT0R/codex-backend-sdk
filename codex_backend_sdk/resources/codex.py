"""Codex and ChatGPT-only resources."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from .._models import (
    ConsumeRateLimitResetCreditResponse,
    MemorySummarizeResponse,
    RateLimitResetCredits,
)
from .._utils import _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


class CodexResources:
    """Codex-only endpoints that do not exist on the official OpenAI API."""

    def __init__(self, client: CodexClient) -> None:
        from .remote_control import RemoteControl
        from .worktree_snapshots import CodexWorktreeSnapshots

        self._client = client
        self.accounts = CodexAccounts(client)
        self.usage_details = CodexUsageDetails(client)
        self.profile = CodexProfile(client)
        self.memories = CodexMemories(client)
        self.tasks = CodexTasks(client)
        self.environments = CodexEnvironments(client)
        self.repositories = CodexRepositories(client)
        self.config = CodexConfig(client)
        self.workspace_messages = CodexWorkspaceMessages(client)
        self.worktree_snapshots = CodexWorktreeSnapshots(client)
        self.remote_control = RemoteControl(client)
        self.rate_limit_reset_credits = CodexRateLimitResetCredits(client)
        self.user_system_messages = CodexUserSystemMessages(client)

    def usage(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/usage")


class CodexAccounts:
    """Codex account availability and entitlement data."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def check(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/accounts/check")


class CodexUsageDetails:
    """Desktop-observed Codex usage and credit history."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def daily_token_breakdown(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/usage/daily-token-usage-breakdown")

    def credit_events(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/usage/credit-usage-events")

    def threads(self, thread_ids: list[str]) -> dict[str, Any]:
        if not thread_ids or any(not value for value in thread_ids):
            raise ValueError("Expected `thread_ids` to contain non-empty identifiers.")
        return self._client._post_wham(
            "/wham/usage/thread_usage/query", body={"thread_ids": thread_ids}
        )


class CodexProfile:
    """Authenticated Codex token-usage profile."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def retrieve(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/profiles/me")


class CodexRateLimitResetCredits:
    """Detailed Codex rate-limit reset credits for the authenticated account."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(self) -> RateLimitResetCredits:
        return RateLimitResetCredits.model_validate(
            self._client._get("/rate-limit-reset-credits")
        )

    def consume(
        self,
        *,
        redeem_request_id: str,
        credit_id: str | None = None,
    ) -> ConsumeRateLimitResetCreditResponse:
        if not redeem_request_id:
            raise ValueError(
                "Expected a non-empty value for `redeem_request_id` "
                f"but received {redeem_request_id!r}"
            )
        if credit_id == "":
            raise ValueError("Expected `credit_id` to be non-empty when provided")
        payload = {"redeem_request_id": redeem_request_id}
        if credit_id is not None:
            payload["credit_id"] = credit_id
        return ConsumeRateLimitResetCreditResponse.model_validate(
            self._client._post(
                "/rate-limit-reset-credits/consume",
                body=payload,
            ).json()
        )


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
        traces: list[Any],
        reasoning: Any = None,
    ) -> MemorySummarizeResponse:
        if not model:
            raise ValueError(f"Expected a non-empty value for `model` but received {model!r}")
        payload: dict[str, Any] = {"model": model, "traces": _jsonable(traces)}
        if reasoning is not None:
            payload["reasoning"] = _jsonable(reasoning)
        return MemorySummarizeResponse.model_validate(
            self._client._post("/memories/trace_summarize", body=payload).json()
        )


class CodexConfig:
    """Codex WHAM account configuration resources."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def requirements(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/config/requirements")

    def bundle(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/config/bundle")

    def user_settings(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/settings/user")


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

    def create(self, body: Any) -> dict[str, Any]:
        payload = _jsonable(body)
        if not isinstance(payload, dict):
            raise TypeError("Expected `body` to serialize to a JSON object.")
        return self._client._post_wham("/wham/tasks", body=payload)

    def archive(self, task_id: str) -> dict[str, Any]:
        return self._post_action(task_id, "archive")

    def cancel(self, task_id: str) -> dict[str, Any]:
        return self._post_action(task_id, "cancel")

    def recover(self, task_id: str) -> dict[str, Any]:
        return self._post_action(task_id, "recover")

    def mark_read(self, task_id: str) -> dict[str, Any]:
        return self._post_action(task_id, "mark_read")

    def _post_action(self, task_id: str, action: str) -> dict[str, Any]:
        if not task_id:
            raise ValueError(f"Expected a non-empty value for `task_id` but received {task_id!r}")
        return self._client._post_wham(f"/wham/tasks/{task_id}/{action}")


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

    def retrieve(self, task_id: str, turn_id: str) -> dict[str, Any]:
        task_id, turn_id = self._ids(task_id, turn_id)
        return self._client._get_wham(f"/wham/tasks/{task_id}/turns/{turn_id}")

    def logs(self, task_id: str, turn_id: str) -> dict[str, Any]:
        task_id, turn_id = self._ids(task_id, turn_id)
        return self._client._get_wham(f"/wham/tasks/{task_id}/turns/{turn_id}/logs")

    def pull_request(self, task_id: str, turn_id: str, body: Any) -> dict[str, Any]:
        task_id, turn_id = self._ids(task_id, turn_id)
        payload = _jsonable(body)
        if not isinstance(payload, dict):
            raise TypeError("Expected `body` to serialize to a JSON object.")
        return self._client._post_wham(
            f"/wham/tasks/{task_id}/turns/{turn_id}/pr", body=payload
        )

    @staticmethod
    def _ids(task_id: str, turn_id: str) -> tuple[str, str]:
        if not task_id:
            raise ValueError(f"Expected a non-empty value for `task_id` but received {task_id!r}")
        if not turn_id:
            raise ValueError(f"Expected a non-empty value for `turn_id` but received {turn_id!r}")
        return task_id, turn_id


class CodexEnvironments:
    """Codex cloud environment data for the authenticated account."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/environments")

    def search(
        self,
        query: str = "",
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        return self._client._get_wham(
            "/wham/environments/search",
            params=_clean_params({"query": query or None, "cursor": cursor, "limit": limit}),
        )

    def retrieve(self, environment_id: str) -> dict[str, Any]:
        self._require_id(environment_id)
        return self._client._get_wham(
            f"/wham/environments/{environment_id}/with-creator-and-machine"
        )

    def by_repo(self, provider: str, owner: str, repo: str) -> dict[str, Any]:
        for name, value in (("provider", provider), ("owner", owner), ("repo", repo)):
            if not value:
                raise ValueError(f"Expected a non-empty value for `{name}`.")
        return self._client._get_wham(
            f"/wham/environments/by-repo/{provider}/{owner}/{repo}"
        )

    def machines(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/machines")

    def create(self, body: Any) -> dict[str, Any]:
        return self._client._post_wham("/wham/environments", body=self._body(body))

    def update(self, environment_id: str, body: Any) -> dict[str, Any]:
        self._require_id(environment_id)
        return self._client._patch_wham(
            f"/wham/environments/{environment_id}", body=self._body(body)
        )

    def delete(self, environment_id: str) -> None:
        self._require_id(environment_id)
        self._client._delete_wham(f"/wham/environments/{environment_id}")

    def reset_cache(self, environment_id: str) -> dict[str, Any]:
        self._require_id(environment_id)
        return self._client._post_wham(
            f"/wham/environments/{environment_id}/reset-cache"
        )

    @staticmethod
    def _require_id(environment_id: str) -> None:
        if not environment_id:
            raise ValueError("Expected a non-empty value for `environment_id`.")

    @staticmethod
    def _body(body: Any) -> dict[str, Any]:
        payload = _jsonable(body)
        if not isinstance(payload, dict):
            raise TypeError("Expected `body` to serialize to a JSON object.")
        return payload


class CodexRepositories:
    """Desktop-observed GitHub repository and branch discovery."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def search(
        self,
        query: str,
        *,
        connector_id: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        if not query or not connector_id:
            raise ValueError("`query` and `connector_id` must be non-empty.")
        return self._client._get_wham(
            "/wham/github/repositories/search/all-installations",
            params={"query": query, "limit": limit, "connector_id": connector_id},
        )

    def branches(
        self,
        repo_id: str,
        query: str,
        *,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not repo_id or not query:
            raise ValueError("`repo_id` and `query` must be non-empty.")
        normalized_id = repo_id if repo_id.startswith("github-") else f"github-{repo_id}"
        return self._client._get_wham(
            f"/wham/github/branches/{normalized_id}/search",
            params=_clean_params({
                "query": query,
                "page_size": page_size,
                "cursor": cursor,
            }),
        )


class CodexUserSystemMessages:
    """ChatGPT customization instructions for the authenticated account."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def retrieve(self) -> dict[str, Any]:
        return self._client._get_chatgpt("/user_system_messages")


class CodexWorkspaceMessages:
    """Workspace-scoped messages supplied by the authenticated Codex backend."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(self) -> dict[str, Any]:
        return self._client._get_wham("/wham/workspace-messages")


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}
