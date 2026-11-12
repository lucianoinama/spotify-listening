import streamlit as st

from spotify_app import data
from spotify_app.ui import fmt, get_range, show_cover

start, end = get_range()

st.title("Álbumes")
st.caption("Los álbumes más escuchados del período, con su portada.")

albums = data.top_albums(start, end, 12)
if albums.empty:
    st.info("No hay reproducciones en este período.")
    st.stop()

PER_ROW = 4
for offset in range(0, len(albums), PER_ROW):
    columns = st.columns(PER_ROW)
    row_albums = albums.iloc[offset : offset + PER_ROW]
    for column, (_, row) in zip(columns, row_albums.iterrows(), strict=False):
        with column:
            show_cover(row["cover"])
            st.markdown(f"**{row['album_name']}**  \n{row['artist']}")
            st.caption(f"{fmt(row['plays'])} reproducciones")
