from datetime import date

import pandas as pd

from spotify_app import series


def daily(rows):
    return pd.DataFrame(rows, columns=["play_date", "hours"])


def test_days_are_summed_into_months():
    out = series.hours_by_month(
        daily([(date(2024, 1, 5), 1.5), (date(2024, 1, 20), 2.0), (date(2024, 2, 3), 1.0)])
    )
    assert out["hours"].tolist() == [3.5, 1.0]
    assert out["label"].tolist() == ["Enero 2024", "Febrero 2024"]


def test_a_month_without_plays_between_two_others_is_kept_with_zero_hours():
    out = series.hours_by_month(daily([(date(2024, 1, 5), 1.0), (date(2024, 4, 9), 2.0)]))
    assert out["label"].tolist() == ["Enero 2024", "Febrero 2024", "Marzo 2024", "Abril 2024"]
    assert out["hours"].tolist() == [1.0, 0.0, 0.0, 2.0]


def test_the_year_column_is_text_so_it_colors_by_category():
    out = series.hours_by_month(daily([(date(2023, 12, 31), 1.0), (date(2024, 1, 1), 1.0)]))
    assert out["year"].tolist() == ["2023", "2024"]


def test_no_days_give_an_empty_table_with_the_same_columns():
    out = series.hours_by_month(daily([]))
    assert out.empty and list(out.columns) == ["month", "hours", "year", "label"]


def test_the_decades_chart_starts_in_1960_and_fills_decades_without_plays():
    from spotify_app import figures

    plays = pd.DataFrame({"decade": [1980, 2000], "plays": [10, 5]})
    fig = figures.decades_figure(plays, 300)
    assert list(fig.layout.xaxis.categoryarray) == ["1960s", "1970s", "1980s", "1990s", "2000s"]
    counts = {x: y for trace in fig.data for x, y in zip(trace.x, trace.y, strict=True)}
    assert counts == {"1960s": 0, "1970s": 0, "1980s": 10, "1990s": 0, "2000s": 5}


def test_periods_are_written_in_full_with_a_capitalized_month():
    d = date
    assert series.describe_period(d(2026, 11, 4), d(2026, 11, 7)) == "4 al 7 de Noviembre de 2026"
    assert series.describe_period(d(2026, 10, 5), d(2026, 11, 5)) == (
        "5 de Octubre al 5 de Noviembre de 2026"
    )
    assert series.describe_period(d(2026, 11, 7), d(2026, 11, 7)) == "7 de Noviembre de 2026"
    assert series.describe_period(d(2025, 12, 28), d(2026, 1, 3)) == (
        "28 de Diciembre de 2025 al 3 de Enero de 2026"
    )


def test_a_ranking_keeps_the_order_and_uses_one_color_for_every_bar():
    from spotify_app import figures

    top = pd.DataFrame({"artist_name": ["B", "A", "C"], "plays": [9, 5, 1]})
    fig = figures.ranking_figure(top, "plays", "artist_name", "#7C5CFC", 300)
    assert list(fig.layout.yaxis.categoryarray) == ["B", "A", "C"]
    assert len(fig.data) == 1 and fig.data[0].marker.color == "#7C5CFC"
    assert fig.layout.height == 300
