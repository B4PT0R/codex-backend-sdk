"""ChatGPT OAuth Remote Control server resources used by Codex App Server."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Literal, Optional, TYPE_CHECKING
from urllib.parse import quote

from pydantic import Field

from .._models import CodexBaseModel
from .._utils import _jsonable

if TYPE_CHECKING:
    from .._client import CodexClient


REMOTE_CONTROL_ROOT = "/wham/remote/control"


class RemoteControlConnectionClosed(ConnectionError):
    """The Remote Control peer closed its WebSocket without an envelope."""


class RemoteControlEnrollment(CodexBaseModel):
    server_id: str
    environment_id: str
    remote_control_token: str
    expires_at: str


class RemoteControlPairing(CodexBaseModel):
    pairing_code: str
    manual_pairing_code: Optional[str] = None
    server_id: str
    environment_id: str
    expires_at: str


class RemoteControlPairingStatus(CodexBaseModel):
    claimed: bool


class RemoteControlClient(CodexBaseModel):
    client_id: str
    account_user_id: Optional[str] = None
    display_name: Optional[str] = None
    device_type: Optional[str] = None
    platform: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    app_version: Optional[str] = None
    enrollment_status: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_seen_city: Optional[str] = None
    last_seen_country: Optional[str] = None
    last_seen_region_code: Optional[str] = None


class RemoteControlClientPage(CodexBaseModel):
    data: list[RemoteControlClient] = Field(default_factory=list, alias="items")
    next_cursor: Optional[str] = Field(default=None, alias="cursor")


class RemoteControlEnvironment(CodexBaseModel):
    env_id: str
    name: Optional[str] = None
    display_name: Optional[str] = None
    host_name: Optional[str] = None
    kind: Optional[str] = None
    client_type: Optional[str] = None
    online: bool = False
    busy: bool = False
    os: Optional[str] = None
    arch: Optional[str] = None
    app_server_version: Optional[str] = None
    installation_id: Optional[str] = None
    last_seen_at: Optional[str] = None


class RemoteControlEnvironmentPage(CodexBaseModel):
    data: list[RemoteControlEnvironment] = Field(default_factory=list, alias="items")
    next_cursor: Optional[str] = Field(default=None, alias="cursor")


class RemoteControlConnection:
    """Synchronous raw Remote Control WebSocket.

    The wire messages are Codex ``ClientEnvelope``/``ServerEnvelope`` objects.
    This class deliberately preserves those dictionaries instead of pretending
    they are an independent public JSON-RPC protocol.
    """

    def __init__(
        self,
        socket: Any,
        *,
        websocket_url: str,
        enrollment: RemoteControlEnrollment,
        installation_id: str,
        server_name: str,
        protocol_version: str,
        subscribe_cursor: Optional[str],
    ) -> None:
        self._socket = socket
        self.websocket_url = websocket_url
        self.enrollment = enrollment
        self.installation_id = installation_id
        self.server_name = server_name
        self.protocol_version = protocol_version
        self.subscribe_cursor = subscribe_cursor

    @property
    def connected(self) -> bool:
        return bool(getattr(self._socket, "connected", True))

    def send(self, envelope: Any) -> None:
        payload = _jsonable(envelope)
        if not isinstance(payload, dict):
            raise TypeError("Expected `envelope` to serialize to a JSON object.")
        self._socket.send(json.dumps(payload, separators=(",", ":")))

    def ping(self, payload: bytes = b"") -> None:
        """Send a WebSocket ping frame to keep the remote path alive."""
        self._socket.ping(payload)

    def receive(self) -> dict[str, Any]:
        message = self._socket.recv()
        if message in {"", b""}:
            raise RemoteControlConnectionClosed(
                "Remote Control WebSocket closed without a final envelope."
            )
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        payload = json.loads(message)
        if not isinstance(payload, dict):
            raise RuntimeError("Remote Control WebSocket returned a non-object message.")
        cursor = payload.get("cursor")
        if isinstance(cursor, str):
            self.subscribe_cursor = cursor
        return payload

    def __iter__(self) -> Iterator[dict[str, Any]]:
        while self.connected:
            yield self.receive()

    def close(self) -> None:
        self._socket.close()

    def __enter__(self) -> "RemoteControlConnection":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class RemoteControl:
    """Remote Control server lifecycle exposed by the ChatGPT Codex backend."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.pairing = RemoteControlPairingResource(client)
        self.clients = RemoteControlClients(client)
        self.desktop = RemoteControlDesktop(client)

    def enroll(
        self,
        *,
        name: str,
        installation_id: str,
        os: str,
        arch: str,
        app_server_version: str,
    ) -> RemoteControlEnrollment:
        _require_non_empty(name=name, installation_id=installation_id, os=os, arch=arch)
        _require_non_empty(app_server_version=app_server_version)
        payload = {
            "name": name,
            "os": os,
            "arch": arch,
            "app_server_version": app_server_version,
            "installation_id": installation_id,
        }
        response = self._client._post_wham(
            f"{REMOTE_CONTROL_ROOT}/server/enroll",
            body=payload,
            headers={"x-codex-installation-id": installation_id},
        )
        return RemoteControlEnrollment.model_validate(response)

    def refresh(
        self,
        enrollment: RemoteControlEnrollment,
        *,
        installation_id: str,
    ) -> RemoteControlEnrollment:
        _require_non_empty(installation_id=installation_id)
        response = self._client._post_wham(
            f"{REMOTE_CONTROL_ROOT}/server/refresh",
            body={
                "server_id": enrollment.server_id,
                "installation_id": installation_id,
            },
            headers={"x-codex-installation-id": installation_id},
        )
        refreshed = RemoteControlEnrollment.model_validate(response)
        if (
            refreshed.server_id != enrollment.server_id
            or refreshed.environment_id != enrollment.environment_id
        ):
            raise RuntimeError("Remote Control refresh returned a mismatched enrollment.")
        return refreshed

    def connect(
        self,
        enrollment: RemoteControlEnrollment,
        *,
        installation_id: str,
        server_name: str,
        protocol_version: str = "3",
        subscribe_cursor: Optional[str] = None,
        refresh_before_connect: bool = True,
        timeout: float = 30,
        websocket_factory: Any = None,
    ) -> RemoteControlConnection:
        _require_non_empty(
            installation_id=installation_id,
            server_name=server_name,
            protocol_version=protocol_version,
        )
        if refresh_before_connect and _needs_refresh(enrollment.expires_at):
            enrollment = self.refresh(enrollment, installation_id=installation_id)
        if websocket_factory is None:
            try:
                import websocket
            except ImportError as exc:  # pragma: no cover - installation error
                raise RuntimeError(
                    "Remote Control WebSocket support requires `websocket-client`."
                ) from exc
            websocket_factory = websocket.create_connection
        headers = {
            "x-codex-server-id": enrollment.server_id,
            "x-codex-name": _base64(server_name),
            "x-codex-protocol-version": protocol_version,
            "Authorization": f"Bearer {enrollment.remote_control_token}",
            "x-codex-installation-id": installation_id,
        }
        if subscribe_cursor:
            headers["x-codex-subscribe-cursor"] = subscribe_cursor
        socket = websocket_factory(
            "wss://chatgpt.com/backend-api/wham/remote/control/server",
            header=[f"{key}: {value}" for key, value in headers.items()],
            timeout=timeout,
        )
        return RemoteControlConnection(
            socket,
            websocket_url="wss://chatgpt.com/backend-api/wham/remote/control/server",
            enrollment=enrollment,
            installation_id=installation_id,
            server_name=server_name,
            protocol_version=protocol_version,
            subscribe_cursor=subscribe_cursor,
        )

    def reconnect(
        self,
        connection: RemoteControlConnection,
        *,
        timeout: float = 30,
        websocket_factory: Any = None,
    ) -> RemoteControlConnection:
        """Reconnect using the latest backend cursor and a refreshed token."""
        connection.close()
        return self.connect(
            connection.enrollment,
            installation_id=connection.installation_id,
            server_name=connection.server_name,
            protocol_version=connection.protocol_version,
            subscribe_cursor=connection.subscribe_cursor,
            timeout=timeout,
            websocket_factory=websocket_factory,
        )


class RemoteControlPairingResource:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def start(
        self,
        enrollment: RemoteControlEnrollment,
        *,
        manual_code: bool = False,
    ) -> RemoteControlPairing:
        response = self._client._post_wham(
            f"{REMOTE_CONTROL_ROOT}/server/pair",
            body={"manual_code": manual_code},
            headers={"Authorization": f"Bearer {enrollment.remote_control_token}"},
            use_oauth_headers=False,
        )
        pairing = RemoteControlPairing.model_validate(response)
        if (
            pairing.server_id != enrollment.server_id
            or pairing.environment_id != enrollment.environment_id
        ):
            raise RuntimeError("Remote Control pairing returned a mismatched enrollment.")
        return pairing

    def status(
        self,
        enrollment: RemoteControlEnrollment,
        *,
        pairing_code: Optional[str] = None,
        manual_pairing_code: Optional[str] = None,
    ) -> RemoteControlPairingStatus:
        if bool(pairing_code) == bool(manual_pairing_code):
            raise ValueError("Provide exactly one pairing code.")
        body = {
            "pairing_code": pairing_code,
            "manual_pairing_code": manual_pairing_code,
        }
        response = self._client._post_wham(
            f"{REMOTE_CONTROL_ROOT}/server/pair/status",
            body={key: value for key, value in body.items() if value is not None},
            headers={"Authorization": f"Bearer {enrollment.remote_control_token}"},
            use_oauth_headers=False,
        )
        return RemoteControlPairingStatus.model_validate(response)


class RemoteControlClients:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        environment_id: str,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        order: Optional[Literal["asc", "desc"]] = None,
    ) -> RemoteControlClientPage:
        _require_non_empty(environment_id=environment_id)
        if limit is not None and not 1 <= limit <= 100:
            raise ValueError("Expected `limit` between 1 and 100.")
        params = {"cursor": cursor, "limit": limit, "order": order}
        response = self._client._get_wham(
            f"{REMOTE_CONTROL_ROOT}/environments/{quote(environment_id, safe='')}/clients",
            params={key: value for key, value in params.items() if value is not None} or None,
        )
        return RemoteControlClientPage.model_validate(response)

    def revoke(self, environment_id: str, client_id: str) -> None:
        _require_non_empty(environment_id=environment_id, client_id=client_id)
        self._client._delete_wham(
            f"{REMOTE_CONTROL_ROOT}/environments/{quote(environment_id, safe='')}/clients/{quote(client_id, safe='')}"
        )


class RemoteControlDesktop:
    """Browser/mobile-client routes used by the official Desktop UI.

    These use the account OAuth bearer, unlike server pairing which uses the
    short-lived enrollment token.
    """

    def __init__(self, client: CodexClient) -> None:
        self._client = client
        self.clients = RemoteControlDesktopClients(client)
        self.environments = RemoteControlDesktopEnvironments(client)

    def mfa_requirement(self) -> str:
        payload = self._client._get_wham(f"{REMOTE_CONTROL_ROOT}/mfa_requirement")
        requirement = payload.get("requirement")
        if not isinstance(requirement, str) or not requirement:
            raise RuntimeError("Remote Control MFA response is missing its requirement.")
        return requirement

    def mfa_info(self) -> dict[str, Any]:
        payload = self._client._get_chatgpt("/accounts/mfa_info")
        if not isinstance(payload.get("mfa_enabled_v2"), bool):
            raise RuntimeError("ChatGPT MFA response is missing `mfa_enabled_v2`.")
        return payload


class RemoteControlDesktopClients:
    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        *,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> RemoteControlClientPage:
        if not 1 <= limit <= 100:
            raise ValueError("Expected `limit` between 1 and 100.")
        params = {"limit": limit, **({} if cursor is None else {"cursor": cursor})}
        payload = self._client._get_wham(f"{REMOTE_CONTROL_ROOT}/clients", params=params)
        return RemoteControlClientPage.model_validate(payload)

    def list_all(self, *, include_pending: bool = True) -> list[RemoteControlClient]:
        clients: list[RemoteControlClient] = []
        cursor: Optional[str] = None
        seen_cursors: set[str] = set()
        while True:
            page = self.list(cursor=cursor)
            clients.extend(
                client
                for client in page.data
                if include_pending or client.enrollment_status != "pending_enrollment"
            )
            cursor = page.next_cursor
            if cursor is None:
                return clients
            if cursor in seen_cursors:
                raise RuntimeError("Remote Control clients returned a repeated cursor.")
            seen_cursors.add(cursor)

    def pair(self, client_id: str, manual_pairing_code: str) -> dict[str, Any]:
        _require_non_empty(
            client_id=client_id, manual_pairing_code=manual_pairing_code
        )
        return self._client._post_wham(
            f"{REMOTE_CONTROL_ROOT}/client/pair",
            body={
                "client_id": client_id,
                "manual_pairing_code": manual_pairing_code,
            },
        )

    def revoke(self, client_id: str) -> None:
        _require_non_empty(client_id=client_id)
        self._client._delete_wham(
            f"{REMOTE_CONTROL_ROOT}/clients/{quote(client_id, safe='')}"
        )


class RemoteControlDesktopEnvironments:
    """Remote hosts visible to an enrolled Desktop/mobile client."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def list(
        self,
        *,
        client_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> RemoteControlEnvironmentPage:
        if not 1 <= limit <= 100:
            raise ValueError("Expected `limit` between 1 and 100.")
        path = "/remote/control/environments"
        if client_id is not None:
            _require_non_empty(client_id=client_id)
            path = f"/remote/control/clients/{quote(client_id, safe='')}/environments"
        payload = self._client._get(
            path,
            params={
                "limit": limit,
                **({} if cursor is None else {"cursor": cursor}),
            },
        )
        return RemoteControlEnvironmentPage.model_validate(payload)

    def list_all(self, *, client_id: Optional[str] = None) -> list[RemoteControlEnvironment]:
        environments: list[RemoteControlEnvironment] = []
        cursor: Optional[str] = None
        seen_cursors: set[str] = set()
        while True:
            page = self.list(client_id=client_id, cursor=cursor)
            environments.extend(page.data)
            cursor = page.next_cursor
            if cursor is None:
                return environments
            if cursor in seen_cursors:
                raise RuntimeError("Remote Control environments returned a repeated cursor.")
            seen_cursors.add(cursor)

    def rename(self, environment_id: str, name: str) -> RemoteControlEnvironment:
        _require_non_empty(environment_id=environment_id, name=name)
        payload = self._client._patch(
            f"/remote/control/environments/{quote(environment_id, safe='')}",
            body={"name": name},
        )
        return RemoteControlEnvironment.model_validate(payload)

    def delete(self, environment_id: str) -> None:
        _require_non_empty(environment_id=environment_id)
        self._client._delete(
            f"/remote/control/environments/{quote(environment_id, safe='')}"
        )


def _require_non_empty(**values: str) -> None:
    for name, value in values.items():
        if not value:
            raise ValueError(f"Expected a non-empty value for `{name}`.")


def _base64(value: str) -> str:
    import base64

    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _needs_refresh(expires_at: str) -> bool:
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= datetime.now(timezone.utc) + timedelta(minutes=5)
