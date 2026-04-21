"""PKCE (Proof Key for Code Exchange) helpers — mirrors codex-rs/login/src/pkce.rs."""

import base64
import hashlib
import os
from dataclasses import dataclass


@dataclass
class PkceCodes:
    code_verifier: str
    code_challenge: str


def generate_pkce() -> PkceCodes:
    """Generate a PKCE pair using S256 method."""
    raw = os.urandom(64)
    code_verifier = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    return PkceCodes(code_verifier=code_verifier, code_challenge=code_challenge)


def generate_state() -> str:
    """Generate a cryptographically random state parameter."""
    raw = os.urandom(32)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
