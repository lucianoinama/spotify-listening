-- One row per (artist, genre). Genres are Last.fm tags: lowercased, minus the tags listed in
-- the ignored_tags seed, keeping those above a popularity cut and at most N per artist.
-- Last.fm scales tag counts so the artist's top tag is 100.
-- genre_position 1 is the artist's most popular remaining tag.
with tags as (
    select
        t.artist_id,
        lower(trim(x.tag ->> 'name')) as genre,
        (x.tag ->> 'count')::int as tag_count
    from {{ source('raw', 'artist_tags') }} as t
    cross join lateral jsonb_array_elements(
        case jsonb_typeof(t.payload -> 'toptags' -> 'tag')
            when 'array' then t.payload -> 'toptags' -> 'tag'
            -- Last.fm returns a bare object instead of a one-item array.
            when 'object' then jsonb_build_array(t.payload -> 'toptags' -> 'tag')
            else '[]'::jsonb
        end
    ) as x(tag)
),

kept as (
    select artist_id, genre, max(tag_count) as tag_count
    from tags
    where genre <> ''
        and tag_count >= {{ var('genre_min_tag_count') }}
        and genre not in (select tag from {{ ref('ignored_tags') }})
    group by artist_id, genre
),

ranked as (
    select
        artist_id,
        genre,
        row_number() over (partition by artist_id order by tag_count desc, genre)::int
            as genre_position
    from kept
)

select artist_id, genre, genre_position
from ranked
where genre_position <= {{ var('genre_max_per_artist') }}
