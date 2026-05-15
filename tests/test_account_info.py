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
