from unittest.mock import Mock, patch

from codex_backend_sdk.oauth import CLIENT_ID, refresh_access_token


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
