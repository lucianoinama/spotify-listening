-- Artist ranking per month. A track with two artists counts fully toward each,
-- so artist hours add up to more than the real total (use mart_daily_listening for that).
with artist_plays as (
    select
        date_trunc('month', f.play_date)::date as month_start,
        b.artist_id,
        count(*) as plays,
        coalesce(sum(f.listened_ms), 0) as listened_ms
    from {{ ref('fct_plays') }} as f
    inner join {{ ref('bridge_track_artists') }} as b on b.track_id = f.track_id
    group by 1, 2
)

select
    p.month_start,
    p.artist_id,
    a.artist_name,
    p.plays,
    p.listened_ms / 3600000.0 as hours,
    rank() over (partition by p.month_start order by p.listened_ms desc) as rank_in_month
from artist_plays as p
inner join {{ ref('dim_artists') }} as a on a.artist_id = p.artist_id
