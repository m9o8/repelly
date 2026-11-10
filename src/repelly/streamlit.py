# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Streamlit integration for repelly."""

from __future__ import annotations

import base64
import inspect
from functools import lru_cache

from repelly._runtime import runtime_js

_MIN_VERSION = "1.52"

# Streamlit sanitises st.html with DOMPurify, which drops any element whose text
# contains "<" followed by a letter or "/". The runtime contains such text, so
# it travels base64-encoded and this loader adds it as a fresh script element.
# The loader also hides its own, otherwise empty, element so it takes no space.
_LOADER = """<script>(function () {{
  var own = document.currentScript;
  var box = own && own.closest('[data-testid="stElementContainer"]');
  if (box) box.style.display = 'none';
  if (window.repelly && window.repelly.version === '{version}') {{
    window.repelly.autoAttach();
    return;
  }}
  var script = document.createElement('script');
  script.textContent = atob('{payload}');
  document.head.appendChild(script);
}})();</script>"""


def init() -> None:
    """Make every ``st.plotly_chart`` on the page render repelly labels.

    Call it in each run of the script, for example near the top. Charts drawn
    with ``st.plotly_chart`` then show the labels of figures returned by
    ``add_text_repel`` and ``add_label_repel``, and re-solve them on zoom,
    resize and reruns. Needs Streamlit 1.52 or newer.

    It runs a script in the page through
    ``st.html(..., unsafe_allow_javascript=True)``. The script is repelly's own
    runtime; no user content is passed to it.
    """
    import streamlit as st

    if "unsafe_allow_javascript" not in inspect.signature(st.html).parameters:
        raise RuntimeError(
            f"repelly.streamlit needs Streamlit {_MIN_VERSION} or newer, "
            f"found {st.__version__}."
        )
    st.html(_loader(), unsafe_allow_javascript=True)


@lru_cache(maxsize=1)
def _loader() -> str:
    script = f"{runtime_js()}\nwindow.repelly.autoAttach();\n"
    payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return _LOADER.format(version=_runtime_version(), payload=payload)


def _runtime_version() -> str:
    from repelly import __version__

    return __version__
