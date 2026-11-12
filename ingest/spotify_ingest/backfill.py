"""Fill in the metadata the extended history lacks, one Spotify call at a time.

    python -m spotify_ingest.backfill [--since 2020-01-01] [--min-ms 30000] [--limit N] [--loop]

The export has track names but no cover, release date, length or artist ids. For every track
played (at least --min-ms) since --since that is not already known, this fetches the track, then
the artists of those tracks, then their Last.fm tags (genres). Each result is stored as it
arrives, so an interrupted run resumes where it stopped: just run it again.

Takes about 0.4 s per track. A rate limit longer than a few minutes stops the Spotify calls of
that pass and is remembered in raw.backfill_state, so nothing calls Spotify again before it ends
(a restart does not call early). With --loop, which the `backfill` service uses, the
process sleeps until then and carries on by itself; when nothing is left it checks every few hours.
"""

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests
from psycopg.types.json import Jsonb

from . import db
from .client import SpotifyClient, SpotifyError
from .lastfm import LastFmClient
from .run import fetch_tags

log = logging.getLogger("spotify_ingest.backfill")

PAUSE_SECONDS = 0.05
LOG_EVERY = 200

BLOCK_KEY = "spotify_blocked_until"
BLOCK_MARGIN_SECONDS = 120  # wait a little past what Spotify asked for
UNKNOWN_BLOCK_SECONDS = 3600  # Spotify refused without saying for how long
IDLE_SECONDS = 6 * 3600  # nothing pending: look again later
FAILURE_SECONDS = 1800  # unexpected error (database down, token revoked): try again later

PENDING_TRACKS = """
    with wanted as (
        select split_part(track_uri, ':', 3) as track_id, count(*) as plays
        from raw.extended_history
        where kind = 'audio' and track_uri like 'spotify:track:%%'
          and ts >= %s and ms_played >= %s
        group by 1
    )
    select w.track_id
    from wanted w
    where not exists (select 1 from raw.tracks t where t.track_id = w.track_id)
      and not exists (select 1 from raw.recently_played r where r.track_id = w.track_id)
    order by w.plays desc, w.track_id
"""

PENDING_ARTISTS = """
    select distinct a ->> 'id' as artist_id
    from raw.tracks t
    cross join lateral jsonb_array_elements(t.payload -> 'artists') as a
    where t.status = 'ok' and a ->> 'id' is not null
      and not exists (select 1 from raw.artists x where x.artist_id = a ->> 'id')
    order by 1
"""


def fetch_track(client: SpotifyClient, track_id: str) -> tuple[str, dict | None]:
    """('ok', payload), or ('not_found', None) for a track Spotify no longer serves."""
    try:
        return "ok", client.track(track_id)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (400, 404):
            return "not_found", None
        raise


def backfill_tracks(
    conn, client: SpotifyClient, since: str, min_ms: int, limit: int | None
) -> tuple[int, SpotifyError | None]:
    """(tracks stored, the Spotify refusal that stopped the run, if any)."""
    pending = [r[0] for r in conn.execute(PENDING_TRACKS, (since, min_ms)).fetchall()]
    if limit:
        pending = pending[:limit]
    log.info("tracks to fetch: %s", len(pending))
    done = 0
    for track_id in pending:
        try:
            status, payload = fetch_track(client, track_id)
        except SpotifyError as exc:
            return done, exc
        conn.execute(
            "insert into raw.tracks (track_id, status, payload) values (%s, %s, %s) "
            "on conflict (track_id) do nothing",
            (track_id, status, Jsonb(payload) if payload else None),
        )
        done += 1
        if done % LOG_EVERY == 0:
            log.info("tracks %s/%s", done, len(pending))
        time.sleep(PAUSE_SECONDS)
    return done, None


def backfill_artists(conn, client: SpotifyClient) -> tuple[int, SpotifyError | None]:
    """(artists stored, the Spotify refusal that stopped the run, if any)."""
    pending = [r[0] for r in conn.execute(PENDING_ARTISTS).fetchall()]
    log.info("artists to fetch: %s", len(pending))
    done = 0
    for artist_id in pending:
        try:
            db.upsert_artist(conn, artist_id, client.artist(artist_id))
        except SpotifyError as exc:
            return done, exc
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (400, 404):
                log.warning("artist %s not served by Spotify, skipped", artist_id)
                continue
            raise
        done += 1
        if done % LOG_EVERY == 0:
            log.info("artists %s/%s", done, len(pending))
        time.sleep(PAUSE_SECONDS)
    return done, None


NAME_ARTISTS = """
    insert into raw.artists (artist_id, payload)
    select 'name:' || lower(trim(d.name)),
           jsonb_build_object('name', d.name, 'source', 'extended_history')
    from (
        select distinct on (lower(trim(name))) name
        from (
            select payload ->> 'master_metadata_album_artist_name' as name
            from raw.extended_history
            where kind = 'audio' and ts >= %s and ms_played >= %s
              and payload ->> 'master_metadata_album_artist_name' is not null
        ) as s
        order by lower(trim(name)), name
    ) as d
    where not exists (
        select 1 from raw.artists a where lower(trim(a.payload ->> 'name')) = lower(trim(d.name))
    )
    on conflict (artist_id) do nothing
"""


def backfill_name_artists(conn, since: str, min_ms: int) -> int:
    """Artists known only by name from the export, so they can get Last.fm tags (genres).

    They get the id 'name:<lowercase name>' and a payload saying where they come from. dbt maps
    them to the real Spotify artist when the same name is known from a fetched track.
    """
    cur = conn.execute(NAME_ARTISTS, (since, min_ms))
    log.info("artists known by name only: %s new", cur.rowcount)
    return cur.rowcount


def backfill_tags(conn, lastfm: LastFmClient) -> int:
    refresh_days = int(os.environ.get("ARTIST_REFRESH_DAYS", "30"))
    total = 0
    while True:
        fetched = fetch_tags(conn, lastfm, refresh_days)
        total += fetched
        log.info("tags fetched so far: %s", total)
        if fetched == 0:
            return total


@dataclass
class Result:
    tracks: int = 0
    artists: int = 0
    names: int = 0
    tags: int = 0
    blocked: SpotifyError | None = None

    @property
    def stored_something(self) -> bool:
        return bool(self.tracks or self.artists or self.names or self.tags)


def blocked_until(conn) -> datetime | None:
    row = conn.execute(
        "select value from raw.backfill_state where key = %s", (BLOCK_KEY,)
    ).fetchone()
    return row[0] if row else None


def remember_block(conn, error: SpotifyError) -> datetime:
    """Store when Spotify may be called again, never earlier than a block already stored."""
    seconds = error.retry_after if error.retry_after else UNKNOWN_BLOCK_SECONDS
    until = datetime.now(UTC) + timedelta(seconds=seconds + BLOCK_MARGIN_SECONDS)
    until = max(until, blocked_until(conn) or until)
    conn.execute(
        """
        insert into raw.backfill_state (key, value) values (%s, %s)
        on conflict (key) do update set value = excluded.value, updated_at = now()
        """,
        (BLOCK_KEY, until),
    )
    return until


def run_pass(conn, client, lastfm, since: str, min_ms: int, limit: int | None) -> Result:
    """One pass over everything pending. Calls Spotify only if no block is on record.

    The first Spotify refusal ends the Spotify calls of the pass and is stored; the steps that
    do not need Spotify (artists known by name, Last.fm genres) run regardless.
    """
    result = Result()
    until = blocked_until(conn)
    if until and until > datetime.now(UTC):
        log.info("Spotify is blocked until %s: skipping its calls", until.astimezone().isoformat())
        result.blocked = SpotifyError("block on record", retry_after=None)
    else:
        result.tracks, result.blocked = backfill_tracks(conn, client, since, min_ms, limit)
        if not result.blocked:
            result.artists, result.blocked = backfill_artists(conn, client)
        if result.blocked:
            log.error("Spotify stopped the calls: %s", result.blocked)
            again = remember_block(conn, result.blocked)
            log.info("next Spotify call not before %s", again.astimezone().isoformat())
    result.names = backfill_name_artists(conn, since, min_ms)
    result.tags = backfill_tags(conn, lastfm) if lastfm else 0
    return result


def log_pass(conn, started_at: datetime, result: Result) -> None:
    """Record the pass in raw.ingest_runs so the transform service rebuilds the models.

    The columns are the ones that service watches: tracks and artists fetched from Spotify count
    as artists_fetched, Last.fm tags (and name-only artists, which get tags next) as tags_fetched.
    """
    db.log_run(
        conn,
        started_at,
        "ok",
        artists_fetched=result.tracks + result.artists,
        tags_fetched=result.tags + result.names,
    )


def seconds_to_wait(conn) -> float:
    until = blocked_until(conn)
    now = datetime.now(UTC)
    if until and until > now:
        return (until - now).total_seconds() + 1
    return IDLE_SECONDS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2020-01-01", help="first day to backfill (UTC)")
    parser.add_argument("--min-ms", type=int, default=30000, help="ignore plays shorter than this")
    parser.add_argument("--limit", type=int, help="fetch at most this many tracks (for a trial)")
    parser.add_argument("--loop", action="store_true", help="keep going: wait out blocks, repeat")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = SpotifyClient()
    lastfm = LastFmClient() if os.environ.get("LASTFM_API_KEY") else None

    while True:
        started_at = datetime.now(UTC)
        try:
            with db.connect() as conn:
                db.ensure_schema(conn)
                result = run_pass(conn, client, lastfm, args.since, args.min_ms, args.limit)
                if result.stored_something:
                    log_pass(conn, started_at, result)
                wait = seconds_to_wait(conn)
        except Exception:
            log.exception("backfill pass failed")
            if not args.loop:
                return 1
            time.sleep(FAILURE_SECONDS)
            continue
        log.info(
            "done: tracks=%s artists=%s names=%s tags=%s",
            result.tracks,
            result.artists,
            result.names,
            result.tags,
        )
        if not args.loop:
            if result.blocked:
                log.error("Spotify stopped some calls. Run it again later to resume.")
                return 3
            return 0
        log.info("next pass in %.0f min", wait / 60)
        time.sleep(wait)


if __name__ == "__main__":
    sys.exit(main())
