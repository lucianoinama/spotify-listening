"""Last.fm client: top tags for an artist, used as a genre source."""

import os

import requests

API_URL = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "spotify-listening-pipeline/1.0 (personal project)"
# Last.fm error codes that mean "no such artist": a stable answer, safe to store.
ARTIST_NOT_FOUND = 6


class LastFmError(RuntimeError):
    pass


class LastFmClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.environ["LASTFM_API_KEY"]
        self.session = session or requests.Session()

    def top_tags(self, artist_name: str) -> dict:
        """Raw artist.getTopTags response. An unknown artist returns the error payload."""
        try:
            resp = self.session.get(
                API_URL,
                params={
                    "method": "artist.gettoptags",
                    "artist": artist_name,
                    "autocorrect": 1,
                    "api_key": self.api_key,
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            # requests puts the full URL, API key included, in its messages: do not chain it.
            raise LastFmError(f"Last.fm request failed ({type(exc).__name__})") from None

        error = body.get("error")
        if error is None or error == ARTIST_NOT_FOUND:
            return body
        raise LastFmError(f"Last.fm error {error}: {body.get('message')}")
