# Dashboard plan (Power BI)

Goal: a four-page report that answers "what, when and how much do I listen to", built only on
the `marts` schema. Power BI does no business logic; every metric that needs rules lives in dbt.

## 1. Connect

1. Power BI Desktop: Get data, PostgreSQL database.
2. Server `localhost:5432`, database `spotify`. Use **Import** mode, not DirectQuery: the data
   is small and Import keeps visuals fast.
3. Credentials: the database tab, user `spotify`, password from your `.env`. If Power BI
   complains about encryption, this is a local container without TLS: choose not to encrypt.
4. Import these tables from `marts` (everything else stays out):

   | Table | Used for |
   |---|---|
   | `mart_daily_listening` | time series, KPIs |
   | `mart_hourly_heatmap` | "when I listen" page |
   | `mart_top_artists_monthly` | artist rankings |
   | `mart_genre_monthly` | genre trends |
   | `fct_plays`, `dim_tracks`, `dim_date` | track-level page, date slicer |
   | `dim_artists` | artist and genre lookup table |

5. **Refresh workflow:** `docker compose run --rm dbt build`, then Refresh in Power BI.

## 2. Model

Keep it simple. The four `mart_*` tables are already aggregated and feed their own visuals, so
they need no relationships. Only the star around `fct_plays` is related:

- `fct_plays[track_id]` many-to-one `dim_tracks[track_id]`
- `fct_plays[play_date]` many-to-one `dim_date[date_day]`

Skip the two bridge tables for now. Using them to let one artist slicer filter every visual
needs bi-directional relationships, which are easy to get wrong. That is a phase 2 feature.

Housekeeping:
- Mark `dim_date` as the date table (on `date_day`).
- Sort `day_name` by `iso_day_of_week`, and `month_name` by `month`.
- Hide key columns (`*_id`, `play_id`) from report view.
- Set `hours` to one decimal place, `plays` to whole numbers.

## 3. Measures

Starting points; check each against a number you can verify in SQL.

```
Total Plays      = COUNTROWS ( fct_plays )
Hours Listened   = SUM ( fct_plays[duration_ms] ) / 3600000
Unique Tracks    = DISTINCTCOUNT ( fct_plays[track_id] )
Active Days      = CALCULATE ( COUNTROWS ( mart_daily_listening ), mart_daily_listening[plays] > 0 )
Avg Hours / Active Day = DIVIDE ( [Hours Listened], [Active Days] )
```

For visuals built on `mart_*` tables, use `SUM` of their own `hours` and `plays` columns.
Do not mix them with the `fct_plays` measures on the same visual.

## 4. Pages

### Page 1: Overview
- **Cards:** Hours listened, Total plays, Unique tracks, Avg hours per active day.
- **Area chart:** hours per day (`mart_daily_listening`).
- **Bar chart:** top 10 artists by hours (`mart_top_artists_monthly`).
- **Bar chart:** top 8 genres by hours (`mart_genre_monthly`).
- **Slicer:** date range (`dim_date`), month for the `mart_*` visuals.

### Page 2: When I listen
- **Matrix heatmap:** `day_name` rows by `play_hour` columns, `hours` as color intensity
  (`mart_hourly_heatmap`).
- **Columns:** plays by hour of day.
- **Columns:** weekday versus weekend (`dim_date[is_weekend]`).
- Hours are already in local time (the dbt `LOCAL_TIMEZONE` setting).

### Page 3: Artists and genres
- **Bar chart:** top artists for the selected month, filter `rank_in_month <= 10`.
- **Stacked area chart:** genre hours per month, top 8 genres, others grouped.
- **Table:** artists with `primary_genre` and `genres` (`dim_artists`).
- **Footnote on the page:** a track with several artists counts fully toward each, so
  artist and genre hours add up to more than the real total.

### Page 4: Tracks
- **Table:** top tracks by plays: track, main artist, plays, hours.
- **Columns:** plays by album release decade (`dim_tracks[release_year]`).
- **Donut:** explicit versus clean (`dim_tracks[is_explicit]`).
- **Bar chart:** plays by source (`fct_plays[context_type]`: playlist, album, artist).

### Optional page 5: About the data
A short page for anyone reading the report, which also works as a portfolio detail:
- Last play date: `MAX ( fct_plays[played_at_local] )`.
- Data range and total plays.
- Text box with the known limitations (see the README): estimated hours, history starts at
  first ingestion, genres from Last.fm.

## 5. Design

- One accent color plus greys. Do not copy Spotify's branding; a neutral palette keeps the
  report professional.
- Page title and a subtitle with the date range on every page.
- Consistent order: KPIs on top, trend in the middle, rankings below.
- Format numbers as hours with one decimal; never show raw `duration_ms`.
- Check the report at 1280 px wide; it is the size most people screenshot.

## 6. Data readiness

- **Now:** a few days of data. Layouts can be built, but trends will look empty.
- **After ~2 weeks:** the heatmap and genre trends start to mean something.
- **After the Extended streaming history import (roadmap):** full history and real listening
  time; add a year-over-year view then.

## 7. Before sharing

- **Do not commit the `.pbix`.** It embeds a copy of the data. `*.pbix` is git-ignored.
- **The heatmap shows your daily routine** (when you sleep, work, commute). For a public
  post, show weekday versus weekend, or four time-of-day buckets, instead of the hour grid.
- Hide or blur anything you would not post as text: exact play timestamps, artist lists
  that reveal more than you want.
- Store screenshots in `docs/img/`.

## 8. Phase 2 ideas

- Artist and genre slicer that filters every visual, using the bridge tables and
  bi-directional relationships (test carefully).
- Skip rate and real listening time, once the extended history is loaded.
- Listening streaks and new-artist discovery per month.
