"""Turns a query result and a small chart spec from the chat model into a Plotly figure."""

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from .labels import label_map

GREEN = "#1DB954"
KINDS = ["bar", "barh", "line", "pie", "scatter", "heatmap"]


def _require(df: pd.DataFrame, **columns: str | None) -> None:
    missing = [name for name in columns.values() if name and name not in df.columns]
    if missing:
        raise ValueError(
            f"Unknown column(s) {missing}. The last query returned: {list(df.columns)}"
        )


def build_figure(df: pd.DataFrame, spec: dict) -> Figure:
    """Raises ValueError with a message the model can act on."""
    kind = spec.get("kind")
    x, y, z = spec.get("x"), spec.get("y"), spec.get("z")
    color, title = spec.get("color"), spec.get("title")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if df.empty:
        raise ValueError("The last query returned no rows, there is nothing to draw.")
    if not x or not y:
        raise ValueError("x and y are required.")
    _require(df, x=x, y=y, z=z, color=color)

    names = label_map(df.columns)
    common = dict(title=title, color=color, color_discrete_sequence=[GREEN], labels=names)
    if kind == "bar":
        fig = px.bar(df, x=x, y=y, **common)
    elif kind == "barh":
        fig = px.bar(df, x=y, y=x, orientation="h", **common)
        fig.update_yaxes(autorange="reversed")
    elif kind == "line":
        fig = px.line(df, x=x, y=y, markers=True, **common)
    elif kind == "scatter":
        fig = px.scatter(df, x=x, y=y, **common)
    elif kind == "pie":
        fig = px.pie(df, names=x, values=y, title=title, hole=0.5, labels=names)
    else:
        if not z:
            raise ValueError("A heatmap needs z (the value that sets the color).")
        grid = df.pivot_table(index=y, columns=x, values=z, aggfunc="sum").fillna(0)
        fig = px.imshow(
            grid,
            aspect="auto",
            title=title,
            color_continuous_scale=["#161616", GREEN],
            labels=dict(x=names[x], y=names[y], color=names[z]),
        )
    fig.update_layout(margin=dict(t=50 if title else 10, b=10))
    return fig
