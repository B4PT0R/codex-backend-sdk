import json

import pytest

from codex_backend_sdk import OpenAI
from codex_backend_sdk.resources.remote_control import RemoteControlEnrollment


class FakeSocket:
    def __init__(self):
        self.connected = True
        self.sent = []
        self.received = [json.dumps({"type": "ping", "cursor": "cursor-2"})]

    def send(self, message):
        self.sent.append(message)

    def recv(self):
        return self.received.pop(0)

    def close(self):
        self.connected = False


class FakeRemoteControlClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.posts = []
        self.gets = []
        self.deletes = []

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
        return {
            "items": [{"client_id": "client-1", "display_name": "Phone"}],
            "cursor": "next-page",
        }

    def _delete_wham(self, path, *, timeout=None):
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
    received = connection.receive()
    connection.close()

    headers = calls[0][1]["header"]
    assert "x-codex-server-id: server-1" in headers
    assert "x-codex-name: TXkgRGVza3RvcA==" in headers
    assert "x-codex-protocol-version: 3" in headers
    assert "Authorization: Bearer remote-token" in headers
    assert "x-codex-subscribe-cursor: cursor-1" in headers
    assert json.loads(socket.sent[0]) == {"type": "ack", "client_id": "client-1"}
    assert received["type"] == "ping"
    assert connection.subscribe_cursor == "cursor-2"
    assert connection.connected is False
