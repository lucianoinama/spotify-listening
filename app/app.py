"""Streamlit entry point: navigation, date filter and the floating chat."""

import streamlit as st

from spotify_app import chat_panel, ui

st.set_page_config(page_title="Spotify Listening", page_icon="🎧", layout="wide")

# Top left, above the page list; the round mark alone when the sidebar is collapsed.
st.logo("assets/spotify-logo.png", icon_image="assets/spotify-icon.png", size="large")

pages = [
    st.Page("views/resumen.py", title="Resumen", icon=":material/dashboard:", default=True),
    st.Page("views/cuando.py", title="Cuándo escucho", icon=":material/schedule:"),
    st.Page("views/artistas.py", title="Artistas y géneros", icon=":material/groups:"),
    st.Page("views/canciones.py", title="Canciones", icon=":material/music_note:"),
    st.Page("views/albumes.py", title="Álbumes", icon=":material/album:"),
]
navigation = st.navigation(pages)
ui.sidebar_filters()
ui.data_status()
navigation.run()
chat_panel.floating_chat()
