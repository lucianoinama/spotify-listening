import streamlit as st

from spotify_app import data, figures
from spotify_app.ui import (
    DECADE,
    PALETTE,
    card_title,
    fmt,
    get_range,
    inject_card_style,
)

start, end = get_range()

inject_card_style()
st.title("Canciones")

tracks = data.top_tracks(start, end, 15)
if tracks.empty:
    st.info("No hay reproducciones en este período.")
    st.stop()

with st.container(border=True, key="card-top-tracks"):
    card_title("Top 15 canciones", PALETTE[0])
    st.dataframe(
        tracks[["cover", "track_name", "artist", "album_name", "plays", "hours"]],
        hide_index=True,
        width="stretch",
        column_config={
            "cover": st.column_config.ImageColumn("", width="small"),
            "track_name": "Canción",
            "artist": "Artista",
            "album_name": "Álbum",
            "plays": "Reproducciones",
            "hours": st.column_config.NumberColumn("Horas", format="%.2f"),
        },
    )

CARD_HEIGHT = 470
left, middle, right = st.columns([5, 3, 2])

with left, st.container(border=True, key="card-decades", height=CARD_HEIGHT):
    card_title("Década de lanzamiento", DECADE)
    decades = data.release_decades(start, end, figures.FIRST_DECADE)
    if len(decades):
        st.plotly_chart(figures.decades_figure(decades, 340), width="stretch", key="decades")
        share = data.release_year_share(start, end)
        st.caption(
            f"Desde 1960, según el año del álbum en Spotify. Cubre el {fmt(share * 100)} % de "
            "las reproducciones del período."
        )
    else:
        st.info("No hay reproducciones con año de lanzamiento en este período.")

with middle, st.container(border=True, key="card-sources", height=CARD_HEIGHT):
    card_title("Desde dónde escucho", PALETTE[6])
    sources = data.play_sources(start, end)
    fig = figures.ranking_figure(sources, "plays", "source", PALETTE[6], 340)
    st.plotly_chart(fig, width="stretch", key="sources")
    st.caption("Reproducciones según el lugar de Spotify desde donde empezaron.")

with right, st.container(border=True, key="card-kpi-2", height=CARD_HEIGHT):
    card_title("Contenido explícito", PALETTE[2])
    share = data.explicit_share(start, end)
    st.metric("Reproducciones explícitas", f"{fmt(share * 100, 0)} %")
    st.progress(min(max(share, 0.0), 1.0))
    st.caption("Parte de las reproducciones que Spotify marca como explícitas.")
