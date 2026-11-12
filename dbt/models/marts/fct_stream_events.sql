-- Every stream in the extended history, including the ones too short to count as a play.
-- Use it for skip behavior: how often a track is skipped, and after how long.
-- fct_plays has the streams that count (is_counted) plus the plays after the export ends.
select
    md5(e.played_at::text || '|' || e.track_id) as event_id,
    e.played_at,
    e.played_at at time zone '{{ var("local_timezone") }}' as played_at_local,
    (e.played_at at time zone '{{ var("local_timezone") }}')::date as play_date,
    e.track_id,
    e.ms_played,
    e.ms_played >= {{ var('min_ms_played') }} as is_counted,
    e.skipped,
    e.reason_start,
    e.reason_end,
    e.shuffle,
    e.offline,
    coalesce(e.incognito_mode, false) as is_private_session,
    e.platform
from {{ ref('stg_extended_plays') }} as e
