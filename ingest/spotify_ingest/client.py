"""Minimal Spotify Web API client: token refresh, retries, the two calls we need."""

import logging
import os
import time

import requests

from . import tokens

API_BASE = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
MAX_ATTEMPTS = 5
# A longer Retry-After usually means a quota block, not a burst limit: fail instead of sleeping.
MAX_RETRY_AFTER_SECONDS = 300

log = logging.getLogger(__name__)


class SpotifyError(RuntimeError):
    """Spotify refused or gave up. retry_after is the wait it asked for, when it asked."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class SpotifyClient:
    def __init__(self, client_id: str | None = None, session: requests.Session | None = None):
        self.client_id = client_id or os.environ["SPOTIFY_CLIENT_ID"]
        self.session = session or requests.Session()

    def _access_token(self) -> str:
        token = tokens.load()
        if token["expires_at"] > time.time():
            return token["access_token"]
        resp = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": self.client_id,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        # Spotify may rotate the refresh token; keep the old one if it did not.
        tokens.save(
            body.get("refresh_token", token["refresh_token"]),
            body["access_token"],
            body["expires_in"],
        )
        return body["access_token"]

    def _get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(MAX_ATTEMPTS):
            resp = self.session.get(
                f"{API_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=30,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "1")) + 1
                if wait > MAX_RETRY_AFTER_SECONDS:
                    raise SpotifyError(
                        f"Rate limited for {wait}s on {path}: {resp.text}", retry_after=wait
                    )
                log.warning("429 on %s, sleeping %ss", path, wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = 2**attempt
                log.warning("%s on %s, retrying in %ss", resp.status_code, path, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise SpotifyError(f"Gave up on {path} after {MAX_ATTEMPTS} attempts")

    def recently_played(self, limit: int = 50) -> list[dict]:
        """Last plays, newest first. Spotify caps this at 50 items and a short window."""
        return self._get("/me/player/recently-played", {"limit": limit}).get("items", [])

    def track(self, track_id: str) -> dict:
        """One track, with its album, artists and cover. Used to fill in the extended history."""
        return self._get(f"/tracks/{track_id}")

    def artist(self, artist_id: str) -> dict:
        """One artist. Batch lookups were removed for development-mode apps in 2026."""
        return self._get(f"/artists/{artist_id}")
