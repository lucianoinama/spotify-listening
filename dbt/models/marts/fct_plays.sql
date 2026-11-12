-- One row per play, from two sources that never overlap:
--   extended: Spotify's extended streaming history, up to its last timestamp. It has the real
--             ms_played, so it wins wherever both sources know a play.
--   api:      recently_played, only for plays after the extended history ends.
-- Only streams of at least min_ms_played count as plays (Spotify's own threshold); shorter ones
-- are in fct_stream_events. Plays made in a private session are left out unless
-- include_private_sessions is true.
--
-- duration_ms is the track length. ms_played is the time actually played (null for api rows).
-- listened_ms is ms_played when known, else the track length as an estimate: use it for hours.
with extended_end as (
    select coalesce(max(played_at), '-infinity'::timestamptz) as last_extended_at
    from {{ ref('stg_extended_plays') }}
),

extended as (
    select played_at, track_id, ms_played, 'extended' as source, null::text as context_type
    from {{ ref('stg_extended_plays') }}
    where ms_played >= {{ var('min_ms_played') }}
    {% if not var('include_private_sessions') %}
      and not coalesce(incognito_mode, false)
    {% endif %}
),

api as (
    select p.played_at, p.track_id, null::int as ms_played, 'api' as source, p.context_type
    from {{ ref('stg_plays') }} as p
    cross join extended_end as e
    where p.played_at > e.last_extended_at
      and p.played_at >= '{{ var("history_start") }}'::timestamptz
),

plays as (
    select * from extended
    union all
    select * from api
)

select
    md5(p.played_at::text || '|' || p.track_id) as play_id,
    p.played_at,
    p.played_at at time zone '{{ var("local_timezone") }}' as played_at_local,
    (p.played_at at time zone '{{ var("local_timezone") }}')::date as play_date,
    extract(hour from p.played_at at time zone '{{ var("local_timezone") }}')::int as play_hour,
    p.track_id,
    t.duration_ms,
    p.ms_played,
    coalesce(p.ms_played, t.duration_ms) as listened_ms,
    p.source,
    p.context_type
from plays as p
left join {{ ref('stg_tracks') }} as t on t.track_id = p.track_id
