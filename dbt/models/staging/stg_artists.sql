-- One row per fetched artist.
select
    artist_id,
    payload ->> 'name' as artist_name,
    fetched_at
from {{ source('raw', 'artists') }}
