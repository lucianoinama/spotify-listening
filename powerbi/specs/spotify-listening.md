# Spec: Spotify listening dashboard

> Status: `building` · Date: 2026-11-06 · Author: Agustin (built with Claude)

## 1. Goal

A personal dashboard on my Spotify listening history. It answers four questions: how much I
listen, when I listen, which artists and genres dominate, and what kind of tracks I play.
"Good" means each page tells one story with a number I can check against the dbt marts, and
a screenshot I can post publicly without exposing my routine.

Data comes from the `marts` schema of the Postgres warehouse in this repository
(`docker-compose.yml`), loaded in Import mode. Genres come from Last.fm, not Spotify.

## 2. Data required

**Source tables** (Postgres, schema `marts`; model names are Spanish for the report)

| Model table | Source | Role | Grain | Notes |
| --- | --- | --- | --- | --- |
| `Reproducciones` | `fct_plays` | fact | one play | local time already applied by dbt |
| `Canciones` | `dim_tracks` | dimension | one track | main artist only |
| `Artistas` | `dim_artists` | dimension | one artist | `Género principal`, `Géneros` from Last.fm |
| `Calendario` | `dim_date` | dimension | one day | marked as date table |
| `Ranking Artistas` | `mart_top_artists_monthly` | aggregate | artist and month | pre-aggregated by dbt |
| `Ranking Géneros` | `mart_genre_monthly` | aggregate | genre and month | pre-aggregated by dbt |
| `Meses` | calculated | dimension | one month | joins both monthly rankings to one slicer |

`mart_daily_listening` and `mart_hourly_heatmap` are **not** imported. With `Calendario`
(one row per day, zeros included) and `Reproducciones.Hora`, the same series come from
measures and then respond to the date slicer. The bridge tables stay out: they need
bi-directional relationships (phase 2).

**Measures** (all in `_Measures`, each with a description; SVG cards in `_SVG_Measures`)

| Measure | Definition (plain English) | Format |
| --- | --- | --- |
| `Total de reproducciones` | Number of plays | whole number, thousand separators |
| `Horas escuchadas` | Sum of `listened_ms` in hours: real time played up to 2026-11-05 (extended history), track length (an estimate) after | one decimal |
| `Canciones únicas` | Distinct tracks played | whole number |
| `Días con actividad` | Distinct days with at least one play | whole number |
| `Horas por día activo` | Hours divided by active days | one decimal |
| `Horas por día` | Hours, with zero (not blank) for days without plays | one decimal |
| `Hora pico` | Hour of day with the most plays | text |
| `Día más activo` | Weekday with the most hours | text |
| `Horas por artista`, `Horas por género` | Monthly ranking hours | one decimal |
| `Horas por artista (Top 10)`, `Horas por género (Top 8)` | Same, blank outside the top N | one decimal |
| `Cantidad de artistas`, `Artistas por género (Top 8)` | Distinct artists, top 8 genres | whole number |
| `Color mapa de calor`, `Color texto mapa de calor` | Cell and text color for the heatmap, by share of the maximum | text |
| `P1_Horas_KPI_SVG`, `P1_Reproducciones_KPI_SVG`, `P1_Canciones_KPI_SVG`, `P1_HorasDia_KPI_SVG` | Overview KPI cards | SVG |
| `P2_HoraPico_KPI_SVG`, `P2_DiaActivo_KPI_SVG` | Rhythm KPI cards | SVG |
| `Puntaje de álbum` | Plays plus a tiny recency term, so album ranks never tie | number |
| `Portada #1` to `Portada #8` | Cover URL of the nth most played album | image URL |
| `P5_Album1_Caption_SVG` to `P5_Album8_Caption_SVG` | Caption under each cover: rank, album, artist, plays | SVG |
| `Fin de datos`, `Reproducciones 30 días`, `Puntaje de álbum 30 días` | Last play day, and plays and album score over the 30 days up to it | date, whole number, number |
| `Portada álbum top 30 días`, `P1_AlbumTop30_Caption_SVG` | Cover and caption of the top album of the last 30 days | image URL, SVG |

**Relationships**

| From | To | Cardinality | Cross-filter |
| --- | --- | --- | --- |
| `Reproducciones[ID canción]` | `Canciones[ID canción]` | many to one | single |
| `Reproducciones[Fecha]` | `Calendario[Fecha]` | many to one | single |
| `Ranking Artistas[Inicio de mes]` | `Meses[Mes]` | many to one | single |
| `Ranking Géneros[Inicio de mes]` | `Meses[Mes]` | many to one | single |

## 3. Pages

Canvas 1280 by 720. Every page: dark header band (0 to 56), filter strip (64 to 120), cards
below. Card titles are drawn in the SVG background; visuals start at `card_y + 34`.

### Page: Resumen

- **Background:** `bg_resumen.svg`
- **Slicers:** date range (`Calendario[Fecha]`, drives KPIs and the daily line) and month
  (`Meses[Mes]`, drives the two rankings). Labelled in the strip.

| Card | Visual | Fields | Notes |
| --- | --- | --- | --- |
| Horas escuchadas, Reproducciones, Canciones únicas, Horas por día activo | image (SVG KPI) | `P1_*_KPI_SVG` | row at y=132, 4 cards |
| Horas por día | lineChart | `Calendario[Fecha]`, `Horas por día` | time series, chronological |
| Top 10 artistas | barChart | `Ranking Artistas[Artista]`, `Horas por artista (Top 10)` | descending |
| Top 8 géneros | barChart | `Ranking Géneros[Género]`, `Horas por género (Top 8)` | descending |
| Álbum más escuchado, últimos 30 días | 2 images | `Portada álbum top 30 días` (cover), `P1_AlbumTop30_Caption_SVG` (name, artist, plays) | right column, beside the KPIs and the daily chart |

The 30 day window ends at the day of the **last recorded play** (`Fin de datos`), not at today,
so the card never empties if ingestion pauses. It ignores the page's date slicer. Ties break
by the most recent play. A measure cannot sit inside a boolean `CALCULATE` filter, so the
window edges go through variables.

### Page: Cuándo escucho

- **Background:** `bg_ritmo.svg` · **Slicer:** date range

| Card | Visual | Fields | Notes |
| --- | --- | --- | --- |
| Mapa de calor | pivotTable | rows `Calendario[Día de la semana]`, columns `Reproducciones[Hora]`, `Horas escuchadas` | cell color from `Color mapa de calor` |
| Hora pico, Día más activo | image (SVG KPI) | `P2_*_KPI_SVG` | |
| Reproducciones por hora | clusteredColumnChart | `Reproducciones[Hora]`, `Total de reproducciones` | hour order |
| Horas por franja | clusteredColumnChart | `Reproducciones[Franja horaria]`, `Horas escuchadas` | sorted by `Franja orden` |
| Semana y fin de semana | clusteredColumnChart | `Calendario[Tipo de día]`, `Horas escuchadas` | |

### Page: Artistas y géneros

- **Background:** `bg_artistas.svg` · **Slicer:** month (`Meses[Mes]`)

| Card | Visual | Fields | Notes |
| --- | --- | --- | --- |
| Top 10 artistas del mes | barChart | `Ranking Artistas[Artista]`, `Horas por artista (Top 10)` | |
| Top 8 géneros del mes | barChart | `Ranking Géneros[Género]`, `Horas por género (Top 8)` | |
| Artistas por género principal | barChart | `Artistas[Género principal]`, `Artistas por género (Top 8)` | not month-filtered |
| Detalle de artistas | tableEx | `Artistas[Artista]`, `Género principal`, `Géneros` | |

### Page: Canciones

- **Background:** `bg_canciones.svg` · **Slicer:** date range

| Card | Visual | Fields | Notes |
| --- | --- | --- | --- |
| Canciones más escuchadas | tableEx | `Canciones[Canción]`, `Artista principal`, `Total de reproducciones` | descending by plays; a fourth column did not fit the card width |
| Reproducciones por década | clusteredColumnChart | `Canciones[Década]`, `Total de reproducciones` | chronological |
| Origen de la reproducción | donutChart | `Reproducciones[Origen]`, `Total de reproducciones` | |
| Contenido explícito | donutChart | `Canciones[Contenido]`, `Total de reproducciones` | |

### Page: Álbumes

- **Background:** `bg_albumes.svg` · **Slicer:** date range
- **Source:** `Canciones[Portada]`, the 300 px cover URL that dbt takes from
  `raw.recently_played` (`dim_tracks.album_image_url`). No extra API call.

| Card | Visual | Fields | Notes |
| --- | --- | --- | --- |
| 8 cards in a 4 by 2 grid | image | `_Measures[Portada #1]` to `#8` | one cover each, ranked by plays |
| Caption under each cover | image (SVG) | `P5_Album1_Caption_SVG` to `8` | rank, album, artist, plays |

- `Puntaje de álbum` is plays plus a tiny recency term, so equal plays never tie and the
  ranking is stable. The slot measures pick the nth score from `ALLSELECTED(Canciones[Portada])`.
- Caption text is escaped for a data URI (`%`, `#`) and for XML (`&`, `<`, `>`) and cut at 30
  characters.
- The covers are fetched by Power BI from Spotify's CDN (`i.scdn.co`) when the page renders.
  The report needs internet access to show them; nothing is uploaded.

## 4. Rules that apply

Everything in `copilot-instructions.md`, with these decisions made inside or against it:

- **Exception, decimals.** Hours show one decimal (labels and SVG KPIs). Whole numbers would
  turn 0.4 hours into 0. Counts stay whole numbers with thousand separators.
- **Exception, sort.** Ordinal axes keep their natural order instead of descending by value:
  hour of day, weekday, time-of-day band, release decade, date.
- **Rule 14 (top N).** The top N is applied inside the measure (blank outside the rank), so no
  `filterConfig` is written by hand. A bar chart omits categories whose value is blank.
- **Names.** Table, column and measure names are Spanish and have no underscores; the source
  column names stay in `sourceColumn`.
- **Localization.** Month and weekday names are calculated columns in Spanish, because
  Postgres returns English names.
- **Data source.** One Postgres connection per table, `localhost:5432`, database `spotify`.
  Credentials are entered in Power BI on the first refresh and are not stored in the project.
- **Hooks and bridge.** Not enabled. Verification is by the local validators and screenshots.
- Chrome: no visual title, background, border or shadow. Titles come from the SVG.
- Theme: `SpotifyListeningTheme.json`. One accent blue plus grays.

## 5. Build tasks

- [x] Measures added to `_Measures` with descriptions
- [x] SVG KPI measures added to `_SVG_Measures` (`P1_`, `P2_`)
- [x] Theme saved to `RegisteredResources/` and registered in `report.json`
- [x] SVG canvas backgrounds generated and registered
- [x] Pages created with backgrounds wired up
- [x] Visuals built and bound to fields
- [x] Build script owns all generated files: `build/build_pbip.py`
- [x] `validate-json.ps1` + `validate-pbip.ps1` + `Test-PbipSemantics.ps1` pass

## 6. Definition of done

- [x] All three validation scripts pass
- [x] PBIP opens in Power BI Desktop 2.159 with no error dialog
- [x] Refresh loads all tables from Postgres (credentials already stored by Desktop)
- [x] Every page screenshot reviewed (2026-11-06, window captures of the running Desktop)
- [x] No visual overlaps its SVG card title; no truncated labels; no blank charts
- [x] KPI values match the marts: 102 plays, 96 tracks, 7.3 hours
- [ ] Not done: checked against `powerbi-visual-verify` with the Desktop Bridge (not installed)

## 7. Open questions

- [x] Does the matrix accept measure-driven `backColor`/`fontColor`? Only with a
      `selector` on the value field (`metadata` = its queryRef, `matchingOption` 1).
      Without the selector the cells stayed unstyled.
- [ ] A weekday with no plays does not appear as a heatmap row. Matrix rows follow the
      data. Revisit with more history.

## 8. Fold-back

Rules that will apply to the next dashboard:

- Conditional formatting by measure in a matrix needs a `selector` on the value field.
- A top N inside the measure (`RANKX` over `ALLSELECTED`, blank outside the rank) needs no
  hand-written `filterConfig`.
- Numeric categories (hour of day) draw a continuous axis; set `categoryAxis.axisType` to
  `'Categorical'`.
- `FORMAT` in SVG KPI measures takes a locale argument (`"es-AR"`); without it the cards show
  a decimal point while charts show a comma.
- A bar chart needs about 25 px per category to avoid a scroll bar.
- A table of three columns fits a 700 px card; four do not.
