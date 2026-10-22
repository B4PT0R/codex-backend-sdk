"""Offline tests for upstream version discovery; no OAuth or npm binary."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
import requests

from codex_backend_sdk import _codex_version as version


@pytest.fixture
def registry(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(version.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(version, "_version", version.CLIENT_VERSION)
    monkeypatch.setattr(version, "_version_refresh_at", 0.0)
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = {"version": "0.170.0"}
    get = MagicMock(return_value=response)
    monkeypatch.setattr(version.requests, "get", get)
    return clock, get, response


def test_version_uses_standalone_https_and_caches_for_24_hours(registry):
    clock, get, response = registry
    assert version.codex_client_version() == "0.170.0"
    get.assert_called_once_with(version._VERSION_URL, timeout=3)
    response.raise_for_status.assert_called_once()
    response.__exit__.assert_called_once()
    clock[0] += 86400 - 1
    assert version.codex_client_version() == "0.170.0"
    assert get.call_count == 1
    clock[0] += 1
    response.json.return_value = {"version": "0.171.0"}
    assert version.codex_client_version() == "0.171.0"
    assert get.call_count == 2


@pytest.mark.parametrize("error", [requests.Timeout(), requests.HTTPError(), ValueError()])
def test_first_failure_uses_verified_fallback_and_backs_off(registry, error):
    clock, get, _ = registry
    get.side_effect = error
    assert version.codex_client_version() == version.CLIENT_VERSION
    assert version.codex_client_version() == version.CLIENT_VERSION
    assert get.call_count == 1
    clock[0] += 300
    get.side_effect = None
    assert version.codex_client_version() == "0.170.0"
    assert get.call_count == 2



@pytest.mark.parametrize("stage", ["raise_for_status", "json"])
def test_response_errors_close_request_and_use_fallback(registry, stage):
    _, _, response = registry
    error = requests.HTTPError() if stage == "raise_for_status" else ValueError()
    getattr(response, stage).side_effect = error
    assert version.codex_client_version() == version.CLIENT_VERSION
    response.__exit__.assert_called_once()


def test_refresh_failure_keeps_last_success(registry):
    clock, get, _ = registry
    assert version.codex_client_version() == "0.170.0"
    clock[0] += 86400
    get.side_effect = requests.ConnectionError()
    assert version.codex_client_version() == "0.170.0"
    assert version.codex_client_version() == "0.170.0"
    assert get.call_count == 2


@pytest.mark.parametrize("payload", [
    None, [], {}, {"version": 123}, {"version": "0.170.0-beta.1"},
    {"version": "garbage"}, {"version": "0.170.0\n"},
])
def test_invalid_registry_metadata_uses_fallback(registry, payload):
    _, _, response = registry
    response.json.return_value = payload
    assert version.codex_client_version() == version.CLIENT_VERSION


def test_concurrent_clients_share_one_lookup(registry):
    _, get, _ = registry
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(lambda _: version.codex_client_version(), range(16))) == ["0.170.0"] * 16
    assert get.call_count == 1
