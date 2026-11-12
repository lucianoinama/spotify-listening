-- One row per play. Flattens the raw JSON and adds the listener's local time.
select
    played_at,
    played_at at time zone '{{ var("local_timezone") }}' as played_at_local,
    track_id,
    payload -> 'track' ->> 'name' as track_name,
    (payload -> 'track' ->> 'duration_ms')::int as duration_ms,
    coalesce((payload -> 'track' ->> 'explicit')::boolean, false) as is_explicit,
    payload -> 'track' -> 'album' ->> 'id' as album_id,
    payload -> 'track' -> 'album' ->> 'name' as album_name,
    payload -> 'track' -> 'album' ->> 'release_date' as album_release_date,
    -- Spotify lists cover sizes largest first (640, 300, 64): take the 300 px one.
    coalesce(
        payload -> 'track' -> 'album' -> 'images' -> 1 ->> 'url',
        payload -> 'track' -> 'album' -> 'images' -> 0 ->> 'url'
    ) as album_image_url,
    payload -> 'context' ->> 'type' as context_type,
    ingested_at
from {{ source('raw', 'recently_played') }}
