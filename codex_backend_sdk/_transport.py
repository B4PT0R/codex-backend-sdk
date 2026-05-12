"""HTTP transport helpers shared by client resources."""

from __future__ import annotations

import time
from typing import Any

import requests


def request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    *,
    max_retries: int,
    retry_base_delay: float,
    use_session: bool = True,
    **kwargs: Any,
) -> requests.Response:
    last_error: requests.RequestException | None = None
    for attempt in range(max_retries + 1):
        try:
            request = session.request if use_session else requests.request
            response = request(method, url, **kwargs)
            if should_retry_response(response, attempt, max_retries=max_retries):
                sleep_before_retry(response, attempt, retry_base_delay=retry_base_delay)
                continue
            response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            sleep_before_retry(None, attempt, retry_base_delay=retry_base_delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Request retry loop exhausted")


def should_retry_response(
    response: requests.Response,
    attempt: int,
    *,
    max_retries: int,
) -> bool:
    if attempt >= max_retries:
        return False
    return response.status_code == 429 or 500 <= response.status_code < 600


def sleep_before_retry(
    response: requests.Response | None,
    attempt: int,
    *,
    retry_base_delay: float,
) -> None:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    delay = parse_retry_after(retry_after)
    if delay is None:
        delay = retry_base_delay * (2 ** attempt)
    time.sleep(delay)


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
