-- A play must come from one source only: api rows must start after the extended history ends.
-- Returns the offending plays; the test fails when there are any.
select f.play_id, f.played_at
from {{ ref('fct_plays') }} as f
where f.source = 'api'
  and f.played_at <= (select max(played_at) from {{ ref('stg_extended_plays') }})
