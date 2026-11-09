# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Static export: solve label positions in headless Chrome, then keep them."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from repelly._runtime import merge_post_script

META_KEY = "repelly"
_DEFAULT_WIDTH = 700
_DEFAULT_HEIGHT = 500
_TIMEOUT_SECONDS = 120
_VIRTUAL_TIME_MS = 30000

_RESULT_RE = re.compile(r'<pre id="repelly-result">(.*?)</pre>', re.DOTALL)

_REPORT_SCRIPT = """
window.repelly.solveNow(document.getElementById('{plot_id}')).then(function (result) {
  var pre = document.createElement('pre');
  pre.id = 'repelly-result';
  pre.textContent = JSON.stringify(result);
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  document.body.appendChild(pre);
}, function (error) {
  var pre = document.createElement('pre');
  pre.id = 'repelly-result';
  pre.textContent = JSON.stringify({ error: String(error) });
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  document.body.appendChild(pre);
});
"""


class ChromeNotFoundError(RuntimeError):
    """Raised when no Chrome or Chromium browser is available for static export."""


def bake(
    fig: go.Figure,
    *,
    width: int | None = None,
    height: int | None = None,
    browser_path: str | None = None,
) -> go.Figure:
    """Return a plain ``go.Figure`` with label positions fixed in place.

    The labels are solved by the same JavaScript as in interactive output, using
    a headless Chrome so that fonts are measured for real. The result contains
    ordinary annotations and needs no runtime, so any Plotly output path can
    handle it. Positions are specific to the given size in pixels.

    Parameters
    ----------
    fig:
        A figure with repelling labels.
    width, height:
        Export size in pixels. Defaults to the figure's own size, or 700x500.
    browser_path:
        Chrome or Chromium executable. Found automatically when omitted; the
        ``BROWSER_PATH`` environment variable also overrides the search.
    """
    baked = go.Figure(fig)
    meta = baked.layout.meta
    if not isinstance(meta, dict) or META_KEY not in meta:
        return baked

    width = width or baked.layout.width or _DEFAULT_WIDTH
    height = height or baked.layout.height or _DEFAULT_HEIGHT

    sized = go.Figure(baked)
    sized.update_layout(width=width, height=height)
    page = sized.to_html(
        full_html=True,
        include_plotlyjs=True,
        animation_opts=None,
        auto_play=False,
        post_script=[*merge_post_script(None), _REPORT_SCRIPT],
    )

    result = _run_headless(page, browser_path)
    if "error" in result:
        raise RuntimeError(f"repelly could not solve labels: {result['error']}")

    _warn_about_labels(result.get("stats", {}))

    existing = list(baked.layout.annotations or ())
    baked.update_layout(annotations=[*existing, *result["annotations"]])
    for axis, axis_range in result["ranges"].items():
        baked.layout[axis].range = axis_range

    remaining = {key: value for key, value in meta.items() if key != META_KEY}
    baked.layout.meta = remaining or None
    return baked


def _warn_about_labels(stats: dict[str, int]) -> None:
    dropped = stats.get("dropped", 0)
    if dropped:
        warnings.warn(
            f"repelly hid {dropped} labels for too many overlaps; "
            "consider increasing max_overlaps",
            stacklevel=3,
        )
    unresolved = stats.get("unresolved", 0)
    if unresolved:
        warnings.warn(
            f"{unresolved} repelly labels still overlap; "
            "consider increasing max_iter or showing fewer labels",
            stacklevel=3,
        )


def find_browser(explicit: str | None = None) -> str:
    """Locate a Chromium-based browser executable."""
    if explicit:
        return explicit
    override = os.environ.get("BROWSER_PATH")
    if override:
        return override

    try:
        from choreographer.browsers.chromium import Chromium
    except ImportError:
        pass
    else:
        found = Chromium.find_browser(skip_local=False)
        if found:
            return found

    for name in ("google-chrome", "chrome", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    raise ChromeNotFoundError(
        "Static export needs Chrome or Chromium. Install one, set BROWSER_PATH, or "
        "run `plotly_get_chrome` after installing kaleido."
    )


def _chrome_args(browser: str, page: Path, profile: str) -> list[str]:
    args = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
        f"--virtual-time-budget={_VIRTUAL_TIME_MS}",
        "--dump-dom",
        page.as_uri(),
    ]
    if (
        sys.platform.startswith("linux")
        and hasattr(os, "geteuid")
        and os.geteuid() == 0
    ):
        args.insert(1, "--no-sandbox")
    return args


def _run_headless(page_html: str, browser_path: str | None) -> dict[str, Any]:
    browser = find_browser(browser_path)
    with tempfile.TemporaryDirectory(
        prefix="repelly-", ignore_cleanup_errors=True
    ) as workdir:
        page = Path(workdir) / "page.html"
        page.write_text(page_html, encoding="utf-8")
        profile = str(Path(workdir) / "profile")
        completed = subprocess.run(
            _chrome_args(browser, page, profile),
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )

    output = completed.stdout.decode("utf-8", errors="replace")
    match = _RESULT_RE.search(output)
    if not match:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[-500:]
        raise RuntimeError(f"headless browser returned no label positions. {detail}")
    return json.loads(_unescape(match.group(1)))


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
