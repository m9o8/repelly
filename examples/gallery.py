# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Write repelly example charts to ./gallery_output as HTML files."""

from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from repelly import add_label_repel, add_text_repel


def volcano() -> go.Figure:
    """Differential expression: label the significant genes, most extreme first."""
    rng = np.random.default_rng(3)
    n = 1500
    effect = rng.normal(0, 1.1, n)
    significance = np.abs(effect) ** 1.6 * rng.uniform(0.4, 1.6, n)
    genes = [f"GENE{i}" for i in range(n)]
    hit = (np.abs(effect) > 2.2) & (significance > 3)

    fig = go.Figure(
        go.Scatter(
            x=effect,
            y=significance,
            mode="markers",
            marker={"size": 5, "color": np.where(hit, "#c0392b", "#bdc3c7")},
        )
    )
    fig.update_layout(
        title="Volcano plot",
        xaxis_title="log2 fold change",
        yaxis_title="-log10 p",
        template="simple_white",
    )
    return add_text_repel(
        fig,
        effect[hit],
        significance[hit],
        np.array(genes)[hit],
        priority=np.abs(effect[hit]),
        font={"size": 11},
    )


def cars() -> go.Figure:
    """Boxed labels on a small scatter plot."""
    frame = pd.DataFrame(
        {
            "weight": [
                2.62,
                2.875,
                2.32,
                3.215,
                3.44,
                3.46,
                3.57,
                3.19,
                3.15,
                3.44,
                3.44,
                4.07,
            ],
            "mpg": [21, 21, 22.8, 21.4, 18.7, 18.1, 14.3, 24.4, 22.8, 19.2, 17.8, 16.4],
            "name": [
                "Mazda RX4",
                "Mazda Wag",
                "Datsun 710",
                "Hornet 4",
                "Hornet Sport",
                "Valiant",
                "Duster 360",
                "Merc 240D",
                "Merc 230",
                "Merc 280",
                "Merc 280C",
                "Merc 450SE",
            ],
        }
    )
    fig = px.scatter(
        frame, x="weight", y="mpg", template="simple_white", title="Boxed labels"
    )
    fig.update_traces(marker_size=9)
    return add_label_repel(fig, frame.weight, frame.mpg, frame.name, max_overlaps=None)


def facets() -> go.Figure:
    """Faceted plotly.express figure, labelled from its traces."""
    frame = px.data.gapminder().query(
        "year == 2007 and continent in ['Europe', 'Asia']"
    )
    fig = px.scatter(
        frame,
        x="gdpPercap",
        y="lifeExp",
        facet_col="continent",
        log_x=True,
        hover_name="country",
        template="simple_white",
        title="Facets on a log axis",
    )
    return add_text_repel(fig, font={"size": 9}, max_labels=25)


def animation() -> go.Figure:
    """Animated figure: every frame gets its own labels."""
    frame = px.data.gapminder().query(
        "continent == 'Oceania' or country in ['Japan', 'Chile', 'Kenya']"
    )
    fig = px.scatter(
        frame,
        x="gdpPercap",
        y="lifeExp",
        animation_frame="year",
        hover_name="country",
        log_x=True,
        range_x=[1000, 60000],
        range_y=[40, 90],
        template="simple_white",
        title="Animation",
    )
    return add_text_repel(fig, on=("render", "frame"))


SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK = "#52514e"
MUTED = "#c9c8c2"


def style(fig, title, subtitle, **layout):
    fig.update_layout(
        title={"text": title, "subtitle": {"text": subtitle}},
        template="simple_white",
        paper_bgcolor="#fcfcfb",
        plot_bgcolor="#fcfcfb",
        margin={"t": 90},
        **layout,
    )
    return fig


def color_by_group():
    frame = px.data.gapminder().query(
        "year == 2007 and continent in ['Asia', 'Europe', 'Americas']"
    )
    fig = px.scatter(
        frame,
        x="gdpPercap",
        y="lifeExp",
        color="continent",
        color_discrete_sequence=SERIES,
        hover_name="country",
        log_x=True,
        labels={
            "gdpPercap": "GDP per capita (US$)",
            "lifeExp": "Life expectancy (years)",
        },
    )
    fig.update_traces(marker_size=9)
    style(
        fig,
        "Each label takes the colour of its group",
        'color="trace" on a plotly.express colour grouping',
    )
    return add_text_repel(
        fig,
        color="trace",
        priority=lambda trace: np.log(
            frame.loc[frame.country.isin(trace.hovertext), "pop"]
        ),
        max_labels=45,
        font={"size": 10},
    )


def bold_text():
    rng = np.random.default_rng(5)
    n = 22
    x = rng.normal(0, 1, n)
    y = rng.normal(0, 1, n)
    names = [
        f"<b>Sample {i}</b>" if i % 3 == 0 else f"Sample {i}<sup>{i % 4 + 1}</sup>"
        for i in range(n)
    ]
    fig = go.Figure(
        go.Scatter(x=x, y=y, mode="markers", marker={"size": 9, "color": SERIES[0]})
    )
    style(
        fig,
        "Bold and superscript labels no longer collide",
        "Widths now follow &lt;b&gt;, &lt;i&gt;, &lt;sup&gt; and font weight",
        xaxis_title="Component 1",
        yaxis_title="Component 2",
    )
    return add_text_repel(fig, x, y, names, max_overlaps=None, font={"size": 14})


def line_end_labels():
    rng = np.random.default_rng(12)
    dates = pd.date_range("2024-01-01", periods=60, freq="W")
    names = ["North", "South", "East", "West", "Central"]
    fig = go.Figure()
    ends = []
    for name, color, drift in zip(
        names, SERIES, [0.42, 0.40, 0.38, 0.37, 0.35], strict=True
    ):
        values = 100 + np.cumsum(rng.normal(drift, 1.1, len(dates)))
        fig.add_scatter(
            x=dates,
            y=values,
            mode="lines",
            name=name,
            line={"color": color, "width": 2},
        )
        ends.append(values[-1])
    limit = dates[-1] + pd.Timedelta(days=6)
    fig.update_xaxes(range=[dates[0], dates[-1] + pd.Timedelta(days=90)])
    style(
        fig,
        "Line-end labels held in a right-hand gutter",
        "nudge_x sets the offset, xlim sets the gutter, direction='y' stacks them",
        yaxis_title="Index (simulated)",
    )
    return add_text_repel(
        fig,
        [dates[-1]] * len(names),
        ends,
        [f"{name} {end:.0f}" for name, end in zip(names, ends, strict=True)],
        nudge_x=70,
        direction="y",
        xlim=(limit, None),
        max_overlaps=None,
        min_segment_length=0,
        font={"size": 12},
    )


def direction_per_label():
    bottom_x = np.linspace(0.8, 3.2, 12) + 2
    left_y = np.linspace(0.8, 3.2, 12) + 2
    x = np.concatenate([bottom_x, np.full(12, 1.0)])
    y = np.concatenate([np.full(12, 1.0), left_y])
    names = [f"bottom-{i}" for i in range(12)] + [f"left-{i}" for i in range(12)]
    directions = ["y"] * 12 + ["x"] * 12
    fig = go.Figure(
        go.Scatter(x=x, y=y, mode="markers", marker={"size": 9, "color": SERIES[0]})
    )
    fig.update_xaxes(range=[-1.2, 6])
    fig.update_yaxes(range=[-1, 6])
    style(
        fig,
        "Each label can have its own direction",
        "Bottom row moves only vertically, left column only horizontally",
        xaxis_title="x",
        yaxis_title="y",
    )
    return add_label_repel(
        fig, x, y, names, direction=directions, max_overlaps=None, font={"size": 11}
    )


def calls_with_their_own_settings():
    rng = np.random.default_rng(3)
    n = 1500
    effect = rng.normal(0, 1.1, n)
    significance = np.abs(effect) ** 1.6 * rng.uniform(0.4, 1.6, n)
    genes = np.array([f"GENE{i}" for i in range(n)])
    left = (effect < -2.2) & (significance > 3)
    right = (effect > 2.2) & (significance > 3)
    colors = np.where(left, SERIES[0], np.where(right, SERIES[1], MUTED))
    fig = go.Figure(
        go.Scatter(
            x=effect,
            y=significance,
            mode="markers",
            marker={"size": 5, "color": colors},
        )
    )
    fig.update_xaxes(range=[-6, 6])
    style(
        fig,
        "Two calls, one chart, separate settings",
        "Left: top 8 labels kept left of -3.  Right: every label, kept right of 3",
        xaxis_title="log2 fold change",
        yaxis_title="-log10 p",
    )
    fig = add_text_repel(
        fig,
        effect[left],
        significance[left],
        genes[left],
        priority=-effect[left],
        max_labels=8,
        xlim=(None, -3),
        font={"size": 11},
    )
    return add_text_repel(
        fig,
        effect[right],
        significance[right],
        genes[right],
        xlim=(3, None),
        max_overlaps=None,
        font={"size": 11},
    )


def dense_first_render():
    rng = np.random.default_rng(9)
    n = 150
    centres = np.array([[-2.2, -1.0], [0.4, 1.2], [2.4, -0.6]])
    groups = np.arange(n) % 3
    x = centres[groups, 0] + rng.normal(0, 0.75, n)
    y = centres[groups, 1] + rng.normal(0, 0.55, n)
    fig = go.Figure(
        go.Scatter(x=x, y=y, mode="markers", marker={"size": 6, "color": SERIES[0]})
    )
    fig.update_layout(height=720)
    style(
        fig,
        "150 labels, separated on first render",
        "A longer first solve, with crossing connectors untangled along the way",
        xaxis_title="x",
        yaxis_title="y",
    )
    return add_text_repel(
        fig, x, y, [f"item {i}" for i in range(n)], max_overlaps=None, font={"size": 10}
    )


def hidden_label_warning():
    rng = np.random.default_rng(2)
    n = 40
    x = rng.normal(0, 0.08, n)
    y = rng.normal(0, 0.08, n)
    fig = go.Figure(
        go.Scatter(x=x, y=y, mode="markers", marker={"size": 9, "color": SERIES[0]})
    )
    fig.update_xaxes(range=[-1, 1])
    fig.update_yaxes(range=[-1, 1])
    style(
        fig,
        "Hidden labels are now reported",
        "max_overlaps=3 hides most of these. Open the browser console (F12) to see the warning",
        xaxis_title="x",
        yaxis_title="y",
    )
    return add_text_repel(fig, x, y, [f"point {i}" for i in range(n)], max_overlaps=3)


ORIGINAL_CHARTS = {
    "volcano": (volcano, "Volcano plot of a simulated experiment."),
    "cars": (cars, "Boxed labels on a small scatter plot."),
    "facets": (facets, "plotly.express facets on a log axis."),
    "animation": (animation, "Animated figure with labels per frame."),
}

FEATURE_CHARTS = {
    "new_dense_first_render": (
        dense_first_render,
        "150 labels separated on first render, with crossings untangled.",
    ),
    "new_bold_text": (
        bold_text,
        "Bold and superscript text measured at its real width.",
    ),
    "new_color_by_group": (
        color_by_group,
        'Labels matching their group with color="trace".',
    ),
    "new_direction_per_label": (
        direction_per_label,
        "A different movement direction per label, on boxed labels.",
    ),
    "new_line_end_labels": (
        line_end_labels,
        "Line-end labels using nudge_x, xlim and direction on a date axis.",
    ),
    "new_calls_with_own_settings": (
        calls_with_their_own_settings,
        "Two calls in one chart, each with its own max_labels and xlim.",
    ),
    "new_hidden_label_warning": (
        hidden_label_warning,
        "Open the browser console (F12) to see the hidden-label warning.",
    ),
}


def index_page() -> str:
    def rows(charts: dict) -> str:
        return "".join(
            f'<li><a href="{name}.html">{name}</a><span>{html.escape(text)}</span></li>'
            for name, (_, text) in charts.items()
        )

    return f"""<!doctype html>
<meta charset="utf-8">
<title>repelly gallery</title>
<style>
:root {{ --bg:#fcfcfb; --ink:#0b0b0b; --muted:#52514e; --link:#2a78d6; --line:#e4e3de; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#1a1a19; --ink:#f0efec; --muted:#c3c2b7; --link:#3987e5; --line:#383835; }}
}}
body {{ background:var(--bg); color:var(--ink); font:16px/1.5 system-ui,sans-serif;
       max-width:760px; margin:40px auto; padding:0 16px; }}
h1 {{ font-size:26px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:32px 0 8px; }}
p {{ color:var(--muted); margin:0; }} ul {{ list-style:none; padding:0; margin:0; }}
li {{ display:flex; flex-wrap:wrap; gap:2px 16px; padding:10px 0;
     border-bottom:1px solid var(--line); }}
a {{ color:var(--link); font-weight:600; min-width:250px; }}
span {{ color:var(--muted); flex:1 1 280px; }}
</style>
<h1>repelly gallery</h1>
<p>Every chart shares the local plotly.min.js, so the gallery works offline.</p>
<h2>Features</h2><ul>{rows(FEATURE_CHARTS)}</ul>
<h2>Original examples</h2><ul>{rows(ORIGINAL_CHARTS)}</ul>
"""


def main() -> None:
    output = Path("gallery_output")
    output.mkdir(exist_ok=True)
    for name, (build, _) in {**ORIGINAL_CHARTS, **FEATURE_CHARTS}.items():
        path = output / f"{name}.html"
        build().write_html(path, include_plotlyjs="directory")
        print(f"wrote {path}")
    (output / "index.html").write_text(index_page(), encoding="utf-8")
    print(f"wrote {output / 'index.html'}")


if __name__ == "__main__":
    main()
