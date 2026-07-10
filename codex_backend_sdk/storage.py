"""Token persistence — mirrors codex-rs/login/src/auth/storage.rs.

Stores tokens in ~/.codex/auth.json (same format as the Codex CLI).
"""

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REFRESH_EXPIRY_MARGIN_S = 5 * 60   # refresh if exp within 5 minutes
REFRESH_INTERVAL_S = 55 * 60       # refresh at least every 55 minutes


def _codex_home() -> Path:
    if env := os.environ.get("CODEX_HOME"):
        return Path(env)
    return Path.home() / ".codex"


def _auth_path() -> Path:
    return _codex_home() / "auth.json"


def _decode_jwt_payload(token: str) -> dict:
    """Decode the payload section of a JWT without verification."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    # Add padding if needed
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    try:
        raw = base64.urlsafe_b64decode(payload_b64)
        return json.loads(raw)
    except Exception:
        return {}


def _extract_openai_claims(token: str) -> dict:
    """Extract the nested 'https://api.openai.com/auth' claims from a JWT."""
    payload = _decode_jwt_payload(token)
    return payload.get("https://api.openai.com/auth", {})


@dataclass
class TokenStore:
    access_token: str
    refresh_token: str
    id_token_raw: str
    account_id: Optional[str] = None
    openai_api_key: Optional[str] = None
    last_refresh: Optional[str] = None
    # Decoded claims from id_token for convenience
    email: Optional[str] = None
    plan_type: Optional[str] = None

    @classmethod
    def from_exchange(
        cls,
        access_token: str,
        refresh_token: str,
        id_token: str,
        openai_api_key: Optional[str] = None,
    ) -> "TokenStore":
        claims = _extract_openai_claims(id_token)
        access_claims = _extract_openai_claims(access_token)

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token_raw=id_token,
            account_id=claims.get("chatgpt_account_id"),
            openai_api_key=openai_api_key,
            last_refresh=datetime.now(timezone.utc).isoformat(),
            email=_decode_jwt_payload(id_token).get("email"),
            plan_type=access_claims.get("chatgpt_plan_type"),
        )


def token_needs_refresh(store: TokenStore) -> bool:
    """
    Return True if the access token should be refreshed before use.

    Mirrors openai-oauth auth.ts shouldRefreshAccessToken:
      - exp claim within REFRESH_EXPIRY_MARGIN_S seconds → refresh
      - last_refresh older than REFRESH_INTERVAL_S → refresh
    """
    now = datetime.now(timezone.utc).timestamp()

    claims = _decode_jwt_payload(store.access_token)
    exp = claims.get("exp")
    if isinstance(exp, (int, float)):
        if exp <= now + REFRESH_EXPIRY_MARGIN_S:
            return True
        # Token has a valid exp and it's not near expiry — trust it
        return False

    # No exp claim — fall back to last_refresh timestamp
    if store.last_refresh:
        try:
            refreshed_at = datetime.fromisoformat(store.last_refresh)
            if (datetime.now(timezone.utc) - refreshed_at).total_seconds() >= REFRESH_INTERVAL_S:
                return True
        except Exception:
            pass

    return False


def save_tokens(store: TokenStore) -> None:
    path = _auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": store.openai_api_key,
        "tokens": {
            "access_token": store.access_token,
            "refresh_token": store.refresh_token,
            "id_token": store.id_token_raw,
            "account_id": store.account_id,
        },
        "last_refresh": store.last_refresh,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Restrict permissions on Unix
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_tokens() -> Optional[TokenStore]:
    path = _auth_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    tokens = data.get("tokens") or {}
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    id_token = tokens.get("id_token", "")

    if not access_token:
        return None

    return TokenStore(
        access_token=access_token,
        refresh_token=refresh_token,
        id_token_raw=id_token,
        account_id=tokens.get("account_id"),
        openai_api_key=data.get("OPENAI_API_KEY") or data.get("openai_api_key"),
        last_refresh=data.get("last_refresh"),
        email=_decode_jwt_payload(id_token).get("email"),
        plan_type=_extract_openai_claims(access_token).get("chatgpt_plan_type"),
    )
