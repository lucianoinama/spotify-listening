{{ config(materialized='view') }}
-- Health of the recently_played ingestion, one row. A view, so it is live: it does not wait for
-- a dbt build, which only runs after a run that stored something new and so would never show a
-- failing ingester. The app reads it through the marts schema, with no access to raw.
-- Backfill passes also log to raw.ingest_runs, as 'ok' rows without plays_fetched: left out.
with runs as (
    select *
    from {{ source('raw', 'ingest_runs') }}
    where not (status = 'ok' and plays_fetched is null)
),

last_ok as (
    select max(finished_at) as finished_at from runs where status = 'ok'
),

last_run as (
    select status, error from runs order by finished_at desc limit 1
)

select
    last_ok.finished_at as last_ok_at,
    (select count(*) from runs where status = 'error'
        and finished_at > coalesce(last_ok.finished_at, '-infinity')) as failures_since_ok,
    (select error from last_run where status = 'error') as last_error
from last_ok
