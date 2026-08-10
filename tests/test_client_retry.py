import requests

import codex_backend_sdk._transport as transport_module
from codex_backend_sdk import OpenAI


class DummySession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class RetryClient(OpenAI):
    def __init__(self, outcomes, **kwargs):
        super().__init__(max_retries=kwargs.pop("max_retries", 2), retry_base_delay=0, **kwargs)
        self._session = DummySession(outcomes)

    def _ensure_auth(self):
        return None


def _response(status_code, *, body=b"{}", headers=None):
    response = requests.Response()
    response.status_code = status_code
    response._content = body
    response.headers.update(headers or {})
    response.url = "https://example.test"
    return response


def test_retry_retries_5xx_then_returns_success(monkeypatch):
    sleeps = []
    monkeypatch.setattr(transport_module.time, "sleep", sleeps.append)
    client = RetryClient([
        _response(503),
        _response(200, body=b'{"ok": true}'),
    ])

    response = client._get_raw("/models")

    assert response.json() == {"ok": True}
    assert len(client._session.calls) == 2
    assert sleeps == [0]


def test_retry_honors_retry_after_header(monkeypatch):
    sleeps = []
    monkeypatch.setattr(transport_module.time, "sleep", sleeps.append)
    client = RetryClient([
        _response(429, headers={"Retry-After": "1.5"}),
        _response(200),
    ])

    client._get_raw("/models")

    assert len(client._session.calls) == 2
    assert sleeps == [1.5]


def test_retry_does_not_retry_client_errors(monkeypatch):
    sleeps = []
    monkeypatch.setattr(transport_module.time, "sleep", sleeps.append)
    client = RetryClient([
        _response(400, body=b'{"error": "bad request"}'),
    ])

    try:
        client._get_raw("/models")
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("Expected HTTPError")

    assert len(client._session.calls) == 1
    assert sleeps == []


def test_retry_retries_transport_timeout(monkeypatch):
    sleeps = []
    monkeypatch.setattr(transport_module.time, "sleep", sleeps.append)
    client = RetryClient([
        requests.Timeout("temporary timeout"),
        _response(200, body=b'{"ok": true}'),
    ])

    response = client._get_raw("/models")

    assert response.json() == {"ok": True}
    assert len(client._session.calls) == 2
    assert sleeps == [0]


def test_chatgpt_backend_download_uses_authenticated_session():
    response = _response(200, body=b"private")
    client = RetryClient([response])

    result = client._download_chatgpt_link("/backend-api/files/private")

    assert result.content == b"private"
    assert client._session.calls[0][1] == "https://chatgpt.com/backend-api/files/private"


def test_external_signed_download_does_not_use_oauth_session(monkeypatch):
    response = _response(200, body=b"signed")
    calls = []

    def external_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response

    monkeypatch.setattr(transport_module.requests, "request", external_request)
    client = RetryClient([])

    result = client._download_chatgpt_link("https://cdn.example.test/signed?token=opaque")

    assert result.content == b"signed"
    assert client._session.calls == []
    assert calls == [
        (
            "GET",
            "https://cdn.example.test/signed?token=opaque",
            {"timeout": 120},
        )
    ]


def test_chatgpt_download_rejects_non_http_urls():
    client = RetryClient([])

    try:
        client._download_chatgpt_link("file:///etc/passwd")
    except ValueError as exc:
        assert "invalid download URL" in str(exc)
    else:
        raise AssertionError("Expected invalid download URL")
