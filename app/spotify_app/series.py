"""Time series shaping for the dashboard charts."""

from datetime import date

import pandas as pd

MONTHS = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


def describe_period(start: date, end: date) -> str:
    """'4 al 7 de Noviembre de 2026', the way the chat writes periods."""
    if start == end:
        return f"{start.day} de {MONTHS[start.month - 1]} de {start.year}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day} al {end.day} de {MONTHS[end.month - 1]} de {end.year}"
    if start.year == end.year:
        return (
            f"{start.day} de {MONTHS[start.month - 1]} al "
            f"{end.day} de {MONTHS[end.month - 1]} de {end.year}"
        )
    return (
        f"{start.day} de {MONTHS[start.month - 1]} de {start.year} al "
        f"{end.day} de {MONTHS[end.month - 1]} de {end.year}"
    )


def hours_by_month(daily: pd.DataFrame) -> pd.DataFrame:
    """Daily hours (columns play_date, hours) to one row per month, every month in between.

    Columns: month (first day, a Timestamp), hours, year (text) and label ("Mayo 2024").
    A month with no plays at all is kept with 0 hours, so gaps in the history show as gaps.
    """
    if daily.empty:
        return pd.DataFrame(columns=["month", "hours", "year", "label"])
    month = pd.to_datetime(daily["play_date"]).dt.to_period("M").dt.to_timestamp()
    totals = daily.assign(month=month).groupby("month")["hours"].sum()
    full = pd.date_range(totals.index.min(), totals.index.max(), freq="MS")
    out = totals.reindex(full, fill_value=0.0).rename_axis("month").reset_index()
    out["hours"] = out["hours"].astype(float)
    out["year"] = out["month"].dt.year.astype(str)
    out["label"] = out["month"].map(lambda d: f"{MONTHS[d.month - 1]} {d.year}")
    return out
