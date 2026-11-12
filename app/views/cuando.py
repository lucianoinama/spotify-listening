import pandas as pd
import plotly.express as px
import streamlit as st

from spotify_app import data
from spotify_app.ui import DAY_NAMES, HEAT_SCALE, HOURS, fmt, get_range

start, end = get_range()

st.title("Cuándo escucho")
st.caption("Horas y días según tu zona horaria local.")

heat = data.heatmap(start, end)
if heat.empty:
    st.info("No hay reproducciones en este período.")
    st.stop()

grid = (
    heat.pivot_table(index="dow", columns="hour", values="hours", aggfunc="sum")
    .reindex(index=range(1, 8), columns=range(24))
    .fillna(0.0)
)
by_hour = heat.groupby("hour")["hours"].sum().reindex(range(24), fill_value=0.0)
by_day = heat.groupby("dow")["hours"].sum().reindex(range(1, 8), fill_value=0.0)

peak_hour = int(by_hour.idxmax())
peak_day = DAY_NAMES[int(by_day.idxmax()) - 1]

split = data.weekday_split(start, end).set_index("is_weekend")


def per_day(is_weekend: bool) -> str:
    if is_weekend not in split.index or split.loc[is_weekend, "days"] == 0:
        return "—"
    return f"{fmt(split.loc[is_weekend, 'hours'] / split.loc[is_weekend, 'days'], 1)} h"


columns = st.columns(4)
columns[0].metric("Hora pico", f"{peak_hour:02d}:00")
columns[1].metric("Día pico", peak_day)
columns[2].metric("Entre semana", per_day(False))
columns[3].metric("Fin de semana", per_day(True))
st.caption("Entre semana y fin de semana: promedio de horas por día con música.")

st.subheader("Mapa de calor: día y hora")
fig = px.imshow(
    grid.values,
    x=[f"{h:02d}" for h in range(24)],
    y=DAY_NAMES,
    color_continuous_scale=HEAT_SCALE,
    aspect="auto",
    labels=dict(x="Hora", y="", color="Horas"),
)
fig.update_layout(margin=dict(t=10, b=10))
st.plotly_chart(fig, width="stretch", key="heatmap")
st.caption("Mostrá el cursor sobre una celda para ver las horas estimadas.")

left, right = st.columns([2, 1])

with left:
    st.subheader("Horas por hora del día")
    hours = pd.DataFrame({"hora": [f"{h:02d}" for h in range(24)], "horas": by_hour.values})
    fig = px.bar(hours, x="hora", y="horas", color_discrete_sequence=[HOURS])
    fig.update_xaxes(type="category", title=None)
    fig.update_layout(yaxis_title="Horas", margin=dict(t=10, b=10))
    st.plotly_chart(fig, width="stretch", key="by_hour")

with right:
    st.subheader("Franja del día")
    parts = {
        "Madrugada (0-5)": by_hour.iloc[0:6].sum(),
        "Mañana (6-11)": by_hour.iloc[6:12].sum(),
        "Tarde (12-17)": by_hour.iloc[12:18].sum(),
        "Noche (18-23)": by_hour.iloc[18:24].sum(),
    }
    day_part = pd.DataFrame({"franja": list(parts), "horas": list(parts.values())})
    fig = px.bar(day_part, x="franja", y="horas", color_discrete_sequence=[HOURS])
    fig.update_xaxes(title=None, type="category")
    fig.update_layout(yaxis_title="Horas", margin=dict(t=10, b=10))
    st.plotly_chart(fig, width="stretch", key="day_part")
