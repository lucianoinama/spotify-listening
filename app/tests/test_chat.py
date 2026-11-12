"""The chat loop with a scripted fake client: no network, no database."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from spotify_app import chat

TABLES = {"fct_plays", "dim_tracks"}


def usage(inp=10, out=5):
    return SimpleNamespace(input_tokens=inp, output_tokens=out,
                           cache_creation_input_tokens=0, cache_read_input_tokens=0)


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(id_, name, **tool_input):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=tool_input)


def reply(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks), usage=usage())


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        # snapshot: the loop appends to the same list afterwards
        self.calls[-1]["messages"] = list(kwargs["messages"])
        return self.replies.pop(0)


def analyst(client, run_query=None):
    frame = pd.DataFrame({"artist": ["A", "B"], "plays": [5, 3]})
    return chat.Analyst(
        client=client,
        run_query=run_query or (lambda sql: frame),
        schema_text="Tables:\n- fct_plays(play_id text)",
        tables=TABLES,
        model="claude-opus-5-5",
    )


def test_prompt_carries_the_fixed_sentences_the_user_asked_for():
    client = FakeClient([reply("end_turn", text_block("ok"))])
    analyst(client).ask("hola")
    system = client.calls[0]["system"][0]["text"]
    assert chat.NO_DATA_PERIOD == "No tengo datos disponibles para ese periodo."
    for sentence in (chat.NO_DATA_PERIOD, chat.NO_DATA_OTHER, chat.OFF_TOPIC):
        assert sentence in system


def test_question_runs_sql_draws_chart_and_answers():
    client = FakeClient([
        reply("tool_use", tool_block("t1", "run_sql", query="select 1 as plays from fct_plays")),
        reply("tool_use", tool_block("t2", "show_chart", kind="barh", x="artist", y="plays")),
        reply("end_turn", text_block("A es tu artista más escuchado.")),
    ])
    bot = analyst(client)
    answer = bot.ask("¿Quién es mi artista top?")

    assert answer.text == "A es tu artista más escuchado."
    assert len(answer.artifacts) == 1
    assert answer.artifacts[0].frame is not None
    assert answer.artifacts[0].figure is not None
    assert answer.input_tokens == 30 and answer.output_tokens == 15

    # the model got the rows back as JSON
    second_call = client.calls[1]["messages"]
    result = second_call[-1]["content"][0]
    assert result["type"] == "tool_result" and "is_error" not in result
    assert json.loads(result["content"])["rows"][0] == {"artist": "A", "plays": 5}
    # the conversation advanced: user, assistant, tool result, assistant, tool result, assistant
    assert len(bot.history) == 6


def test_unsafe_sql_is_not_run_and_the_model_is_told():
    ran = []
    client = FakeClient([
        reply("tool_use", tool_block("t1", "run_sql", query="drop table fct_plays")),
        reply("end_turn", text_block("No puedo borrar datos.")),
    ])
    bot = analyst(client, run_query=lambda sql: ran.append(sql))
    answer = bot.ask("borrá todo")

    assert ran == []
    assert answer.artifacts[0].error
    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and result["content"].startswith("Rejected")


def test_database_error_goes_back_to_the_model():
    def boom(sql):
        raise RuntimeError('column "x" does not exist\nLINE 1: select x')

    client = FakeClient([
        reply("tool_use", tool_block("t1", "run_sql", query="select x from fct_plays")),
        reply("end_turn", text_block("Esa consulta falló.")),
    ])
    answer = analyst(client, run_query=boom).ask("hola")

    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and 'column "x" does not exist' in result["content"]
    assert answer.text == "Esa consulta falló."


def test_chart_with_unknown_column_returns_the_available_columns():
    client = FakeClient([
        reply("tool_use", tool_block("t1", "run_sql", query="select 1 from fct_plays")),
        reply("tool_use", tool_block("t2", "show_chart", kind="bar", x="nope", y="plays")),
        reply("end_turn", text_block("ok")),
    ])
    answer = analyst(client).ask("x")

    result = client.calls[2]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "artist" in result["content"]
    assert answer.artifacts[0].figure is None


def test_chart_before_any_query_is_an_error():
    client = FakeClient([
        reply("tool_use", tool_block("t1", "show_chart", kind="bar", x="a", y="b")),
        reply("end_turn", text_block("ok")),
    ])
    analyst(client).ask("x")
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_refusal_gives_a_message_and_stops():
    client = FakeClient([reply("refusal")])
    assert analyst(client).ask("x").text == "No puedo responder esa pregunta."


def test_runaway_tool_loop_stops_after_max_steps():
    looping = [
        reply("tool_use", tool_block(f"t{i}", "run_sql", query="select 1 from fct_plays"))
        for i in range(chat.MAX_STEPS)
    ]
    answer = analyst(FakeClient(looping)).ask("x")
    assert "demasiados pasos" in answer.text


def test_failed_turn_leaves_history_untouched():
    class Broken(FakeClient):
        def create(self, **kwargs):
            raise RuntimeError("network down")

    bot = analyst(Broken([]))
    try:
        bot.ask("x")
    except RuntimeError:
        pass
    assert bot.history == []


def test_second_question_sees_the_first_exchange():
    client = FakeClient([
        reply("end_turn", text_block("uno")),
        reply("end_turn", text_block("dos")),
    ])
    bot = analyst(client)
    bot.ask("primera")
    bot.ask("segunda")
    assert len(client.calls[1]["messages"]) == 3  # user, assistant, user


def test_rows_sent_to_the_model_are_capped():
    big = pd.DataFrame({"n": range(chat.ROWS_TO_USER + 50), "s": "x" * 500})
    client = FakeClient([
        reply("tool_use", tool_block("t1", "run_sql", query="select 1 from fct_plays")),
        reply("end_turn", text_block("ok")),
    ])
    answer = analyst(client, run_query=lambda sql: big).ask("x")

    sent = json.loads(client.calls[1]["messages"][-1]["content"][0]["content"])
    assert sent["rows_shown"] == chat.ROWS_TO_MODEL
    assert len(sent["rows"][0]["s"]) == chat.CELL_CHARS
    assert answer.artifacts[0].truncated is True
    assert len(answer.artifacts[0].frame) == chat.ROWS_TO_USER


# --- what the user sees ----------------------------------------------------------------------


def test_the_table_is_the_last_query_that_worked():
    answer = chat.Answer(
        text="",
        artifacts=[
            chat.Artifact(sql="a", frame=pd.DataFrame({"x": [1, 2]})),
            chat.Artifact(sql="b", frame=pd.DataFrame({"y": [3, 4]})),
            chat.Artifact(sql="c", error="boom"),
        ],
    )
    assert list(answer.table().columns) == ["y"]


@pytest.mark.parametrize(
    "frame",
    [pd.DataFrame({"horas": [6.5]}), pd.DataFrame({"horas": []})],
    ids=["single value", "no rows"],
)
def test_a_single_value_or_an_empty_result_is_not_shown_as_a_table(frame):
    assert chat.Answer(text="", artifacts=[chat.Artifact(sql="a", frame=frame)]).table() is None


def test_the_prompt_asks_for_neutral_wording_full_dates_and_a_top_five_table():
    assert 'Never "Tu artista"' in chat.RULES
    assert "4 al 7 de Noviembre de 2026" in chat.RULES
    assert "top 5" in chat.RULES
    assert "never sees the SQL" in chat.RULES


def album_answer(cover):
    frame = pd.DataFrame(
        {"album": ["Humbug", "AM"], "reproducciones": [503, 276], "album_image_url": [cover, None]}
    )
    return chat.Answer(text="", artifacts=[chat.Artifact(sql="a", frame=frame)])


def test_the_cover_of_the_first_row_is_found_and_left_out_of_the_table():
    answer = album_answer("https://i.scdn.co/image/humbug")
    assert answer.cover() == (True, "https://i.scdn.co/image/humbug")
    assert list(answer.table().columns) == ["album", "reproducciones"]


def test_an_unknown_cover_is_reported_as_a_missing_picture_not_as_no_cover_column():
    assert album_answer(None).cover() == (True, None)


def test_a_result_without_a_cover_column_has_no_picture():
    frame = pd.DataFrame({"artista": ["A"], "reproducciones": [3]})
    assert chat.Answer(text="", artifacts=[chat.Artifact(sql="a", frame=frame)]).cover() == (
        False,
        None,
    )


def test_the_prompt_asks_for_the_cover_in_album_answers():
    assert "album_image_url" in chat.RULES


# --- set_period: the chat changes the dashboard's date filter ---------------------------------


def period_chat(*tool_calls, setter):
    blocks = [tool_block(f"t{i}", "set_period", **call) for i, call in enumerate(tool_calls)]
    client = FakeClient([reply("tool_use", *blocks), reply("end_turn", text_block("Listo."))])
    bot = chat.Analyst(
        client=client,
        run_query=lambda sql: pd.DataFrame(),
        schema_text="Tables:",
        tables=TABLES,
        model="claude-opus-5-5",
        period_setter=setter,
    )
    bot.ask("Filtrame el periodo")
    return client.calls[1]["messages"][-1]["content"]  # the tool results sent back to the model


def test_the_model_can_set_the_period_with_two_dates():
    from datetime import date

    seen = []

    def setter(start, end, preset):
        seen.append((start, end, preset))
        return "Dashboard period set."

    results = period_chat({"start": "2026-10-05", "end": "2026-11-05"}, setter=setter)
    assert seen == [(date(2026, 10, 5), date(2026, 11, 5), None)]
    assert results[0]["content"] == "Dashboard period set." and "is_error" not in results[0]


def test_a_preset_is_passed_on_without_dates():
    seen = []
    period_chat({"preset": "last_7_days"}, setter=lambda s, e, p: seen.append((s, e, p)) or "ok")
    assert seen == [(None, None, "last_7_days")]


@pytest.mark.parametrize(
    "call",
    [
        {"start": "5 de octubre", "end": "2026-11-05"},
        {"start": "2026-11-05", "end": "2026-10-05"},
        {"start": "2026-10-05"},
        {},
        {"preset": "last_year"},
    ],
    ids=["bad date", "start after end", "no end", "nothing", "unknown preset"],
)
def test_bad_period_requests_come_back_as_errors_the_model_can_fix(call):
    results = period_chat(call, setter=lambda s, e, p: pytest.fail("must not be applied"))
    assert results[0]["is_error"] is True


def test_a_refusal_from_the_dashboard_reaches_the_model_as_an_error():
    def setter(start, end, preset):
        raise ValueError("The data covers 2020-01-02 to 2026-11-10. That period is outside it.")

    results = period_chat({"start": "2031-01-01", "end": "2031-02-01"}, setter=setter)
    assert results[0]["is_error"] is True and "outside it" in results[0]["content"]


def test_without_a_setter_the_filter_cannot_be_changed():
    results = period_chat({"preset": "all"}, setter=None)
    assert results[0]["is_error"] is True


def test_the_prompt_explains_the_filter_and_keeps_the_no_data_sentence():
    assert "set_period" in chat.RULES
    assert chat.NO_DATA_PERIOD in chat.RULES.split("Dashboard filter")[1]
    assert "set_period" in [tool["name"] for tool in chat.TOOLS]
