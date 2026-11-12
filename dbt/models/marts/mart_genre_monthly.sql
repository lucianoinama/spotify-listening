-- Genre ranking per month. A play counts once per genre, even if two artists share it,
-- but a multi-genre play counts toward every genre, so genre hours exceed the real total.
-- Plays by artists with no genre are not included.
with play_genres as (
    select distinct
        f.play_id,
        date_trunc('month', f.play_date)::date as month_start,
        f.listened_ms,
        g.genre
    from {{ ref('fct_plays') }} as f
    inner join {{ ref('bridge_track_artists') }} as ta on ta.track_id = f.track_id
    inner join {{ ref('bridge_artist_genres') }} as g on g.artist_id = ta.artist_id
)

select
    month_start,
    genre,
    count(*) as plays,
    coalesce(sum(listened_ms), 0) / 3600000.0 as hours,
    rank() over (partition by month_start order by coalesce(sum(listened_ms), 0) desc)
        as rank_in_month
from play_genres
group by month_start, genre
