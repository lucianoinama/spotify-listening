-- Plays and hours per day. Days without plays appear as zeros.
-- Hours use listened_ms: real time played where the extended history has it, else an estimate.
select
    d.date_day as play_date,
    count(f.play_id) as plays,
    coalesce(sum(f.listened_ms), 0) / 3600000.0 as hours,
    count(distinct f.track_id) as unique_tracks
from {{ ref('dim_date') }} as d
left join {{ ref('fct_plays') }} as f on f.play_date = d.date_day
group by d.date_day
