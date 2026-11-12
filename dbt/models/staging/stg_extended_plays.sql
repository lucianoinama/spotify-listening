-- One row per audio stream in the extended history, from history_start on.
-- The export sometimes has two rows for the same track at the same second: one with
-- almost no time played and one with the real play. Keep the one with the most time played.
select distinct on (e.ts, track_id)
    e.ts as played_at,
    split_part(e.track_uri, ':', 3) as track_id,
    e.ms_played,
    (e.payload ->> 'skipped')::boolean as skipped,
    e.payload ->> 'reason_start' as reason_start,
    e.payload ->> 'reason_end' as reason_end,
    (e.payload ->> 'shuffle')::boolean as shuffle,
    (e.payload ->> 'offline')::boolean as offline,
    (e.payload ->> 'incognito_mode')::boolean as incognito_mode,
    e.payload ->> 'platform' as platform,
    e.payload ->> 'conn_country' as conn_country,
    e.payload ->> 'master_metadata_track_name' as track_name,
    e.payload ->> 'master_metadata_album_artist_name' as album_artist_name,
    e.payload ->> 'master_metadata_album_album_name' as album_name
from {{ source('raw', 'extended_history') }} as e
where e.kind = 'audio'
  and e.track_uri like 'spotify:track:%'
  and e.ts >= '{{ var("history_start") }}'::timestamptz
order by e.ts, track_id, e.ms_played desc
