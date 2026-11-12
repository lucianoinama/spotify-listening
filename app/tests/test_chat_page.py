"""The chat page end to end with Streamlit's test runner: fake model, fake database."""

from types import SimpleNamespace

import anthropic
import pandas as pd
from streamlit.testing.v1 import AppTest

from spotify_app import db


def chat_page():
    """The chat on its own, without the floating button around it."""
    from spotify_app import chat_panel

    chat_panel.render_chat()


def floating_page():
    from spotify_app import chat_panel

    chat_panel.floating_chat()


def run_chat():
    return AppTest.from_function(chat_page, default_timeout=30).run()
FRAME = pd.DataFrame({"artist": ["A", "B"], "plays": [5, 3]})


def fake_run_query(sql, params=None):
    if "information_schema" in sql:
        return pd.DataFrame(
            {
                "table_name": ["fct_plays"],
                "column_name": ["play_id"],
                "data_type": ["text"],
            }
        )
    return FRAME


class FakeAnthropic:
    def __init__(self, **kwargs):
        self.messages = self
        self.replies = [
            ("tool_use", [("run_sql", {"query": "select artist, plays from fct_plays"})]),
            ("tool_use", [("show_chart", {"kind": "barh", "x": "artist", "y": "plays"})]),
            ("end_turn", "El artista más escuchado es A."),
        ]

    def create(self, **kwargs):
        stop, payload = self.replies.pop(0)
        if stop == "end_turn":
            content = [SimpleNamespace(type="text", text=payload)]
        else:
            content = [
                SimpleNamespace(type="tool_use", id=f"t{len(self.replies)}", name=n, input=i)
                for n, i in payload
            ]
        usage = SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        return SimpleNamespace(stop_reason=stop, content=content, usage=usage)


def test_page_without_api_key_explains_how_to_enable_chat(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = run_chat()
    assert not at.exception
    assert "ANTHROPIC_API_KEY" in at.info[0].value


def test_question_renders_answer_chart_and_a_table_without_sql(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(db, "run_query", fake_run_query)
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    at = run_chat()
    assert not at.exception

    at.chat_input[0].set_value("¿Quién es mi artista top?").run()
    assert not at.exception

    texts = [m.markdown[0].value for m in at.chat_message if m.markdown]
    assert "¿Quién es mi artista top?" in texts
    assert "El artista más escuchado es A." in texts
    assert at.session_state.tokens == (30, 15)
    assert len(at.session_state.turns) == 1

    # The result is a table with readable column names, and the SQL is not on screen.
    assert list(at.dataframe[0].value.columns) == ["Artista", "Reproducciones"]
    assert not at.code
    assert not at.expander


def test_the_sql_is_shown_only_when_asked_for(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_SHOW_SQL", "1")
    monkeypatch.setattr(db, "run_query", fake_run_query)
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    at = run_chat()
    at.chat_input[0].set_value("¿Quién es mi artista top?").run()
    assert not at.exception
    assert at.code[0].value == "select artist, plays from fct_plays"


ALBUMS = pd.DataFrame(
    {
        "album": ["Humbug", "AM"],
        "reproducciones": [503, 276],
        "album_image_url": ["https://i.scdn.co/image/humbug", None],
    }
)


class AlbumAnthropic(FakeAnthropic):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.replies = [
            ("tool_use", [("run_sql", {"query": "select album from fct_plays"})]),
            ("end_turn", "El álbum más escuchado es Humbug."),
        ]


def test_an_album_answer_shows_the_cover_of_the_first_album_and_not_its_url(monkeypatch):
    def run_query(sql, params=None):
        return fake_run_query(sql) if "information_schema" in sql else ALBUMS

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(db, "run_query", run_query)
    monkeypatch.setattr(anthropic, "Anthropic", AlbumAnthropic)

    at = run_chat()
    at.chat_input[0].set_value("¿Cuál es mi álbum más escuchado?").run()
    assert not at.exception
    assert list(at.dataframe[0].value.columns) == ["Álbum", "Reproducciones"]
    images = at.get("image")
    assert len(images) == 1
    assert images[0].proto.imgs[0].url == "https://i.scdn.co/image/humbug"


def test_the_floating_button_holds_the_whole_chat(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(db, "run_query", fake_run_query)
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    at = AppTest.from_function(floating_page, default_timeout=30).run()
    assert not at.exception
    popovers = at.get("popover")
    assert len(popovers) == 1
    assert popovers[0].proto.popover.label == "Preguntale a los datos"
    assert popovers[0].proto.popover.help == "Preguntale a los datos"
    # The chat is inside it: examples to click and the input to type in.
    assert len(at.chat_input) == 1
    assert [b.label for b in at.button if b.key and b.key.startswith("example-")]
