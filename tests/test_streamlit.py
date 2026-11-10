# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""End-to-end Streamlit tests: a live ``streamlit run`` driven by Chrome."""

from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
import time
import urllib.request

import pytest

pytest.importorskip("streamlit")

pytestmark = pytest.mark.browser

PREAMBLE = """
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import repelly.streamlit
from repelly import add_label_repel, add_text_repel

repelly.streamlit.init()


def labelled(names, **kwargs):
    points = list(range(1, len(names) + 1))
    fig = go.Figure(go.Scatter(x=points, y=points, mode="markers"))
    return add_text_repel(fig, points, points, names, **kwargs)
"""

CHARTS = """() => Array.from(document.querySelectorAll('.js-plotly-plot')).map(gd => {
  const ours = (gd.layout.annotations || []).filter(a => (a.name || '').startsWith('repelly-'));
  const state = gd.__repelly;
  return {
    texts: ours.map(a => a.text).sort(),
    drawn: Array.from(gd.querySelectorAll('.annotation-text')).map(e => e.textContent).sort(),
    width: Math.round(gd.getBoundingClientRect().width),
    settled: !!state && !state.applying && !state.timer && !!state.parts,
  };
})"""

BOXES = """() => Array.from(document.querySelectorAll('.annotation .bg'))
  .map(e => e.getBoundingClientRect()).filter(r => r.width > 0)
  .map(r => ({left: r.left, right: r.right, top: r.top, bottom: r.bottom}))"""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def run_app(tmp_path):
    """Start ``streamlit run`` on an app made from source; returns its URL."""
    servers = []

    def start(source, pages=None, theme="light"):
        (tmp_path / "app.py").write_text(
            PREAMBLE + textwrap.dedent(source), encoding="utf-8"
        )
        for name, body in (pages or {}).items():
            (tmp_path / name).write_text(
                PREAMBLE + textwrap.dedent(body), encoding="utf-8"
            )
        port = free_port()
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app.py",
                "--server.headless=true",
                f"--server.port={port}",
                "--browser.gatherUsageStats=false",
                f"--theme.base={theme}",
            ],
            cwd=tmp_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        servers.append(server)
        url = f"http://127.0.0.1:{port}/"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url + "_stcore/health", timeout=2):
                    return url
            except OSError:
                time.sleep(0.25)
        raise RuntimeError("streamlit did not start")

    yield start
    for server in servers:
        server.terminate()
        server.wait(timeout=20)


def charts(page):
    return page.evaluate(CHARTS)


def wait_for(page, check, timeout=30):
    """Polls the charts until check(charts) holds and every chart has settled."""
    deadline = time.monotonic() + timeout
    while True:
        current = charts(page)
        if current and all(c["settled"] for c in current) and check(current):
            page.wait_for_timeout(300)
            current = charts(page)
            if all(c["settled"] for c in current) and check(current):
                return current
        if time.monotonic() > deadline:
            raise AssertionError(f"charts never matched: {current}")
        page.wait_for_timeout(100)


def open_app(page, url):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda m: errors.append(m.text) if m.type == "error" else None,
    )
    page.goto(url)
    page.wait_for_selector(".js-plotly-plot", state="attached", timeout=60000)
    return errors


def overlapping(boxes):
    return [
        (a, b)
        for i, a in enumerate(boxes)
        for b in boxes[i + 1 :]
        if a["left"] < b["right"] - 0.5
        and b["left"] < a["right"] - 0.5
        and a["top"] < b["bottom"] - 0.5
        and b["top"] < a["bottom"] - 0.5
    ]


def test_labels_appear_on_plotly_chart(page, run_app):
    url = run_app(
        """
        names = [f"label-{i}" for i in range(12)]
        st.plotly_chart(labelled(names))
        """
    )
    errors = open_app(page, url)
    names = sorted(f"label-{i}" for i in range(12))
    [chart] = wait_for(page, lambda c: c[0]["texts"] == names)
    assert chart["drawn"] == names
    assert overlapping(page.evaluate(BOXES)) == []
    assert errors == []


def test_init_takes_no_space_in_the_layout(page, run_app):
    url = run_app('st.write("after")\n')
    open_app_without_chart(page, url)
    hidden = page.evaluate("""() => Array.from(
      document.querySelectorAll('[data-testid="stElementContainer"]'))
      .filter(box => box.querySelector('[data-testid="stHtml"]'))
      .map(box => getComputedStyle(box).display)""")
    assert hidden == ["none"]
    assert page.evaluate("() => !!window.repelly")


def open_app_without_chart(page, url):
    page.goto(url)
    page.wait_for_function("() => !!window.repelly", timeout=60000)
    page.wait_for_timeout(500)


def test_zoom_resolves_labels(page, run_app):
    url = run_app('st.plotly_chart(labelled(["a", "b", "c"]))\n')
    open_app(page, url)
    wait_for(page, lambda c: c[0]["texts"] == ["a", "b", "c"])
    page.evaluate("""() => Plotly.relayout(document.querySelector('.js-plotly-plot'),
      {'xaxis.range': [0.5, 1.5], 'yaxis.range': [0.5, 1.5]})""")
    wait_for(page, lambda c: c[0]["texts"] == ["a"])


def test_rerun_with_a_new_figure_resolves(page, run_app):
    url = run_app(
        """
        if st.toggle("more"):
            names = [f"n{i}" for i in range(9)]
        else:
            names = ["x", "y"]
        st.plotly_chart(labelled(names), key="chart")
        """
    )
    open_app(page, url)
    wait_for(page, lambda c: c[0]["texts"] == ["x", "y"])
    page.get_by_text("more").click()
    [chart] = wait_for(page, lambda c: len(c[0]["texts"]) == 9)
    assert chart["drawn"] == sorted(f"n{i}" for i in range(9))
    assert overlapping(page.evaluate(BOXES)) == []


def test_chart_in_a_hidden_tab_is_labelled_when_shown(page, run_app):
    url = run_app(
        """
        first, second = st.tabs(["first", "second"])
        first.write("nothing here")
        second.plotly_chart(labelled([f"t{i}" for i in range(15)]))
        """
    )
    open_app(page, url)
    page.get_by_role("tab", name="second").click()
    [chart] = wait_for(page, lambda c: c[0]["width"] > 0 and len(c[0]["drawn"]) == 15)
    assert overlapping(page.evaluate(BOXES)) == []


def test_selection_events_still_work(page, run_app):
    url = run_app(
        """
        event = st.plotly_chart(
            labelled(["a", "b", "c", "d"]), on_select="rerun", key="chart",
            selection_mode="box",
        )
        st.write(f"selected {len(event.selection.points)} points")
        """
    )
    open_app(page, url)
    wait_for(page, lambda c: len(c[0]["texts"]) == 4)
    plot = page.locator(".js-plotly-plot .nsewdrag").first.bounding_box()
    page.mouse.move(plot["x"] + 2, plot["y"] + 2)
    page.mouse.down()
    page.mouse.move(plot["x"] + plot["width"] - 2, plot["y"] + plot["height"] - 2)
    page.mouse.up()
    page.get_by_text("selected 4 points").wait_for(timeout=20000)
    wait_for(page, lambda c: len(c[0]["drawn"]) == 4)


def test_labels_work_on_every_page_of_a_multipage_app(page, run_app):
    url = run_app(
        """
        nav = st.navigation([st.Page("one.py", title="One"), st.Page("two.py", title="Two")])
        nav.run()
        """,
        pages={
            "one.py": 'st.plotly_chart(labelled(["p1", "p2"]))\n',
            "two.py": 'st.plotly_chart(labelled(["q1", "q2", "q3"]))\n',
        },
    )
    open_app(page, url)
    wait_for(page, lambda c: c[0]["texts"] == ["p1", "p2"])
    page.get_by_role("link", name="Two").click()
    wait_for(page, lambda c: c[0]["drawn"] == ["q1", "q2", "q3"])


def test_dark_theme(page, run_app):
    url = run_app('st.plotly_chart(labelled(["dark", "mode"]))\n', theme="dark")
    open_app(page, url)
    [chart] = wait_for(page, lambda c: c[0]["texts"] == ["dark", "mode"])
    assert chart["drawn"] == ["dark", "mode"]


def test_facets_label_every_panel(page, run_app):
    url = run_app(
        """
        df = px.data.tips().head(24)
        df["name"] = [f"t{i}" for i in range(len(df))]
        fig = px.scatter(df, x="total_bill", y="tip", facet_col="sex", text="name")
        fig.update_traces(mode="markers")
        st.plotly_chart(add_label_repel(fig))
        """
    )
    open_app(page, url)
    names = {f"t{i}" for i in range(24)}
    [chart] = wait_for(page, lambda c: set(c[0]["texts"]) == names)
    assert names <= set(chart["drawn"])
    assert overlapping(page.evaluate(BOXES)) == []


def test_calling_init_twice_loads_the_runtime_once(page, run_app):
    url = run_app(
        """
        repelly.streamlit.init()
        st.plotly_chart(labelled(["once", "twice"]))
        """
    )
    errors = open_app(page, url)
    wait_for(page, lambda c: c[0]["drawn"] == ["once", "twice"])
    scripts = page.evaluate(
        "() => Array.from(document.scripts).filter(s => s.textContent.includes("
        "'repelly label placement solver')).length"
    )
    assert scripts == 1
    assert errors == []


def test_old_streamlit_gets_a_clear_error(monkeypatch):
    import streamlit as st

    import repelly.streamlit

    def html_without_javascript(body, *, width="stretch"):
        raise AssertionError("must not be called")

    monkeypatch.setattr(st, "html", html_without_javascript)
    with pytest.raises(RuntimeError, match="Streamlit 1.52 or newer"):
        repelly.streamlit.init()
