-- One row per track. No genre here: it belongs to artists (see bridge_artist_genres).
with main_artist as (
    select track_id, artist_id, artist_name
    from {{ ref('stg_track_artists') }}
    where artist_position = 1
)

select
    t.track_id,
    t.track_name,
    t.duration_ms,
    t.is_explicit,
    t.album_id,
    t.album_name,
    t.album_image_url,
    case
        when t.album_release_date ~ '^[0-9]{4}' then left(t.album_release_date, 4)::int
    end as release_year,
    m.artist_id as main_artist_id,
    m.artist_name as main_artist_name
from {{ ref('stg_tracks') }} as t
left join main_artist as m on m.track_id = t.track_id
