import json

import pytest

from codex_backend_sdk import OpenAI
from codex_backend_sdk.resources.remote_control import (
    RemoteControlConnection,
    RemoteControlConnectionClosed,
    RemoteControlEnrollment,
)


class FakeSocket:
    def __init__(self):
        self.connected = True
        self.sent = []
        self.pings = []
        self.received = [json.dumps({"type": "ping", "cursor": "cursor-2"})]

    def send(self, message):
        self.sent.append(message)

    def recv(self):
        return self.received.pop(0)

    def ping(self, payload=b""):
        self.pings.append(payload)

    def close(self):
        self.connected = False


class FakeRemoteControlClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.posts = []
        self.gets = []
        self.deletes = []
        self.patches = []

    def _post_wham(self, path, *, body, headers=None, use_oauth_headers=True, timeout=None):
        self.posts.append((path, body, headers, use_oauth_headers))
        if path.endswith("/enroll") or path.endswith("/refresh"):
            return {
                "server_id": "server-1",
                "environment_id": "environment-1",
                "remote_control_token": "remote-token",
                "expires_at": "2026-08-11T00:00:00Z",
            }
        if path.endswith("/pair/status"):
            return {"claimed": True}
        if path.endswith("/pair"):
            return {
                "pairing_code": "pair-code",
                "manual_pairing_code": "ABCD-EFGH",
                "server_id": "server-1",
                "environment_id": "environment-1",
                "expires_at": "2026-08-10T01:00:00Z",
            }
        raise AssertionError(path)

    def _get_wham(self, path, *, params=None):
        self.gets.append((path, params))
        if path.endswith("/mfa_requirement"):
            return {"requirement": "required"}
        return {
            "items": [{"client_id": "client-1", "display_name": "Phone"}],
            "cursor": "next-page",
        }

    def _get_chatgpt(self, path, *, params=None):
        self.gets.append((path, params))
        return {"mfa_enabled_v2": True, "factors": []}

    def _delete_wham(self, path, *, timeout=None):
        self.deletes.append(path)

    def _get(self, path, *, params=None):
        self.gets.append((path, params))
        return {
            "items": [{
                "env_id": "environment-1",
                "display_name": "Office",
                "online": True,
            }],
            "cursor": None,
        }

    def _patch(self, path, *, body):
        self.patches.append((path, body))
        return {"env_id": "environment /1", "name": body["name"]}

    def _delete(self, path):
        self.deletes.append(path)


def enrollment():
    return RemoteControlEnrollment(
        server_id="server-1",
        environment_id="environment-1",
        remote_control_token="remote-token",
        expires_at="2026-08-11T00:00:00Z",
    )


def test_remote_control_enroll_and_refresh_use_oauth_installation_headers():
    client = FakeRemoteControlClient()

    created = client.codex.remote_control.enroll(
        name="Desktop",
        installation_id="installation-1",
        os="linux",
        arch="x86_64",
        app_server_version="0.147.0",
    )
    refreshed = client.codex.remote_control.refresh(
        created,
        installation_id="installation-1",
    )

    assert refreshed.server_id == created.server_id
    assert client.posts[0] == (
        "/wham/remote/control/server/enroll",
        {
            "name": "Desktop",
            "os": "linux",
            "arch": "x86_64",
            "app_server_version": "0.147.0",
            "installation_id": "installation-1",
        },
        {"x-codex-installation-id": "installation-1"},
        True,
    )
    assert client.posts[1][1] == {
        "server_id": "server-1",
        "installation_id": "installation-1",
    }


def test_remote_control_pairing_uses_short_lived_server_token():
    client = FakeRemoteControlClient()

    pairing = client.codex.remote_control.pairing.start(enrollment(), manual_code=True)
    status = client.codex.remote_control.pairing.status(
        enrollment(), manual_pairing_code=pairing.manual_pairing_code
    )

    assert status.claimed is True
    assert client.posts[0][1] == {"manual_code": True}
    assert client.posts[0][2] == {"Authorization": "Bearer remote-token"}
    assert client.posts[0][3] is False
    assert client.posts[1][1] == {"manual_pairing_code": "ABCD-EFGH"}

    with pytest.raises(ValueError, match="exactly one"):
        client.codex.remote_control.pairing.status(enrollment())


def test_remote_control_clients_list_and_revoke_use_environment_paths():
    client = FakeRemoteControlClient()

    page = client.codex.remote_control.clients.list(
        "environment-1", limit=20, order="desc"
    )
    client.codex.remote_control.clients.revoke("environment-1", "client-1")

    assert page.data[0].display_name == "Phone"
    assert page.next_cursor == "next-page"
    assert client.gets == [
        (
            "/wham/remote/control/environments/environment-1/clients",
            {"limit": 20, "order": "desc"},
        )
    ]
    assert client.deletes == [
        "/wham/remote/control/environments/environment-1/clients/client-1"
    ]


def test_remote_control_desktop_reads_mfa_and_browser_clients():
    client = FakeRemoteControlClient()

    assert client.codex.remote_control.desktop.mfa_requirement() == "required"
    assert client.codex.remote_control.desktop.mfa_info()["mfa_enabled_v2"] is True
    page = client.codex.remote_control.desktop.clients.list(limit=50)

    assert page.data[0].client_id == "client-1"
    assert client.gets == [
        ("/wham/remote/control/mfa_requirement", None),
        ("/accounts/mfa_info", None),
        ("/wham/remote/control/clients", {"limit": 50}),
    ]


def test_remote_control_desktop_pair_and_revoke_are_explicit_account_mutations():
    client = FakeRemoteControlClient()

    client.codex.remote_control.desktop.clients.pair("client-1", "ABCD-EFGH")
    client.codex.remote_control.desktop.clients.revoke("client-1")

    assert client.posts[0][0:2] == (
        "/wham/remote/control/client/pair",
        {"client_id": "client-1", "manual_pairing_code": "ABCD-EFGH"},
    )
    assert client.deletes == ["/wham/remote/control/clients/client-1"]


class PaginatedDesktopClients(FakeRemoteControlClient):
    def _get_wham(self, path, *, params=None):
        self.gets.append((path, params))
        if params.get("cursor") is None:
            return {
                "items": [
                    {"client_id": "pending", "enrollment_status": "pending_enrollment"},
                    {"client_id": "phone", "enrollment_status": "enrolled_device_key"},
                ],
                "cursor": "page-2",
            }
        return {
            "items": [{"client_id": "browser", "enrollment_status": "enrolled_browser"}],
            "cursor": None,
        }


def test_remote_control_desktop_list_all_paginates_and_can_filter_pending():
    client = PaginatedDesktopClients()

    clients = client.codex.remote_control.desktop.clients.list_all(include_pending=False)

    assert [item.client_id for item in clients] == ["phone", "browser"]
    assert client.gets[1][1] == {"limit": 100, "cursor": "page-2"}


def test_remote_control_desktop_validates_limits_and_pairing_fields():
    client = FakeRemoteControlClient()

    with pytest.raises(ValueError, match="between 1 and 100"):
        client.codex.remote_control.desktop.clients.list(limit=0)
    with pytest.raises(ValueError, match="manual_pairing_code"):
        client.codex.remote_control.desktop.clients.pair("client-1", "")


def test_remote_control_desktop_environment_discovery_and_mutations_use_codex_route():
    client = FakeRemoteControlClient()

    page = client.codex.remote_control.desktop.environments.list(
        client_id="client /1", limit=25
    )
    renamed = client.codex.remote_control.desktop.environments.rename(
        "environment /1", "Home"
    )
    client.codex.remote_control.desktop.environments.delete("environment /1")

    assert page.data[0].display_name == "Office"
    assert renamed.name == "Home"
    assert client.gets == [
        (
            "/remote/control/clients/client%20%2F1/environments",
            {"limit": 25},
        )
    ]
    assert client.patches == [
        ("/remote/control/environments/environment%20%2F1", {"name": "Home"})
    ]
    assert client.deletes == [
        "/remote/control/environments/environment%20%2F1"
    ]


def test_remote_control_connection_builds_codex_headers_and_tracks_cursor():
    client = FakeRemoteControlClient()
    calls = []
    socket = FakeSocket()

    def factory(url, **kwargs):
        calls.append((url, kwargs))
        return socket

    connection = client.codex.remote_control.connect(
        enrollment(),
        installation_id="installation-1",
        server_name="My Desktop",
        protocol_version="3",
        subscribe_cursor="cursor-1",
        refresh_before_connect=False,
        websocket_factory=factory,
    )
    connection.send({"type": "ack", "client_id": "client-1"})
    connection.ping(b"heartbeat")
    received = connection.receive()
    connection.close()

    headers = calls[0][1]["header"]
    assert "x-codex-server-id: server-1" in headers
    assert "x-codex-name: TXkgRGVza3RvcA==" in headers
    assert "x-codex-protocol-version: 3" in headers
    assert "Authorization: Bearer remote-token" in headers
    assert "x-codex-subscribe-cursor: cursor-1" in headers
    assert json.loads(socket.sent[0]) == {"type": "ack", "client_id": "client-1"}
    assert socket.pings == [b"heartbeat"]
    assert received["type"] == "ping"
    assert connection.subscribe_cursor == "cursor-2"
    assert connection.connected is False


@pytest.mark.parametrize("closed_frame", ["", b""])
def test_remote_control_connection_reports_an_empty_close_frame(closed_frame):
    socket = FakeSocket()
    socket.received = [closed_frame]
    connection = RemoteControlConnection(
        socket,
        websocket_url="wss://example.test/remote",
        enrollment=enrollment(),
        installation_id="installation-1",
        server_name="Desktop",
        protocol_version="3",
        subscribe_cursor="stale-cursor",
    )

    with pytest.raises(RemoteControlConnectionClosed, match="closed without"):
        connection.receive()
