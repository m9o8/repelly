# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Tests for the Python API and the configuration it stores in the figure."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import pytest
from plotly.subplots import make_subplots

import repelly
from repelly import RepelFigure, add_label_repel, add_text_repel, as_repel_figure


def config(fig):
    return fig.layout.meta["repelly"]


def layer(fig, index=0):
    return config(fig)["layers"][index]


@pytest.fixture
def base():
    return go.Figure(go.Scatter(x=[1, 2, 3], y=[4, 5, 6], mode="markers"))


def test_returns_subclass_and_leaves_input_alone(base):
    result = add_text_repel(base, [1, 2], [3, 4], ["a", "b"])
    assert isinstance(result, RepelFigure)
    assert isinstance(result, go.Figure)
    assert base.layout.meta is None
    assert layer(result)["text"] == ["a", "b"]


def test_config_survives_json_round_trip(base):
    result = add_text_repel(base, [1, 2], [3, 4], ["a", "b"])
    restored = pio.from_json(result.to_json())
    assert config(restored)["layers"][0]["text"] == ["a", "b"]
    assert isinstance(as_repel_figure(restored), RepelFigure)


def test_layers_accumulate(base):
    result = add_text_repel(base, [1], [2], ["a"])
    result = add_label_repel(result, [3], [4], ["b"])
    assert [entry["text"] for entry in config(result)["layers"]] == [["a"], ["b"]]
    assert "label" in layer(result, 1)
    assert "label" not in layer(result, 0)


def test_keeps_existing_meta_dict(base):
    base.update_layout(meta={"owner": "me"})
    result = add_text_repel(base, [1], [2], ["a"])
    assert result.layout.meta["owner"] == "me"


def test_rejects_scalar_meta(base):
    base.update_layout(meta="title text")
    with pytest.raises(ValueError, match="layout.meta"):
        add_text_repel(base, [1], [2], ["a"])


def test_hash_changes_with_content(base):
    first = add_text_repel(base, [1], [2], ["a"])
    second = add_text_repel(base, [1], [2], ["b"])
    assert config(first)["hash"] != config(second)["hash"]


def test_accepts_numpy_and_pandas(base):
    frame = pd.DataFrame({"x": [1.0, 2.0], "y": [3, 4], "name": ["a", "b"]})
    result = add_text_repel(base, frame.x, np.array(frame.y), frame.name)
    json.dumps(config(result))
    assert layer(result)["x"] == [1.0, 2.0]
    assert layer(result)["y"] == [3, 4]


@pytest.mark.parametrize(
    "values",
    [
        pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01"])),
        np.array(["2024-01-01", "2024-02-01"], dtype="datetime64[ns]"),
        [dt.datetime(2024, 1, 1), dt.datetime(2024, 2, 1)],
        [dt.date(2024, 1, 1), dt.date(2024, 2, 1)],
    ],
)
def test_dates_become_iso_strings(base, values):
    result = add_text_repel(base, values, [1, 2], ["a", "b"])
    assert [v[:10] for v in layer(result)["x"]] == ["2024-01-01", "2024-02-01"]


def test_missing_values_are_dropped(base):
    result = add_text_repel(
        base,
        [1.0, float("nan"), 3.0, 4.0],
        [1.0, 2.0, None, 4.0],
        ["a", "b", "c", ""],
    )
    assert layer(result)["text"] == ["a"]


def test_numeric_text_is_formatted(base):
    result = add_text_repel(base, [1, 2], [1, 2], [10, 2.5])
    assert layer(result)["text"] == ["10", "2.5"]


def test_row_col_targets_subplot():
    fig = make_subplots(rows=1, cols=2)
    fig.add_scatter(x=[1], y=[1], row=1, col=2)
    result = add_text_repel(fig, [1], [1], ["a"], row=1, col=2)
    assert (layer(result)["xref"], layer(result)["yref"]) == ("x2", "y2")


def test_secondary_y():
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_scatter(x=[1], y=[1], secondary_y=True)
    result = add_text_repel(fig, [1], [1], ["a"], row=1, col=1, secondary_y=True)
    assert layer(result)["yref"] == "y2"


def test_labels_traces_from_px_facets():
    frame = pd.DataFrame(
        {
            "x": [1, 2, 3, 4],
            "y": [1, 2, 3, 4],
            "g": ["a", "a", "b", "b"],
            "n": list("pqrs"),
        }
    )
    fig = px.scatter(frame, x="x", y="y", facet_col="g", text="n")
    result = add_text_repel(fig)
    assert layer(result)["text"] == list("pqrs")
    assert layer(result)["xref"] == ["x", "x", "x2", "x2"]
    assert layer(result)["trace"] == [0, 0, 1, 1]


def test_trace_mode_text_callable():
    frame = pd.DataFrame({"x": [1, 2], "y": [3, 4], "n": ["p", "q"]})
    fig = px.scatter(frame, x="x", y="y", custom_data=["n"])
    result = add_text_repel(fig, text=lambda trace: trace.customdata[:, 0])
    assert layer(result)["text"] == ["p", "q"]


def test_trace_mode_selector_filters():
    fig = go.Figure()
    fig.add_scatter(x=[1], y=[1], text=["a"], name="one")
    fig.add_scatter(x=[2], y=[2], text=["b"], name="two")
    result = add_text_repel(fig, selector={"name": "two"})
    assert layer(result)["text"] == ["b"]
    assert layer(result)["trace"] == 1


def test_trace_mode_reads_animation_frames():
    frame = pd.DataFrame(
        {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "t": [0, 0, 1, 1], "n": list("pqrs")}
    )
    fig = px.scatter(frame, x="x", y="y", animation_frame="t", text="n")
    result = add_text_repel(fig)
    assert layer(result)["text"] == list("pqrs")
    assert layer(result)["frame"] == ["0", "0", "1", "1"]
    assert config(result)["first_frame"] == "0"


def test_trace_mode_needs_text():
    fig = go.Figure(go.Scatter(x=[1], y=[1]))
    with pytest.raises(ValueError, match="no text"):
        add_text_repel(fig)


def test_trace_mode_rejects_non_cartesian():
    fig = go.Figure(go.Bar(x=[1], y=[1], text=["a"]))
    with pytest.raises(TypeError, match="bar"):
        add_text_repel(fig)


@pytest.mark.parametrize(
    ("args", "kwargs", "error", "message"),
    [
        (([1],), {}, ValueError, "both x and y"),
        (([1], [2]), {}, ValueError, "text is required"),
        (([1, 2], [2], ["a", "b"]), {}, ValueError, "y has 1"),
        (([1], [2], ["a"]), {"priority": [1, 2]}, ValueError, "priority has 2"),
        (([1], [2], ["a"]), {"visible": [True, False]}, ValueError, "visible has 2"),
        (([1], [2], ["a"]), {"direction": "z"}, ValueError, "direction"),
        (([1], [2], ["a"]), {"force": -1}, ValueError, "force"),
        (([1], [2], ["a"]), {"max_iter": 0}, ValueError, "max_iter"),
        (([1], [2], ["a"]), {"max_overlaps": -1}, ValueError, "max_overlaps"),
        (([1], [2], ["a"]), {"on": ["hover"]}, ValueError, "unknown events"),
        (([1], [2], ["a"]), {"segment": {"colour": "red"}}, ValueError, "segment"),
        (([1], [2], ["a"]), {"row": 1}, ValueError, "row and col"),
        (([1], [2], ["a"]), {"selector": {"name": "x"}}, ValueError, "selector"),
        (([1], [2], ""), {}, TypeError, "text must be a sequence"),
        (([None], [None], ["a"]), {}, ValueError, "no labels"),
    ],
)
def test_invalid_arguments(base, args, kwargs, error, message):
    with pytest.raises(error, match=message):
        add_text_repel(base, *args, **kwargs)


def test_rejects_non_figure():
    with pytest.raises(TypeError, match="plotly Figure"):
        add_text_repel({"data": []}, [1], [2], ["a"])


def test_label_style_keys_validated(base):
    with pytest.raises(ValueError, match="label style"):
        add_label_repel(base, [1], [2], ["a"], label={"background": "red"})


def test_to_html_includes_runtime(base):
    page = add_text_repel(base, [1], [2], ["a"]).to_html(include_plotlyjs=False)
    assert "window.repelly.attach" in page
    assert "{plot_id}" not in page


def test_to_html_keeps_user_post_script(base):
    page = add_text_repel(base, [1], [2], ["a"]).to_html(
        include_plotlyjs=False, post_script="console.log('mine')"
    )
    assert "console.log('mine')" in page
    assert "window.repelly.attach" in page


def test_write_html(base, tmp_path: Path):
    target = tmp_path / "plot.html"
    add_text_repel(base, [1], [2], ["a"]).write_html(target, include_plotlyjs=False)
    assert "window.repelly.attach" in target.read_text(encoding="utf-8")


def test_label_text_cannot_close_the_script_tag(base):
    page = add_text_repel(base, [1], [2], ["</script><b>x"]).to_html(
        include_plotlyjs=False
    )
    assert "</script><b>x" not in page


def test_plain_figure_conversion_keeps_labels(base):
    result = add_text_repel(base, [1], [2], ["a"])
    plain = go.Figure(result)
    assert not isinstance(plain, RepelFigure)
    assert "window.repelly.attach" in as_repel_figure(plain).to_html(
        include_plotlyjs=False
    )


def test_mimetype_renderers_use_iframe(base, monkeypatch):
    monkeypatch.setattr(pio.renderers, "default", "vscode")
    bundle = add_text_repel(base, [1], [2], ["a"])._repr_mimebundle_()
    assert "application/vnd.plotly.v1+json" not in bundle
    assert bundle["text/html"].startswith("<iframe srcdoc=")
    assert "window.repelly.attach" in bundle["text/html"]


def test_html_renderers_receive_post_script(base, monkeypatch):
    monkeypatch.setattr(pio.renderers, "default", "notebook_connected")
    bundle = add_text_repel(base, [1], [2], ["a"])._repr_mimebundle_()
    assert "window.repelly.attach" in bundle["text/html"]


def test_exported_html_keeps_license_notice(base):
    page = add_text_repel(base, [1], [2], ["a"]).to_html(include_plotlyjs=False)
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in page
    assert "Copyright (C) 2026 Moritz Peist" in page


def test_runtime_version_matches_package():
    source = (Path(repelly.__file__).parent / "js" / "runtime.js").read_text(
        encoding="utf-8"
    )
    assert f"var VERSION = '{repelly.__version__}'" in source


def test_combined_notebook_renderers_draw_once(base, monkeypatch):
    monkeypatch.setenv("VSCODE_PID", "1")
    monkeypatch.setattr(pio.renderers, "default", "plotly_mimetype+notebook")
    shown = []
    monkeypatch.setattr(pio, "show", lambda *args, **kwargs: shown.append("pio"))
    monkeypatch.setattr(
        "IPython.display.display", lambda *args, **kwargs: shown.append("iframe")
    )
    add_text_repel(base, [1], [2], ["a"]).show()
    assert shown == ["iframe"]


def test_color_per_label_stays_aligned_after_dropping(base):
    result = add_text_repel(
        base, [1, 2, 3], [1, None, 3], ["a", "b", "c"], color=["red", "green", "blue"]
    )
    assert layer(result)["color"] == ["red", "blue"]


def test_scalar_color_and_direction_are_compact(base):
    result = add_text_repel(base, [1, 2], [1, 2], ["a", "b"], color="navy")
    assert layer(result)["color"] == "navy"
    assert layer(result)["solver"]["direction"] == "both"


def test_no_color_is_omitted(base):
    assert "color" not in layer(add_text_repel(base, [1], [2], ["a"]))


def test_direction_per_label(base):
    result = add_text_repel(base, [1, 2], [1, 2], ["a", "b"], direction=["x", "y"])
    assert layer(result)["solver"]["direction"] == ["x", "y"]


def test_trace_color_uses_marker_colors():
    fig = go.Figure()
    fig.add_scatter(x=[1], y=[1], text=["a"], marker_color="red")
    fig.add_scatter(x=[1, 2], y=[1, 2], text=["b", "c"], marker_color=["blue", "green"])
    fig.add_scatter(x=[3], y=[3], text=["d"])
    result = add_text_repel(fig, color="trace")
    assert layer(result)["color"] == ["red", "blue", "green", "trace"]


def test_trace_color_defers_numeric_marker_colors():
    fig = go.Figure(
        go.Scatter(x=[1, 2], y=[1, 2], text=["a", "b"], marker_color=[1, 2])
    )
    assert layer(add_text_repel(fig, color="trace"))["color"] == "trace"


def test_trace_mode_callable_color_and_direction():
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], text=["a", "b"]))
    result = add_text_repel(
        fig,
        color=lambda trace: ["red", "blue"],
        direction=lambda trace: ["x", "both"],
    )
    assert layer(result)["color"] == ["red", "blue"]
    assert layer(result)["solver"]["direction"] == ["x", "both"]


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"direction": "z"}, ValueError, "direction must be"),
        ({"direction": ["x"]}, ValueError, "direction has 1"),
        ({"direction": ["x", "z"]}, ValueError, "direction must be"),
        ({"color": "trace"}, ValueError, "needs labels made from traces"),
        ({"color": ["red"]}, ValueError, "color has 1"),
        ({"color": [1, 2]}, ValueError, "color values must be strings"),
    ],
)
def test_invalid_per_label_style(base, kwargs, error, message):
    with pytest.raises(error, match=message):
        add_text_repel(base, [1, 2], [1, 2], ["a", "b"], **kwargs)


def test_trace_mode_rejects_sequences_for_color():
    fig = go.Figure(go.Scatter(x=[1], y=[1], text=["a"]))
    with pytest.raises(TypeError, match="color must be a function"):
        add_text_repel(fig, color=["red"])


def test_nudges_are_stored_per_label_and_stay_aligned(base):
    result = add_text_repel(
        base, [1, None, 3], [1, 2, 3], ["a", "b", "c"], nudge_x=[10, 20, 30], nudge_y=5
    )
    assert layer(result)["nudge_x"] == [10.0, 30.0]
    assert layer(result)["nudge_y"] == 5.0


def test_zero_nudges_and_open_limits_are_omitted(base):
    result = add_text_repel(base, [1], [2], ["a"], xlim=(None, None))
    assert not {"nudge_x", "nudge_y", "xlim", "ylim"} & set(layer(result))


def test_limits_accept_dates_and_open_sides(base):
    result = add_text_repel(
        base, [1], [2], ["a"], xlim=(dt.date(2024, 1, 1), None), ylim=[0, 5]
    )
    assert layer(result)["xlim"] == ["2024-01-01", None]
    assert layer(result)["ylim"] == [0, 5]


def test_trace_mode_callable_nudge():
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], text=["a", "b"]))
    result = add_text_repel(fig, nudge_y=lambda trace: [5, 10], nudge_x=3)
    assert layer(result)["nudge_y"] == [5.0, 10.0]
    assert layer(result)["nudge_x"] == 3.0


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"nudge_x": [1]}, ValueError, "nudge_x has 1"),
        ({"nudge_y": ["a", "b"]}, ValueError, "nudge_y values must be numbers"),
        ({"nudge_x": "a"}, TypeError, "nudge_x must be a sequence"),
        ({"xlim": (1, 2, 3)}, ValueError, "xlim must have two"),
        ({"ylim": 5}, TypeError, "ylim must be a sequence"),
    ],
)
def test_invalid_nudges_and_limits(base, kwargs, error, message):
    with pytest.raises(error, match=message):
        add_text_repel(base, [1, 2], [1, 2], ["a", "b"], **kwargs)


def test_initial_time_budget_is_stored_and_validated(base):
    assert (
        layer(add_text_repel(base, [1], [2], ["a"]))["solver"]["initial_max_time_ms"]
        == 250.0
    )
    custom = add_text_repel(base, [1], [2], ["a"], initial_max_time_ms=90)
    assert layer(custom)["solver"]["initial_max_time_ms"] == 90
    with pytest.raises(ValueError, match="initial_max_time_ms"):
        add_text_repel(base, [1], [2], ["a"], initial_max_time_ms=-1)


@pytest.fixture
def outside_vscode(monkeypatch):
    for name in [name for name in os.environ if name.startswith("VSCODE_")]:
        monkeypatch.delenv(name)


def capture_display(monkeypatch):
    shown = []
    monkeypatch.setattr(
        "IPython.display.display", lambda data, **kwargs: shown.append(data)
    )
    return shown


@pytest.mark.parametrize(
    "renderer", ["plotly_mimetype", "jupyterlab", "plotly_mimetype+notebook"]
)
def test_jupyterlab_uses_native_plotly_and_a_script(
    base, monkeypatch, outside_vscode, renderer
):
    monkeypatch.setattr(pio.renderers, "default", renderer)
    monkeypatch.setattr(pio, "show", lambda *a, **k: pytest.fail("HTML renderer ran"))
    shown = capture_display(monkeypatch)
    add_text_repel(base, [1], [2], ["a"]).show()
    assert len(shown) == 2
    assert "application/vnd.plotly.v1+json" in shown[0]
    script = shown[1]["text/html"]
    assert script.startswith("<script>") and "autoAttach" in script
    assert "iframe" not in script[:20]
    assert len(script) < 100_000


def test_native_output_needs_no_plotly_copy(base, monkeypatch, outside_vscode):
    monkeypatch.setattr(pio.renderers, "default", "plotly_mimetype")
    shown = capture_display(monkeypatch)
    add_text_repel(base, [1], [2], ["a"]).show()
    assert "cdn.plot.ly" not in shown[1]["text/html"]


def test_native_script_keeps_license_notice(base, monkeypatch, outside_vscode):
    monkeypatch.setattr(pio.renderers, "default", "plotly_mimetype")
    shown = capture_display(monkeypatch)
    add_text_repel(base, [1], [2], ["a"]).show()
    assert "GPL-3.0-or-later" in shown[1]["text/html"]


@pytest.mark.parametrize("renderer", ["vscode", "nteract"])
def test_other_frontends_keep_the_iframe(base, monkeypatch, outside_vscode, renderer):
    monkeypatch.setattr(pio.renderers, "default", renderer)
    shown = capture_display(monkeypatch)
    add_text_repel(base, [1], [2], ["a"]).show()
    assert len(shown) == 1
    assert shown[0]["text/html"].startswith("<iframe srcdoc=")


def test_vscode_keeps_the_iframe_even_with_the_generic_renderer(base, monkeypatch):
    monkeypatch.setenv("VSCODE_PID", "1")
    monkeypatch.setattr(pio.renderers, "default", "plotly_mimetype")
    shown = capture_display(monkeypatch)
    add_text_repel(base, [1], [2], ["a"]).show()
    assert len(shown) == 1
    assert shown[0]["text/html"].startswith("<iframe srcdoc=")
    assert "cdn.plot.ly" in shown[0]["text/html"]


def test_vscode_can_still_embed_on_request(base, monkeypatch):
    monkeypatch.setenv("VSCODE_PID", "1")
    monkeypatch.setattr(pio.renderers, "default", "vscode")
    shown = capture_display(monkeypatch)
    add_text_repel(base, [1], [2], ["a"]).show(include_plotlyjs=False)
    assert "cdn.plot.ly" not in shown[0]["text/html"]
