"""The sidebar's period filter, and the chat driving it."""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from spotify_app import chat_panel, data, ui

FIRST, LAST = date(2020, 1, 2), date(2026, 11, 10)


@pytest.fixture(autouse=True)
def bounds(monkeypatch):
    monkeypatch.setattr(data, "date_bounds", lambda: (FIRST, LAST))


def sidebar_page():
    from spotify_app import ui

    ui.sidebar_filters()


def run_sidebar() -> AppTest:
    return AppTest.from_function(sidebar_page, default_timeout=30).run()


def test_without_a_request_the_period_is_all_the_data():
    at = run_sidebar()
    assert at.session_state["range"] == (FIRST, LAST)
    assert at.sidebar.radio[0].value == "Todo"


def test_a_requested_range_selects_personalizado_with_those_dates():
    at = run_sidebar()
    at.session_state[ui.PENDING_KEY] = (None, (date(2026, 10, 5), date(2026, 11, 5)))
    at.run()
    assert not at.exception
    assert at.session_state["range"] == (date(2026, 10, 5), date(2026, 11, 5))
    assert at.sidebar.radio[0].value == "Personalizado"
    assert ui.PENDING_KEY not in at.session_state  # applied once, not on every run


def test_a_requested_preset_selects_it():
    at = run_sidebar()
    at.session_state[ui.PENDING_KEY] = ("last_7_days", None)
    at.run()
    assert at.sidebar.radio[0].value == "Últimos 7 días"
    assert at.session_state["range"] == (date(2026, 11, 4), date(2026, 11, 10))


def test_presets_stay_inside_the_data():
    first, last = date(2026, 11, 8), date(2026, 11, 10)
    assert ui.preset_range("last_30_days", first, last) == (first, last)
    assert ui.preset_range("all", first, last) == (first, last)


# --- chat_panel.apply_period: what the chat's set_period tool does -------------------------


def apply_page():
    import streamlit as st

    from spotify_app import chat_panel

    args = st.session_state["args"]
    try:
        st.session_state["result"] = chat_panel.apply_period(*args)
    except ValueError as exc:
        st.session_state["result"] = f"error: {exc}"


def apply(start, end, preset=None) -> tuple[str, dict]:
    at = AppTest.from_function(apply_page, default_timeout=30)
    at.session_state["args"] = (start, end, preset)
    at.run()
    assert not at.exception
    return at.session_state["result"], at.session_state


def test_a_period_inside_the_data_is_requested_as_given():
    result, state = apply(date(2026, 10, 5), date(2026, 11, 5))
    assert state[ui.PENDING_KEY] == (None, (date(2026, 10, 5), date(2026, 11, 5)))
    assert "5 de Octubre al 5 de Noviembre de 2026" in result


def test_a_period_that_overhangs_the_data_is_cut_to_it():
    result, state = apply(date(2019, 12, 1), date(2020, 1, 20))
    assert state[ui.PENDING_KEY] == (None, (FIRST, date(2020, 1, 20)))
    assert "2020-01-02 to 2020-01-20" in result


def test_a_period_outside_the_data_is_refused_with_the_range_the_data_has():
    result, state = apply(date(2031, 1, 1), date(2031, 2, 1))
    assert result.startswith("error:") and "2026-11-10" in result
    assert ui.PENDING_KEY not in state


def test_a_preset_is_requested_by_name():
    result, state = apply(None, None, "last_30_days")
    assert state[ui.PENDING_KEY] == ("last_30_days", None)
    assert "2026-10-12 to 2026-11-10" in result


def test_the_chat_panel_hands_its_analyst_the_period_setter(monkeypatch):
    assert chat_panel.apply_period is not None
