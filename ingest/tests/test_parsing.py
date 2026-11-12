import base64
import hashlib
from datetime import UTC, datetime

from spotify_ingest.auth import build_authorize_url, make_pkce_pair
from spotify_ingest.run import artist_ids_from, parse_plays

ITEMS = [
    {
        "played_at": "2026-10-28T21:15:03.123Z",
        "track": {
            "id": "t1",
            "name": "Song One",
            "artists": [{"id": "a1", "name": "A"}, {"id": "a2", "name": "B"}],
        },
    },
    {
        "played_at": "2026-10-28T21:10:00.000Z",
        "track": {"id": "t2", "name": "Song Two", "artists": [{"id": "a1", "name": "A"}]},
    },
    {
        "played_at": "2026-10-28T21:05:00.000Z",
        "track": {"id": None, "name": "Local file", "artists": [{"id": None, "name": "x"}]},
    },
]


def test_parse_plays_skips_tracks_without_id():
    plays = parse_plays(ITEMS)
    assert [p[1] for p in plays] == ["t1", "t2"]


def test_parse_plays_reads_utc_timestamp():
    played_at = parse_plays(ITEMS)[0][0]
    assert played_at == datetime(2026, 10, 28, 21, 15, 3, 123000, tzinfo=UTC)


def test_artist_ids_are_unique_and_sorted():
    assert artist_ids_from(ITEMS) == ["a1", "a2"]


def test_pkce_challenge_matches_verifier():
    verifier, challenge = make_pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected
    assert 43 <= len(verifier) <= 128


def test_authorize_url_carries_pkce_and_scope():
    url = build_authorize_url("cid", "http://127.0.0.1:8888/callback", "chal", "st")
    assert "code_challenge_method=S256" in url
    assert "code_challenge=chal" in url
    assert "scope=user-read-recently-played" in url
