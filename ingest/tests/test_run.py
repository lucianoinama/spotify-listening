import pytest

from spotify_ingest import db, run
from spotify_ingest.client import SpotifyError


class FakeClient:
    """Serves the first `ok` artists, then Spotify refuses."""

    def __init__(self, ok, error=None):
        self.ok, self.error, self.calls = ok, error or SpotifyError("quota", retry_after=80000), []

    def artist(self, artist_id):
        self.calls.append(artist_id)
        if len(self.calls) > self.ok:
            raise self.error
        return {"id": artist_id}


@pytest.fixture
def stored(monkeypatch):
    saved = []
    monkeypatch.setattr(db, "upsert_artist", lambda conn, aid, payload: saved.append(aid))
    monkeypatch.setattr(run.time, "sleep", lambda seconds: None)
    return saved


def test_all_artists_are_stored_when_spotify_answers(stored):
    assert run.fetch_artists(None, FakeClient(ok=3), ["a", "b", "c"]) == 3
    assert stored == ["a", "b", "c"]


def test_a_spotify_refusal_ends_the_lookups_without_failing_the_run(stored):
    client = FakeClient(ok=1)
    assert run.fetch_artists(None, client, ["a", "b", "c"]) == 1
    assert stored == ["a"]
    assert client.calls == ["a", "b"]  # nothing is asked after the refusal


def test_other_errors_are_not_swallowed(stored):
    client = FakeClient(ok=0, error=ValueError("bug"))
    with pytest.raises(ValueError):
        run.fetch_artists(None, client, ["a"])
