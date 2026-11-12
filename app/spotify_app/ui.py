"""Shared pieces of the dashboard: number format, date filter, colors."""

from datetime import date, timedelta

import streamlit as st

from . import data, health

# One palette for every chart and card: Spotify green first, then colors that stay apart.
PALETTE = [
    "#1DB954",  # green
    "#7C5CFC",  # violet
    "#FF6B57",  # coral
    "#FFB524",  # amber
    "#2FA8F0",  # sky
    "#EC5B9D",  # pink
    "#12B5A5",  # teal
    "#4F6BED",  # indigo
]
GREEN = PALETTE[0]
# One color per kind of thing, the same on every page and chart, so a color means something:
# artists violet, genres coral, decades amber, hours and listening times sky, albums pink.
ARTIST, GENRE, DECADE, HOURS, ALBUM = PALETTE[1], PALETTE[2], PALETTE[3], PALETTE[4], PALETTE[5]
HEAT_SCALE = ["#F3F0FF", "#7C5CFC", "#EC5B9D", "#FFB524"]  # light to hot, for heatmaps
DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]  # ISO weekday 1..7


def fmt(value: float, decimals: int = 0) -> str:
    """1234.5 -> '1.234,5' (es-AR)."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


CARD_CSS = """
<style>
.stApp { background: #F3F5F9; }
[data-testid="stSidebar"] { background: #FFFFFF; }
[class*="st-key-card"] {
    background: #FFFFFF;
    border: 1px solid #E6E9EF;
    border-radius: 12px;
    box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    padding: 0.9rem 1.1rem;
}
.card-title { font-size: 1.02rem; font-weight: 600; margin: 0 0 0.35rem 0; }
.card-title .dot {
    display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px;
}
[class*="st-key-card-kpi"] [data-testid="stMetricLabel"] { opacity: 0.7; }
[class*="st-key-card-kpi"] [data-testid="stMetricLabel"] * { white-space: normal; }
[class*="st-key-card-kpi"] [data-testid="stMetricValue"] { font-weight: 600; }
{accents}
</style>
"""

# Each KPI card gets a colored top edge and a number of the same color (keys card-kpi-0, -1, ...).
KPI_ACCENTS = "\n".join(
    f".st-key-card-kpi-{i} {{ border-top: 4px solid {color}; }}\n"
    f'.st-key-card-kpi-{i} [data-testid="stMetricValue"] {{ color: {color}; }}'
    for i, color in enumerate(PALETTE[:5])
)


def inject_card_style() -> None:
    """Light grey page with white rounded cards. Lasts only while the calling page is shown."""
    st.markdown(CARD_CSS.replace("{accents}", KPI_ACCENTS), unsafe_allow_html=True)


def card_title(text: str, color: str | None = None) -> None:
    """Card heading, with a small dot of the card's color in front."""
    dot = f'<span class="dot" style="background:{color}"></span>' if color else ""
    st.markdown(f'<div class="card-title">{dot}{text}</div>', unsafe_allow_html=True)


def has_cover(value) -> bool:
    """True for a usable image URL. None, NaN (what pandas makes of a NULL) and '' are not."""
    return isinstance(value, str) and value.strip() != ""


def show_cover(value, width: int | None = None) -> None:
    """The album cover, or a square that says 'Sin portada' when there is none.

    Full column width by default; width is a size in pixels for places like the chat.
    """
    if has_cover(value):
        if width:
            st.image(value, width=width)
        else:
            st.image(value, width="stretch")
        return
    size = f"width:{width}px;" if width else ""
    st.markdown(
        f'<div style="{size}aspect-ratio:1/1;display:flex;align-items:center;'
        "justify-content:center;border-radius:4px;background:rgba(128,128,128,0.15);"
        'opacity:0.7">Sin portada</div>',
        unsafe_allow_html=True,
    )


def sidebar_filters() -> None:
    """Date range shared by every dashboard page. Stored in session_state['range']."""
    first, last = data.date_bounds()
    if first is None:
        st.sidebar.warning("Todavía no hay reproducciones en la base.")
        st.session_state["range"] = None
        return
    apply_pending_period()
    st.sidebar.subheader("Período")
    preset = st.sidebar.radio(
        "Rango rápido",
        [*PRESET_LABELS.values(), CUSTOM],
        key=PRESET_KEY,
        label_visibility="collapsed",
    )
    preset_key = next((k for k, label in PRESET_LABELS.items() if label == preset), None)
    if preset_key:
        chosen = preset_range(preset_key, first, last)
    else:
        # A value set through the session state (by the chat) must not also be passed as default.
        default = {} if DATES_KEY in st.session_state else {"value": (first, last)}
        picked = st.sidebar.date_input(
            "Fechas",
            min_value=first,
            max_value=last,
            format="DD/MM/YYYY",
            key=DATES_KEY,
            **default,
        )
        chosen = tuple(picked) if len(picked) == 2 else None
    st.session_state["range"] = chosen
    if chosen:
        st.sidebar.caption(f"{chosen[0]:%d/%m/%Y} a {chosen[1]:%d/%m/%Y}")


def data_status() -> None:
    """How fresh the data is: a line in the sidebar always, and a banner when the ingester has
    not worked for hours (the cause has to be fixed outside the dashboard)."""
    status = data.ingest_status()
    if status is None:
        return
    last_ok, failures, error = status
    state = health.freshness(last_ok, failures)
    _, last_play = data.date_bounds()
    last_play_text = f" · Última reproducción: {last_play:%d/%m/%Y}" if last_play else ""
    st.sidebar.caption(f"{state.dot} {state.text}{last_play_text}")
    if state.level == health.STALE:
        failed = f" {failures} intentos fallaron." if failures else ""
        last_error = f"\n\nÚltimo error: `{error}`" if error else ""
        st.warning(
            f"**La ingesta no sincroniza.** {state.text.split(': ')[1].capitalize()} que no "
            f"llegan reproducciones nuevas.{failed} Revisá `docker compose logs ingest`."
            f"{last_error}",
            icon=":material/warning:",
        )


PRESET_LABELS = {"all": "Todo", "last_30_days": "Últimos 30 días", "last_7_days": "Últimos 7 días"}
CUSTOM = "Personalizado"
PRESET_KEY, DATES_KEY, PENDING_KEY = "period_preset", "period_dates", "pending_period"


def preset_range(preset: str, first: date, last: date) -> tuple[date, date]:
    """The days a preset covers, inside the days the data has."""
    if preset == "all":
        return first, last
    days = {"last_30_days": 30, "last_7_days": 7}[preset]
    return max(first, last - timedelta(days=days - 1)), last


def request_period(preset: str | None, dates: tuple[date, date] | None = None) -> None:
    """Ask for a period on the next run. Widgets cannot be changed after they are drawn, so the
    request waits in the session state and the sidebar applies it before drawing its widgets.

    preset is a key of PRESET_LABELS; with dates, the custom range is selected instead.
    """
    st.session_state[PENDING_KEY] = (preset, dates)


def apply_pending_period() -> None:
    pending = st.session_state.pop(PENDING_KEY, None)
    if not pending:
        return
    preset, dates = pending
    if dates:
        st.session_state[PRESET_KEY] = CUSTOM
        st.session_state[DATES_KEY] = dates
    else:
        st.session_state[PRESET_KEY] = PRESET_LABELS[preset]


def get_range() -> tuple[date, date]:
    """The selected range, or stop the page with a message when there is none."""
    chosen = st.session_state.get("range")
    if not chosen:
        st.info("Elegí una fecha de inicio y una de fin en la barra lateral.")
        st.stop()
    return chosen
