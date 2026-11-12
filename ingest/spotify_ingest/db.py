"""Postgres access for the raw layer."""

import os
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    )


def ensure_schema(conn: psycopg.Connection) -> None:
    # One statement per execute. Comment lines go first so a ';' inside one cannot split it.
    lines = [
        line for line in SCHEMA_FILE.read_text().splitlines() if not line.strip().startswith("--")
    ]
    for statement in "\n".join(lines).split(";"):
        if statement.strip():
            conn.execute(statement)


def insert_plays(conn: psycopg.Connection, plays: list[tuple[datetime, str, dict]]) -> int:
    """Insert plays, skipping ones already stored. Returns how many were new."""
    inserted = 0
    with conn.cursor() as cur:
        for played_at, track_id, payload in plays:
            cur.execute(
                """
                insert into raw.recently_played (played_at, track_id, payload)
                values (%s, %s, %s)
                on conflict do nothing
                """,
                (played_at, track_id, Jsonb(payload)),
            )
            inserted += cur.rowcount
    return inserted


def artists_to_fetch(
    conn: psycopg.Connection, artist_ids: list[str], refresh_days: int
) -> list[str]:
    """Artists never fetched, or last fetched more than refresh_days ago."""
    if not artist_ids:
        return []
    rows = conn.execute(
        """
        select ids.artist_id
        from unnest(%s::text[]) as ids(artist_id)
        left join raw.artists a on a.artist_id = ids.artist_id
        where a.artist_id is null
           or a.fetched_at < now() - make_interval(days => %s)
        """,
        (artist_ids, refresh_days),
    ).fetchall()
    return [r[0] for r in rows]


def upsert_artist(conn: psycopg.Connection, artist_id: str, payload: dict) -> None:
    conn.execute(
        """
        insert into raw.artists (artist_id, payload)
        values (%s, %s)
        on conflict (artist_id)
        do update set payload = excluded.payload, fetched_at = now()
        """,
        (artist_id, Jsonb(payload)),
    )


def artists_needing_tags(
    conn: psycopg.Connection, refresh_days: int, limit: int
) -> list[tuple[str, str]]:
    """(artist_id, name) for artists with no Last.fm tags yet, or tags older than refresh_days."""
    rows = conn.execute(
        """
        select a.artist_id, a.payload ->> 'name'
        from raw.artists a
        left join raw.artist_tags t on t.artist_id = a.artist_id
        where a.payload ->> 'name' is not null
          and (t.artist_id is null or t.fetched_at < now() - make_interval(days => %s))
        order by t.fetched_at nulls first, a.artist_id
        limit %s
        """,
        (refresh_days, limit),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def upsert_artist_tags(conn: psycopg.Connection, artist_id: str, payload: dict) -> None:
    conn.execute(
        """
        insert into raw.artist_tags (artist_id, payload)
        values (%s, %s)
        on conflict (artist_id)
        do update set payload = excluded.payload, fetched_at = now()
        """,
        (artist_id, Jsonb(payload)),
    )


def log_run(
    conn: psycopg.Connection,
    started_at: datetime,
    status: str,
    plays_fetched: int | None = None,
    plays_inserted: int | None = None,
    artists_fetched: int | None = None,
    tags_fetched: int | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        insert into raw.ingest_runs
            (started_at, status, plays_fetched, plays_inserted, artists_fetched,
             tags_fetched, error)
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        (started_at, status, plays_fetched, plays_inserted, artists_fetched, tags_fetched, error),
    )


if __name__ == "__main__":
    # Used by CI to create the raw tables before running dbt.
    with connect() as _conn:
        ensure_schema(_conn)
    print("raw schema ready")
