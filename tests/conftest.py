"""Shared fixtures for integration tests (real API calls)."""

import pytest
from codex_backend_sdk import CodexClient


@pytest.fixture(scope="session")
def client() -> CodexClient:
    """Authenticated client reused across the whole test session."""
    return CodexClient().authenticate()
