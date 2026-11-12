-- Synthetic data for demos and local validation. Not real listening history.
-- Covers: a multi-artist track, an artist with no genres, and an artist never fetched.
-- Load with:
--   docker compose exec -T postgres psql -U spotify -d spotify < dev/seed.sql

-- Spotify artists carry no genres anymore; they come from Last.fm tags (raw.artist_tags).
insert into raw.artists (artist_id, payload) values
    ('a1', '{"id": "a1", "name": "Synthetic Band"}'),
    ('a2', '{"id": "a2", "name": "Fake DJ"}'),
    ('a3', '{"id": "a3", "name": "No Genre Artist"}')
on conflict do nothing;

-- a1: a noisy tag list (ignored tag, low-count tag, mixed case, duplicate).
-- a2: a single tag, which Last.fm returns as an object instead of an array.
-- a3: unknown to Last.fm (error 6).
insert into raw.artist_tags (artist_id, payload) values
    ('a1', '{"toptags": {"tag": [
        {"name": "Indie Rock", "count": 100},
        {"name": "alt rock", "count": 64},
        {"name": "seen live", "count": 55},
        {"name": "indie rock", "count": 30},
        {"name": "shoegaze", "count": 8}
    ]}}'),
    ('a2', '{"toptags": {"tag": {"name": "house", "count": 100}}}'),
    ('a3', '{"error": 6, "message": "The artist you supplied could not be found"}')
on conflict do nothing;

with tracks(track_id, name, duration_ms, artists) as (
    values
        ('t1', 'Song One', 180000, '[{"id": "a1", "name": "Synthetic Band"}]'::jsonb),
        ('t2', 'Song Two', 240000,
         '[{"id": "a2", "name": "Fake DJ"}, {"id": "a1", "name": "Synthetic Band"}]'::jsonb),
        ('t3', 'Song Three', 200000, '[{"id": "a3", "name": "No Genre Artist"}]'::jsonb),
        ('t4', 'Song Four', 150000, '[{"id": "a4", "name": "Unfetched Artist"}]'::jsonb)
),

slots as (
    select
        d.d as day_offset,
        h.h as hour_of_day,
        row_number() over (order by d.d, h.h) as n
    from generate_series(0, 13) as d(d)
    cross join generate_series(8, 22, 5) as h(h)
),

plays as (
    select
        date_trunc('day', now()) - make_interval(days => day_offset)
            + make_interval(hours => hour_of_day, mins => (n % 7)::int) as played_at,
        't' || (1 + n % 4) as track_id
    from slots
)

insert into raw.recently_played (played_at, track_id, payload)
select
    p.played_at,
    p.track_id,
    jsonb_build_object(
        'played_at', p.played_at,
        'context', jsonb_build_object('type', 'playlist'),
        'track', jsonb_build_object(
            'id', t.track_id,
            'name', t.name,
            'duration_ms', t.duration_ms,
            'explicit', false,
            'album', jsonb_build_object(
                'id', 'al' || t.track_id,
                'name', 'Album ' || t.name,
                'release_date', '2020-05-01'
            ),
            'artists', t.artists
        )
    )
from plays as p
inner join tracks as t on t.track_id = p.track_id
on conflict do nothing;
