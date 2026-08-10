import base64
import json
from unittest.mock import Mock, call, patch

import pytest

from codex_backend_sdk import OpenAI
from codex_backend_sdk.oauth import (
    CLIENT_ID,
    DeviceCode,
    complete_device_code_login,
    refresh_access_token,
    request_device_code,
)


def test_refresh_does_not_narrow_original_oauth_scopes():
    response = Mock()
    response.json.return_value = {"access_token": "refreshed"}

    with patch("codex_backend_sdk.oauth.requests.post", return_value=response) as post:
        result = refresh_access_token("refresh-token")

    assert result == {"access_token": "refreshed"}
    assert post.call_args.kwargs["json"] == {
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token",
    }
    response.raise_for_status.assert_called_once_with()


def response(payload, *, status=200):
    result = Mock()
    result.ok = 200 <= status < 300
    result.status_code = status
    result.json.return_value = payload
    return result


def jwt(account_id="account-1"):
    payload = base64.urlsafe_b64encode(json.dumps({
        "https://api.openai.com/auth": {"chatgpt_account_id": account_id}
    }).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_request_device_code_uses_official_account_route_and_aliases():
    result = response({
        "device_auth_id": "device-1",
        "usercode": "ABCD-EFGH",
        "interval": "5",
    })

    with patch("codex_backend_sdk.oauth.requests.post", return_value=result) as post:
        code = request_device_code()

    assert code == DeviceCode(
        verification_url="https://auth.openai.com/codex/device",
        user_code="ABCD-EFGH",
        device_auth_id="device-1",
        interval=5,
    )
    post.assert_called_once_with(
        "https://auth.openai.com/api/accounts/deviceauth/usercode",
        json={"client_id": CLIENT_ID},
        timeout=30,
    )
    result.raise_for_status.assert_called_once_with()


def test_complete_device_code_polls_exchanges_and_persists():
    pending = response({}, status=404)
    success = response({
        "authorization_code": "authorization-code",
        "code_challenge": "challenge",
        "code_verifier": "verifier",
    })
    tokens = response({
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "id_token": jwt(),
    })
    code = DeviceCode(
        verification_url="https://auth.openai.com/codex/device",
        user_code="ABCD-EFGH",
        device_auth_id="device-1",
        interval=2,
    )
    sleeps = []

    with (
        patch(
            "codex_backend_sdk.oauth.requests.post",
            side_effect=[pending, success, tokens],
        ) as post,
        patch("codex_backend_sdk.oauth.obtain_api_key", return_value="api-key"),
        patch("codex_backend_sdk.oauth.save_tokens") as save,
    ):
        store = complete_device_code_login(
            code,
            allowed_workspace_ids=["account-1"],
            _sleep=sleeps.append,
            _monotonic=lambda: 0,
        )

    assert sleeps == [2]
    assert store.account_id == "account-1"
    assert store.openai_api_key == "api-key"
    save.assert_called_once_with(store)
    assert post.call_args_list == [
        call(
            "https://auth.openai.com/api/accounts/deviceauth/token",
            json={"device_auth_id": "device-1", "user_code": "ABCD-EFGH"},
            timeout=30,
        ),
        call(
            "https://auth.openai.com/api/accounts/deviceauth/token",
            json={"device_auth_id": "device-1", "user_code": "ABCD-EFGH"},
            timeout=30,
        ),
        call(
            "https://auth.openai.com/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": "authorization-code",
                "redirect_uri": "https://auth.openai.com/deviceauth/callback",
                "client_id": CLIENT_ID,
                "code_verifier": "verifier",
            },
            timeout=30,
        ),
    ]


def test_device_code_rejects_workspace_mismatch_before_persistence():
    code = DeviceCode(
        verification_url="https://auth.openai.com/codex/device",
        user_code="CODE",
        device_auth_id="device",
        interval=1,
    )
    success = response({
        "authorization_code": "code",
        "code_challenge": "challenge",
        "code_verifier": "verifier",
    })
    tokens = response({
        "access_token": "access",
        "refresh_token": "refresh",
        "id_token": jwt("other-workspace"),
    })
    with (
        patch("codex_backend_sdk.oauth.requests.post", side_effect=[success, tokens]),
        patch("codex_backend_sdk.oauth.obtain_api_key", return_value=None),
        patch("codex_backend_sdk.oauth.save_tokens") as save,
        pytest.raises(PermissionError, match="outside"),
    ):
        complete_device_code_login(code, allowed_workspace_ids=["allowed"])
    save.assert_not_called()


def test_device_code_validates_issuer_and_timeout():
    with pytest.raises(ValueError, match="HTTPS"):
        request_device_code(issuer="http://example.test")
    code = DeviceCode("https://auth.openai.com/codex/device", "CODE", "id", 1)
    with pytest.raises(ValueError, match="timeout"):
        complete_device_code_login(code, timeout=0)


def test_client_device_authentication_reports_code_and_sets_store():
    code = DeviceCode("https://auth.openai.com/codex/device", "CODE", "id", 1)
    store = Mock(account_id="account-1")
    seen = []
    client = OpenAI()
    with (
        patch("codex_backend_sdk.oauth.request_device_code", return_value=code),
        patch(
            "codex_backend_sdk.oauth.complete_device_code_login", return_value=store
        ) as complete,
        patch.object(client, "_set_store") as set_store,
    ):
        result = client.authenticate_device_code(
            on_code=seen.append,
            persist=False,
            timeout=60,
            allowed_workspace_ids=["account-1"],
        )
    assert result is client
    assert seen == [code]
    complete.assert_called_once_with(
        code,
        timeout=60,
        persist=False,
        allowed_workspace_ids=["account-1"],
    )
    set_store.assert_called_once_with(store)
