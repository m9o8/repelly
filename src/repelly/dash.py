# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Dash integration for repelly."""

from __future__ import annotations

from typing import Any

from repelly._runtime import runtime_js

_ROUTE = "_repelly/runtime.js"
_ENDPOINT = "repelly_runtime"


def init_app(app: Any) -> None:
    """Make every ``dcc.Graph`` in ``app`` render repelly labels.

    Call this once, before the app starts serving. After that, figures returned
    by ``add_text_repel`` and ``add_label_repel`` work anywhere a figure is
    accepted, including as callback outputs. Calling it again for the same app
    has no effect, and several apps may share one Flask server.
    """
    from flask import Response

    from repelly import __version__

    script = f"{runtime_js()}\nwindow.repelly.autoAttach();\n"

    def serve_runtime() -> Response:
        return Response(script, mimetype="application/javascript")

    route = f"{app.config.routes_pathname_prefix}{_ROUTE}"
    # Each app mounted on a shared Flask server has its own prefix, so the
    # endpoint name includes it.
    endpoint = f"{_ENDPOINT}:{app.config.routes_pathname_prefix}"
    if endpoint not in app.server.view_functions:
        app.server.add_url_rule(route, endpoint=endpoint, view_func=serve_runtime)

    # The version in the URL makes browsers fetch the new runtime after an
    # upgrade instead of reusing a cached copy.
    url = f"{app.config.requests_pathname_prefix}{_ROUTE}?v={__version__}"
    if url not in app.config.external_scripts:
        app.config.external_scripts = [*app.config.external_scripts, url]
