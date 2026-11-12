"""The chat as a floating panel: a round button at the bottom right of every page.

render_chat() is the whole chat (history, examples, input, limits). floating_chat() puts it in
a popover opened by that button, so the page behind stays as it is. The conversation lives in
st.session_state, so it survives going from one page to another.
"""

import os
from datetime import date

import anthropic
import streamlit as st
from streamlit.errors import StreamlitAPIException

from . import chat, data, db, labels, series, ui
from .ui import show_cover

COVER_WIDTH = 180
MAX_QUESTIONS = int(os.environ.get("CHAT_MAX_QUESTIONS", "25"))
TITLE = "Preguntale a los datos"
EXAMPLES = [
    "¿Cuál fue mi artista más escuchado este mes?",
    "¿A qué hora del día escucho más música?",
    "¿Qué géneros escucho más los fines de semana?",
    "Mostrame las horas escuchadas por día en el último mes",
]

PANEL_CSS = """
<style>
.st-key-chat-fab {
    position: fixed; right: 28px; bottom: 28px; z-index: 1000; width: auto;
}
.st-key-chat-fab button {
    width: 60px; height: 60px; min-height: 60px; padding: 0; border-radius: 50%;
    border: none; color: #FFFFFF; background: linear-gradient(135deg, #7C5CFC, #2FA8F0);
    box-shadow: 0 6px 18px rgba(79, 107, 237, 0.45);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.st-key-chat-fab button:hover {
    transform: scale(1.07); box-shadow: 0 8px 22px rgba(79, 107, 237, 0.6); color: #FFFFFF;
}
.st-key-chat-fab button p { display: none; }
.st-key-chat-fab button [data-testid="stIconMaterial"] { font-size: 30px; }
.st-key-chat-fab button > div { justify-content: center; }
.st-key-chat-fab button div[aria-hidden="true"] { display: none; }
[data-testid="stPopoverBody"] {
    width: min(520px, 92vw); max-height: 78vh; overflow-y: auto;
    background: #FFFFFF; border: 1px solid #C9CFDB; border-radius: 16px;
    box-shadow: 0 16px 48px rgba(16, 24, 40, 0.32), 0 3px 10px rgba(16, 24, 40, 0.14);
}
</style>
"""


def show_sql() -> bool:
    """CHAT_SHOW_SQL=1 shows the SQL under each answer, for debugging the prompt."""
    return os.environ.get("CHAT_SHOW_SQL") == "1"


def api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY")


@st.cache_resource(show_spinner=False)
def schema() -> tuple[str, set[str]]:
    return chat.describe_schema(db.run_query)


def apply_period(start: date | None, end: date | None, preset: str | None) -> str:
    """Set the dashboard's period filter on behalf of the chat. The sidebar picks it up on the
    next run, which the chat triggers when the answer is ready.

    Returns what was applied. Raises ValueError, with a message for the model, when the data has
    nothing in that period.
    """
    first, last = data.date_bounds()
    if first is None:
        raise ValueError("There is no data yet.")
    if preset:
        start, end = ui.preset_range(preset, first, last)
        ui.request_period(preset)
    else:
        if end < first or start > last:
            raise ValueError(f"The data covers {first} to {last}. That period is outside it.")
        start, end = max(start, first), min(end, last)
        ui.request_period(None, (start, end))
    return (
        f"Dashboard period set to {start} to {end}, in the user's terms "
        f"{series.describe_period(start, end)}. The data covers {first} to {last}."
    )


def new_analyst() -> chat.Analyst:
    text, tables = schema()
    return chat.Analyst(
        client=anthropic.Anthropic(api_key=api_key()),
        run_query=db.run_query,
        schema_text=text,
        tables=tables,
        model=os.environ.get("CHAT_MODEL", "claude-haiku-5-5"),
        effort=os.environ.get("CHAT_EFFORT", "low"),
        period_setter=apply_period,
    )


def render_answer(answer: chat.Answer, key: str) -> None:
    """The answer, the charts it drew and the result table. The SQL stays out of sight."""
    st.markdown(answer.text)
    for i, artifact in enumerate(answer.artifacts):
        if artifact.figure is not None:
            st.plotly_chart(artifact.figure, width="stretch", key=f"{key}-chart-{i}")
    has_cover, cover = answer.cover()
    if has_cover:
        show_cover(cover, width=COVER_WIDTH)
    table = answer.table()
    if table is not None:
        st.dataframe(labels.friendly(table), hide_index=True, width="stretch")
        if any(a.truncated for a in answer.artifacts):
            st.caption(f"Se muestran las primeras {chat.ROWS_TO_USER} filas.")
    if show_sql():
        for i, artifact in enumerate(answer.artifacts):
            with st.expander(f"Consulta {i + 1}" + (" (con error)" if artifact.error else "")):
                st.code(artifact.sql, language="sql")
                if artifact.error:
                    st.error(artifact.error)


def redraw() -> None:
    """Draw the chat again, and the whole dashboard only when the answer changed the period.

    A fragment rerun leaves the page behind alone, so asking something does not reload every
    chart. Outside a fragment run (the tests) there is only the full rerun.
    """
    if ui.PENDING_KEY in st.session_state:
        st.rerun()
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


@st.fragment
def render_chat() -> None:
    """The chat itself. Same behavior as the old full page, inside whatever container is open.

    A fragment: typing and answering rerun only this function, not the page behind it.
    """
    st.markdown(f"**{TITLE}**")
    if not api_key():
        st.info(
            "El chat necesita una clave de Anthropic. Agregala como `ANTHROPIC_API_KEY` en el "
            "archivo `.env` y reiniciá con `docker compose up -d app`. El resto del tablero "
            "funciona sin ella."
        )
        return

    if "analyst" not in st.session_state:
        st.session_state.analyst = new_analyst()
        st.session_state.turns = []
        st.session_state.tokens = (0, 0)

    analyst: chat.Analyst = st.session_state.analyst
    turns: list[tuple[str, chat.Answer | str]] = st.session_state.turns

    tokens_in, tokens_out = st.session_state.tokens
    st.caption(
        f"Modelo: {analyst.model} · Preguntas: {len(turns)} de {MAX_QUESTIONS} · "
        f"Tokens: {tokens_in:,} de entrada, {tokens_out:,} de salida"
    )
    if st.button("Nueva conversación", key="chat-new", width="stretch"):
        for key in ("analyst", "turns", "tokens"):
            st.session_state.pop(key, None)
        redraw()

    for i, (question, answer) in enumerate(turns):
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            if isinstance(answer, str):
                st.error(answer)
            else:
                render_answer(answer, f"turn-{i}")

    clicked = None
    if not turns:
        st.write("Probá con:")
        for example in EXAMPLES:
            if st.button(example, key=f"example-{example}"):
                clicked = example

    # Inside a panel the input is drawn where it is called: after the history, like a chat.
    typed = st.chat_input(
        "Preguntá algo sobre lo que escuchás",
        key="chat-input",
        disabled=len(turns) >= MAX_QUESTIONS,
    )
    question = typed or clicked

    if len(turns) >= MAX_QUESTIONS:
        st.warning("Llegaste al máximo de preguntas de esta sesión. Empezá una conversación nueva.")
    st.caption(
        "Tus preguntas y las filas que responden se envían a Anthropic. "
        "El chat solo puede leer las tablas del tablero."
    )

    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Consultando tus datos..."):
                try:
                    result = analyst.ask(question)
                except Exception as exc:
                    result = chat.friendly_error(exc)
            if isinstance(result, str):
                st.error(result)
            else:
                render_answer(result, f"turn-{len(turns)}")
                tokens_in, tokens_out = st.session_state.tokens
                st.session_state.tokens = (
                    tokens_in + result.input_tokens,
                    tokens_out + result.output_tokens,
                )
        turns.append((question, result))
        redraw()


def floating_chat() -> None:
    """A round AI button fixed at the bottom right, opening the chat in a panel over the page."""
    st.markdown(PANEL_CSS, unsafe_allow_html=True)
    with st.popover(
        TITLE, icon=":material/auto_awesome:", help=TITLE, key="chat-fab"
    ):
        render_chat()
