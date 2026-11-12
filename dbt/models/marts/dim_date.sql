-- One row per calendar day from the first play to today, including days with no plays.
with bounds as (
    select
        coalesce(min(play_date), current_date) as first_day,
        greatest(coalesce(max(play_date), current_date), current_date) as last_day
    from {{ ref('fct_plays') }}
)

select
    d::date as date_day,
    extract(year from d)::int as year,
    extract(month from d)::int as month,
    date_trunc('month', d)::date as month_start,
    to_char(d, 'FMMonth') as month_name,
    extract(isodow from d)::int as iso_day_of_week,
    to_char(d, 'FMDay') as day_name,
    extract(isodow from d) in (6, 7) as is_weekend
from bounds
cross join lateral generate_series(
    bounds.first_day::timestamp, bounds.last_day::timestamp, interval '1 day'
) as d
