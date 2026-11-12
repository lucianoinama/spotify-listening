"""The 'Última sincronización' line and the banner when the ingester stops."""

from datetime import UTC, date, datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from spotify_app import data, health

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("age", "text"),
    [
        (timedelta(seconds=20), "hace instantes"),
        (timedelta(minutes=1), "hace 1 minuto"),
        (timedelta(minutes=12), "hace 12 minutos"),
        (timedelta(hours=1, minutes=5), "hace 1 hora"),
        (timedelta(hours=7), "hace 7 horas"),
        (timedelta(days=3), "hace 3 días"),
    ],
)
def test_ago_is_written_in_the_largest_unit(age, text):
    assert health.ago(age) == text


@pytest.mark.parametrize(
    ("age", "level"),
    [
        (timedelta(minutes=14), health.OK),
        (timedelta(hours=2), health.LATE),
        (timedelta(hours=6), health.STALE),
        (timedelta(days=2), health.STALE),
    ],
)
def test_the_level_follows_the_age_of_the_last_good_run(age, level):
    assert health.freshness(NOW - age, now=NOW).level == level


def test_a_database_that_never_synced_is_unknown_not_an_alarm():
    state = health.freshness(None, now=NOW)
    assert state.level == health.UNKNOWN and "sin registro" in state.text


def test_one_failure_between_good_runs_does_not_raise_the_level():
    assert health.freshness(NOW - timedelta(minutes=5), failures=1, now=NOW).level == health.OK


def status_page():
    from spotify_app import ui

    ui.data_status()


def run_status(monkeypatch, status):
    monkeypatch.setattr(data, "ingest_status", lambda: status)
    monkeypatch.setattr(data, "date_bounds", lambda: (date(2020, 1, 2), date(2026, 11, 10)))
    return AppTest.from_function(status_page, default_timeout=30).run()


def test_a_working_ingester_shows_a_line_in_the_sidebar_and_no_banner(monkeypatch):
    at = run_status(monkeypatch, (datetime.now(UTC) - timedelta(minutes=3), 0, None))
    assert not at.exception and not at.warning
    line = at.sidebar.caption[0].value
    assert "🟢" in line and "hace 3 minutos" in line and "10/11/2026" in line


def test_a_stopped_ingester_shows_the_banner_with_the_last_error(monkeypatch):
    stale = datetime.now(UTC) - timedelta(hours=30)
    at = run_status(monkeypatch, (stale, 12, "429 Too Many Requests"))
    banner = at.warning[0].value
    assert "no sincroniza" in banner and "Hace 30 horas" in banner
    assert "12 intentos fallaron" in banner and "429 Too Many Requests" in banner
    assert "🔴" in at.sidebar.caption[0].value


def test_without_the_status_view_the_dashboard_shows_nothing_extra(monkeypatch):
    at = run_status(monkeypatch, None)
    assert not at.exception and not at.warning and not at.sidebar.caption
