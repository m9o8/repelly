# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""End-to-end Dash tests: a live server driven by Chrome."""

from __future__ import annotations

import socket
import threading

import plotly.graph_objects as go
import pytest
from dash import Dash, Input, Output, dcc, html
from flask import Flask
from werkzeug.serving import make_server

import repelly.dash as repelly_dash
from repelly import __version__, add_text_repel

GD = "document.querySelector('#graph .js-plotly-plot')"
LABELS = f"""() => {{
  const gd = {GD};
  if (!gd || !gd.layout) return null;
  return (gd.layout.annotations || [])
    .filter(a => (a.name || '').startsWith('repelly-')).map(a => a.text).sort();
}}"""


def labelled(names):
    points = list(range(1, len(names) + 1))
    fig = go.Figure(go.Scatter(x=points, y=points, mode="markers"))
    return add_text_repel(fig, points, points, names)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve(app):
    server = make_server("127.0.0.1", free_port(), app.server, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def build_app(**kwargs):
    app = Dash(__name__, **kwargs)
    repelly_dash.init_app(app)
    app.layout = html.Div(
        [
            html.Button("swap", id="swap", n_clicks=0),
            dcc.Graph(id="graph", figure=labelled(["first", "second"])),
        ]
    )

    @app.callback(
        Output("graph", "figure"), Input("swap", "n_clicks"), prevent_initial_call=True
    )
    def swap(_clicks):
        return labelled(["third", "fourth", "fifth"])

    return app


@pytest.fixture
def running_app():
    server = serve(build_app())
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


def wait_for_labels(page, expected):
    page.wait_for_function(
        f"() => JSON.stringify(({LABELS})()) === JSON.stringify({sorted(expected)!r})",
        timeout=15000,
    )


@pytest.mark.browser
def test_initial_figure_gets_labels(page, running_app):
    page.goto(running_app)
    wait_for_labels(page, ["first", "second"])
    assert page.console_errors == []


@pytest.mark.browser
def test_callback_update_replaces_labels(page, running_app):
    page.goto(running_app)
    wait_for_labels(page, ["first", "second"])
    page.click("#swap")
    wait_for_labels(page, ["third", "fourth", "fifth"])
    assert page.console_errors == []


@pytest.mark.browser
def test_zoom_inside_dash_resolves(page, running_app):
    page.goto(running_app)
    wait_for_labels(page, ["first", "second"])
    page.evaluate(
        f"() => Plotly.relayout({GD}, {{'xaxis.range': [0.5, 1.5], 'yaxis.range': [0.5, 1.5]}})"
    )
    wait_for_labels(page, ["first"])


@pytest.mark.browser
def test_url_prefix_is_respected(page):
    server = serve(build_app(url_base_pathname="/nested/"))
    try:
        page.goto(f"http://127.0.0.1:{server.server_port}/nested/")
        wait_for_labels(page, ["first", "second"])
    finally:
        server.shutdown()


def runtime_scripts(app):
    return [s for s in app.config.external_scripts if "_repelly/" in s]


def bare_app(**kwargs):
    app = Dash(__name__, **kwargs)
    app.layout = html.Div()
    return app


def test_runtime_url_carries_the_version():
    app = bare_app()
    repelly_dash.init_app(app)
    assert runtime_scripts(app) == [f"/_repelly/runtime.js?v={__version__}"]


def test_init_app_twice_has_no_effect():
    app = bare_app()
    repelly_dash.init_app(app)
    repelly_dash.init_app(app)
    assert len(runtime_scripts(app)) == 1
    client = app.server.test_client()
    response = client.get("/_repelly/runtime.js")
    assert response.status_code == 200
    assert b"window.repelly.autoAttach()" in response.data


def test_apps_can_share_a_flask_server():
    server = Flask(__name__)
    first = bare_app(server=server, url_base_pathname="/one/")
    second = bare_app(server=server, url_base_pathname="/two/")
    repelly_dash.init_app(first)
    repelly_dash.init_app(second)
    client = server.test_client()
    assert client.get("/one/_repelly/runtime.js").status_code == 200
    assert client.get("/two/_repelly/runtime.js").status_code == 200
