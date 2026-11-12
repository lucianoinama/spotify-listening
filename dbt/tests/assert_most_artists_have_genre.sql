{{ config(severity='warn') }}

-- Warns when over half of the artists have no genre: usually a missing or invalid
-- LASTFM_API_KEY, or Last.fm failing for every lookup. Returns a row only in that case.
select unknown_share
from (
    select
        count(*) filter (where primary_genre = 'unknown')::numeric
            / nullif(count(*), 0) as unknown_share
    from {{ ref('dim_artists') }}
) as share
where unknown_share > 0.5
