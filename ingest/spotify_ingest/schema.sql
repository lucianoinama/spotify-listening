-- Raw layer: append-only copies of what Spotify returned. dbt reads from here.
-- Applied on every ingester start; every statement is idempotent.

create schema if not exists raw;

-- One row per play. Natural key: when it was played plus which track.
create table if not exists raw.recently_played (
    played_at   timestamptz not null,
    track_id    text        not null,
    payload     jsonb       not null,
    ingested_at timestamptz not null default now(),
    primary key (played_at, track_id)
);

-- One row per artist; refreshed periodically, so only the latest snapshot is kept.
create table if not exists raw.artists (
    artist_id  text        primary key,
    payload    jsonb       not null,
    fetched_at timestamptz not null default now()
);

-- Last.fm top tags per artist, used as genres (Spotify stopped returning genres in 2026).
-- The Last.fm response is stored as-is; dbt decides which tags count as genres.
create table if not exists raw.artist_tags (
    artist_id  text        primary key,
    payload    jsonb       not null,
    fetched_at timestamptz not null default now()
);

-- Operational log, one row per ingestion run.
create table if not exists raw.ingest_runs (
    run_id           bigserial   primary key,
    started_at       timestamptz not null,
    finished_at      timestamptz not null default now(),
    status           text        not null,
    plays_fetched    integer,
    plays_inserted   integer,
    artists_fetched  integer,
    error            text
);

-- Added after the first release; the table above predates it on existing databases.
alter table raw.ingest_runs add column if not exists tags_fetched integer;

-- Spotify "Extended streaming history" export (privacy page download), loaded from its JSON
-- files by spotify_ingest.extended. Unlike recently_played it has the real ms_played, the skip
-- flags and the whole past, but no Spotify ids for artists or albums. ip_addr is dropped on load.
-- row_hash identifies the row without ip_addr, so reloading the same file adds nothing.
create table if not exists raw.extended_history (
    row_hash    text        primary key,
    ts          timestamptz not null,
    kind        text        not null,
    track_uri   text,
    ms_played   integer     not null,
    payload     jsonb       not null,
    source_file text        not null,
    loaded_at   timestamptz not null default now()
);

create index if not exists extended_history_ts_idx on raw.extended_history (ts);

-- Track metadata fetched one by one (GET /tracks/{id}) for tracks that appear in the extended
-- history but never in recently_played: cover, release date, length and artist ids.
-- payload has the same shape as the "track" object inside raw.recently_played.
-- status 'not_found' marks tracks Spotify no longer serves, so they are not asked for again.
create table if not exists raw.tracks (
    track_id   text        primary key,
    status     text        not null default 'ok',
    payload    jsonb,
    fetched_at timestamptz not null default now()
);

-- Small key/value state for the backfill service. spotify_blocked_until: Spotify said to stop
-- calling until then. Kept in the database so a restart does not call early and extend the block.
create table if not exists raw.backfill_state (
    key        text        primary key,
    value      timestamptz,
    updated_at timestamptz not null default now()
);
