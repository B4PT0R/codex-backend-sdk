#!/usr/bin/env python3
"""Probe OpenAI/Codex endpoints available to the current ChatGPT auth store.

The default mode is intentionally read-only: it sends GET/OPTIONS requests to
candidate endpoints and records status codes, content types, request IDs, and a
small body preview. It does not create resources.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from codex_backend_sdk.storage import TokenStore, load_tokens


OPENAI_BASE_URL = "https://api.openai.com/v1"
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
WHAM_BASE_URL = "https://chatgpt.com/backend-api"
ORIGINATOR = "codex_cli_rs"


@dataclass(frozen=True)
class Candidate:
    name: str
    base: str
    method: str
    path: str
    auth: str
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    body: dict[str, Any] | None = None
    mutating: bool = False
    note: str = ""


@dataclass
class ProbeResult:
    name: str
    base: str
    method: str
    path: str
    url: str
    auth: str
    status_code: int | None
    category: str
    elapsed_ms: int
    content_type: str | None = None
    request_id: str | None = None
    allow: str | None = None
    body_preview: Any = None
    error: str | None = None
    note: str = ""


def openai_candidates() -> list[Candidate]:
    base_headers = {"OpenAI-Beta": "assistants=v2"}
    return [
        Candidate("models.list", OPENAI_BASE_URL, "GET", "/models", "openai"),
        Candidate("files.list", OPENAI_BASE_URL, "GET", "/files", "openai", {"limit": 1}),
        Candidate("vector_stores.list", OPENAI_BASE_URL, "GET", "/vector_stores", "openai", {"limit": 1}, base_headers),
        Candidate("assistants.list", OPENAI_BASE_URL, "GET", "/assistants", "openai", {"limit": 1}, base_headers),
        Candidate("threads.probe", OPENAI_BASE_URL, "OPTIONS", "/threads", "openai", headers=base_headers),
        Candidate("responses.probe", OPENAI_BASE_URL, "OPTIONS", "/responses", "openai"),
        Candidate("responses.compact.probe", OPENAI_BASE_URL, "OPTIONS", "/responses/compact", "openai"),
        Candidate("realtime.calls.probe", OPENAI_BASE_URL, "OPTIONS", "/realtime/calls", "openai", headers={"OpenAI-Beta": "realtime=v1"}),
        Candidate("batches.list", OPENAI_BASE_URL, "GET", "/batches", "openai", {"limit": 1}),
        Candidate("uploads.probe", OPENAI_BASE_URL, "OPTIONS", "/uploads", "openai"),
        Candidate("containers.list", OPENAI_BASE_URL, "GET", "/containers", "openai", {"limit": 1}),
        Candidate("evals.list", OPENAI_BASE_URL, "GET", "/evals", "openai", {"limit": 1}),
        Candidate("fine_tuning.jobs.list", OPENAI_BASE_URL, "GET", "/fine_tuning/jobs", "openai", {"limit": 1}),
        Candidate("organization.costs", OPENAI_BASE_URL, "GET", "/organization/costs", "openai", {"limit": 1}),
        Candidate("organization.usage.completions", OPENAI_BASE_URL, "GET", "/organization/usage/completions", "openai", {"limit": 1}),
        Candidate("organization.usage.responses", OPENAI_BASE_URL, "GET", "/organization/usage/responses", "openai", {"limit": 1}),
        Candidate("organization.usage.vector_stores", OPENAI_BASE_URL, "GET", "/organization/usage/vector_stores", "openai", {"limit": 1}),
        Candidate("moderations.probe", OPENAI_BASE_URL, "OPTIONS", "/moderations", "openai"),
        Candidate("images.probe", OPENAI_BASE_URL, "OPTIONS", "/images/generations", "openai"),
        Candidate("audio.speech.probe", OPENAI_BASE_URL, "OPTIONS", "/audio/speech", "openai"),
        Candidate("audio.transcriptions.probe", OPENAI_BASE_URL, "OPTIONS", "/audio/transcriptions", "openai"),
        Candidate("chat.completions.probe", OPENAI_BASE_URL, "OPTIONS", "/chat/completions", "openai"),
        Candidate("embeddings.probe", OPENAI_BASE_URL, "OPTIONS", "/embeddings", "openai"),
    ]


def chatgpt_candidates() -> list[Candidate]:
    return [
        Candidate("codex.models", CODEX_BASE_URL, "GET", "/models", "chatgpt", {"client_version": "0.3.0"}),
        Candidate("codex.responses.probe", CODEX_BASE_URL, "OPTIONS", "/responses", "chatgpt"),
        Candidate("codex.responses.compact.probe", CODEX_BASE_URL, "OPTIONS", "/responses/compact", "chatgpt"),
        Candidate("codex.realtime.calls.probe", CODEX_BASE_URL, "OPTIONS", "/realtime/calls", "chatgpt"),
        Candidate("codex.memories.trace_summarize.probe", CODEX_BASE_URL, "OPTIONS", "/memories/trace_summarize", "chatgpt"),
        Candidate("wham.usage", WHAM_BASE_URL, "GET", "/wham/usage", "chatgpt"),
        Candidate("wham.config.requirements", WHAM_BASE_URL, "GET", "/wham/config/requirements", "chatgpt"),
        Candidate("wham.tasks.list", WHAM_BASE_URL, "GET", "/wham/tasks/list", "chatgpt", {"limit": 1}),
        Candidate("wham.remote.control.enroll.probe", WHAM_BASE_URL, "OPTIONS", "/wham/remote/control/server/enroll", "chatgpt"),
    ]


def build_headers(store: TokenStore, auth: str, extra: dict[str, str] | None) -> dict[str, str]:
    if auth == "openai":
        if not store.openai_api_key:
            raise RuntimeError("No openai_api_key in auth store. Run authenticate(request_api_key=True).")
        headers = {"Authorization": f"Bearer {store.openai_api_key}"}
    elif auth == "chatgpt":
        headers = {
            "Authorization": f"Bearer {store.access_token}",
            "originator": ORIGINATOR,
            "OpenAI-Beta": "responses=experimental",
        }
        if store.account_id:
            headers["ChatGPT-Account-ID"] = store.account_id
    else:
        raise ValueError(f"Unknown auth mode: {auth}")

    headers.update(extra or {})
    return headers


def categorize(status_code: int | None, error: str | None = None) -> str:
    if error is not None:
        return "error"
    if status_code is None:
        return "error"
    if 200 <= status_code < 300:
        return "available"
    if status_code == 401:
        return "unauthenticated"
    if status_code == 403:
        return "forbidden_or_plan_gated"
    if status_code == 404:
        return "not_found_or_hidden"
    if status_code == 405:
        return "exists_method_not_allowed"
    if status_code == 429:
        return "rate_limited"
    if 400 <= status_code < 500:
        return "client_rejected"
    if 500 <= status_code < 600:
        return "server_error"
    return "other"


def preview_body(response: requests.Response) -> Any:
    text = response.text[:1000]
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        return text
    try:
        data = response.json()
    except ValueError:
        return text
    if isinstance(data, dict):
        return redact(data)
    return data


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(secret in lowered for secret in ("token", "secret", "key", "email", "account_id", "user_id")):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def probe(candidate: Candidate, store: TokenStore, timeout: float) -> ProbeResult:
    url = urljoin(candidate.base.rstrip("/") + "/", candidate.path.lstrip("/"))
    start = time.monotonic()
    try:
        response = requests.request(
            candidate.method,
            url,
            params=candidate.params,
            json=candidate.body,
            headers=build_headers(store, candidate.auth, candidate.headers),
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ProbeResult(
            name=candidate.name,
            base=candidate.base,
            method=candidate.method,
            path=candidate.path,
            url=response.url,
            auth=candidate.auth,
            status_code=response.status_code,
            category=categorize(response.status_code),
            elapsed_ms=elapsed_ms,
            content_type=response.headers.get("content-type"),
            request_id=response.headers.get("x-request-id") or response.headers.get("openai-processing-ms"),
            allow=response.headers.get("allow"),
            body_preview=preview_body(response),
            note=candidate.note,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ProbeResult(
            name=candidate.name,
            base=candidate.base,
            method=candidate.method,
            path=candidate.path,
            url=url,
            auth=candidate.auth,
            status_code=None,
            category=categorize(None, str(exc)),
            elapsed_ms=elapsed_ms,
            error=f"{type(exc).__name__}: {exc}",
            note=candidate.note,
        )


def select_candidates(scope: str, include_mutating: bool) -> list[Candidate]:
    candidates: list[Candidate] = []
    if scope in {"all", "openai"}:
        candidates.extend(openai_candidates())
    if scope in {"all", "chatgpt"}:
        candidates.extend(chatgpt_candidates())
    if not include_mutating:
        candidates = [candidate for candidate in candidates if not candidate.mutating]
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["all", "openai", "chatgpt"], default="all")
    parser.add_argument("--output", type=Path, default=Path("endpoint-probe-results.json"))
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--sleep", type=float, default=0.25, help="Delay between probes in seconds.")
    parser.add_argument("--include-mutating", action="store_true", help="Include candidates marked mutating.")
    args = parser.parse_args()

    store = load_tokens()
    if store is None:
        raise SystemExit("No Codex auth store found. Run `python -c 'from codex_backend_sdk import OpenAI; OpenAI().authenticate()'` first.")

    results: list[ProbeResult] = []
    for candidate in select_candidates(args.scope, args.include_mutating):
        result = probe(candidate, store, args.timeout)
        results.append(result)
        print(f"{result.category:25} {result.status_code or '-':>3} {candidate.method:7} {candidate.auth:7} {candidate.path} ({candidate.name})")
        if args.sleep:
            time.sleep(args.sleep)

    payload = {
        "generated_at": int(time.time()),
        "scope": args.scope,
        "read_only_default": not args.include_mutating,
        "results": [asdict(result) for result in results],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
