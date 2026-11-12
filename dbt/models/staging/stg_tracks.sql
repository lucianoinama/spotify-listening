-- One row per track. Metadata comes from the best source that knows the track:
--   1. its most recent play in recently_played (the API's own payload)
--   2. the track fetched for the extended history (raw.tracks, same shape)
--   3. names only, from the extended history, for tracks Spotify no longer serves
with from_plays as (
    select
        track_id, track_name, duration_ms, is_explicit, album_id, album_name,
        album_release_date, album_image_url,
        1 as source_rank,
        played_at as seen_at
    from {{ ref('stg_plays') }}
),

from_fetched as (
    select
        track_id,
        payload ->> 'name' as track_name,
        (payload ->> 'duration_ms')::int as duration_ms,
        coalesce((payload ->> 'explicit')::boolean, false) as is_explicit,
        payload -> 'album' ->> 'id' as album_id,
        payload -> 'album' ->> 'name' as album_name,
        payload -> 'album' ->> 'release_date' as album_release_date,
        coalesce(
            payload -> 'album' -> 'images' -> 1 ->> 'url',
            payload -> 'album' -> 'images' -> 0 ->> 'url'
        ) as album_image_url,
        2 as source_rank,
        fetched_at as seen_at
    from {{ source('raw', 'tracks') }}
    where status = 'ok'
),

from_export as (
    select
        track_id,
        track_name,
        null::int as duration_ms,
        false as is_explicit,
        'export:' || md5(coalesce(album_artist_name, '') || '|' || coalesce(album_name, ''))
            as album_id,
        album_name,
        null::text as album_release_date,
        null::text as album_image_url,
        3 as source_rank,
        played_at as seen_at
    from {{ ref('stg_extended_plays') }}
)

select distinct on (track_id)
    track_id,
    track_name,
    duration_ms,
    is_explicit,
    album_id,
    album_name,
    album_release_date,
    album_image_url
from (
    select * from from_plays
    union all
    select * from from_fetched
    union all
    select * from from_export
) as candidates
order by track_id, source_rank, seen_at desc
