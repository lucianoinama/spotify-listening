-- A track can have several artists; this resolves the many-to-many.
select
    track_id,
    artist_id,
    artist_position
from {{ ref('stg_track_artists') }}
