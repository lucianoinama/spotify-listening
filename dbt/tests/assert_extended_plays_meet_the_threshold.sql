-- Every extended row in fct_plays must have lasted at least min_ms_played.
select play_id, ms_played
from {{ ref('fct_plays') }}
where source = 'extended'
  and ms_played < {{ var('min_ms_played') }}
