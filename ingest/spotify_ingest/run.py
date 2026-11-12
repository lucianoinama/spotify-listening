"""Ingestion entry point: recently-played plus artist metadata into the raw schema.

    python -m spotify_ingest.run           # one run
    python -m spotify_ingest.run --loop    # repeat every INGEST_INTERVAL_MINUTES
"""

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime

from . import db
from .client import SpotifyClient, SpotifyError
from .lastfm import LastFmClient, LastFmError

log = logging.getLogger("spotify_ingest")

RETRY_AFTER_FAILURE_SECONDS = 60


def parse_plays(items: list[dict]) -> list[tuple[datetime, str, dict]]:
    """(played_at, track_id, original item) for each play. Local files have no id: skipped."""
    plays = []
    for item in items:
        track = item.get("track") or {}
        track_id = track.get("id")
        if not track_id:
            continue
        played_at = datetime.fromisoformat(item["played_at"].replace("Z", "+00:00"))
        plays.append((played_at, track_id, item))
    return plays


def artist_ids_from(items: list[dict]) -> list[str]:
    ids = {
        artist["id"]
        for item in items
        for artist in (item.get("track") or {}).get("artists", [])
        if artist.get("id")
    }
    return sorted(ids)


def fetch_tags(conn, lastfm: LastFmClient, refresh_days: int) -> int:
    """Fetch Last.fm tags for artists that have none. Returns how many were stored.

    An unknown artist is stored as an empty answer. Any other Last.fm failure (bad key,
    rate limit, outage) stops the batch; plays are already saved and the next run retries.
    """
    batch_size = int(os.environ.get("LASTFM_BATCH_SIZE", "100"))
    fetched = 0
    for artist_id, name in db.artists_needing_tags(conn, refresh_days, batch_size):
        try:
            payload = lastfm.top_tags(name)
        except LastFmError as exc:
            log.warning("stopping tag fetch: %s", exc)
            break
        db.upsert_artist_tags(conn, artist_id, payload)
        fetched += 1
        time.sleep(0.25)
    return fetched


def fetch_artists(conn, client: SpotifyClient, artist_ids: list[str]) -> int:
    """Fetch artists from Spotify. Returns how many were stored.

    If Spotify refuses (a quota block can last a day), stop here and keep the plays: the artists
    are asked for again on the next run, at the normal interval. Failing the whole run would
    retry every minute for as long as the block lasts.
    """
    fetched = 0
    for artist_id in artist_ids:
        try:
            payload = client.artist(artist_id)
        except SpotifyError as exc:
            log.warning("Spotify stopped artist lookups, trying again next run: %s", exc)
            break
        db.upsert_artist(conn, artist_id, payload)
        fetched += 1
        time.sleep(0.1)
    return fetched


def run_once(client: SpotifyClient, lastfm: LastFmClient | None = None) -> None:
    started_at = datetime.now(UTC)
    refresh_days = int(os.environ.get("ARTIST_REFRESH_DAYS", "30"))
    with db.connect() as conn:
        db.ensure_schema(conn)
        try:
            items = client.recently_played()
            plays = parse_plays(items)
            inserted = db.insert_plays(conn, plays)

            to_fetch = db.artists_to_fetch(conn, artist_ids_from(items), refresh_days)
            artists = fetch_artists(conn, client, to_fetch)

            tags = fetch_tags(conn, lastfm, refresh_days) if lastfm else 0

            db.log_run(conn, started_at, "ok", len(plays), inserted, artists, tags)
            log.info(
                "plays fetched=%s new=%s, artists fetched=%s, tags fetched=%s",
                len(plays),
                inserted,
                artists,
                tags,
            )
        except Exception as exc:
            db.log_run(conn, started_at, "error", error=str(exc)[:500])
            raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="repeat forever")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = SpotifyClient()
    lastfm = LastFmClient() if os.environ.get("LASTFM_API_KEY") else None
    if lastfm is None:
        log.warning("LASTFM_API_KEY is not set: artists will have no genres")
    interval = int(os.environ.get("INGEST_INTERVAL_MINUTES", "30")) * 60

    while True:
        try:
            run_once(client, lastfm)
        except Exception:
            log.exception("ingestion run failed")
            if not args.loop:
                return 1
            # Usually Postgres still starting after a Docker restart: retry soon, not in 30 min.
            time.sleep(min(interval, RETRY_AFTER_FAILURE_SECONDS))
            continue
        if not args.loop:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
