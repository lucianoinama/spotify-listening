-- One row per artist seen in a play. Genres live here because Spotify assigns them to artists.
with artists as (
    select artist_id, min(artist_name) as artist_name
    from {{ ref('stg_track_artists') }}
    group by artist_id
),

genres as (
    select
        artist_id,
        max(genre) filter (where genre_position = 1) as primary_genre,
        string_agg(genre, ', ' order by genre_position) as genres,
        count(*) as genre_count
    from {{ ref('stg_artist_genres') }}
    group by artist_id
)

select
    a.artist_id,
    a.artist_name,
    coalesce(g.primary_genre, 'unknown') as primary_genre,
    coalesce(g.genres, '') as genres,
    coalesce(g.genre_count, 0) as genre_count
from artists as a
left join genres as g on g.artist_id = a.artist_id
