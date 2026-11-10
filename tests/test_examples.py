# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""The example gallery must keep building and must work without internet."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import urlparse

import pytest

EXAMPLE = Path(__file__).parent.parent / "examples" / "gallery.py"


@pytest.fixture(scope="module")
def built_gallery(tmp_path_factory):
    output_root = tmp_path_factory.mktemp("gallery")
    spec = importlib.util.spec_from_file_location("repelly_gallery", EXAMPLE)
    gallery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gallery)
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(output_root)
        gallery.main()
    return output_root / "gallery_output", gallery


def test_gallery_writes_every_chart_and_one_shared_plotly(built_gallery):
    output, gallery = built_gallery
    pages = {*gallery.ORIGINAL_CHARTS, *gallery.FEATURE_CHARTS}
    assert {p.stem for p in output.glob("*.html")} == pages | {"index"}
    assert (output / "plotly.min.js").exists()
    index = (output / "index.html").read_text(encoding="utf-8")
    assert all(f'href="{name}.html"' in index for name in pages)


@pytest.mark.browser
def test_gallery_charts_render_without_internet(page, built_gallery):
    output, gallery = built_gallery
    external = []

    def route(request_route):
        url = urlparse(request_route.request.url)
        if url.scheme in ("http", "https"):
            external.append(url.hostname)
            request_route.abort()
        else:
            request_route.continue_()

    page.context.route("**/*", route)
    for name in gallery.FEATURE_CHARTS:
        page.goto((output / f"{name}.html").as_uri())
        page.wait_for_selector(".annotation-text", timeout=15000)
    assert external == []
