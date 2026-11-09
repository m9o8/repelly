# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Write a few repelly example charts to ./gallery_output as HTML files."""

from __future__ import annotations

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


def main() -> None:
    output = Path("gallery_output")
    output.mkdir(exist_ok=True)
    charts = {
        "volcano": volcano,
        "cars": cars,
        "facets": facets,
        "animation": animation,
    }
    for name, build in charts.items():
        path = output / f"{name}.html"
        build().write_html(path, include_plotlyjs="cdn")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
