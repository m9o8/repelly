# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""End-to-end tests: real figures, real Plotly, real label geometry in Chrome."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pytest
from plotly.subplots import make_subplots

from repelly import add_label_repel, add_text_repel, bake

pytestmark = pytest.mark.browser

GD = "document.querySelector('.js-plotly-plot')"

COUNT_OURS = f"""() => ({GD}.layout.annotations || [])
  .filter(a => (a.name || '').startsWith('repelly-')).length"""

SETTLED = f"""() => {{
  const gd = {GD};
  return gd && gd.__repelly && !gd.__repelly.applying && !gd.__repelly.timer && !!gd.__repelly.parts;
}}"""

BOXES = """() => Array.from(document.querySelectorAll('.annotation'))
  .filter(el => el.querySelector('.annotation-text'))
  .map(el => {
    const r = el.querySelector('.bg').getBoundingClientRect();
    return {left: r.left, right: r.right, top: r.top, bottom: r.bottom,
            text: el.querySelector('.annotation-text').textContent};
  })"""


def render(page, fig, tmp_path, **kwargs):
    target = tmp_path / "plot.html"
    fig.write_html(target, include_plotlyjs=True, **kwargs)
    page.goto(target.as_uri())
    wait_settled(page)


def wait_settled(page):
    page.wait_for_function(SETTLED, timeout=15000)
    page.wait_for_timeout(250)
    page.wait_for_function(SETTLED, timeout=15000)


def overlaps(boxes):
    pairs = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            if (
                a["left"] < b["right"] - 0.5
                and b["left"] < a["right"] - 0.5
                and a["top"] < b["bottom"] - 0.5
                and b["top"] < a["bottom"] - 0.5
            ):
                pairs.append((a["text"], b["text"]))
    return pairs


def dense_figure(n=30):
    xs = [1 + 0.02 * (i % 6) for i in range(n)]
    ys = [1 + 0.03 * (i // 6) for i in range(n)]
    names = [f"label-{i}" for i in range(n)]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="markers"))
    return fig, xs, ys, names


def ours(page):
    return page.evaluate(
        f"() => {GD}.layout.annotations.filter(a => (a.name||'').startsWith('repelly-'))"
    )


def test_labels_render_without_overlap(page, tmp_path):
    fig, xs, ys, names = dense_figure()
    render(page, add_text_repel(fig, xs, ys, names, max_overlaps=None), tmp_path)
    boxes = page.evaluate(BOXES)
    assert len(boxes) == len(names)
    assert overlaps(boxes) == []
    assert page.console_errors == []


def test_measured_box_matches_solver_position(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], mode="markers"))
    result = add_text_repel(fig, [1], [1], ["hello world"])
    render(page, result, tmp_path)
    data = page.evaluate(f"""() => {{
      const gd = {GD};
      const a = gd.layout.annotations[0];
      const xa = gd._fullLayout.xaxis, ya = gd._fullLayout.yaxis;
      const plot = gd.getBoundingClientRect();
      return {{ expectX: plot.left + xa._offset + xa.d2p(1) + a.ax,
                expectY: plot.top + ya._offset + ya.d2p(1) + a.ay }};
    }}""")
    box = page.evaluate(BOXES)[0]
    assert (box["left"] + box["right"]) / 2 == pytest.approx(data["expectX"], abs=1.5)
    assert (box["top"] + box["bottom"]) / 2 == pytest.approx(data["expectY"], abs=1.5)


def test_label_box_style_applies(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], mode="markers"))
    result = add_label_repel(
        fig, [1], [1], ["boxed"], label={"bgcolor": "rgb(255, 0, 0)"}
    )
    render(page, result, tmp_path)
    assert ours(page)[0]["bgcolor"] == "rgb(255, 0, 0)"


def test_settles_without_relayout_loop(page, tmp_path):
    fig, xs, ys, names = dense_figure()
    render(page, add_text_repel(fig, xs, ys, names), tmp_path)
    page.evaluate(
        f"() => {{ window.__n = 0; {GD}.on('plotly_relayout', () => window.__n++); }}"
    )
    page.wait_for_timeout(800)
    assert page.evaluate("() => window.__n") == 0


def test_user_annotations_preserved(page, tmp_path):
    fig, xs, ys, names = dense_figure(5)
    fig.add_annotation(x=1, y=1, text="user note", showarrow=False)
    render(page, add_text_repel(fig, xs, ys, names), tmp_path)
    texts = page.evaluate(f"() => {GD}.layout.annotations.map(a => a.text)")
    assert "user note" in texts
    assert len(texts) == 6


def test_zoom_resolves_and_hides_points_out_of_view(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    render(page, add_text_repel(fig, [1, 2, 3], [1, 2, 3], list("abc")), tmp_path)
    assert page.evaluate(COUNT_OURS) == 3
    page.evaluate(
        f"() => Plotly.relayout({GD}, {{'xaxis.range': [0.5, 1.5], 'yaxis.range': [0.5, 1.5]}})"
    )
    page.wait_for_function(f"{COUNT_OURS} === 1")
    wait_settled(page)
    assert ours(page)[0]["text"] == "a"


def test_on_render_only_does_not_resolve_on_zoom(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    render(
        page,
        add_text_repel(fig, [1, 2, 3], [1, 2, 3], list("abc"), on="render"),
        tmp_path,
    )
    page.evaluate(f"() => Plotly.relayout({GD}, {{'xaxis.range': [0.5, 1.5]}})")
    page.wait_for_timeout(500)
    assert page.evaluate(COUNT_OURS) == 3


def test_resize_resolves(page, tmp_path):
    fig, xs, ys, names = dense_figure(12)
    render(page, add_text_repel(fig, xs, ys, names, max_overlaps=None), tmp_path)
    page.set_viewport_size({"width": 500, "height": 400})
    page.wait_for_timeout(600)
    wait_settled(page)
    assert overlaps(page.evaluate(BOXES)) == []


def test_autorange_axes_are_pinned_and_reset_works(page, tmp_path):
    fig, xs, ys, names = dense_figure(10)
    render(page, add_text_repel(fig, xs, ys, names), tmp_path)
    initial = page.evaluate(f"() => {GD}._fullLayout.xaxis.range.slice()")
    assert page.evaluate(f"() => {GD}._fullLayout.xaxis.autorange") is False
    page.evaluate(f"() => Plotly.relayout({GD}, {{'xaxis.range': [1.0, 1.02]}})")
    wait_settled(page)
    assert page.evaluate(f"() => {GD}._fullLayout.xaxis.range") == [1.0, 1.02]

    box = page.evaluate(f"""() => {{
      const r = {GD}.querySelector('.nsewdrag').getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2];
    }}""")
    page.mouse.dblclick(box[0], box[1])
    page.wait_for_function(f"() => {GD}._fullLayout.xaxis.range[1] !== 1.02")
    wait_settled(page)
    assert page.evaluate(f"() => {GD}._fullLayout.xaxis.range") == pytest.approx(
        initial, rel=1e-6
    )
    assert page.evaluate(COUNT_OURS) == 10


def test_notebook_iframe_renders_labels(page, tmp_path):
    fig, xs, ys, names = dense_figure(6)
    labelled = add_text_repel(fig, xs, ys, names, max_overlaps=None)
    target = tmp_path / "host.html"
    target.write_text(
        f"<!doctype html><body>{labelled._iframe_html(True, {})}</body>",
        encoding="utf-8",
    )
    page.goto(target.as_uri())
    inner = page.frame_locator("iframe").locator(".annotation-text")
    inner.first.wait_for(timeout=15000)
    page.wait_for_timeout(300)
    assert inner.count() == 6
    assert page.console_errors == []


def test_show_passes_runtime_to_browser_renderer(monkeypatch):
    opened = []
    monkeypatch.setattr(
        "plotly.io._base_renderers.open_html_in_browser",
        lambda html, *args, **kwargs: opened.append(html),
    )
    fig = go.Figure(go.Scatter(x=[1], y=[1], mode="markers"))
    add_text_repel(fig, [1], [1], ["a"]).show(renderer="browser")
    assert len(opened) == 1
    assert "window.repelly.attach" in opened[0]


@pytest.mark.parametrize(
    ("x_values", "layout"),
    [
        ([1, 10, 100], {"xaxis_type": "log"}),
        (["2024-01-01", "2024-02-01", "2024-03-01"], {}),
        (["red", "green", "blue"], {}),
        ([1, 2, 3], {"xaxis_autorange": "reversed"}),
    ],
    ids=["log", "date", "category", "reversed"],
)
def test_axis_types_place_anchor_on_point(page, tmp_path, x_values, layout):
    fig = go.Figure(go.Scatter(x=x_values, y=[1, 2, 3], mode="markers"))
    fig.update_layout(**layout)
    render(page, add_text_repel(fig, x_values, [1, 2, 3], list("abc")), tmp_path)
    assert page.evaluate(COUNT_OURS) == 3
    assert page.evaluate(f"""() => {{
      const gd = {GD};
      const xa = gd._fullLayout.xaxis;
      const heads = Array.from(document.querySelectorAll('.annotation-arrow-g path'));
      const anns = gd._fullLayout.annotations;
      return anns.every((a, i) => {{
        const expected = xa.d2p({x_values!r}[i]) + xa._offset;
        return Math.abs(xa._offset + xa.r2p(a.x) - expected) < 1;
      }});
    }}""")


def test_subplots_solve_each_panel(page, tmp_path):
    fig = make_subplots(rows=1, cols=2)
    fig.add_scatter(x=[1, 2], y=[1, 2], mode="markers", row=1, col=1)
    fig.add_scatter(x=[1, 2], y=[1, 2], mode="markers", row=1, col=2)
    result = add_text_repel(fig, [1, 2], [1, 2], ["L1", "L2"], row=1, col=1)
    result = add_text_repel(result, [1, 2], [1, 2], ["R1", "R2"], row=1, col=2)
    render(page, result, tmp_path)
    data = ours(page)
    assert {a["xref"] for a in data} == {"x", "x2"}
    panels = page.evaluate(f"""() => ['xaxis', 'xaxis2'].map(n => {{
      const a = {GD}._fullLayout[n]; return [a._offset, a._length];
    }})""")
    plot_left = page.evaluate(f"() => {GD}.getBoundingClientRect().left")
    boxes = {b["text"]: b for b in page.evaluate(BOXES)}
    for name, (offset, length) in zip("LR", panels, strict=True):
        for suffix in "12":
            box = boxes[name + suffix]
            assert plot_left + offset - 1 <= box["left"]
            assert box["right"] <= plot_left + offset + length + 1


def test_px_facets(page, tmp_path):
    frame = pd.DataFrame(
        {
            "x": [1, 2, 3, 4],
            "y": [1, 2, 3, 4],
            "g": ["a", "a", "b", "b"],
            "n": list("pqrs"),
        }
    )
    fig = px.scatter(frame, x="x", y="y", facet_col="g", text="n")
    fig.update_traces(mode="markers")
    render(page, add_text_repel(fig), tmp_path)
    assert page.evaluate(COUNT_OURS) == 4


def test_legend_hidden_trace_hides_labels(page, tmp_path):
    fig = go.Figure()
    fig.add_scatter(x=[1, 2], y=[1, 2], text=["a", "b"], mode="markers", name="one")
    fig.add_scatter(x=[3, 4], y=[3, 4], text=["c", "d"], mode="markers", name="two")
    render(page, add_text_repel(fig), tmp_path)
    assert page.evaluate(COUNT_OURS) == 4
    page.evaluate(f"() => Plotly.restyle({GD}, {{visible: 'legendonly'}}, [1])")
    page.wait_for_function(f"{COUNT_OURS} === 2")
    assert sorted(a["text"] for a in ours(page)) == ["a", "b"]


def test_priority_and_max_labels(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    result = add_text_repel(
        fig, [1, 2, 3], [1, 2, 3], list("abc"), priority=[1, 3, 2], max_labels=2
    )
    render(page, result, tmp_path)
    assert sorted(a["text"] for a in ours(page)) == ["b", "c"]


def test_visibility_mask(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    result = add_text_repel(
        fig, [1, 2, 3], [1, 2, 3], list("abc"), visible=[True, False, True]
    )
    render(page, result, tmp_path)
    assert sorted(a["text"] for a in ours(page)) == ["a", "c"]


def test_animation_frames(page, tmp_path):
    frame = pd.DataFrame(
        {
            "x": [1, 2, 1, 2],
            "y": [1, 2, 2, 1],
            "t": ["one", "one", "two", "two"],
            "n": list("pqrs"),
        }
    )
    fig = px.scatter(frame, x="x", y="y", animation_frame="t", text="n")
    fig.update_traces(mode="markers")
    fig.update_xaxes(range=[0, 3])
    fig.update_yaxes(range=[0, 3])
    render(page, add_text_repel(fig), tmp_path, auto_play=False)
    assert sorted(a["text"] for a in ours(page)) == ["p", "q"]
    page.evaluate(
        f"() => Plotly.animate({GD}, ['two'], {{mode: 'immediate', frame: {{duration: 0}}, transition: {{duration: 0}}}})"
    )
    page.wait_for_function(
        f"""() => ({GD}.layout.annotations || []).some(a => a.text === 'r')"""
    )
    wait_settled(page)
    assert sorted(a["text"] for a in ours(page)) == ["r", "s"]
    assert page.console_errors == []


def test_scattergl_points_are_avoided(page, tmp_path):
    fig = go.Figure(
        go.Scattergl(x=[1, 1.01, 1.02], y=[1, 1, 1], mode="markers", marker_size=12)
    )
    render(page, add_text_repel(fig, [1.01], [1], ["gl"]), tmp_path)
    assert page.evaluate(COUNT_OURS) == 1
    assert page.console_errors == []


def test_many_labels_finish_quickly(page, tmp_path):
    n = 400
    xs = [i % 20 for i in range(n)]
    ys = [i // 20 for i in range(n)]
    names = [f"n{i}" for i in range(n)]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="markers"))
    render(page, add_text_repel(fig, xs, ys, names), tmp_path)
    assert page.evaluate(COUNT_OURS) > 0
    assert page.console_errors == []


def test_bake_returns_plain_figure_with_positions(chrome_path):
    fig, xs, ys, names = dense_figure(12)
    baked = bake(
        add_text_repel(fig, xs, ys, names, max_overlaps=None), width=800, height=500
    )
    assert type(baked) is go.Figure
    assert len(baked.layout.annotations) == 12
    assert baked.layout.meta is None
    assert baked.layout.xaxis.range is not None
    assert all(a.axref == "pixel" for a in baked.layout.annotations)


def test_bake_is_deterministic(chrome_path):
    fig, xs, ys, names = dense_figure(12)
    labelled = add_text_repel(fig, xs, ys, names, max_overlaps=None)
    first = bake(labelled, width=800, height=500)
    second = bake(labelled, width=800, height=500)
    assert [(a.ax, a.ay) for a in first.layout.annotations] == [
        (a.ax, a.ay) for a in second.layout.annotations
    ]


def test_write_image_produces_png(chrome_path, tmp_path):
    fig, xs, ys, names = dense_figure(6)
    target = tmp_path / "plot.png"
    add_text_repel(fig, xs, ys, names).write_image(target, width=600, height=400)
    assert target.read_bytes().startswith(b"\x89PNG")


def test_plain_figure_is_returned_by_bake_without_labels(chrome_path):
    fig = go.Figure(go.Scatter(x=[1], y=[1]))
    assert len(bake(fig).layout.annotations) == 0


def test_max_labels_applies_to_each_call(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2, 3, 4], y=[1, 2, 3, 4], mode="markers"))
    result = add_text_repel(fig, [1, 2], [1, 2], ["a", "b"], max_labels=1)
    result = add_text_repel(result, [3, 4], [3, 4], ["c", "d"])
    render(page, result, tmp_path)
    assert sorted(a["text"] for a in ours(page)) == ["a", "c", "d"]


def test_max_overlaps_applies_to_each_call(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], mode="markers"))
    xs, ys = [1.5] * 3, [1.5] * 3
    result = add_text_repel(fig, xs, ys, ["k1", "k2", "k3"], max_overlaps=None)
    result = add_text_repel(result, xs, ys, ["d1", "d2", "d3"], max_overlaps=0)
    render(page, result, tmp_path)
    assert sorted(a["text"] for a in ours(page)) == ["k1", "k2", "k3"]


@pytest.mark.parametrize(
    ("template", "font"),
    [
        ("<b>WWWWWWWW{}</b>", {"size": 16}),
        ("<b>WWWW</b>WWWW{}", {"size": 16}),
        ("WWWWWWWW{}", {"size": 16, "weight": "bold"}),
        ("<i><b>WWWWWWWW{}</b></i>", {"size": 16}),
    ],
    ids=["bold-tag", "partly-bold", "font-weight", "bold-italic"],
)
def test_styled_text_is_measured_for_real(page, tmp_path, template, font):
    xs = [1.0 + 0.002 * i for i in range(5)]
    ys = [1.0] * 5
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    result = add_text_repel(
        fig,
        xs,
        ys,
        [template.format(i) for i in range(5)],
        direction="x",
        box_padding=0,
        avoid_points=False,
        max_overlaps=None,
        font=font,
    )
    render(page, result, tmp_path)
    boxes = page.evaluate(BOXES)
    assert len(boxes) == 5
    assert overlaps(boxes) == []


def test_multiline_and_entities_are_measured(page, tmp_path):
    xs = [1.0 + 0.002 * i for i in range(4)]
    names = [f"<b>first</b><br>A&amp;B WWWW{i}<sup>2</sup>" for i in range(4)]
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    result = add_text_repel(
        fig,
        xs,
        [1.0] * 4,
        names,
        direction="y",
        box_padding=0,
        avoid_points=False,
        max_overlaps=None,
        font={"size": 14},
    )
    render(page, result, tmp_path)
    boxes = page.evaluate(BOXES)
    assert len(boxes) == 4
    assert overlaps(boxes) == []


def test_color_per_label_reaches_the_page(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], mode="markers"))
    result = add_text_repel(
        fig,
        [1, 2],
        [1, 2],
        ["a", "b"],
        color=["rgb(255, 0, 0)", "rgb(0, 0, 255)"],
        font={"size": 15},
    )
    render(page, result, tmp_path)
    fills = page.evaluate("""() => Object.fromEntries(
      Array.from(document.querySelectorAll('.annotation-text')).map(
        el => [el.textContent, el.style.fill]))""")
    assert fills == {"a": "rgb(255, 0, 0)", "b": "rgb(0, 0, 255)"}
    assert {a["font"]["size"] for a in ours(page)} == {15}


def test_color_trace_matches_px_group_colors(page, tmp_path):
    frame = pd.DataFrame(
        {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "g": list("aabb"), "n": list("pqrs")}
    )
    fig = px.scatter(frame, x="x", y="y", color="g", text="n")
    fig.update_traces(mode="markers")
    render(page, add_text_repel(fig, color="trace"), tmp_path)
    colors = {a["text"]: a["font"]["color"] for a in ours(page)}
    assert colors["p"] == colors["q"] != colors["r"] == colors["s"]


def test_color_trace_uses_default_colorway(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], text=["a", "b"], mode="markers"))
    render(page, add_text_repel(fig, color="trace"), tmp_path)
    expected = page.evaluate(f"() => {GD}._fullData[0].marker.color")
    assert {a["font"]["color"] for a in ours(page)} == {expected}


def test_direction_per_label_constrains_each_label(page, tmp_path):
    xs = [1.0, 1.001, 1.002, 1.003]
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    result = add_text_repel(
        fig,
        xs,
        [1.0] * 4,
        list("abcd"),
        direction=["x", "y", "x", "y"],
        max_overlaps=None,
    )
    render(page, result, tmp_path)
    moved = {a["text"]: (a["ax"], a["ay"]) for a in ours(page)}
    assert moved["a"][1] == 0 and moved["c"][1] == 0
    assert moved["b"][0] == 0 and moved["d"][0] == 0


def plot_box(page, xaxis="xaxis", yaxis="yaxis"):
    return page.evaluate(f"""() => {{
      const gd = {GD};
      const rect = gd.getBoundingClientRect();
      const xa = gd._fullLayout.{xaxis}, ya = gd._fullLayout.{yaxis};
      return {{left: rect.left + xa._offset, top: rect.top + ya._offset,
               width: xa._length, height: ya._length}};
    }}""")


def test_nudge_moves_label_right_and_up(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    render(page, add_text_repel(fig, [1], [1], ["a"], nudge_x=90, nudge_y=60), tmp_path)
    annotation = ours(page)[0]
    assert annotation["ax"] == pytest.approx(90, abs=3)
    assert annotation["ay"] == pytest.approx(-60, abs=3)


def test_nudge_differs_per_label_and_labels_still_separate(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    xs = [1.0, 1.001, 1.002, 1.5]
    result = add_text_repel(
        fig, xs, [1.0] * 4, ["aaaa", "bbbb", "cccc", "dddd"], nudge_y=[50, 50, 50, -70]
    )
    render(page, result, tmp_path)
    moved = {a["text"]: a["ay"] for a in ours(page)}
    assert moved["dddd"] == pytest.approx(70, abs=3)
    assert all(moved[name] < 0 for name in ("aaaa", "bbbb", "cccc"))
    assert overlaps(page.evaluate(BOXES)) == []


def test_nudged_label_survives_zoom(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    render(page, add_text_repel(fig, [1], [1], ["a"], nudge_x=90), tmp_path)
    page.evaluate(f"() => Plotly.relayout({GD}, {{'xaxis.range': [0.5, 1.5]}})")
    page.wait_for_timeout(300)
    wait_settled(page)
    assert ours(page)[0]["ax"] == pytest.approx(90, abs=3)


@pytest.mark.parametrize(
    ("xs", "limit", "layout"),
    [
        ([1, 2, 3, 4], (2.5, None), {}),
        ([10, 100, 1000, 10000], (500, None), {"xaxis_type": "log"}),
        (
            ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
            ("2024-02-15", None),
            {},
        ),
        ([1, 2, 3, 4], (2.5, None), {"xaxis_autorange": "reversed"}),
    ],
    ids=["linear", "log", "date", "reversed"],
)
def test_xlim_keeps_labels_on_one_side(page, tmp_path, xs, limit, layout):
    fig = go.Figure(go.Scatter(x=xs, y=[1, 2, 3, 4], mode="markers"))
    fig.update_layout(**layout)
    render(
        page, add_text_repel(fig, xs, [1, 2, 3, 4], list("abcd"), xlim=limit), tmp_path
    )
    boundary = page.evaluate(f"""() => {{
      const gd = {GD};
      const xa = gd._fullLayout.xaxis;
      return gd.getBoundingClientRect().left + xa._offset + xa.d2p({limit[0]!r});
    }}""")
    reversed_axis = bool(layout.get("xaxis_autorange"))
    boxes = page.evaluate(BOXES)
    assert len(boxes) == 4
    for box in boxes:
        if reversed_axis:
            assert box["right"] <= boundary + 1
        else:
            assert box["left"] >= boundary - 1


def test_ylim_upper_bound_is_respected(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    render(
        page,
        add_text_repel(fig, [1, 2, 3], [1, 2, 3], list("abc"), ylim=(None, 1.5)),
        tmp_path,
    )
    boundary = page.evaluate(f"""() => {{
      const gd = {GD};
      const ya = gd._fullLayout.yaxis;
      return gd.getBoundingClientRect().top + ya._offset + ya.d2p(1.5);
    }}""")
    assert all(box["top"] >= boundary - 1 for box in page.evaluate(BOXES))


def test_limit_outside_the_view_does_not_lose_labels(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], mode="markers"))
    result = add_text_repel(fig, [1, 2], [1, 2], ["a", "b"], xlim=(100, 200))
    render(page, result, tmp_path)
    assert page.evaluate(COUNT_OURS) == 2
    assert page.console_errors == []
    box = plot_box(page)
    for label in page.evaluate(BOXES):
        assert label["right"] <= box["left"] + box["width"] + 1


def test_limits_apply_to_each_call_only(page, tmp_path):
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    result = add_text_repel(fig, [1], [1], ["free"])
    result = add_text_repel(result, [2], [2], ["held"], xlim=(2.5, None))
    render(page, result, tmp_path)
    boundary = page.evaluate(f"""() => {{
      const gd = {GD};
      const xa = gd._fullLayout.xaxis;
      return gd.getBoundingClientRect().left + xa._offset + xa.d2p(2.5);
    }}""")
    boxes = {b["text"]: b for b in page.evaluate(BOXES)}
    assert boxes["held"]["left"] >= boundary - 1
    assert boxes["free"]["left"] < boundary


def test_bake_keeps_nudges(chrome_path):
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    labelled = add_text_repel(fig, [1], [1], ["a"], nudge_x=90)
    baked = bake(labelled, width=800, height=500)
    assert baked.layout.annotations[0].ax == pytest.approx(90, abs=3)


CROWDED = {"x": [1.0] * 12, "y": [1.0] * 12, "text": [f"label-{i}" for i in range(12)]}


def collect_warnings(page):
    messages = []
    page.on(
        "console",
        lambda m: messages.append(m.text) if m.type == "warning" else None,
    )
    return messages


def test_dropped_labels_are_reported_in_the_console(page, tmp_path):
    messages = collect_warnings(page)
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    render(page, add_text_repel(fig, **CROWDED, max_overlaps=1), tmp_path)
    assert [m for m in messages if "10 labels hidden" in m and "max_overlaps" in m]


def test_no_warning_when_everything_fits(page, tmp_path):
    messages = collect_warnings(page)
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], mode="markers"))
    render(page, add_text_repel(fig, [1, 2], [1, 2], ["a", "b"]), tmp_path)
    assert not [m for m in messages if "repelly" in m]


def test_repeated_solves_do_not_repeat_the_warning(page, tmp_path):
    messages = collect_warnings(page)
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    render(page, add_text_repel(fig, **CROWDED, max_overlaps=1), tmp_path)
    for upper in (1.9, 1.8, 1.7):
        page.evaluate(f"() => Plotly.relayout({GD}, {{'xaxis.range': [0, {upper}]}})")
        page.wait_for_timeout(250)
        wait_settled(page)
    assert len([m for m in messages if "labels hidden" in m]) == 1


def test_labels_that_cannot_separate_are_reported(page, tmp_path):
    messages = collect_warnings(page)
    n = 60
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    fig.update_layout(width=320, height=260)
    result = add_text_repel(
        fig, [1.0] * n, [1.0] * n, ["a-long-label"] * n, max_overlaps=None
    )
    render(page, result, tmp_path)
    assert [m for m in messages if "labels still overlap" in m]


def test_bake_warns_about_dropped_labels(chrome_path):
    fig = go.Figure(go.Scatter(x=[0, 2], y=[0, 2], mode="markers"))
    labelled = add_text_repel(fig, **CROWDED, max_overlaps=1)
    with pytest.warns(UserWarning, match="hid 10 labels"):
        bake(labelled, width=700, height=500)


def test_bake_is_quiet_when_everything_fits(chrome_path, recwarn):
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], mode="markers"))
    bake(add_text_repel(fig, [1, 2], [1, 2], ["a", "b"]), width=700, height=500)
    assert not [w for w in recwarn if "repelly" in str(w.message)]


RECORD_SOLVER_BUDGETS = """(() => {
  let api;
  window.__budgets = [];
  Object.defineProperty(window, '__repellySolver', {
    configurable: true,
    get() { return api; },
    set(value) {
      const original = value.solve;
      value.solve = function (input) {
        window.__budgets.push(input.options.maxTimeMs);
        return original(input);
      };
      api = value;
    },
  });
})()"""


def budgets(page):
    return page.evaluate("() => window.__budgets")


def test_first_render_gets_the_longer_budget_and_zoom_the_short_one(page, tmp_path):
    page.add_init_script(RECORD_SOLVER_BUDGETS)
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    render(page, add_text_repel(fig, [1, 2, 3], [1, 2, 3], list("abc")), tmp_path)
    assert budgets(page)[0] == 250
    seen = len(budgets(page))
    page.evaluate(f"() => Plotly.relayout({GD}, {{'xaxis.range': [0.8, 2.6]}})")
    page.wait_for_timeout(300)
    wait_settled(page)
    assert len(budgets(page)) > seen
    assert set(budgets(page)[seen:]) == {40}


def test_custom_budgets_are_used(page, tmp_path):
    page.add_init_script(RECORD_SOLVER_BUDGETS)
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="markers"))
    result = add_text_repel(
        fig,
        [1, 2, 3],
        [1, 2, 3],
        list("abc"),
        initial_max_time_ms=123,
        max_time_ms=17,
    )
    render(page, result, tmp_path)
    assert budgets(page)[0] == 123
    seen = len(budgets(page))
    page.evaluate(f"() => Plotly.relayout({GD}, {{'xaxis.range': [0.8, 2.6]}})")
    page.wait_for_timeout(300)
    wait_settled(page)
    assert set(budgets(page)[seen:]) == {17}


def test_animation_frames_keep_the_short_budget(page, tmp_path):
    page.add_init_script(RECORD_SOLVER_BUDGETS)
    frame = pd.DataFrame(
        {
            "x": [1, 2, 1, 2],
            "y": [1, 2, 2, 1],
            "t": ["one", "one", "two", "two"],
            "n": list("pqrs"),
        }
    )
    fig = px.scatter(frame, x="x", y="y", animation_frame="t", text="n")
    fig.update_traces(mode="markers")
    fig.update_xaxes(range=[0, 3])
    fig.update_yaxes(range=[0, 3])
    render(page, add_text_repel(fig), tmp_path, auto_play=False)
    seen = len(budgets(page))
    page.evaluate(
        f"() => Plotly.animate({GD}, ['two'], "
        "{mode: 'immediate', frame: {duration: 0}, transition: {duration: 0}})"
    )
    page.wait_for_function(f"() => {GD}.layout.annotations.some(a => a.text === 'r')")
    wait_settled(page)
    assert budgets(page)[seen:] and set(budgets(page)[seen:]) == {40}


def test_dense_chart_is_fully_separated_on_first_render(page, tmp_path):
    n = 100
    xs = [1 + 0.01 * (i % 10) for i in range(n)]
    ys = [1 + 0.01 * (i // 10) for i in range(n)]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="markers"))
    fig.update_layout(width=1000, height=650)
    result = add_text_repel(
        fig, xs, ys, [f"item-{i}" for i in range(n)], max_overlaps=None
    )
    render(page, result, tmp_path)
    assert overlaps(page.evaluate(BOXES)) == []
