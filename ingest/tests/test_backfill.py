from types import SimpleNamespace

import pytest
import requests

from spotify_ingest import backfill


def http_error(status: int) -> requests.HTTPError:
    return requests.HTTPError(response=SimpleNamespace(status_code=status))


class FakeClient:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def track(self, track_id):
        if self.error:
            raise self.error
        return self.result


def test_a_served_track_is_returned_with_its_payload():
    payload = {"id": "abc", "name": "Song"}
    assert backfill.fetch_track(FakeClient(result=payload), "abc") == ("ok", payload)


@pytest.mark.parametrize("status", [400, 404])
def test_a_track_spotify_does_not_serve_is_marked_not_found(status):
    assert backfill.fetch_track(FakeClient(error=http_error(status)), "abc") == ("not_found", None)


@pytest.mark.parametrize("status", [401, 403, 500])
def test_other_http_errors_stop_the_run(status):
    with pytest.raises(requests.HTTPError):
        backfill.fetch_track(FakeClient(error=http_error(status)), "abc")


def test_the_pending_query_asks_for_tracks_not_yet_known():
    sql = backfill.PENDING_TRACKS
    assert "raw.tracks" in sql and "raw.recently_played" in sql
    assert "ms_played >= %s" in sql


# --- blocks and partial progress -------------------------------------------------------------


class FakeConn:
    """Just enough of a connection: pending rows for the SELECTs, a dict for backfill_state."""

    def __init__(self, pending=(), block=None):
        self.pending, self.block, self.inserted = list(pending), block, []

    def execute(self, sql, params=()):
        text = " ".join(sql.split())
        if "from raw.backfill_state" in text and text.startswith("select"):
            return SimpleNamespace(fetchone=lambda: (self.block,) if self.block else None)
        if text.startswith("insert into raw.backfill_state"):
            self.block = params[1]
        elif text.startswith("insert into raw.tracks"):
            self.inserted.append(params[0])
        elif text.startswith("insert into raw.artists"):
            return SimpleNamespace(rowcount=0)
        return SimpleNamespace(fetchall=lambda: [(p,) for p in self.pending])


class FlakyClient:
    """Serves the first `ok` tracks, then Spotify refuses with a long Retry-After."""

    def __init__(self, ok):
        self.ok = ok

    def track(self, track_id):
        if self.ok == 0:
            raise backfill.SpotifyError("quota", retry_after=25000)
        self.ok -= 1
        return {"id": track_id}


def test_tracks_stored_before_a_refusal_are_counted_and_the_refusal_is_returned(monkeypatch):
    monkeypatch.setattr(backfill, "PAUSE_SECONDS", 0)
    conn = FakeConn(pending=["a", "b", "c"])
    done, error = backfill.backfill_tracks(conn, FlakyClient(ok=2), "2020-01-01", 30000, None)
    assert (done, conn.inserted) == (2, ["a", "b"])
    assert error.retry_after == 25000


def test_a_block_is_stored_with_a_margin_past_what_spotify_asked():
    conn = FakeConn()
    until = backfill.remember_block(conn, backfill.SpotifyError("quota", retry_after=1000))
    wanted = backfill.datetime.now(backfill.UTC) + backfill.timedelta(
        seconds=1000 + backfill.BLOCK_MARGIN_SECONDS
    )
    assert abs((until - wanted).total_seconds()) < 5
    assert conn.block == until


def test_a_new_block_never_shortens_one_already_stored():
    later = backfill.datetime.now(backfill.UTC) + backfill.timedelta(hours=9)
    conn = FakeConn(block=later)
    until = backfill.remember_block(conn, backfill.SpotifyError("quota", retry_after=60))
    assert until == later


def test_a_refusal_without_a_wait_blocks_for_the_default_time():
    conn = FakeConn()
    until = backfill.remember_block(conn, backfill.SpotifyError("gave up"))
    seconds = (until - backfill.datetime.now(backfill.UTC)).total_seconds()
    assert seconds > backfill.UNKNOWN_BLOCK_SECONDS


def test_no_spotify_call_is_made_while_a_block_is_on_record():
    later = backfill.datetime.now(backfill.UTC) + backfill.timedelta(hours=2)
    conn = FakeConn(pending=["a"], block=later)

    class Forbidden:
        def track(self, track_id):
            raise AssertionError("Spotify was called during a block")

        artist = track

    result = backfill.run_pass(conn, Forbidden(), None, "2020-01-01", 30000, None)
    assert result.blocked is not None and result.tracks == 0
    assert 7000 < backfill.seconds_to_wait(conn) < 7300


def test_with_nothing_blocked_and_nothing_pending_the_wait_is_the_idle_one():
    assert backfill.seconds_to_wait(FakeConn()) == backfill.IDLE_SECONDS
