from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from spotify_app import data, figures, series
from spotify_app.ui import (
    ALBUM,
    ARTIST,
    DECADE,
    GENRE,
    HOURS,
    card_title,
    fmt,
    get_range,
    inject_card_style,
    show_cover,
)

start, end = get_range()
days = (end - start).days + 1
prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)
first_day = data.date_bounds()[0]

inject_card_style()
st.title("Resumen")

current = data.kpis(start, end)
previous = data.kpis(prev_start, prev_end) if prev_end >= first_day else None


def delta(key: str) -> str | None:
    if not previous or previous[key] == 0:
        return None
    return f"{(current[key] - previous[key]) / previous[key]:+.0%}"


def longest_streak(dates: pd.Series) -> int:
    ordered = sorted(set(dates))
    best = run = 0
    for i, day in enumerate(ordered):
        run = run + 1 if i and (day - ordered[i - 1]).days == 1 else 1
        best = max(best, run)
    return best


daily = data.daily(start, end)

GRID = dict(gridcolor="#EEF0F4", zeroline=False)


def style(fig, height: int):
    """Same look for every chart: no frame, light grid, fixed height so cards line up."""
    fig.update_layout(height=height, margin=dict(t=8, b=8, l=8, r=8), xaxis_title=None)
    return fig


streak = longest_streak(daily["play_date"]) if len(daily) else 0
kpis = [
    ("Horas escuchadas", fmt(current["hours"]), delta("hours")),
    ("Reproducciones", fmt(current["plays"]), delta("plays")),
    ("Artistas distintos", fmt(current["artists"]), delta("artists")),
    ("Canciones distintas", fmt(current["tracks"]), delta("tracks")),
    ("Racha más larga", f"{streak} días", None),
]
for i, (column, (label, value, change)) in enumerate(zip(st.columns(5), kpis, strict=True)):
    with column, st.container(border=True, key=f"card-kpi-{i}"):
        st.metric(label, value, change)

compared = (
    f"Las variaciones comparan contra los {days} días anteriores al período. " if previous else ""
)
st.caption(
    compared + "Las horas son tiempo real escuchado hasta el 5/11/2026 (historial extendido) "
    "y una estimación después."
)

left, right = st.columns([2, 1])

HIGH_CARD = 580  # the daily chart and the album card are the same height

SHORT_PERIOD_DAYS = 62  # up to about two months, a month per bar would show one or two bars

with left, st.container(border=True, key="card-daily", height=HIGH_CARD):
    by_day = days <= SHORT_PERIOD_DAYS
    card_title("Horas por día" if by_day else "Horas por mes", HOURS)
    if len(daily) and by_day:
        fig = px.bar(daily, x="play_date", y="hours", color_discrete_sequence=[HOURS])
        fig.update_yaxes(title="Horas", **GRID)
        st.plotly_chart(style(fig, HIGH_CARD - 80), width="stretch", key="daily")
    elif len(daily):
        monthly = series.hours_by_month(daily)
        fig = px.bar(
            monthly,
            x="month",
            y="hours",
            color_discrete_sequence=[HOURS],
            custom_data=["label"],
        )
        fig.update_traces(hovertemplate="%{customdata[0]}<br>%{y:,.0f} horas<extra></extra>")
        fig.update_xaxes(tickformat="%Y", dtick="M12", ticklabelmode="period")
        fig.update_yaxes(title="Horas", **GRID)
        st.plotly_chart(style(fig, HIGH_CARD - 80), width="stretch", key="monthly")
        st.caption("Suma de horas de cada mes. El primer y el último mes pueden estar incompletos.")
    else:
        st.info("No hay reproducciones en este período.")

with right, st.container(border=True, key="card-album", height=HIGH_CARD):
    card_title("Álbum más escuchado", ALBUM)
    album = data.top_albums(start, end, 1)
    if len(album):
        row = album.iloc[0]
        show_cover(row["cover"])
        st.markdown(f"**{row['album_name']}**  \n{row['artist']}")
        st.caption(f"{fmt(row['plays'])} reproducciones")
    else:
        st.info("No hay reproducciones en este período.")

col_artists, col_genres = st.columns(2)

with col_artists, st.container(border=True, key="card-artists", height=420):
    card_title("Top 10 artistas", ARTIST)
    artists = data.top_artists(start, end, 10)
    if len(artists):
        fig = figures.ranking_figure(artists, "plays", "artist_name", ARTIST, 310)
        st.plotly_chart(fig, width="stretch", key="top_artists")
        st.caption("La escala inferior indica la cantidad de escuchas.")

with col_genres, st.container(border=True, key="card-genres", height=420):
    card_title("Top 8 géneros", GENRE)
    genres = data.top_genres(start, end, 8)
    if len(genres):
        fig = figures.ranking_figure(genres, "plays", "genre", GENRE, 310)
        st.plotly_chart(fig, width="stretch", key="top_genres")
        st.caption(
            "Reproducciones. Géneros según Last.fm: una reproducción cuenta para todos los "
            "géneros del artista."
        )

with st.container(border=True, key="card-decades", height=470):
    card_title("Reproducciones por década de lanzamiento", DECADE)
    decades = data.release_decades(start, end, figures.FIRST_DECADE)
    if len(decades):
        st.plotly_chart(figures.decades_figure(decades, 340), width="stretch", key="decades")
        share = data.release_year_share(start, end)
        st.caption(
            f"Desde 1960, según el año del álbum en Spotify (una reedición cuenta con su año "
            f"nuevo). Cubre el {fmt(share * 100)} % de las reproducciones del período: el resto "
            "todavía no tiene año y se completa a medida que avanza la carga de metadatos."
        )
    else:
        st.info("No hay reproducciones con año de lanzamiento en este período.")
