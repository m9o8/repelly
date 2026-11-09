# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Access to the JavaScript runtime and the scripts that start it."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

_JS_FILES = ("solver.js", "runtime.js")

_ATTACH_TEMPLATE = "window.repelly.attach(document.getElementById('{plot_id}'));"


@lru_cache(maxsize=1)
def runtime_js() -> str:
    """Return the full browser runtime as one script."""
    package = resources.files("repelly") / "js"
    return "\n".join((package / name).read_text(encoding="utf-8") for name in _JS_FILES)


def post_script() -> str:
    """Return a Plotly ``post_script`` that loads the runtime and attaches it."""
    return f"{runtime_js()}\n{_ATTACH_TEMPLATE}"


def merge_post_script(
    user_script: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Combine the repelly post script with any supplied by the caller."""
    if user_script is None:
        extra: list[str] = []
    elif isinstance(user_script, str):
        extra = [user_script]
    else:
        extra = list(user_script)
    return [post_script(), *extra]
