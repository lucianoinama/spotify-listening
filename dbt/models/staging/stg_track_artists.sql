-- One row per (track, artist). artist_position 1 is the main artist.
-- Real Spotify artists come from recently_played first, then from the tracks fetched for the
-- extended history. A track not fetched yet only has the artist name from the export: it gets
-- the real artist id when the same name is known, else a 'name:<lowercase name>' id. Only the
-- main (album) artist is known for those tracks, and the name id is replaced by the real ones
-- as soon as the track is fetched.
with candidates as (
    select
        p.track_id,
        a.artist ->> 'id' as artist_id,
        a.artist ->> 'name' as artist_name,
        a.ord::int as artist_position,
        1 as source_rank,
        p.played_at as seen_at
    from {{ source('raw', 'recently_played') }} as p
    cross join lateral jsonb_array_elements(p.payload -> 'track' -> 'artists')
        with ordinality as a(artist, ord)

    union all

    select
        t.track_id,
        a.artist ->> 'id',
        a.artist ->> 'name',
        a.ord::int,
        2,
        t.fetched_at
    from {{ source('raw', 'tracks') }} as t
    cross join lateral jsonb_array_elements(t.payload -> 'artists')
        with ordinality as a(artist, ord)
    where t.status = 'ok'
),

known as (
    select distinct on (track_id, artist_id)
        track_id,
        artist_id,
        artist_name,
        artist_position
    from candidates
    where artist_id is not null
    order by track_id, artist_id, source_rank, seen_at desc
),

real_artist_by_name as (
    select distinct on (lower(trim(artist_name)))
        lower(trim(artist_name)) as name_key,
        artist_id
    from known
    order by lower(trim(artist_name)), artist_id
),

export_main_artist as (
    select distinct on (e.track_id)
        e.track_id,
        e.album_artist_name
    from {{ ref('stg_extended_plays') }} as e
    where e.album_artist_name is not null
    order by e.track_id, e.played_at desc
),

from_export as (
    select
        m.track_id,
        coalesce(r.artist_id, 'name:' || lower(trim(m.album_artist_name))) as artist_id,
        m.album_artist_name as artist_name,
        1 as artist_position
    from export_main_artist as m
    left join real_artist_by_name as r on r.name_key = lower(trim(m.album_artist_name))
    where not exists (select 1 from known as k where k.track_id = m.track_id)
)

select track_id, artist_id, artist_name, artist_position from known
union all
select track_id, artist_id, artist_name, artist_position from from_export
