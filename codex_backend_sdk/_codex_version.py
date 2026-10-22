"""Shared discovery of the upstream Codex CLI version (not the SDK version)."""

import re
import threading
import time

import requests


# Last verified upstream protocol version, used when discovery is unavailable.
CLIENT_VERSION = "0.163.0"
_RETRY_TTL = 300
_VERSION_TTL = 24 * 60 * 60
_VERSION_URL = "https://registry.npmjs.org/@openai/codex/latest"
_version = CLIENT_VERSION
_version_refresh_at = 0.0
_version_lock = threading.Lock()


def codex_client_version() -> str:
    """Discover the stable CLI version without sharing backend credentials.

    Cache across clients in this process. Failed refreshes retain the last known
    version and wait five minutes before retrying, including on first use.
    """
    global _version, _version_refresh_at
    with _version_lock:
        if time.monotonic() < _version_refresh_at:
            return _version
        ttl = _VERSION_TTL
        try:
            with requests.get(_VERSION_URL, timeout=3) as response:
                response.raise_for_status()
                payload = response.json()
            candidate = payload.get("version") if isinstance(payload, dict) else None
            if not isinstance(candidate, str) or not re.fullmatch(
                r"[0-9]+\.[0-9]+\.[0-9]+", candidate
            ):
                raise ValueError("Invalid stable Codex version")
            _version = candidate
        except (requests.RequestException, ValueError):
            ttl = _RETRY_TTL
        _version_refresh_at = time.monotonic() + ttl
        return _version

