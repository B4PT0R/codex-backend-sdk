import requests

import codex_backend_sdk._client as client_module
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
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
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
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
    client = RetryClient([
        _response(429, headers={"Retry-After": "1.5"}),
        _response(200),
    ])

    client._get_raw("/models")

    assert len(client._session.calls) == 2
    assert sleeps == [1.5]


def test_retry_does_not_retry_client_errors(monkeypatch):
    sleeps = []
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
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
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
    client = RetryClient([
        requests.Timeout("temporary timeout"),
        _response(200, body=b'{"ok": true}'),
    ])

    response = client._get_raw("/models")

    assert response.json() == {"ok": True}
    assert len(client._session.calls) == 2
    assert sleeps == [0]
