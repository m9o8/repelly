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


def init_app(app: Any) -> None:
    """Make every ``dcc.Graph`` in ``app`` render repelly labels.

    Call this once, before the app starts serving. After that, figures returned
    by ``add_text_repel`` and ``add_label_repel`` work anywhere a figure is
    accepted, including as callback outputs.
    """
    from flask import Response

    script = f"{runtime_js()}\nwindow.repelly.autoAttach();\n"

    def serve_runtime() -> Response:
        return Response(script, mimetype="application/javascript")

    app.server.add_url_rule(
        f"{app.config.routes_pathname_prefix}{_ROUTE}",
        endpoint="repelly_runtime",
        view_func=serve_runtime,
    )
    app.config.external_scripts = [
        *app.config.external_scripts,
        f"{app.config.requests_pathname_prefix}{_ROUTE}",
    ]
