"""One-time Spotify login (Authorization Code flow with PKCE).

Prints a URL, waits for Spotify to redirect back to a local callback, then stores the
refresh token in the token file. The ingester renews access tokens from it afterwards.
"""

import base64
import hashlib
import os
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from . import tokens

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = "user-read-recently-played"
LOGIN_TIMEOUT_SECONDS = 300


def make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) as defined by RFC 7636 (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "scope": SCOPES,
            "redirect_uri": redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.server.callback_path:
            self.send_error(404)
            return
        self.server.params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Login received. You can close this tab.")

    def log_message(self, *args):
        pass


def wait_for_callback(redirect_uri: str) -> dict:
    parsed = urllib.parse.urlparse(redirect_uri)
    bind_host = os.environ.get("AUTH_BIND_HOST", parsed.hostname)
    server = HTTPServer((bind_host, parsed.port), _CallbackHandler)
    server.callback_path = parsed.path
    server.params = None
    server.timeout = 1
    deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
    try:
        while server.params is None:
            if time.monotonic() > deadline:
                raise TimeoutError("No callback received from Spotify within 5 minutes.")
            server.handle_request()
    finally:
        server.server_close()
    return server.params


def main() -> None:
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    redirect_uri = os.environ["SPOTIFY_REDIRECT_URI"]

    verifier, challenge = make_pkce_pair()
    state = secrets.token_urlsafe(16)
    url = build_authorize_url(client_id, redirect_uri, challenge, state)

    print("Open this URL in your browser and approve access:\n")
    print(url, "\n")
    webbrowser.open(url)

    params = wait_for_callback(redirect_uri)
    if params.get("state") != state:
        raise SystemExit("State mismatch: aborting login.")
    if "error" in params:
        raise SystemExit(f"Spotify returned an error: {params['error']}")

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": params["code"],
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    tokens.save(body["refresh_token"], body["access_token"], body["expires_in"])
    print(f"Login OK. Token saved to {tokens.token_path()}")


if __name__ == "__main__":
    main()
