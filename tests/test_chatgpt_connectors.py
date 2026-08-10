from pathlib import Path

import pytest

from codex_backend_sdk import ConnectorAuthenticationRequiredError, OpenAI


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeConnectorClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.directory_pages = [
            {"apps": [{"id": "connector-1"}], "next_token": "page-2"},
            {"apps": [{"id": "connector-2"}], "next_token": None},
        ]

    def _get_chatgpt(self, path, *, params=None, headers=None):
        self.calls.append(("GET", path, params, headers))
        if path == "/connectors/directory/list":
            return self.directory_pages.pop(0)
        if path == "/aip/connectors/product_specific":
            return {"connectors": [{"id": "connector-github"}]}
        if path.endswith("/link"):
            return {"link": None}
        if path.endswith("/logo"):
            return {"base64": "aWNvbg==", "contentType": "image/png"}
        return {"id": "connector-1", "actions": []}

    def _post_chatgpt(self, path, *, body, **kwargs):
        self.calls.append(("POST", path, body))
        if path.endswith("list_accessible"):
            return {"links": []}
        return {"path": path}

    def _request_chatgpt(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return FakeResponse({"apps": [{"id": "connector-1", "tools": []}]})

    def _post_chatgpt_raw(self, path, **kwargs):
        file_tuple = kwargs["files"]["file"]
        self.calls.append(
            (
                "MULTIPART",
                path,
                kwargs["data"],
                (file_tuple[0], file_tuple[1].read(), file_tuple[2]),
            )
        )
        return FakeResponse(
            {"connector_result": {"content": [], "structuredContent": {}}}
        )


def test_connector_directory_paginates_official_next_token_shape():
    client = FakeConnectorClient()

    apps = client.chatgpt.connectors.directory.list_all()

    assert [app["id"] for app in apps] == ["connector-1", "connector-2"]
    assert client.calls == [
        (
            "GET",
            "/connectors/directory/list",
            {"external_logos": True},
            None,
        ),
        (
            "GET",
            "/connectors/directory/list",
            {"external_logos": True, "token": "page-2"},
            None,
        ),
    ]


def test_connector_metadata_detail_terms_logo_and_batch_contracts():
    client = FakeConnectorClient()

    client.chatgpt.connectors.retrieve(
        "connector /1", include_actions=True, include_logo=False
    )
    product = client.chatgpt.connectors.product_specific("hermes")
    client.chatgpt.connectors.terms("connector /1")
    logo = client.chatgpt.connectors.logo("connector /1", theme="dark")
    batch = client.chatgpt.connectors.batch_metadata(
        ["connector-1"], include_tools=True
    )

    assert logo["contentType"] == "image/png"
    assert batch["apps"][0]["id"] == "connector-1"
    assert product["connectors"][0]["id"] == "connector-github"
    assert client.calls == [
        (
            "GET",
            "/aip/connectors/connector%20%2F1",
            {"include_actions": True, "include_logo": False},
            {"OAI-Product-Sku": "CODEX"},
        ),
        (
            "GET",
            "/aip/connectors/product_specific",
            {"purpose": "hermes"},
            {"OAI-Product-Sku": "CODEX"},
        ),
        (
            "GET",
            "/aip/connectors/connector%20%2F1/tos",
            None,
            {"OAI-Product-Sku": "CODEX"},
        ),
        (
            "GET",
            "/aip/connectors/connector%20%2F1/logo",
            {"theme": "dark"},
            None,
        ),
        (
            "POST",
            "/ps/apps/batch",
            {
                "body": {"app_ids": ["connector-1"], "include_tools": True},
                "headers": {"X-OpenAI-Product-Sku": "codex"},
            },
        ),
    ]


def test_connector_link_reads_are_separate_from_authentication_mutations():
    client = FakeConnectorClient()

    client.chatgpt.connectors.links.retrieve("connector /1")
    client.chatgpt.connectors.links.list_accessible()
    client.chatgpt.connectors.authentication.connect_without_auth(
        "connector-1", "Demo"
    )
    client.chatgpt.connectors.authentication.start_oauth(
        "connector-1",
        "Demo",
        callback_url="codex://connector/oauth_callback",
        post_auth_url="https://chatgpt.com/apps/connector-1",
    )
    client.chatgpt.connectors.authentication.start_reauthentication(
        "link-1",
        callback_url="codex://connector/oauth_callback",
        post_auth_url="https://chatgpt.com/apps/connector-1",
        requested_scopes=["scope.read"],
    )
    client.chatgpt.connectors.authentication.complete_oauth(
        "codex://connector/oauth_callback?code=opaque"
    )

    assert client.calls == [
        ("GET", "/aip/connectors/connector%20%2F1/link", None, None),
        (
            "POST",
            "/aip/connectors/links/list_accessible",
            {"principals": [], "link_refresh_strategy": "BLOCKING"},
        ),
        (
            "POST",
            "/aip/connectors/links/noauth",
            {"connector_id": "connector-1", "name": "Demo", "action_names": []},
        ),
        (
            "POST",
            "/aip/connectors/links/oauth",
            {
                "connector_id": "connector-1",
                "name": "Demo",
                "action_names": None,
                "callback_url": "codex://connector/oauth_callback",
                "post_auth_url": "https://chatgpt.com/apps/connector-1",
            },
        ),
        (
            "POST",
            "/aip/connectors/links/oauth/reauth",
            {
                "link_id": "link-1",
                "callback_url": "codex://connector/oauth_callback",
                "post_auth_url": "https://chatgpt.com/apps/connector-1",
                "requested_scopes": ["scope.read"],
            },
        ),
        (
            "POST",
            "/aip/connectors/links/oauth/callback",
            {"full_redirect_url": "codex://connector/oauth_callback?code=opaque"},
        ),
    ]


def test_connector_external_actions_have_an_explicit_authority_namespace():
    client = FakeConnectorClient()
    actions = client.chatgpt.connectors.external_actions

    actions.search_contacts({"query": "Ada"})
    actions.send_email({"to": ["person@example.test"], "subject": "Hello"})
    actions.email_status({"message_id": "message-1"})
    actions.unsend_email({"message_id": "message-1"})

    assert [call[1] for call in client.calls] == [
        "/aip/connectors/google_contacts/search_contacts",
        "/aip/connectors/email/send_email",
        "/aip/connectors/email/send_email_status",
        "/aip/connectors/email/unsend_email",
    ]


def test_connector_boundaries_reject_invalid_pages_payloads_and_ids():
    client = FakeConnectorClient()
    client.directory_pages = [{"apps": "invalid", "next_token": None}]
    with pytest.raises(RuntimeError, match="app list"):
        client.chatgpt.connectors.directory.list_all()

    with pytest.raises(ValueError, match="connector_id"):
        client.chatgpt.connectors.retrieve("")
    with pytest.raises(TypeError, match="JSON object"):
        client.chatgpt.connectors.external_actions.send_email(["invalid"])
    assert client.chatgpt.connectors.batch_metadata([]) == {"apps": []}


def test_google_drive_upload_uses_official_multipart_contract(tmp_path: Path):
    client = FakeConnectorClient()
    document = tmp_path / "report.docx"
    document.write_bytes(b"office-document")

    payload = client.chatgpt.connectors.external_actions.upload_google_drive_file(
        document, title="Quarterly report"
    )

    assert payload == {
        "connector_result": {"content": [], "structuredContent": {}}
    }
    assert client.calls == [
        (
            "MULTIPART",
            "/wham/apps/google_drive/upload",
            {"arguments": '{"title": "Quarterly report"}'},
            (
                "report.docx",
                b"office-document",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            ),
        )
    ]


def test_google_drive_upload_detects_connector_auth_failure(tmp_path: Path):
    client = FakeConnectorClient()
    document = tmp_path / "report.xlsx"
    document.write_bytes(b"sheet")
    client._post_chatgpt_raw = lambda *args, **kwargs: FakeResponse(
        {
            "connector_result": {
                "_meta": {
                    "_codex_apps": {
                        "connector_auth_failure": {"is_auth_failure": True}
                    }
                }
            }
        }
    )

    with pytest.raises(ConnectorAuthenticationRequiredError):
        client.chatgpt.connectors.external_actions.upload_google_drive_file(document)


def test_google_drive_upload_rejects_unsupported_files(tmp_path: Path):
    client = FakeConnectorClient()
    unsupported = tmp_path / "report.pdf"
    unsupported.write_bytes(b"pdf")

    with pytest.raises(ValueError, match="docx"):
        client.chatgpt.connectors.external_actions.upload_google_drive_file(unsupported)
