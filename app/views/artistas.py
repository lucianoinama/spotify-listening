import plotly.express as px
import streamlit as st

from spotify_app import data, figures
from spotify_app.ui import ARTIST, GENRE, fmt, get_range

start, end = get_range()

st.title("Artistas y géneros")

artists = data.top_artists(start, end, 15)
genres = data.top_genres(start, end, 10)
if artists.empty:
    st.info("No hay reproducciones en este período.")
    st.stop()

left, right = st.columns(2)

with left:
    st.subheader("Top 15 artistas")
    table = artists.rename(
        columns={
            "artist_name": "Artista",
            "plays": "Reproducciones",
            "hours": "Horas",
            "tracks": "Canciones",
        }
    )
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={"Horas": st.column_config.NumberColumn(format="%.1f")},
    )

with right:
    st.subheader("Top 10 géneros")
    fig = figures.ranking_figure(genres, "plays", "genre", GENRE)
    fig.update_xaxes(title="Reproducciones")
    st.plotly_chart(fig, width="stretch", key="genres")
    st.caption("Géneros según Last.fm. Una reproducción cuenta para todos los géneros del artista.")

st.divider()
st.subheader("Artistas de un género")
genre = st.selectbox("Género", genres["genre"].tolist())
by_genre = data.genre_artists(genre, start, end, 10)
if len(by_genre):
    fig = figures.ranking_figure(by_genre, "plays", "artist_name", ARTIST)
    fig.update_xaxes(title="Reproducciones")
    st.plotly_chart(fig, width="stretch", key="genre_artists")

st.divider()
st.subheader("Detalle de un artista")
names = data.artist_names()
artist = st.selectbox("Artista", names, index=0)
monthly = data.artist_monthly(artist, start, end)
tracks = data.artist_tracks(artist, start, end, 10)
col_a, col_b = st.columns(2)
with col_a:
    st.markdown("**Reproducciones por mes**")
    if len(monthly):
        fig = px.bar(monthly, x="month_start", y="plays", color_discrete_sequence=[ARTIST])
        fig.update_layout(xaxis_title=None, yaxis_title="Reproducciones", margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch", key="artist_monthly")
    else:
        st.caption("Sin reproducciones en este período.")
with col_b:
    st.markdown("**Canciones más escuchadas**")
    if len(tracks):
        st.dataframe(
            tracks.rename(columns={"track_name": "Canción", "plays": "Reproducciones"}),
            hide_index=True,
            width="stretch",
        )
    total = int(monthly["plays"].sum()) if len(monthly) else 0
    st.caption(f"{fmt(total)} reproducciones en el período.")
