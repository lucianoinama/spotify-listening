-- An artist can have several genres; this resolves the many-to-many.
-- Only artists that appear in dim_artists: tags are also fetched for artists known only from
-- plays that do not count (private sessions) or that map to a real Spotify artist by name.
select
    g.artist_id,
    g.genre,
    g.genre_position
from {{ ref('stg_artist_genres') }} as g
inner join {{ ref('dim_artists') }} as a on a.artist_id = g.artist_id
