from codex_backend_sdk import CodexClient, TokenStore



def _store() -> TokenStore:
    return TokenStore(
        access_token="access-secret",
        refresh_token="refresh-secret",
        id_token_raw="id-secret",
        account_id="acct_123",
        openai_api_key="api-secret",
        email="user@example.com",
        plan_type="pro",
    )



def test_account_info_exposes_safe_metadata_only():
    client = CodexClient(store=_store())

    info = client.account_info()

    assert client.authenticated is True
    assert info == {
        "authenticated": True,
        "account_id": "acct_123",
        "email": "user@example.com",
        "plan_type": "pro",
    }
    assert "access-secret" not in repr(info)
    assert "refresh-secret" not in repr(info)
    assert "api-secret" not in repr(info)



def test_account_info_when_not_authenticated():
    client = CodexClient()

    assert client.authenticated is False
    assert client.account_info() == {
        "authenticated": False,
        "account_id": None,
        "email": None,
        "plan_type": None,
    }


def test_client_matches_official_lifecycle_and_copy_helpers():
    client = CodexClient(
        store=_store(),
        timeout=20,
        default_headers={"x-default": "one"},
        default_query={"preview": "one"},
    )

    copied = client.with_options(
        timeout=30,
        max_retries=4,
        default_headers={"x-extra": "two"},
        default_query={"page": "2"},
    )

    assert copied._timeout == 30
    assert copied._max_retries == 4
    assert copied._session.headers["x-default"] == "one"
    assert copied._session.headers["x-extra"] == "two"
    assert copied._session.params == {"preview": "one", "page": "2"}
    assert copied.authenticated is True

    with client as entered:
        assert entered is client
        assert client.is_closed() is False
    assert client.is_closed() is True



def test_authenticate_non_interactive_uses_loaded_tokens(monkeypatch):
    monkeypatch.setattr("codex_backend_sdk._client.load_tokens", lambda: _store())
    monkeypatch.setattr("codex_backend_sdk._client.token_needs_refresh", lambda store: False)

    client = CodexClient().authenticate(interactive=False)

    assert client.authenticated is True
    assert client.account_info()["email"] == "user@example.com"



def test_authenticate_non_interactive_without_tokens_raises(monkeypatch):
    monkeypatch.setattr("codex_backend_sdk._client.load_tokens", lambda: None)

    try:
        CodexClient().authenticate(interactive=False)
    except RuntimeError as exc:
        assert "interactive login required" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_authenticate_force_runs_interactive_flow(monkeypatch):
    expected = _store()
    monkeypatch.setattr("codex_backend_sdk._client.load_tokens", lambda: _store())
    monkeypatch.setattr("codex_backend_sdk.oauth.run_oauth_flow", lambda: expected)

    client = CodexClient().authenticate(force=True)

    assert client._store is expected


def test_authenticate_force_requires_interactive_mode():
    try:
        CodexClient().authenticate(force=True, interactive=False)
    except ValueError as exc:
        assert "interactive=True" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_logout_clears_persisted_and_in_memory_credentials(monkeypatch):
    cleared = []
    monkeypatch.setattr("codex_backend_sdk.storage.clear_tokens", lambda: cleared.append(True) or True)
    client = CodexClient(store=_store())

    assert client.logout() is True

    assert cleared == [True]
    assert client.authenticated is False
    assert client.account_info()["authenticated"] is False
    assert "Authorization" not in client._session.headers
    assert "ChatGPT-Account-ID" not in client._session.headers


def test_logout_is_idempotent(monkeypatch):
    monkeypatch.setattr("codex_backend_sdk.storage.clear_tokens", lambda: False)
    client = CodexClient()

    assert client.logout() is False
    assert client.authenticated is False
