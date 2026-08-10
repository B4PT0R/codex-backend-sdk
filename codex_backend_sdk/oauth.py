"""
ChatGPT OAuth flow — mirrors codex-rs/login/src/server.rs.

Flow:
  1. Generate PKCE + state
  2. Build authorization URL → open browser
  3. Listen on localhost:1455 for the OAuth callback
  4. Exchange authorization code for tokens
  5. Optionally exchange id_token for an OpenAI API key
  6. Persist tokens to ~/.codex/auth.json
"""

import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import requests

from .pkce import PkceCodes, generate_pkce, generate_state
from .storage import TokenStore, save_tokens

ISSUER = "https://auth.openai.com"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CALLBACK_PORT = 1455
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/auth/callback"
SCOPES = "openid profile email offline_access api.connectors.read api.connectors.invoke"
ORIGINATOR = "codex_cli_rs"

# Result container shared between the HTTP handler and the caller
_oauth_result: dict = {}
_oauth_event = threading.Event()   # set when code received
_server_done_event = threading.Event()  # set when /success is served


def _build_authorize_url(
    pkce: PkceCodes,
    state: str,
    workspace_id: Optional[str] = None,
    scopes: Optional[str] = None,
) -> str:
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": scopes or SCOPES,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": ORIGINATOR,
    }
    if workspace_id:
        params["allowed_workspace_id"] = workspace_id
    # Use quote (RFC 3986, spaces → %20) not quote_plus (spaces → +),
    # matching the urlencoding::encode behaviour in codex-rs/login/src/server.rs.
    qs = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in params.items())
    return f"{ISSUER}/oauth/authorize?{qs}"


def _make_handler(pkce: PkceCodes, state: str):
    """Factory that returns an HTTP handler class closed over pkce/state."""

    class _CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # suppress default access log
            pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(parsed.query))

            if parsed.path == "/auth/callback":
                self._handle_callback(params)
            elif parsed.path == "/success":
                self._send_html(200, (
                    "<html><body style='font-family:sans-serif;padding:2em'>"
                    "<h2>✓ Login successful</h2>"
                    "<p>You can close this tab and return to the terminal.</p>"
                    "</body></html>"
                ))
                _server_done_event.set()
            else:
                self._send_text(404, "Not found")

        def _handle_callback(self, params: dict):
            if params.get("state") != state:
                self._send_text(400, "State mismatch — possible CSRF attack.")
                _oauth_result["error"] = "state_mismatch"
                _oauth_event.set()
                return

            if error := params.get("error"):
                desc = params.get("error_description", error)
                self._send_html(400, f"<h2>Login failed</h2><p>{desc}</p>")
                _oauth_result["error"] = desc
                _oauth_event.set()
                return

            code = params.get("code", "")
            if not code:
                self._send_text(400, "Missing authorization code.")
                _oauth_result["error"] = "missing_code"
                _oauth_event.set()
                return

            # Redirect browser to /success while we process in background
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{CALLBACK_PORT}/success")
            self.end_headers()

            _oauth_result["code"] = code
            _oauth_event.set()

        def _send_text(self, status: int, body: str):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, status: int, body: str):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return _CallbackHandler


def _exchange_code(code: str, pkce: PkceCodes) -> dict:
    """POST authorization code to token endpoint, return raw JSON."""
    resp = requests.post(
        f"{ISSUER}/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": pkce.code_verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def obtain_api_key(id_token: str) -> str:
    """Exchange a fresh ChatGPT ID token for the API key used by Realtime."""
    resp = requests.post(
        f"{ISSUER}/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": CLIENT_ID,
            "requested_token": "openai-api-key",
            "subject_token": id_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def refresh_access_token(refresh_token: str) -> dict:
    """
    Use a refresh token to get a new access_token (and optionally a new refresh_token).
    Returns the raw JSON response from the token endpoint.
    """
    resp = requests.post(
        f"{ISSUER}/oauth/token",
        headers={"Content-Type": "application/json"},
        json={
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def run_oauth_flow(
    *,
    open_browser: bool = True,
    persist: bool = True,
    workspace_id: Optional[str] = None,
    scopes: Optional[str] = None,
) -> TokenStore:
    """
    Run the full OAuth authorization-code + PKCE flow.

    Opens the browser (unless open_browser=False), waits for the callback,
    exchanges the code for OAuth tokens and saves them to ~/.codex/auth.json.

    Returns a TokenStore with all credentials.
    """
    global _oauth_result, _oauth_event, _server_done_event
    _oauth_result = {}
    _oauth_event = threading.Event()
    _server_done_event = threading.Event()

    pkce = generate_pkce()
    state = generate_state()

    handler_cls = _make_handler(pkce, state)
    try:
        server = HTTPServer(("127.0.0.1", CALLBACK_PORT), handler_cls)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot bind to localhost:{CALLBACK_PORT} — "
            "another process may still be holding that port from a previous login attempt. "
            f"(OS error: {exc})"
        ) from exc
    server.timeout = 1  # allow periodic _oauth_event checks

    auth_url = _build_authorize_url(pkce, state, workspace_id=workspace_id, scopes=scopes)
    print(f"\n[auth] Opening browser for login:\n  {auth_url}\n")

    if open_browser:
        webbrowser.open(auth_url)
    else:
        print("[auth] open_browser=False — open the URL above manually.")

    print("[auth] Waiting for OAuth callback on localhost:1455 …")
    # Keep serving until /success is served (happy path) or callback signals an error
    while not _server_done_event.is_set():
        server.handle_request()
        if _oauth_event.is_set() and _oauth_result.get("error"):
            break

    server.server_close()

    if error := _oauth_result.get("error"):
        raise RuntimeError(f"OAuth callback error: {error}")

    code = _oauth_result["code"]
    print("[auth] Authorization code received — exchanging for tokens …")

    raw = _exchange_code(code, pkce)
    access_token = raw["access_token"]
    refresh_token = raw["refresh_token"]
    id_token = raw["id_token"]

    try:
        openai_api_key = obtain_api_key(id_token)
    except requests.HTTPError:
        openai_api_key = None

    store = TokenStore.from_exchange(
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
        openai_api_key=openai_api_key,
    )

    if persist:
        save_tokens(store)
        print("[auth] Tokens saved to ~/.codex/auth.json")

    return store
