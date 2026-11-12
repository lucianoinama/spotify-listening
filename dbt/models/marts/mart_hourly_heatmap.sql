-- Day of week by hour of day, in local time. For a heatmap.
select
    extract(isodow from play_date)::int as iso_day_of_week,
    to_char(play_date, 'FMDay') as day_name,
    play_hour,
    count(*) as plays,
    coalesce(sum(listened_ms), 0) / 3600000.0 as hours
from {{ ref('fct_plays') }}
group by 1, 2, 3
