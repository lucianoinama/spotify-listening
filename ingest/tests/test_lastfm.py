import pytest
import requests

from spotify_ingest.lastfm import LastFmClient, LastFmError


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, body=None, exc=None):
        self.body = body
        self.exc = exc
        self.params = None

    def get(self, url, params=None, **kwargs):
        self.params = params
        if self.exc:
            raise self.exc
        return FakeResponse(self.body)


def test_top_tags_returns_payload_and_autocorrects():
    session = FakeSession({"toptags": {"tag": [{"name": "rock", "count": 100}]}})
    body = LastFmClient("key", session).top_tags("Some Band")
    assert body["toptags"]["tag"][0]["name"] == "rock"
    assert session.params["artist"] == "Some Band"
    assert session.params["autocorrect"] == 1


def test_unknown_artist_is_returned_not_raised():
    session = FakeSession({"error": 6, "message": "The artist you supplied could not be found"})
    assert LastFmClient("key", session).top_tags("Nobody")["error"] == 6


def test_other_api_errors_raise():
    session = FakeSession({"error": 29, "message": "Rate limit exceeded"})
    with pytest.raises(LastFmError, match="29"):
        LastFmClient("key", session).top_tags("Anyone")


def test_network_errors_do_not_leak_the_api_key():
    exc = requests.ConnectionError("Max retries exceeded with url: /2.0/?api_key=SECRET123")
    session = FakeSession(exc=exc)
    with pytest.raises(LastFmError) as info:
        LastFmClient("SECRET123", session).top_tags("Anyone")
    assert "SECRET123" not in str(info.value)
    assert info.value.__cause__ is None
