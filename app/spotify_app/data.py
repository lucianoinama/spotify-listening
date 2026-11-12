"""Dashboard queries. Every function takes a date range and returns a DataFrame.

Cached for five minutes: the marts only change after an ingestion run, so this keeps page
switches instant without showing stale numbers for long.

Hours use listened_ms: the real time played for plays up to the end of the extended history,
and the track length (an estimate) for later ones. A play with several artists counts fully
toward each one, same as the Power BI report.
"""

from datetime import date, datetime

import pandas as pd
import psycopg
import streamlit as st

from . import db

HOURS = "sum(f.listened_ms) / 3600000.0"


def cached(fn):
    return st.cache_data(ttl=300, show_spinner=False)(fn)


@st.cache_data(ttl=60, show_spinner=False)
def ingest_status() -> tuple[datetime | None, int, str | None] | None:
    """(last good ingestion, failed runs since, last error), or None while the view is missing
    (a fresh database before the first dbt build). Cached for a minute: it should look live."""
    try:
        row = db.run_query("select last_ok_at, failures_since_ok, last_error from ingest_status")
    except psycopg.Error:
        return None
    if row.empty:
        return None
    last_ok = row["last_ok_at"].iloc[0]
    return (
        None if pd.isna(last_ok) else last_ok.to_pydatetime(),
        int(row["failures_since_ok"].iloc[0]),
        row["last_error"].iloc[0] if isinstance(row["last_error"].iloc[0], str) else None,
    )


@cached
def date_bounds() -> tuple[date, date]:
    df = db.run_query("select min(play_date) as first, max(play_date) as last from fct_plays")
    return df["first"].iloc[0], df["last"].iloc[0]


@cached
def kpis(start: date, end: date) -> dict:
    totals = db.run_query(
        f"""select count(*) as plays, coalesce({HOURS}, 0) as hours,
                   count(distinct f.track_id) as tracks
            from fct_plays f where f.play_date between %s and %s""",
        (start, end),
    ).iloc[0]
    artists = db.run_query(
        """select count(distinct b.artist_id) as artists
           from fct_plays f join bridge_track_artists b using (track_id)
           where f.play_date between %s and %s""",
        (start, end),
    ).iloc[0]
    return {
        "plays": int(totals["plays"]),
        "hours": float(totals["hours"]),
        "tracks": int(totals["tracks"]),
        "artists": int(artists["artists"]),
    }


@cached
def daily(start: date, end: date) -> pd.DataFrame:
    return db.run_query(
        f"""select f.play_date, count(*) as plays, {HOURS} as hours
            from fct_plays f where f.play_date between %s and %s
            group by f.play_date order by f.play_date""",
        (start, end),
    )


@cached
def top_artists(start: date, end: date, limit: int = 10) -> pd.DataFrame:
    return db.run_query(
        f"""select a.artist_name, count(*) as plays, {HOURS} as hours,
                   count(distinct f.track_id) as tracks
            from fct_plays f
            join bridge_track_artists b using (track_id)
            join dim_artists a using (artist_id)
            where f.play_date between %s and %s
            group by a.artist_id, a.artist_name
            order by plays desc, hours desc limit %s""",
        (start, end, limit),
    )


@cached
def top_genres(start: date, end: date, limit: int = 8) -> pd.DataFrame:
    return db.run_query(
        f"""select g.genre, count(*) as plays, {HOURS} as hours,
                   count(distinct b.artist_id) as artists
            from fct_plays f
            join bridge_track_artists b using (track_id)
            join bridge_artist_genres g on g.artist_id = b.artist_id
            where f.play_date between %s and %s
            group by g.genre order by plays desc, hours desc limit %s""",
        (start, end, limit),
    )


@cached
def top_albums(start: date, end: date, limit: int = 12) -> pd.DataFrame:
    return db.run_query(
        f"""select t.album_name, min(t.main_artist_name) as artist,
                   max(t.album_image_url) as cover, count(*) as plays,
                   {HOURS} as hours, max(f.played_at) as last_play
            from fct_plays f join dim_tracks t using (track_id)
            where f.play_date between %s and %s
            group by t.album_id, t.album_name
            order by plays desc, last_play desc limit %s""",
        (start, end, limit),
    )


@cached
def top_tracks(start: date, end: date, limit: int = 15) -> pd.DataFrame:
    return db.run_query(
        f"""select t.track_name, t.main_artist_name as artist, t.album_name,
                   t.album_image_url as cover, count(*) as plays, {HOURS} as hours
            from fct_plays f join dim_tracks t using (track_id)
            where f.play_date between %s and %s
            group by t.track_id, t.track_name, t.main_artist_name, t.album_name,
                     t.album_image_url
            order by plays desc, hours desc limit %s""",
        (start, end, limit),
    )


@cached
def heatmap(start: date, end: date) -> pd.DataFrame:
    return db.run_query(
        f"""select d.iso_day_of_week as dow, f.play_hour as hour,
                   count(*) as plays, {HOURS} as hours
            from fct_plays f join dim_date d on d.date_day = f.play_date
            where f.play_date between %s and %s
            group by 1, 2""",
        (start, end),
    )


@cached
def weekday_split(start: date, end: date) -> pd.DataFrame:
    return db.run_query(
        f"""select d.is_weekend, count(distinct f.play_date) as days,
                   coalesce({HOURS}, 0) as hours
            from fct_plays f join dim_date d on d.date_day = f.play_date
            where f.play_date between %s and %s
            group by d.is_weekend""",
        (start, end),
    )


@cached
def release_decades(start: date, end: date, since_year: int = 0) -> pd.DataFrame:
    """Plays per release decade, only for tracks with a known year, from since_year on."""
    return db.run_query(
        """select (t.release_year / 10) * 10 as decade, count(*) as plays
           from fct_plays f join dim_tracks t using (track_id)
           where f.play_date between %s and %s and t.release_year >= %s
           group by 1 order by 1""",
        (start, end, since_year),
    )


@cached
def release_year_share(start: date, end: date) -> float:
    """Share of plays (0 to 1) whose track has a known release year."""
    row = db.run_query(
        """select count(t.release_year)::float / nullif(count(*), 0) as share
           from fct_plays f join dim_tracks t using (track_id)
           where f.play_date between %s and %s""",
        (start, end),
    )
    value = row["share"].iloc[0]
    return 0.0 if value is None or value != value else float(value)


@cached
def play_sources(start: date, end: date) -> pd.DataFrame:
    return db.run_query(
        """select coalesce(f.context_type, 'sin contexto') as source, count(*) as plays
           from fct_plays f where f.play_date between %s and %s
           group by 1 order by plays desc""",
        (start, end),
    )


@cached
def explicit_share(start: date, end: date) -> float:
    df = db.run_query(
        """select coalesce(avg(case when t.is_explicit then 1.0 else 0.0 end), 0) as share
           from fct_plays f join dim_tracks t using (track_id)
           where f.play_date between %s and %s""",
        (start, end),
    )
    return float(df["share"].iloc[0])


@cached
def artist_names() -> list[str]:
    df = db.run_query(
        """select a.artist_name from dim_artists a
           join bridge_track_artists b using (artist_id)
           join fct_plays f using (track_id)
           group by a.artist_id, a.artist_name order by count(*) desc, a.artist_name"""
    )
    return df["artist_name"].tolist()


@cached
def artist_monthly(artist: str, start: date, end: date) -> pd.DataFrame:
    return db.run_query(
        f"""select d.month_start, count(*) as plays, {HOURS} as hours
            from fct_plays f
            join dim_date d on d.date_day = f.play_date
            join bridge_track_artists b using (track_id)
            join dim_artists a using (artist_id)
            where a.artist_name = %s and f.play_date between %s and %s
            group by d.month_start order by d.month_start""",
        (artist, start, end),
    )


@cached
def artist_tracks(artist: str, start: date, end: date, limit: int = 10) -> pd.DataFrame:
    return db.run_query(
        """select t.track_name, count(*) as plays
           from fct_plays f
           join dim_tracks t using (track_id)
           join bridge_track_artists b using (track_id)
           join dim_artists a using (artist_id)
           where a.artist_name = %s and f.play_date between %s and %s
           group by t.track_id, t.track_name order by plays desc limit %s""",
        (artist, start, end, limit),
    )


@cached
def genre_artists(genre: str, start: date, end: date, limit: int = 10) -> pd.DataFrame:
    return db.run_query(
        f"""select a.artist_name, count(*) as plays, {HOURS} as hours
            from fct_plays f
            join bridge_track_artists b using (track_id)
            join dim_artists a using (artist_id)
            join bridge_artist_genres g on g.artist_id = a.artist_id
            where g.genre = %s and f.play_date between %s and %s
            group by a.artist_id, a.artist_name order by plays desc limit %s""",
        (genre, start, end, limit),
    )
