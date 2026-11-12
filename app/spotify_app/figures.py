"""Charts shared by more than one dashboard page."""

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from .ui import DECADE, fmt

FIRST_DECADE = 1960
GRID = dict(gridcolor="#EEF0F4", zeroline=False)


def decades_figure(decades: pd.DataFrame, height: int) -> Figure:
    """Vertical bars of plays per release decade, from 1960 to the latest, in order.

    decades has columns decade (1960, 1970, ...) and plays. A decade with no plays in between
    is drawn with 0, so the axis has no holes.
    """
    last = int(decades["decade"].max())
    grid = pd.DataFrame({"decade": range(FIRST_DECADE, last + 10, 10)})
    full = grid.merge(decades, how="left", on="decade").fillna({"plays": 0})
    full["decada"] = full["decade"].astype(int).astype(str) + "s"
    full["plays"] = full["plays"].astype(int)
    fig = px.bar(
        full,
        x="decada",
        y="plays",
        color_discrete_sequence=[DECADE],
        text=[fmt(v) for v in full["plays"]],
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=full["decada"].tolist(),
        tickmode="array",  # every decade, not every other one
        tickvals=full["decada"].tolist(),
        title=None,
    )
    fig.update_yaxes(title="Reproducciones", **GRID)
    fig.update_layout(showlegend=False, height=height, margin=dict(t=30, b=8, l=8, r=8))
    return fig


def ranking_figure(
    frame: pd.DataFrame, value: str, label: str, color: str, height: int | None = None
) -> Figure:
    """Horizontal bars in the order of the frame (biggest on top), all in one color.

    The color says what the bars are (see ui.ARTIST, ui.GENRE), not how big they are: size is
    already the length of the bar.
    """
    fig = px.bar(frame, x=value, y=label, orientation="h", color_discrete_sequence=[color])
    fig.update_yaxes(
        autorange="reversed", categoryorder="array", categoryarray=frame[label].tolist(), title=None
    )
    fig.update_xaxes(title=None, **GRID)
    fig.update_layout(showlegend=False, margin=dict(t=8, b=8, l=8, r=8))
    if height:
        fig.update_layout(height=height)
    return fig
